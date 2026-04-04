from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import csv
import os
import tempfile
import requests
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from spoilage_algorithm import (
    predict_spoilage,
    predict_gas_contributors,
    MQ_HIGH_THRESHOLD_OFFSET,
    refresh_mq_sensor_config,
)
from sensor_interface import get_sensor
import google.genai as genai
from google.genai import types
from PIL import Image
import sys
import threading
import time

# Make the IMAGE_CLASS module importable regardless of cwd
_IMAGE_CLASS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'IMAGE_CLASS')
if _IMAGE_CLASS_DIR not in sys.path:
    sys.path.insert(0, _IMAGE_CLASS_DIR)
try:
    import local_classifier as _local_clf
    _LOCAL_MODEL_AVAILABLE = True
except ImportError as _e:
    _LOCAL_MODEL_AVAILABLE = False
    print(f"[local_classifier] import failed (PyTorch not installed?): {_e}")

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB max upload
CORS(app)  # Enable CORS for frontend connection

# Spoonacular API configuration
SPOONACULAR_API_KEY = os.environ.get('SPOONACULAR_API_KEY')

# Gemini API configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

PI_CAMERA_STREAM_URL = os.environ.get('PI_CAMERA_STREAM_URL', 'http://raspberrypi.local:8081/stream')
PI_CAMERA_SNAPSHOT_URL = os.environ.get('PI_CAMERA_SNAPSHOT_URL', 'http://raspberrypi.local:8081/snapshot')
SENSOR_UPSTREAM_BASE_URL = (os.environ.get('SENSOR_UPSTREAM_BASE_URL') or '').strip().rstrip('/')


def _is_http_camera_url(url: str) -> bool:
    if not url:
        return False
    return url.startswith('http://') or url.startswith('https://')


def _get_timeout_seconds(env_name, default_seconds):
    raw_value = os.environ.get(env_name)
    if raw_value is None:
        return default_seconds
    try:
        return max(0.1, float(raw_value))
    except Exception:
        return default_seconds


_GEMINI_REQUEST_TIMEOUT_SECONDS = _get_timeout_seconds('GEMINI_REQUEST_TIMEOUT_SECONDS', 10.0)
_SENSOR_UPSTREAM_TIMEOUT_SECONDS = _get_timeout_seconds('SENSOR_UPSTREAM_TIMEOUT_SECONDS', 3.0)


def _coerce_float(value, default):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _normalize_mq_readings(raw_readings):
    normalized = {}
    if not isinstance(raw_readings, dict):
        return normalized
    for key, value in raw_readings.items():
        try:
            sensor_id = int(key)
            sensor_value = int(float(value))
        except Exception:
            continue
        normalized[sensor_id] = sensor_value
    return normalized


def _get_sensor_snapshot():
    """Return normalized sensor values from upstream API or local serial sensor."""
    if SENSOR_UPSTREAM_BASE_URL:
        try:
            upstream = requests.get(
                f'{SENSOR_UPSTREAM_BASE_URL}/api/sensor',
                timeout=_SENSOR_UPSTREAM_TIMEOUT_SECONDS,
            )
            upstream.raise_for_status()
            payload = upstream.json() if upstream.content else {}
            connected = bool(payload.get('connected', False))
            temperature = _coerce_float(payload.get('temperature'), 4.0)
            humidity = _coerce_float(payload.get('humidity'), 50.0)
            mq_readings = _normalize_mq_readings(payload.get('mq_readings', {}))
            return {
                'connected': connected,
                'temperature': temperature,
                'humidity': humidity,
                'mq_readings': mq_readings,
            }
        except Exception as e:
            print(f'[sensor upstream] Failed to fetch from {SENSOR_UPSTREAM_BASE_URL}/api/sensor: {e}')
            return {
                'connected': False,
                'temperature': 4.0,
                'humidity': 50.0,
                'mq_readings': {},
            }

    sensor = get_sensor()
    connected = sensor.has_environment_data()
    mq_readings = {}
    for sid in _MQ_SENSOR_IDS:
        val = sensor.get_mq_reading(sid)
        if val is not None:
            mq_readings[sid] = val
    return {
        'connected': connected,
        'temperature': sensor.get_temperature(),
        'humidity': sensor.get_humidity(),
        'mq_readings': mq_readings,
    }


def _run_with_timeout(func, timeout_seconds):
    """Run a blocking function with a soft timeout using a daemon thread."""
    outcome = {}

    def _target():
        try:
            outcome['value'] = func()
        except Exception as exc:
            outcome['error'] = exc

    worker = threading.Thread(target=_target, daemon=True, name='gemini-request')
    worker.start()
    worker.join(timeout_seconds)

    if worker.is_alive():
        raise TimeoutError(f'Gemini request timed out after {timeout_seconds:.1f}s')
    if 'error' in outcome:
        raise outcome['error']
    return outcome.get('value')


def _extract_json_payload(text):
    """Extract raw JSON text from model output that may be wrapped in markdown fences."""
    if not text:
        return ''
    result_text = text
    if '```json' in result_text:
        result_text = result_text.split('```json', 1)[1].split('```', 1)[0]
    elif '```' in result_text:
        result_text = result_text.split('```', 1)[1].split('```', 1)[0]
    return result_text.strip()


def _build_local_primary_result(local_result):
    """Map local model output to the same schema the frontend expects from Gemini."""
    if not local_result or not local_result.get('predicted_class'):
        return {
            'predicted_class': 'No Food Detected',
            'confidence': 0,
            'category': 'other',
            'packaging_type': 'sealed',
            'storage_location': 'regular',
            'expiration_date': None,
            'description': '',
            'notes': '',
            'spoilage_parameters': None,
            'top5': []
        }

    return {
        'predicted_class': local_result.get('predicted_class', 'Unknown'),
        'confidence': local_result.get('confidence', 0),
        'category': 'other',
        'packaging_type': 'sealed',
        'storage_location': 'regular',
        'expiration_date': None,
        'description': '',
        'notes': '',
        'spoilage_parameters': None,
        'top5': local_result.get('top5', [])
    }


def _request_gemini_enabled(default=True):
    """Read per-request Gemini toggle sent by the frontend.

    Accepts form or JSON values. Missing/invalid values fall back to default.
    """
    raw_value = None
    if request.form and 'gemini_enabled' in request.form:
        raw_value = request.form.get('gemini_enabled')
    elif request.is_json:
        payload = request.get_json(silent=True) or {}
        raw_value = payload.get('gemini_enabled')

    if raw_value is None:
        return default

    value = str(raw_value).strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return default


def _attach_grounded_spoilage_params(results, allow_gemini_lookup=True, timeout_seconds=None):
    """Populate spoilage_parameters from grounded cache/API for detected foods."""
    detected_foods = [
        {
            'name': r['predicted_class'],
            'category': r.get('category', 'other') or 'other',
            'packaging_type': r.get('packaging_type', 'sealed') or 'sealed'
        }
        for r in results
        if r.get('predicted_class') and r['predicted_class'].lower() != 'no food detected'
    ]
    if not detected_foods:
        return

    grounded_params = get_grounded_spoilage_params(
        detected_foods,
        allow_gemini_lookup=allow_gemini_lookup,
        timeout_seconds=timeout_seconds,
    )
    param_keys = [
        'shelf_life_days', 'optimal_temp', 'temp_sensitivity',
        'temp_abuse_threshold', 'optimal_humidity', 'humidity_sensitivity', 'optimal_packaging'
    ]
    for result in results:
        food_name = result.get('predicted_class', '').lower()
        if food_name in grounded_params:
            gp = grounded_params[food_name]
            result['spoilage_parameters'] = {k: gp[k] for k in param_keys if k in gp}

# ---------------------------------------------------------------------------
# Shelf-life parameter cache
# ---------------------------------------------------------------------------
# Persisted as JSON so results survive server restarts.
# Key: "{food_name_lower}|{category}|{packaging_type}"
# Value: the full params dict returned by Gemini.
_SHELF_LIFE_CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'shelf_life_cache.json')
_shelf_life_cache: dict = {}

def _load_shelf_life_cache():
    global _shelf_life_cache
    try:
        if os.path.exists(_SHELF_LIFE_CACHE_PATH):
            with open(_SHELF_LIFE_CACHE_PATH, 'r', encoding='utf-8') as f:
                _shelf_life_cache = json.load(f)
    except Exception as e:
        print(f"[shelf_life_cache] load error: {e}")
        _shelf_life_cache = {}

def _save_shelf_life_cache():
    try:
        with open(_SHELF_LIFE_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_shelf_life_cache, f, indent=2)
    except Exception as e:
        print(f"[shelf_life_cache] save error: {e}")

def _cache_key(item: dict) -> str:
    return f"{item['name'].lower()}|{item.get('category','').lower()}|{item.get('packaging_type','').lower()}"

_load_shelf_life_cache()

def get_grounded_spoilage_params(food_items, allow_gemini_lookup=True, timeout_seconds=None):
    """
    Return shelf life parameters for a list of food items.
    Results are cached to disk — Gemini is only called for items not yet in the cache.
    Uses temperature=0 for deterministic, consistent output (no web search).
    food_items: list of dicts with keys: name, category, packaging_type
    Returns a dict keyed by lowercase food name.
    """
    if not food_items:
        return {}

    # Split into cached and uncached
    results = {}
    uncached = []
    for item in food_items:
        key = _cache_key(item)
        if key in _shelf_life_cache:
            results[item['name'].lower()] = _shelf_life_cache[key]
        else:
            uncached.append(item)

    if not uncached or not gemini_client or not allow_gemini_lookup:
        return results

    timeout_budget = _GEMINI_REQUEST_TIMEOUT_SECONDS if timeout_seconds is None else max(0.0, float(timeout_seconds))
    if timeout_budget <= 0.0:
        return results

    food_list = '\n'.join([
        f"{i+1}. {item['name']} (category: {item['category']}, packaging: {item['packaging_type']})"
        for i, item in enumerate(uncached)
    ])

    prompt = f"""You are a food safety expert with knowledge of USDA FoodKeeper, FDA, CFIA, and StillTasty guidelines.
Provide accurate refrigerator shelf life and optimal storage parameters for each food item below.
Pay attention to the specific form of the food (e.g. opened vs sealed, fresh vs processed).

Foods:
{food_list}

Return ONLY a JSON array with exactly {len(uncached)} objects, one per food in the same order:
[
  {{
    "food_name": "exact name as given",
    "shelf_life_days": <integer: days in fridge under ideal conditions>,
    "optimal_temp": <float: ideal storage temp in Celsius>,
    "temp_sensitivity": <float 0.5-3.5: spoilage acceleration rate above optimal temp>,
    "temp_abuse_threshold": <float: hours at unsafe temp before significant quality loss>,
    "optimal_humidity": <integer: ideal relative humidity percentage>,
    "humidity_sensitivity": <float 0.2-2.0: impact of humidity deviation on shelf life>,
    "optimal_packaging": <one of: sealed, opened, loose, canned, bottled, boxed, bagged, wrapped>
  }}
]"""

    try:
        response = _run_with_timeout(
            lambda: gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type='application/json'
                )
            )
            ,
            timeout_budget
        )
        params_list = json.loads(response.text)
        # Use positional zip — the prompt guarantees same order as input.
        # This avoids cache misses caused by Gemini slightly changing the food name.
        cache_updated = False
        for source_item, item_params in zip(uncached, params_list):
            if not isinstance(item_params, dict):
                continue
            # Always key results by the original name we sent, not Gemini's returned name
            results[source_item['name'].lower()] = item_params
            _shelf_life_cache[_cache_key(source_item)] = item_params
            cache_updated = True
        if cache_updated:
            _save_shelf_life_cache()
    except Exception as e:
        print(f"Spoilage param lookup error: {e}")

    return results

# Path to the CSV database
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'database.csv')
ENV_ALERTS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'environment_alerts.csv')
OUTCOME_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'item_outcomes.csv')
TEMP_RECENT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'temperature_recent.csv')
MQ_RECENT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mq_recent.csv')
TEMP_HISTORY_12H_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'temperature_history.csv')
MQ_HISTORY_12H_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mq_history.csv')
MQ_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'UI', 'src', 'config', 'mqSensorConfig.json'
)

_RECENT_SAMPLE_LIMIT = 60
_RECENT_TO_LONG_ROLLUP_SECONDS = 60
_LONG_HISTORY_HOURS = 12
_SAMPLER_INTERVAL_SECONDS = 1

_MQ_SENSOR_IDS = [2, 3, 4, 5, 8, 9, 135]

# Lock that serialises every CSV read-modify-write cycle.
# Prevents file truncation races when multiple requests arrive simultaneously.
_csv_lock = threading.Lock()
_history_lock = threading.Lock()
_last_history_rollup_at: datetime | None = None

_OUTCOME_FIELDNAMES = [
    'item_id',
    'food_name',
    'outcome',
    'outcome_date',
    'freshness_at_outcome',
    'days_tracked',
    'source'
]


def _append_outcome_record(item_id, food_name, outcome, freshness_at_outcome=0, days_tracked=0, source='manual'):
    """Append a single outcome record, creating/upgrading the CSV schema if needed."""
    rows = []

    if os.path.exists(OUTCOME_PATH):
        with open(OUTCOME_PATH, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            existing_fields = list(reader.fieldnames or [])
            merged_fields = existing_fields[:]
            for f in _OUTCOME_FIELDNAMES:
                if f not in merged_fields:
                    merged_fields.append(f)

            for row in reader:
                normalized = {field: row.get(field, '') for field in merged_fields}
                if 'source' not in existing_fields:
                    normalized['source'] = row.get('source', '')
                rows.append(normalized)
    else:
        merged_fields = _OUTCOME_FIELDNAMES[:]

    rows.append({
        'item_id': item_id,
        'food_name': food_name,
        'outcome': outcome,
        'outcome_date': datetime.now().isoformat(),
        'freshness_at_outcome': freshness_at_outcome,
        'days_tracked': days_tracked,
        'source': source
    })

    with open(OUTCOME_PATH, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=merged_fields)
        writer.writeheader()
        writer.writerows(rows)


def _revoke_scan_outcome(item_id):
    """Remove scan-generated provisional outcomes for an item when it re-enters."""
    if not os.path.exists(OUTCOME_PATH):
        return 0

    removed = 0
    kept_rows = []

    with open(OUTCOME_PATH, 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or _OUTCOME_FIELDNAMES)
        if 'source' not in fieldnames:
            fieldnames.append('source')

        for row in reader:
            normalized = {field: row.get(field, '') for field in fieldnames}
            if normalized.get('item_id') == item_id and normalized.get('source') == 'scan_outgoing':
                removed += 1
                continue
            kept_rows.append(normalized)

    with open(OUTCOME_PATH, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_rows)

    return removed


def _revoke_latest_outcome(item_id):
    """Remove the most recent outcome row for an item when re-entry is confirmed."""
    if not os.path.exists(OUTCOME_PATH):
        return 0

    with open(OUTCOME_PATH, 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or _OUTCOME_FIELDNAMES)
        if 'source' not in fieldnames:
            fieldnames.append('source')
        rows = [{field: row.get(field, '') for field in fieldnames} for row in reader]

    target_idx = None
    target_ts = ''
    for idx, row in enumerate(rows):
        if row.get('item_id') != item_id:
            continue
        ts = row.get('outcome_date', '')
        if target_idx is None or ts >= target_ts:
            target_idx = idx
            target_ts = ts

    if target_idx is None:
        return 0

    rows.pop(target_idx)
    with open(OUTCOME_PATH, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return 1


def _scan_outcome_from_freshness(freshness):
    """Classify scan-confirmed outgoing items based on freshness.

    > 0 means item was likely still usable (consumed); 0 or below is wasted.
    """
    try:
        return 'consumed' if float(freshness) > 0 else 'wasted'
    except Exception:
        return 'wasted'

# ---------------------------------------------------------------------------
# Environment monitoring — thresholds for "unsafe fridge conditions"
# ---------------------------------------------------------------------------
# Fridge danger zone: above 8 °C bacteria multiply rapidly (USDA / Health Canada).
# Humidity: below 20% causes rapid desiccation; above 95% promotes mould.
_UNSAFE_TEMP_HIGH   = 8.0    # °C
_UNSAFE_HUMIDITY_LOW  = 20.0  # %
_UNSAFE_HUMIDITY_HIGH = 95.0  # %
# Minimum duration of a single unsafe episode before it is recorded (hours).
# Prevents noise from momentary spikes.
_ALERT_MIN_DURATION_HOURS = 0.1

def _ensure_env_alerts_file():
    """Create the environment_alerts CSV if it doesn't exist yet."""
    if not os.path.exists(ENV_ALERTS_PATH):
        with open(ENV_ALERTS_PATH, 'w', newline='', encoding='utf-8') as f:
            csv.DictWriter(f, fieldnames=[
                'item_id', 'alert_type', 'duration_hours', 'detected_at'
            ]).writeheader()

def _load_env_alerts():
    """Return a dict mapping item_id → list of alert dicts."""
    _ensure_env_alerts_file()
    alerts_by_item = {}
    try:
        with open(ENV_ALERTS_PATH, 'r', newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                item_id = row['item_id']
                alerts_by_item.setdefault(item_id, []).append({
                    'alert_type':     row['alert_type'],
                    'duration_hours': float(row['duration_hours']),
                    'detected_at':    row['detected_at'],
                })
    except Exception as e:
        print(f"[env monitor] Failed to load alerts: {e}")
    return alerts_by_item

def _append_env_alerts(alert_rows):
    """Append a list of alert dicts to the environment_alerts CSV."""
    _ensure_env_alerts_file()
    try:
        with open(ENV_ALERTS_PATH, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'item_id', 'alert_type', 'duration_hours', 'detected_at'
            ])
            writer.writerows(alert_rows)
    except Exception as e:
        print(f"[env monitor] Failed to append alerts: {e}")

# ---------------------------------------------------------------------------
# Background environment monitor
# ---------------------------------------------------------------------------
# Tracks the start time of the current "unsafe" window.  None means the fridge
# is currently within safe ranges.
_unsafe_window_start: datetime | None = None
_unsafe_window_type: str | None = None          # 'temperature' | 'humidity' | 'temperature_and_humidity'
_monitor_lock = threading.Lock()
# Timestamp of the last read_foods() call — used for incremental temp-abuse accounting.
_last_temp_abuse_update: datetime | None = None

def _environment_monitor_tick():
    """
    Called every 60 s by the background thread.
    - Checks whether current sensor readings are outside safe fridge ranges.
    - Opens / closes "unsafe windows" and, when a window closes,
      appends an environment alert for every confirmed item in the fridge
      AND adds the duration to each item's cumulative_temp_abuse.
    """
    global _unsafe_window_start, _unsafe_window_type

    snapshot = _get_sensor_snapshot()
    if not snapshot['connected']:
        return   # No data → don't penalise items

    temp = snapshot['temperature']
    humidity = snapshot['humidity']

    temp_unsafe     = temp     > _UNSAFE_TEMP_HIGH
    humidity_unsafe = (humidity < _UNSAFE_HUMIDITY_LOW or humidity > _UNSAFE_HUMIDITY_HIGH)
    currently_unsafe = temp_unsafe or humidity_unsafe

    now = datetime.now()

    with _monitor_lock:
        if currently_unsafe:
            if _unsafe_window_start is None:
                # Begin a new unsafe window
                if temp_unsafe and humidity_unsafe:
                    _unsafe_window_type = 'temperature_and_humidity'
                elif temp_unsafe:
                    _unsafe_window_type = 'temperature'
                else:
                    _unsafe_window_type = 'humidity'
                _unsafe_window_start = now
                print(f"[env monitor] Unsafe window opened: {_unsafe_window_type} "
                      f"(temp={temp:.1f}°C, humidity={humidity:.1f}%)")
        else:
            if _unsafe_window_start is not None:
                # Conditions returned to safe — close the window
                duration_hours = (now - _unsafe_window_start).total_seconds() / 3600
                alert_type = _unsafe_window_type
                _unsafe_window_start = None
                _unsafe_window_type  = None

                if duration_hours < _ALERT_MIN_DURATION_HOURS:
                    print(f"[env monitor] Unsafe window closed after {duration_hours:.2f}h "
                          f"(below {_ALERT_MIN_DURATION_HOURS}h threshold — not recorded)")
                    return

                print(f"[env monitor] Unsafe window closed: {alert_type}, "
                      f"duration={duration_hours:.2f}h — updating all confirmed items")

                # Add alert + abuse to every confirmed item currently in the fridge
                alert_rows = []
                detected_at = now.isoformat()

                # cumulative_temp_abuse is now updated incrementally in read_foods();
                # the monitor only needs to record the alerts.
                try:
                    with _csv_lock:
                        with open(DB_PATH, 'r', newline='', encoding='utf-8') as f:
                            for row in csv.DictReader(f):
                                if row.get('status') in ('confirmed', 'outgoing', 'pending_reentry'):
                                    alert_rows.append({
                                        'item_id':        row['item_id'],
                                        'alert_type':     alert_type,
                                        'duration_hours': round(duration_hours, 2),
                                        'detected_at':    detected_at,
                                    })
                except Exception as e:
                    print(f"[env monitor] Error reading database for alerts: {e}")

                if alert_rows:
                    _append_env_alerts(alert_rows)

def _start_environment_monitor():
    """Start the background 60-second monitor thread."""
    def _loop():
        while True:
            try:
                _environment_monitor_tick()
            except Exception as e:
                print(f"[env monitor] Unhandled error: {e}")
            time.sleep(60)

    t = threading.Thread(target=_loop, daemon=True, name="env-monitor")
    t.start()
    print("[env monitor] Background environment monitor started (60s interval)")

_ensure_env_alerts_file()
_start_environment_monitor()

# Recipe cache to avoid excessive API calls
# Cache persists until manually cleared by user clicking 'Refresh Results'
recipe_cache = {
    'data': None,
    'timestamp': None,
    'cache_key': None,
    'backup': None,  # Backup cache for failed refresh attempts
    'offset': 0  # Track offset for fetching new recipes on refresh
}

def read_foods():
    """
    Recalculate freshness for every non-removed item, persist the results back
    to the CSV (so the database is always the single source of truth), then
    return the data that was just written.
    """
    global _last_temp_abuse_update

    snapshot = _get_sensor_snapshot()
    sensor_connected = snapshot['connected']
    
    # If sensor is disconnected, assume safe conditions rather than penalizing food
    # with potentially stale/incorrect readings
    if sensor_connected:
        current_temp = snapshot['temperature']
        current_humidity = snapshot['humidity']
        current_mq_readings = snapshot['mq_readings']
    else:
        # Assume safe middle-ground values when disconnected
        current_temp = 4.0
        current_humidity = 50.0
        current_mq_readings = None

    # Incremental temperature-abuse accounting.
    # Every time read_foods() runs while the fridge is above the unsafe threshold,
    # add the elapsed time since the last call to every live item's cumulative_temp_abuse.
    # _last_temp_abuse_update is only advanced after a successful DB write to ensure
    # no elapsed time is silently dropped if the write fails.
    now = datetime.now()
    if sensor_connected and current_temp > _UNSAFE_TEMP_HIGH and _last_temp_abuse_update is not None:
        _abuse_delta_hours = (now - _last_temp_abuse_update).total_seconds() / 3600
    else:
        _abuse_delta_hours = 0.0

    # Load per-item environment alerts (written by the background monitor)
    env_alerts_by_item = _load_env_alerts()

    foods = []
    try:
        with _csv_lock:
            # --- 1. Read ALL rows (removed rows are preserved intact) ---
            with open(DB_PATH, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                all_rows = list(reader)

            # --- 2. Recalculate predictions for non-removed rows, update in place ---
            for row in all_rows:
                if row.get('status') == 'removed':
                    continue

                try:
                    entry_date = datetime.fromisoformat(row['entry_date']) if row['entry_date'] else datetime.now()
                except Exception:
                    entry_date = datetime.now()

                try:
                    expiration_date = datetime.fromisoformat(row['expiration_date']) if row['expiration_date'] else None
                except Exception:
                    expiration_date = None

                # Apply incremental abuse accumulated since the last read_foods() call
                if _abuse_delta_hours > 0:
                    old_abuse = float(row.get('cumulative_temp_abuse') or 0)
                    row['cumulative_temp_abuse'] = str(round(old_abuse + _abuse_delta_hours, 4))

                cumulative_temp_abuse = float(row['cumulative_temp_abuse']) if row['cumulative_temp_abuse'] else 0.0

                gemini_shelf_life_raw = row.get('gemini_shelf_life', '')
                gemini_shelf_life = float(gemini_shelf_life_raw) if gemini_shelf_life_raw else None

                gemini_params_raw = row.get('gemini_spoilage_params', '')
                gemini_params = json.loads(gemini_params_raw) if gemini_params_raw else None

                prediction = predict_spoilage(
                    food_category=row['food_category'] if row['food_category'] else 'other',
                    purchase_date=entry_date,
                    current_temp=current_temp,
                    current_humidity=current_humidity,
                    packaging_type=row['packaging_type'] if row['packaging_type'] else 'sealed',
                    cumulative_temp_abuse=cumulative_temp_abuse,
                    expiration_date=expiration_date,
                    food_name=row['food_name'] if row['food_name'] else '',
                    storage_location=row.get('storage_location', 'regular'),
                    gemini_shelf_life_days=gemini_shelf_life,
                    gemini_params=gemini_params,
                    mq_readings=current_mq_readings
                )

                # Persist updated values back into the row dict (written to CSV below)
                row['freshness_score'] = prediction['freshness_score']
                row['days_until_spoilage'] = int(prediction['days_until_spoilage'])
                row['safety_category'] = prediction['safety_category']

                # Build the API response from the now-persisted values
                food = {
                    'id': row['item_id'],
                    'name': row['food_name'],
                    'freshnessScore': float(row['freshness_score']),
                    'daysUntilSpoilage': int(row['days_until_spoilage']),
                    'timeInFridge': calculate_time_in_fridge(row['entry_date']),
                    'foodGroup': row['food_category'].lower() if row['food_category'] else 'other',
                    'packagingType': row['packaging_type'] if row['packaging_type'] else '',
                    'expirationDate': row['expiration_date'] if row['expiration_date'] else '',
                    'storageLocation': row.get('storage_location', 'regular'),
                    'status': row.get('status', 'confirmed'),
                    'cumulativeTempAbuse': cumulative_temp_abuse,
                    'safetyCategory': row['safety_category'],
                    'warnings': prediction.get('warnings', []),
                    'spoilageMetadata': prediction.get('metadata', {}),
                    'confidence': float(row['confidence']) if row.get('confidence') else None,
                    'top5Predictions': json.loads(row['top5_predictions']) if row.get('top5_predictions') else [],
                    'predictionSource': row.get('prediction_source') or None,
                    'geminiError': row.get('gemini_error') or None,
                    'description': row.get('description', ''),
                    'entryDate': row.get('entry_date', ''),
                    'removedAt': '',
                    # Per-item environment alerts from background monitor
                    'environmentAlerts': env_alerts_by_item.get(row['item_id'], []),
                }
                foods.append(food)

            # --- 3. Write all rows back (removed rows preserved, live rows updated) ---
            with open(DB_PATH, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)

            # Advance the abuse timestamp only after a confirmed successful write.
            # If the write above raised an exception we stay at the previous
            # timestamp so the elapsed interval is retried on the next call.
            _last_temp_abuse_update = now

    except Exception as e:
        print(f"Error reading/updating database: {e}")
    return foods

def calculate_time_in_fridge(entry_date):
    """Calculate how long the item has been in the fridge"""
    if not entry_date:
        return '0 days'
    try:
        entry = datetime.fromisoformat(entry_date.replace('Z', '+00:00'))
        now = datetime.now()
        days = (now - entry).days
        if days == 0:
            hours = (now - entry).seconds // 3600
            return f"{hours} hours" if hours != 1 else "1 hour"
        return f"{days} days" if days != 1 else "1 day"
    except:
        return '0 days'

def _trim_history_file(filepath: str, fieldnames: list):
    """Remove rows older than 12 hours from a sensor history CSV in-place.
    Safe to call even if the file does not exist yet."""
    if not os.path.exists(filepath):
        return
    try:
        cutoff = datetime.now() - timedelta(hours=12)
        recent = []
        total_rows = 0
        with open(filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_rows += 1
                try:
                    if datetime.fromisoformat(row['timestamp']) >= cutoff:
                        recent.append(row)
                except Exception:
                    # Preserve malformed rows instead of dropping them silently.
                    recent.append(row)

        # Safety guard: never collapse a non-empty history file to header-only.
        # If there are no recent rows, keep the current file as-is.
        if total_rows > 0 and len(recent) == 0:
            print(f'History trim skipped for {filepath}: no recent rows found')
            return

        # Use a unique temp file to avoid collisions when concurrent requests
        # trim the same history file at nearly the same time.
        tmp_dir = os.path.dirname(filepath) or '.'
        with tempfile.NamedTemporaryFile(
            mode='w',
            newline='',
            encoding='utf-8',
            dir=tmp_dir,
            prefix=os.path.basename(filepath) + '.',
            suffix='.tmp',
            delete=False,
        ) as f:
            tmp_path = f.name
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(recent)
        os.replace(tmp_path, filepath)
    except Exception as e:
        print(f'Error trimming history file {filepath}: {e}')


def _ensure_history_files():
    """Create history files with headers if they do not exist yet."""
    files = [
        (TEMP_RECENT_PATH, ['timestamp', 'temperature', 'humidity']),
        (MQ_RECENT_PATH, ['timestamp', 'mq2', 'mq3', 'mq4', 'mq5', 'mq8', 'mq9', 'mq135']),
        (TEMP_HISTORY_12H_PATH, ['timestamp', 'temperature', 'humidity']),
        (MQ_HISTORY_12H_PATH, ['timestamp', 'mq2', 'mq3', 'mq4', 'mq5', 'mq8', 'mq9', 'mq135']),
    ]
    for path, fieldnames in files:
        if os.path.exists(path):
            continue
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
        except Exception as e:
            print(f'Error initializing history file {path}: {e}')


def _read_csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _append_recent_row(path, fieldnames, row):
    """Append a row to a recent-history file and keep only the newest samples."""
    with _history_lock:
        rows = []
        if os.path.exists(path):
            rows = _read_csv_rows(path)
        rows.append(row)
        rows = rows[-_RECENT_SAMPLE_LIMIT:]
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _rollup_recent_histories():
    """Roll up last 60 one-second samples into one per-minute average for 12-hour history."""
    temp_fields = ['timestamp', 'temperature', 'humidity']
    mq_fields = ['timestamp', 'mq2', 'mq3', 'mq4', 'mq5', 'mq8', 'mq9', 'mq135']
    timestamp = datetime.now().isoformat()

    try:
        with _history_lock:
            temp_recent_rows = _read_csv_rows(TEMP_RECENT_PATH)
            mq_recent_rows = _read_csv_rows(MQ_RECENT_PATH)

            if temp_recent_rows:
                temp_vals = [_safe_float(r.get('temperature')) for r in temp_recent_rows]
                humidity_vals = [_safe_float(r.get('humidity')) for r in temp_recent_rows]
                temp_vals = [v for v in temp_vals if v is not None]
                humidity_vals = [v for v in humidity_vals if v is not None]
                if temp_vals and humidity_vals:
                    with open(TEMP_HISTORY_12H_PATH, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=temp_fields)
                        writer.writerow({
                            'timestamp': timestamp,
                            'temperature': round(sum(temp_vals) / len(temp_vals), 2),
                            'humidity': round(sum(humidity_vals) / len(humidity_vals), 2),
                        })

            if mq_recent_rows:
                avg_row = {'timestamp': timestamp}
                has_any_value = False
                for sid in _MQ_SENSOR_IDS:
                    key = f'mq{sid}'
                    vals = [_safe_float(r.get(key)) for r in mq_recent_rows]
                    vals = [v for v in vals if v is not None]
                    if vals:
                        avg_row[key] = int(round(sum(vals) / len(vals)))
                        has_any_value = True
                    else:
                        avg_row[key] = ''
                if has_any_value:
                    with open(MQ_HISTORY_12H_PATH, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=mq_fields)
                        writer.writerow(avg_row)

        # Trim outside lock; these functions rewrite full files.
        _trim_history_file(TEMP_HISTORY_12H_PATH, temp_fields)
        _trim_history_file(MQ_HISTORY_12H_PATH, mq_fields)
    except Exception as e:
        print(f'Error rolling up recent histories: {e}')


def _sensor_history_sampler_tick():
    """Sample sensors every second and periodically roll up to 12-hour history."""
    global _last_history_rollup_at

    snapshot = _get_sensor_snapshot()
    if snapshot['connected']:
        temperature = snapshot['temperature']
        humidity = snapshot['humidity']
        mq_readings = snapshot['mq_readings']

        log_temperature_reading(temperature, humidity)
        if mq_readings:
            log_mq_reading(mq_readings)

    now = datetime.now()
    if _last_history_rollup_at is None:
        _last_history_rollup_at = now
        return

    if (now - _last_history_rollup_at).total_seconds() >= _RECENT_TO_LONG_ROLLUP_SECONDS:
        _last_history_rollup_at = now
        _rollup_recent_histories()


def _start_sensor_history_sampler():
    """Start backend history sampling thread (1 Hz)."""
    def _loop():
        while True:
            loop_started = time.monotonic()
            try:
                _sensor_history_sampler_tick()
            except Exception as e:
                print(f'[history sampler] Unhandled error: {e}')

            elapsed = time.monotonic() - loop_started
            sleep_for = max(0.0, _SAMPLER_INTERVAL_SECONDS - elapsed)
            time.sleep(sleep_for)

    _ensure_history_files()
    t = threading.Thread(target=_loop, daemon=True, name='history-sampler')
    t.start()
    print('[history sampler] Background sensor history sampler started (1s interval)')


_start_sensor_history_sampler()


def log_temperature_reading(temperature, humidity):
    """Log one-second temperature sample to short-term history."""
    try:
        fieldnames = ['timestamp', 'temperature', 'humidity']
        row = {
            'timestamp': datetime.now().isoformat(),
            'temperature': round(temperature, 2),
            'humidity': round(humidity, 2),
        }
        _append_recent_row(TEMP_RECENT_PATH, fieldnames, row)

    except Exception as e:
        print(f'Error logging temperature: {e}')


def log_mq_reading(mq_readings: dict):
    """Log one-second MQ samples to short-term history."""
    try:
        fieldnames = ['timestamp'] + [f'mq{sid}' for sid in _MQ_SENSOR_IDS]
        row = {'timestamp': datetime.now().isoformat()}
        for sid in _MQ_SENSOR_IDS:
            row[f'mq{sid}'] = mq_readings.get(sid, '')
        _append_recent_row(MQ_RECENT_PATH, fieldnames, row)

    except Exception as e:
        print(f'Error logging MQ readings: {e}')


def _sanitize_text(value):
    """Strip embedded newlines and carriage returns from a field value.
    Prevents multi-line CSV rows caused by LLM-generated text with embedded \n."""
    if not value:
        return value
    return value.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')


def write_foods(foods):
    """Write foods back to the CSV database.

    The entire read-modify-write is held under _csv_lock so that concurrent
    callers (e.g. delete_outgoing_foods running on another thread) cannot
    interleave their own writes between our read and our write, which was the
    root cause of confirmed items ending up with a stale removed_at timestamp.
    """
    try:
        with _csv_lock:
            # Read existing data to preserve all fields
            existing_data = {}
            with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                fieldnames = list(reader.fieldnames)
                if 'gemini_shelf_life' not in fieldnames:
                    fieldnames.append('gemini_shelf_life')
                if 'gemini_spoilage_params' not in fieldnames:
                    fieldnames.append('gemini_spoilage_params')
                if 'description' not in fieldnames:
                    fieldnames.append('description')
                if 'removed_at' not in fieldnames:
                    fieldnames.append('removed_at')
                if 'prediction_source' not in fieldnames:
                    fieldnames.append('prediction_source')
                if 'gemini_error' not in fieldnames:
                    fieldnames.append('gemini_error')
                for row in reader:
                    existing_data[row['item_id']] = row

            # Update or add new foods
            for food in foods:
                item_id = food['id']
                # If the existing row was 'removed', treat this as a fresh item
                # rather than an update — the ID has been recycled and all stale
                # fields (entry_date, gemini params, etc.) must be overwritten.
                existing_is_removed = (
                    item_id in existing_data and
                    existing_data[item_id].get('status') == 'removed'
                )
                if item_id in existing_data and not existing_is_removed:
                    # Update existing item
                    existing_data[item_id]['food_name'] = food['name']
                    existing_data[item_id]['freshness_score'] = str(food['freshnessScore'])
                    existing_data[item_id]['days_until_spoilage'] = str(food['daysUntilSpoilage'])
                    existing_data[item_id]['safety_category'] = food.get('safetyCategory', 'Fresh')
                    existing_data[item_id]['food_category'] = food['foodGroup'].capitalize()
                    if 'packagingType' in food:
                        existing_data[item_id]['packaging_type'] = food['packagingType']
                    if 'expirationDate' in food:
                        existing_data[item_id]['expiration_date'] = food['expirationDate']
                    if 'storageLocation' in food:
                        existing_data[item_id]['storage_location'] = food['storageLocation']
                    if 'status' in food:
                        existing_data[item_id]['status'] = food['status']
                    if 'confidence' in food:
                        existing_data[item_id]['confidence'] = str(food['confidence']) if food['confidence'] is not None else ''
                    if 'top5Predictions' in food:
                        existing_data[item_id]['top5_predictions'] = json.dumps(food['top5Predictions']) if food['top5Predictions'] else ''
                    if 'description' in food:
                        existing_data[item_id]['description'] = _sanitize_text(food.get('description', ''))
                    if 'predictionSource' in food:
                        existing_data[item_id]['prediction_source'] = food.get('predictionSource') or ''
                    if 'geminiError' in food:
                        existing_data[item_id]['gemini_error'] = _sanitize_text(food.get('geminiError', '')) or ''
                    if 'daysInFridge' in food:
                        try:
                            days_in_fridge = max(float(food.get('daysInFridge', 0)), 0.0)
                        except Exception:
                            days_in_fridge = 0.0
                        existing_data[item_id]['entry_date'] = (datetime.now() - timedelta(days=days_in_fridge)).isoformat()
                    if 'cumulativeTempAbuse' in food:
                        try:
                            cumulative_temp_abuse = max(float(food.get('cumulativeTempAbuse', 0)), 0.0)
                        except Exception:
                            cumulative_temp_abuse = 0.0
                        existing_data[item_id]['cumulative_temp_abuse'] = str(round(cumulative_temp_abuse, 4))
                    # removed_at must only be set for actually-removed rows.
                    # For every other status we always clear it so that a stale
                    # removed_at timestamp can never "leak" back onto a live item.
                    item_status = food.get('status', existing_data[item_id].get('status', 'confirmed'))
                    if item_status == 'removed' and 'removedAt' in food:
                        existing_data[item_id]['removed_at'] = food.get('removedAt', '')
                    else:
                        existing_data[item_id]['removed_at'] = ''
                else:
                    # Create new item (or overwrite a recycled removed row).
                    # removed_at is always empty for new items.
                    try:
                        days_in_fridge = max(float(food.get('daysInFridge', 0)), 0.0)
                    except Exception:
                        days_in_fridge = 0.0
                    try:
                        cumulative_temp_abuse = max(float(food.get('cumulativeTempAbuse', 0)), 0.0)
                    except Exception:
                        cumulative_temp_abuse = 0.0
                    entry_date = datetime.now() - timedelta(days=days_in_fridge)
                    existing_data[item_id] = {
                        'item_id': item_id,
                        'food_name': food['name'],
                        'food_category': food['foodGroup'].capitalize(),
                        'entry_date': entry_date.isoformat(),
                        'expiration_date': food.get('expirationDate', ''),
                        'temp_at_entry': '4.5',
                        'humidity_at_entry': '85.0',
                        'packaging_type': food.get('packagingType', 'sealed'),
                        'storage_location': food.get('storageLocation', 'regular'),
                        'status': food.get('status', 'confirmed'),
                        'cumulative_temp_abuse': str(round(cumulative_temp_abuse, 4)),
                        'freshness_score': str(food['freshnessScore']),
                        'days_until_spoilage': str(food['daysUntilSpoilage']),
                        'safety_category': 'Fresh',
                        'confidence': str(food['confidence']) if food.get('confidence') is not None else '',
                        'top5_predictions': json.dumps(food['top5Predictions']) if food.get('top5Predictions') else '',
                        'gemini_shelf_life': str(food['daysUntilSpoilage']),
                        'gemini_spoilage_params': json.dumps(food['geminiSpoilageParams']) if food.get('geminiSpoilageParams') else '',
                        'description': _sanitize_text(food.get('description', '')),
                        'prediction_source': food.get('predictionSource') or '',
                        'gemini_error': _sanitize_text(food.get('geminiError', '')) or '',
                        'removed_at': ''
                    }

            with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for row in existing_data.values():
                    writer.writerow(row)

        return True
    except Exception as e:
        print(f"Error writing database: {e}")
        return False

# API Routes

@app.route('/api/foods', methods=['GET'])
def get_foods():
    """Get all foods (excludes removed items)"""
    foods = read_foods()  # read_foods already skips 'removed'
    return jsonify(foods)

@app.route('/api/foods/<item_id>', methods=['GET'])
def get_food(item_id):
    """Get a specific food by ID"""
    foods = read_foods()
    food = next((f for f in foods if f['id'] == item_id), None)
    if food:
        return jsonify(food)
    return jsonify({'error': 'Food not found'}), 404

def _purge_old_removed_items():
    """Hard-delete rows that are stale and no longer actionable:
    - 'removed' rows whose removed_at is older than 2 hours
    - 'pending_reentry' rows that were never acted on
    The entire read-modify-write is held under _csv_lock to prevent
    concurrent calls from racing on the file.
    """
    try:
        with _csv_lock:
            cutoff = datetime.now() - timedelta(hours=2)
            rows_to_keep = []
            with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                fieldnames = reader.fieldnames
                for row in reader:
                    status = row.get('status')
                    if status == 'removed':
                        try:
                            removed_at = datetime.fromisoformat(row.get('removed_at', ''))
                            if removed_at < cutoff:
                                continue  # drop it
                        except:
                            continue  # malformed timestamp — drop it too
                    elif status == 'pending_reentry':
                        pass  # cleaned up by outgoing-detection on the next scan
                    rows_to_keep.append(row)
            with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows_to_keep)
    except Exception as e:
        print(f'Error purging old removed items: {e}')


def _read_removed_items_raw():
    """
    Read only 'removed' rows directly from the CSV (bypasses read_foods filtering).
    Returns a list of dicts with keys: id, name, foodGroup, description, removed_at,
    packagingType, storageLocation, expirationDate, freshnessScore, daysUntilSpoilage,
    timeInFridge, entryDate, cumulativeTempAbuse, safetyCategory, warnings,
    environmentAlerts, geminiSpoilageParams.
    """
    removed = []
    env_alerts_by_item = _load_env_alerts()
    try:
        with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get('status') != 'removed':
                    continue
                try:
                    removed_at = datetime.fromisoformat(row.get('removed_at', ''))
                except:
                    continue
                # Only consider items removed within the last 2 hours
                if (datetime.now() - removed_at).total_seconds() > 7200:
                    continue
                gemini_params_raw = row.get('gemini_spoilage_params', '')
                item_id = row['item_id']
                removed.append({
                    'id': item_id,
                    'name': row['food_name'],
                    'foodGroup': row['food_category'].lower() if row['food_category'] else 'other',
                    'description': row.get('description', ''),
                    'removed_at': removed_at,
                    'packagingType': row.get('packaging_type', 'sealed'),
                    'storageLocation': row.get('storage_location', 'regular'),
                    'expirationDate': row.get('expiration_date', ''),
                    'freshnessScore': float(row.get('freshness_score') or 100),
                    'daysUntilSpoilage': int(float(row.get('days_until_spoilage') or 7)),
                    'timeInFridge': row.get('entry_date', ''),  # raw ISO string
                    'entryDate': row.get('entry_date', ''),
                    'cumulativeTempAbuse': float(row.get('cumulative_temp_abuse') or 0),
                    'safetyCategory': row.get('safety_category', ''),
                    'warnings': [],  # not persisted; removed items don't need recompute
                    'environmentAlerts': env_alerts_by_item.get(item_id, []),
                    'geminiSpoilageParams': json.loads(gemini_params_raw) if gemini_params_raw else None,
                    'geminiShelfLife': row.get('gemini_shelf_life', '')
                })
    except Exception as e:
        print(f'Error reading removed items: {e}')
    return removed


def find_matching_removed_item(name, category, description):
    """
    Find a 'removed' item within the last 2 hours that matches the scanned item.
    Uses the same fuzzy name + category matching as confirmed items,
    plus optional description keyword overlap.
    """
    candidates = _read_removed_items_raw()
    desc_words = set(w.lower() for w in description.split() if len(w) > 3) if description else set()

    for item in candidates:
        if not names_match(name, item['name']):
            continue
        # Strong subset match: name alone is sufficient.
        if is_strong_name_match(name, item['name']):
            return item
        # Weaker Jaccard match: use description as a tiebreaker.
        if not desc_words:
            return item
        existing_words = set(w.lower() for w in item['description'].split() if len(w) > 3)
        if existing_words:
            overlap = len(desc_words & existing_words) / max(len(desc_words), 1)
            if overlap >= 0.3:
                return item
        else:
            return item
    return None


def find_all_matching_removed_items(name, category, description):
    """
    Return ALL 'removed' items within the last 2 hours that match the scanned item
    (same matching logic as find_matching_removed_item, but collects every match).
    Results are sorted most-recently-removed first.
    """
    candidates = _read_removed_items_raw()
    desc_words = set(w.lower() for w in description.split() if len(w) > 3) if description else set()
    matches = []
    for item in candidates:
        if not names_match(name, item['name']):
            continue
        if is_strong_name_match(name, item['name']):
            matches.append(item)
            continue
        if not desc_words:
            matches.append(item)
            continue
        existing_words = set(w.lower() for w in item['description'].split() if len(w) > 3)
        if existing_words:
            overlap = len(desc_words & existing_words) / max(len(desc_words), 1)
            if overlap >= 0.3:
                matches.append(item)
        else:
            matches.append(item)
    # Most recently removed first — most likely candidate to return
    matches.sort(key=lambda r: r['removed_at'], reverse=True)
    return matches


def normalise_name(name):
    """
    Normalise a food name for fuzzy comparison:
    - lowercase
    - replace '&' with 'and'
    - remove common brand/filler words that don't identify the core product
    - return the resulting set of meaningful words
    """
    # Normalise separators and case
    s = name.lower().strip()
    s = s.replace('&', 'and')
    # Remove punctuation except spaces
    s = ''.join(c if c.isalnum() or c == ' ' else ' ' for c in s)
    words = s.split()
    # Stop-words that are not meaningful for matching.
    # Includes brand qualifiers, sizes, AND packaging/preparation descriptors
    # so that e.g. "Canned Artichoke Hearts" == "Artichoke Hearts".
    stop = {'the', 'a', 'an', 'of', 'with', 'and', 'or', 'in', 'on', 'at', 'for',
            'organic', 'original', 'classic', 'fresh', 'natural', 'low', 'fat',
            'free', 'light', 'extra', 'plain', 'whole', 'reduced', 'zero', 'g', 'ml', 'oz', 'kg',
            # packaging / preparation qualifiers
            'canned', 'bottled', 'jarred', 'frozen', 'dried', 'raw'}
    return {w for w in words if w not in stop and len(w) > 1}


def names_match(a, b):
    """
    Return True if name `a` and name `b` refer to the same core food.
    Strategy: one name's meaningful word-set must be a subset of the other's
    (handles "Greek Yogurt" ⊂ "Oikos Greek Yogurt", "Canned Artichoke Hearts" ⊃ "Artichoke Hearts")
    OR they share ≥50% of their combined unique words (Jaccard).
    """
    wa = normalise_name(a)
    wb = normalise_name(b)
    if not wa or not wb:
        return False
    # Subset check: the shorter set of words is fully contained in the longer
    if wa <= wb or wb <= wa:
        return True
    # Fallback: Jaccard-like overlap ≥ 50%
    overlap = len(wa & wb) / len(wa | wb)
    return overlap >= 0.5


def is_strong_name_match(a, b):
    """Return True if one name's normalised word-set is a strict subset of the other.
    This is a high-confidence match that doesn't need description confirmation."""
    wa = normalise_name(a)
    wb = normalise_name(b)
    if not wa or not wb:
        return False
    return wa <= wb or wb <= wa


def find_matching_confirmed_item(foods, name, category, description):
    """
    Find a confirmed inventory item that matches the scanned item.
    Uses fuzzy name matching + category equality, confirmed by optional
    description keyword overlap.
    Returns the matching food dict or None.
    """
    desc_words = set(w.lower() for w in description.split() if len(w) > 3) if description else set()

    for food in foods:
        if food.get('status') != 'confirmed':
            continue
        if not names_match(name, food.get('name', '')):
            continue
        # Strong subset match (e.g. "Canned Artichoke Hearts" ↔ "Artichoke Hearts"):
        # name alone is sufficient — skip description check.
        if is_strong_name_match(name, food.get('name', '')):
            return food
        # Weaker Jaccard match: use description as a tiebreaker.
        if not desc_words:
            return food  # No description to compare, trust the name match
        existing_desc = food.get('description', '')
        existing_words = set(w.lower() for w in existing_desc.split() if len(w) > 3)
        if existing_words:
            overlap = len(desc_words & existing_words) / max(len(desc_words), 1)
            if overlap >= 0.3:
                return food  # ≥30% keyword overlap confirms the match
        else:
            return food  # No existing description to compare against
    return None


def find_all_matching_confirmed_items(foods, name, category, description):
    """
    Return ALL confirmed inventory items that match the scanned item (same logic as
    find_matching_confirmed_item but collects every match instead of stopping at the first).
    Results are NOT sorted here — caller sorts as needed.
    """
    desc_words = set(w.lower() for w in description.split() if len(w) > 3) if description else set()
    matches = []
    for food in foods:
        if food.get('status') != 'confirmed':
            continue
        if not names_match(name, food.get('name', '')):
            continue
        if is_strong_name_match(name, food.get('name', '')):
            matches.append(food)
            continue
        if not desc_words:
            matches.append(food)
            continue
        existing_words = set(w.lower() for w in food.get('description', '').split() if len(w) > 3)
        if existing_words:
            overlap = len(desc_words & existing_words) / max(len(desc_words), 1)
            if overlap >= 0.3:
                matches.append(food)
        else:
            matches.append(food)
    return matches


@app.route('/api/foods', methods=['POST'])
def create_food():
    """Create a new food item; if a matching confirmed item exists, mark it 'outgoing' instead."""
    data = request.json

    # Purge stale removed/reentry rows before matching so old removed items
    # don't trigger false re-entry detections. This is the only place purging
    # is needed; read_foods() no longer calls it so GET requests don't write.
    _purge_old_removed_items()
    foods = read_foods()

    # Only check for matches when scanning (status='pending')
    if data.get('status') == 'pending':
        name = data.get('name', 'Unknown')
        category = data.get('foodGroup', 'other')
        description = _sanitize_text(data.get('description', ''))

        # IDs already claimed by earlier disambiguation cards in the same batch scan.
        # The frontend tracks these and passes them so we don't create duplicate
        # disambiguation cards for the same match across multiple scanned items.
        claimed_confirmed_ids = set(data.get('claimed_confirmed_ids', []))
        claimed_removed_ids = set(data.get('claimed_removed_ids', []))

        # Collect ALL potential matches up-front before deciding what to do,
        # then exclude any IDs already claimed by sibling disambiguation cards.
        all_removed = [
            r for r in find_all_matching_removed_items(name, category, description)
            if r['id'] not in claimed_removed_ids
        ]
        all_confirmed = [
            f for f in find_all_matching_confirmed_items(foods, name, category, description)
            if f['id'] not in claimed_confirmed_ids
        ]

        # --- Disambiguation: ambiguous situation, user must choose ---
        # Trigger when:
        #   - removed item(s) + confirmed item(s) conflict (reentry_or_outgoing)
        #   - multiple confirmed items match (multi_confirmed)
        #   - multiple removed items but nothing confirmed (multi_removed)
        needs_disambiguation = (
            (len(all_confirmed) > 0 and len(all_removed) > 0) or
            len(all_confirmed) > 1 or
            len(all_removed) > 1
        )
        if needs_disambiguation:
            # Sort confirmed oldest-first; default selection will be the oldest item
            all_confirmed.sort(key=lambda f: f.get('entryDate', ''))

            confirmed_payload = [
                {
                    'id': f['id'],
                    'name': f['name'],
                    'foodGroup': f['foodGroup'],
                    'packagingType': f.get('packagingType', ''),
                    'storageLocation': f.get('storageLocation', 'regular'),
                    'expirationDate': f.get('expirationDate', ''),
                    'freshnessScore': f['freshnessScore'],
                    'daysUntilSpoilage': f['daysUntilSpoilage'],
                    'timeInFridge': f['timeInFridge'],
                    'entryDate': f.get('entryDate', ''),
                    'description': f.get('description', ''),
                    'safetyCategory': f.get('safetyCategory', ''),
                    'warnings': f.get('warnings', []),
                    'cumulativeTempAbuse': f.get('cumulativeTempAbuse', 0),
                    'environmentAlerts': f.get('environmentAlerts', []),
                }
                for f in all_confirmed
            ]

            # Build payload for each removed candidate (most recently removed first)
            removed_payloads = [
                {
                    'id': r['id'],
                    'name': r['name'],
                    'foodGroup': r['foodGroup'],
                    'packagingType': r.get('packagingType', 'sealed'),
                    'storageLocation': r.get('storageLocation', 'regular'),
                    'expirationDate': r.get('expirationDate', ''),
                    'freshnessScore': r['freshnessScore'],
                    'daysUntilSpoilage': r['daysUntilSpoilage'],
                    'timeInFridge': calculate_time_in_fridge(r['timeInFridge']),
                    'entryDate': r.get('entryDate', ''),
                    'description': r.get('description', ''),
                    'hoursOutside': round((datetime.now() - r['removed_at']).total_seconds() / 3600, 1),
                    'safetyCategory': r.get('safetyCategory', ''),
                    'warnings': r.get('warnings', []),
                    'cumulativeTempAbuse': r.get('cumulativeTempAbuse', 0),
                    'environmentAlerts': r.get('environmentAlerts', []),
                }
                for r in all_removed
            ]

            # Determine type for UI hint
            if all_removed and all_confirmed:
                dis_type = 'reentry_or_outgoing'
            elif len(all_confirmed) > 1:
                dis_type = 'multi_confirmed'
            else:  # len(all_removed) > 1, no confirmed
                dis_type = 'multi_removed'

            return jsonify({
                'disambiguation': True,
                'type': dis_type,
                'confirmedMatches': confirmed_payload,
                'removedMatches': removed_payloads,
                'defaultOutgoingId': all_confirmed[0]['id'] if all_confirmed else None,
                'defaultReentryId': all_removed[0]['id'] if all_removed else None
            }), 200

        # --- Only removed match(es), no confirmed: straight re-entry ---
        # (only reached when exactly 1 removed, 0 confirmed — multi_removed is
        # caught by needs_disambiguation above)
        if all_removed:
            removed_match = all_removed[0]
            hours_outside = (datetime.now() - removed_match['removed_at']).total_seconds() / 3600
            with _csv_lock:
                rows = []
                with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    fieldnames = list(reader.fieldnames)
                    for row in reader:
                        if row['item_id'] == removed_match['id']:
                            new_abuse = float(row.get('cumulative_temp_abuse') or 0) + hours_outside
                            row['cumulative_temp_abuse'] = str(round(new_abuse, 2))
                            row['status'] = 'pending_reentry'
                            row['removed_at'] = ''
                        rows.append(row)
                with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
            return jsonify({'reentry': True, 'id': removed_match['id'], 'hours_outside': round(hours_outside, 2)}), 200

        # --- Exactly one confirmed match: auto-mark as outgoing (fallback) ---
        # Single confirmed match (and no removed conflict): auto-mark outgoing.
        if all_confirmed:
            match = all_confirmed[0]
            stale_purged = []
            with _csv_lock:
                rows = []
                with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    fieldnames = list(reader.fieldnames)
                    for row in reader:
                        if row['item_id'] == match['id']:
                            row['status'] = 'outgoing'
                            row['removed_at'] = ''  # never carry a stale removed_at onto an outgoing row
                            rows.append(row)
                        elif row.get('status') in ('pending', 'pending_reentry') and \
                                names_match(row.get('food_name', ''), match['name']):
                            stale_purged.append(row['item_id'])
                            # omit → hard-deletes the stale pending row
                        else:
                            rows.append(row)
                with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
            return jsonify({'matched': True, 'outgoing_id': match['id'], 'stale_purged': stale_purged}), 200

    # Generate new ID from ALL rows in the CSV (including removed) so that a
    # previously-used and then removed item ID is never recycled for a new item.
    max_id = 0
    try:
        with open(DB_PATH, 'r', newline='', encoding='utf-8') as _f:
            for _row in csv.DictReader(_f):
                try:
                    num = int(_row['item_id'].split('_')[1])
                    max_id = max(max_id, num)
                except Exception:
                    pass
    except Exception:
        # Fallback: use the in-memory list if the file is unreadable
        for food in foods:
            try:
                num = int(food['id'].split('_')[1])
                max_id = max(max_id, num)
            except Exception:
                pass

    new_food = {
        'id': f'ITEM_{str(max_id + 1).zfill(3)}',
        'name': data.get('name', 'Unknown'),
        'freshnessScore': data.get('freshnessScore', 100),
        'daysUntilSpoilage': data.get('daysUntilSpoilage', 7),
        'timeInFridge': '0 days',
        'foodGroup': data.get('foodGroup', 'other'),
        'predictionSource': data.get('predictionSource', None),
        'geminiError': data.get('geminiError', None),
        'packagingType': data.get('packagingType', 'sealed'),
        'expirationDate': data.get('expirationDate', ''),
        'storageLocation': data.get('storageLocation', 'regular'),
        'status': data.get('status', 'confirmed'),
        'daysInFridge': data.get('daysInFridge', 0),
        'cumulativeTempAbuse': data.get('cumulativeTempAbuse', data.get('timeOutsideFridge', 0)),
        'confidence': data.get('confidence'),
        'top5Predictions': data.get('top5Predictions', []),
        'geminiSpoilageParams': data.get('geminiSpoilageParams', None),
        'description': _sanitize_text(data.get('description', ''))
    }

    foods.append(new_food)
    if write_foods(foods):
        return jsonify(new_food), 201
    return jsonify({'error': 'Failed to create food'}), 500


@app.route('/api/foods/<item_id>/switch-to-incoming', methods=['POST'])
def switch_to_incoming(item_id):
    """Restore an outgoing item to confirmed and create a new pending item for it."""
    foods = read_foods()

    outgoing_food = next((f for f in foods if f['id'] == item_id and f.get('status') == 'outgoing'), None)
    if not outgoing_food:
        return jsonify({'error': 'Item not found or not in outgoing state'}), 404

    # Restore original item to confirmed
    for food in foods:
        if food['id'] == item_id:
            food['status'] = 'confirmed'
            break

    # Create a new pending item using the same food data
    max_id = 0
    try:
        with open(DB_PATH, 'r', newline='', encoding='utf-8') as _f:
            for _row in csv.DictReader(_f):
                try:
                    num = int(_row['item_id'].split('_')[1])
                    max_id = max(max_id, num)
                except Exception:
                    pass
    except Exception:
        for food in foods:
            try:
                num = int(food['id'].split('_')[1])
                max_id = max(max_id, num)
            except Exception:
                pass

    pending_food = {
        'id': f'ITEM_{str(max_id + 1).zfill(3)}',
        'name': outgoing_food['name'],
        'freshnessScore': 100,
        'daysUntilSpoilage': outgoing_food.get('daysUntilSpoilage', 7),
        'timeInFridge': '0 days',
        'foodGroup': outgoing_food.get('foodGroup', 'other'),
        'packagingType': outgoing_food.get('packagingType', 'sealed'),
        'expirationDate': outgoing_food.get('expirationDate', ''),
        'storageLocation': outgoing_food.get('storageLocation', 'regular'),
        'status': 'pending',
        'daysInFridge': 0,
        'confidence': None,
        'top5Predictions': [],
        'geminiSpoilageParams': None,
        'description': outgoing_food.get('description', '')
    }
    foods.append(pending_food)

    if write_foods(foods):
        return jsonify({'message': 'Item restored to confirmed', 'id': item_id, 'pending_id': pending_food['id']})
    return jsonify({'error': 'Failed to restore item'}), 500


@app.route('/api/foods/<item_id>/mark-as-new', methods=['POST'])
def mark_as_new(item_id):
    """
    Override a pending_reentry item: reset it to a plain 'pending' item with
    fresh stats (new entry date, zeroed temp abuse, full freshness score).
    """
    try:
        found = False
        rows = []
        with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = list(reader.fieldnames)
            for row in reader:
                if row['item_id'] == item_id and row.get('status') == 'pending_reentry':
                    row['status'] = 'pending'
                    row['entry_date'] = datetime.now().isoformat()
                    row['cumulative_temp_abuse'] = '0.0'
                    row['freshness_score'] = '100'
                    row['removed_at'] = ''
                    found = True
                rows.append(row)

        if not found:
            return jsonify({'error': 'Item not found or not in pending_reentry state'}), 404

        with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return jsonify({'message': 'Item reset to new pending', 'id': item_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/foods/resolve-disambiguation', methods=['POST'])
def resolve_disambiguation():
    """
    Resolve a scan that produced multiple matches (multi_confirmed or reentry_or_outgoing).
    Actions:
      mark_outgoing  — mark target_id as outgoing (user selected which item is leaving)
      mark_reentry   — restore removed_id as pending_reentry (user confirmed it's returning)
      keep_new       — create a fresh pending item from scan_data (user says it's a new item)
    """
    data = request.json
    action = data.get('action')
    target_id = data.get('target_id')       # for mark_outgoing
    removed_id = data.get('removed_id')     # for mark_reentry
    scan_data = data.get('scan_data', {})

    try:
        if action == 'mark_outgoing':
            if not target_id:
                return jsonify({'error': 'target_id required'}), 400

            with _csv_lock:
                rows = []
                with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    fieldnames = list(reader.fieldnames)
                    for row in reader:
                        if row['item_id'] == target_id:
                            row['status'] = 'outgoing'
                        rows.append(dict(row))
                with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

            # Only create a new pending item when the disambiguation was
            # 'reentry_or_outgoing': in that context mark_outgoing means
            # "the scanned bar is a NEW item going IN (not the removed one)
            # while the confirmed bar goes out."
            #
            # For 'outgoing_or_new' and 'multi_confirmed', mark_outgoing means
            # "the scan was OF the outgoing item itself" — no new item should be
            # created; the other scanned bars in the batch already fell through
            # to plain pending in the scan loop.
            dis_type = data.get('dis_type', '')
            new_food_id = None
            if dis_type == 'reentry_or_outgoing' and scan_data:
                foods = read_foods()
                max_id = 0
                for food in foods:
                    try:
                        num = int(food['id'].split('_')[1])
                        max_id = max(max_id, num)
                    except:
                        pass
                new_food = {
                    'id': f'ITEM_{str(max_id + 1).zfill(3)}',
                    'name': scan_data.get('name', 'Unknown'),
                    'freshnessScore': 100,
                    'daysUntilSpoilage': scan_data.get('daysUntilSpoilage', 7),
                    'timeInFridge': '0 days',
                    'foodGroup': scan_data.get('foodGroup', 'other'),
                    'packagingType': scan_data.get('packagingType', 'sealed'),
                    'expirationDate': scan_data.get('expirationDate', ''),
                    'storageLocation': scan_data.get('storageLocation', 'regular'),
                    'status': 'pending',
                    'daysInFridge': 0,
                    'confidence': scan_data.get('confidence'),
                    'top5Predictions': scan_data.get('top5Predictions', []),
                    'geminiSpoilageParams': scan_data.get('geminiSpoilageParams', None),
                    'description': _sanitize_text(scan_data.get('description', ''))
                }
                foods.append(new_food)
                if write_foods(foods):
                    new_food_id = new_food['id']

            return jsonify({'matched': True, 'outgoing_id': target_id, 'new_pending_id': new_food_id}), 200

        elif action == 'mark_reentry':
            if not removed_id:
                return jsonify({'error': 'removed_id required'}), 400
            hours_outside = 0
            with _csv_lock:
                rows = []
                with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    fieldnames = list(reader.fieldnames)
                    for row in reader:
                        if row['item_id'] == removed_id and row.get('status') == 'removed':
                            try:
                                removed_at = datetime.fromisoformat(row.get('removed_at', ''))
                                hours_outside = (datetime.now() - removed_at).total_seconds() / 3600
                            except:
                                hours_outside = 0
                            new_abuse = float(row.get('cumulative_temp_abuse') or 0) + hours_outside
                            row['cumulative_temp_abuse'] = str(round(new_abuse, 2))
                            row['status'] = 'pending_reentry'
                            row['removed_at'] = ''
                        rows.append(row)
                with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
            return jsonify({'reentry': True, 'id': removed_id, 'hours_outside': round(hours_outside, 2)}), 200

        elif action == 'keep_new':
            foods = read_foods()
            max_id = 0
            for food in foods:
                try:
                    num = int(food['id'].split('_')[1])
                    max_id = max(max_id, num)
                except:
                    pass
            new_food = {
                'id': f'ITEM_{str(max_id + 1).zfill(3)}',
                'name': scan_data.get('name', 'Unknown'),
                'freshnessScore': 100,
                'daysUntilSpoilage': scan_data.get('daysUntilSpoilage', 7),
                'timeInFridge': '0 days',
                'foodGroup': scan_data.get('foodGroup', 'other'),
                'packagingType': scan_data.get('packagingType', 'sealed'),
                'expirationDate': scan_data.get('expirationDate', ''),
                'storageLocation': scan_data.get('storageLocation', 'regular'),
                'status': 'pending',
                'daysInFridge': 0,
                'confidence': scan_data.get('confidence'),
                'top5Predictions': scan_data.get('top5Predictions', []),
                'geminiSpoilageParams': scan_data.get('geminiSpoilageParams', None),
                'description': _sanitize_text(scan_data.get('description', ''))
            }
            foods.append(new_food)
            if write_foods(foods):
                return jsonify(new_food), 201
            return jsonify({'error': 'Failed to create food'}), 500

        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/foods/outgoing', methods=['GET'])
def get_outgoing_foods():
    """Get all outgoing food items."""
    all_foods = read_foods()
    outgoing_foods = [food for food in all_foods if food.get('status') == 'outgoing']
    return jsonify(outgoing_foods)


@app.route('/api/foods/outgoing/delete', methods=['DELETE'])
def delete_outgoing_foods():
    """Soft-delete all outgoing items (mark removed with timestamp for 2-hour reentry window)."""
    try:
        with _csv_lock:
            removed_at = datetime.now().isoformat()
            updated_count = 0
            rows = []
            removed_items = []
            with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                fieldnames = list(reader.fieldnames)
                if 'removed_at' not in fieldnames:
                    fieldnames.append('removed_at')
                for row in reader:
                    if row.get('status') == 'outgoing':
                        removed_items.append({
                            'id': row.get('item_id', ''),
                            'name': row.get('food_name', ''),
                            'freshness': row.get('freshness_score', '0')
                        })
                        row['status'] = 'removed'
                        row['removed_at'] = removed_at
                        updated_count += 1
                    rows.append(row)
            with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            for item in removed_items:
                try:
                    freshness = float(item['freshness']) if item['freshness'] != '' else 0
                except Exception:
                    freshness = 0
                _append_outcome_record(
                    item_id=item['id'],
                    food_name=item['name'],
                    outcome=_scan_outcome_from_freshness(freshness),
                    freshness_at_outcome=freshness,
                    days_tracked=0,
                    source='scan_outgoing'
                )

            if removed_items:
                update_daily_stats()
        return jsonify({'message': f'{updated_count} outgoing items removed', 'count': updated_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/foods/outgoing/restore', methods=['POST'])
def restore_outgoing_foods():
    """Restore all outgoing items back to confirmed (bulk Keep as New)."""
    foods = read_foods()
    updated_count = 0
    for food in foods:
        if food.get('status') == 'outgoing':
            food['status'] = 'confirmed'
            updated_count += 1
    if write_foods(foods):
        return jsonify({'message': f'{updated_count} items restored', 'count': updated_count})
    return jsonify({'error': 'Failed to restore items'}), 500


@app.route('/api/foods/<item_id>', methods=['PUT'])
def update_food(item_id):
    """Update an existing food item"""
    data = request.json
    foods = read_foods()
    
    for i, food in enumerate(foods):
        if food['id'] == item_id:
            new_status = data.get('status', food.get('status', 'confirmed'))
            becoming_confirmed = new_status == 'confirmed' and food.get('status') == 'pending'
            foods[i] = {
                'id': item_id,
                'name': data.get('name', food['name']),
                'freshnessScore': data.get('freshnessScore', food['freshnessScore']),
                'daysUntilSpoilage': data.get('daysUntilSpoilage', food['daysUntilSpoilage']),
                'timeInFridge': food['timeInFridge'],
                'foodGroup': data.get('foodGroup', food['foodGroup']),
                'packagingType': data.get('packagingType', food.get('packagingType', '')),
                'expirationDate': data.get('expirationDate', food.get('expirationDate', '')),
                'storageLocation': data.get('storageLocation', food.get('storageLocation', 'regular')),
                'status': new_status,
                'confidence': None if becoming_confirmed else food.get('confidence'),
                'top5Predictions': [] if becoming_confirmed else food.get('top5Predictions', [])
            }
            if 'daysInFridge' in data:
                foods[i]['daysInFridge'] = data.get('daysInFridge', 0)
            if 'cumulativeTempAbuse' in data:
                foods[i]['cumulativeTempAbuse'] = data.get('cumulativeTempAbuse', 0)
            if write_foods(foods):
                return jsonify(foods[i])
            return jsonify({'error': 'Failed to update food'}), 500
    
    return jsonify({'error': 'Food not found'}), 404

@app.route('/api/foods/<item_id>', methods=['DELETE'])
def delete_food(item_id):
    """Delete or revert a food item depending on its current status:

    - pending          → hard-delete: item was never confirmed, discard entirely.
    - outgoing         → revert to 'confirmed': cancels the pending removal,
                         item stays in the fridge.
    - pending_reentry  → revert to 'removed' with a fresh removed_at: cancels
                         the re-entry scan; item returns to its 2-hour window.
    - confirmed        → soft-delete: mark 'removed' with timestamp so it can
                         be re-scanned within 2 hours.
    """
    try:
        with _csv_lock:
            now = datetime.now().isoformat()
            rows = []
            found = False
            item_status = None
            with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                fieldnames = list(reader.fieldnames)
                if 'removed_at' not in fieldnames:
                    fieldnames.append('removed_at')
                for row in reader:
                    if row['item_id'] == item_id:
                        found = True
                        item_status = row.get('status', '')
                        if item_status == 'pending':
                            # Hard-delete: omit the row entirely
                            continue
                        elif item_status == 'outgoing':
                            # Revert to confirmed — cancels the pending removal
                            row['status'] = 'confirmed'
                            row['removed_at'] = ''
                        elif item_status == 'pending_reentry':
                            # Revert to removed — cancels the re-entry scan
                            row['status'] = 'removed'
                            row['removed_at'] = now
                        else:
                            # confirmed (or anything else): normal soft-delete
                            row['status'] = 'removed'
                            row['removed_at'] = now
                    rows.append(row)

            if not found:
                return jsonify({'error': 'Food not found'}), 404

            with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        return jsonify({'message': 'Food removed successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/foods/pending', methods=['GET'])
def get_pending_foods():
    """Get all pending and pending_reentry food items"""
    all_foods = read_foods()
    pending_foods = [food for food in all_foods if food.get('status') in ('pending', 'pending_reentry')]
    return jsonify(pending_foods)

@app.route('/api/foods/pending/confirm', methods=['POST'])
def confirm_pending_foods():
    """Confirm all pending/pending_reentry items (change status to confirmed)"""
    foods = read_foods()
    updated_count = 0
    reentry_confirmed_ids = []
    
    for food in foods:
        if food.get('status') in ('pending', 'pending_reentry'):
            if food.get('status') == 'pending_reentry':
                reentry_confirmed_ids.append(food.get('id'))
            food['status'] = 'confirmed'
            food['confidence'] = None
            food['top5Predictions'] = []
            updated_count += 1
    
    if write_foods(foods):
        revoked_total = 0
        for item_id in reentry_confirmed_ids:
            if item_id:
                revoked_total += _revoke_latest_outcome(item_id)
        if revoked_total > 0:
            update_daily_stats()
        return jsonify({'message': f'{updated_count} items confirmed', 'count': updated_count})
    return jsonify({'error': 'Failed to confirm items'}), 500

@app.route('/api/foods/pending/delete', methods=['DELETE'])
def delete_pending_foods():
    """Delete all pending and pending_reentry items"""
    try:
        with _csv_lock:
            # Read all data
            rows = []
            deleted_count = 0
            with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('status') in ('pending', 'pending_reentry'):
                        deleted_count += 1
                    else:
                        rows.append(row)
            
            # Write back without pending/pending_reentry items
            with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        
        return jsonify({'message': f'{deleted_count} pending items deleted', 'count': deleted_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/camera/stream', methods=['GET'])
def proxy_camera_stream():
    """Proxy Raspberry Pi MJPEG stream to avoid mixed-content/CORS issues."""
    if not _is_http_camera_url(PI_CAMERA_STREAM_URL):
        return jsonify({'error': 'Invalid PI_CAMERA_STREAM_URL configuration'}), 500

    try:
        upstream = requests.get(
            PI_CAMERA_STREAM_URL,
            stream=True,
            timeout=(5, 60),
            headers={'Accept': 'multipart/x-mixed-replace'}
        )
        upstream.raise_for_status()
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to connect to Pi camera stream: {e}'}), 502

    content_type = upstream.headers.get('Content-Type', 'multipart/x-mixed-replace; boundary=frame')

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        except GeneratorExit:
            # Client disconnected; close upstream stream promptly.
            return
        except requests.RequestException as e:
            print(f'[camera stream] upstream read error: {e}')
        finally:
            upstream.close()

    response = Response(
        stream_with_context(generate()),
        mimetype=content_type,
        headers={
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
        }
    )
    response.call_on_close(upstream.close)
    return response


@app.route('/api/camera/snapshot', methods=['GET'])
def proxy_camera_snapshot():
    """Proxy a single Pi camera frame for clients that prefer snapshots."""
    if not _is_http_camera_url(PI_CAMERA_SNAPSHOT_URL):
        return jsonify({'error': 'Invalid PI_CAMERA_SNAPSHOT_URL configuration'}), 500

    try:
        upstream = requests.get(PI_CAMERA_SNAPSHOT_URL, timeout=10)
        upstream.raise_for_status()
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to fetch Pi camera snapshot: {e}'}), 502

    return Response(
        upstream.content,
        mimetype=upstream.headers.get('Content-Type', 'image/jpeg'),
        headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'}
    )

@app.route('/api/sensor', methods=['GET'])
def get_sensor_data():
    """Get current sensor readings (temperature, humidity, and MQ gas sensors)"""
    snapshot = _get_sensor_snapshot()
    temperature = snapshot['temperature']
    humidity = snapshot['humidity']
    connected = snapshot['connected']
    mq_readings = snapshot['mq_readings']

    return jsonify({
        'temperature': temperature,
        'humidity': humidity,
        'connected': connected,
        'mq_readings': mq_readings
    })


@app.route('/api/sensor/mq/calibrate', methods=['POST'])
def calibrate_mq_sensor_max():
    """Calibrate each MQ sensor max value to the current live reading."""
    if SENSOR_UPSTREAM_BASE_URL:
        return jsonify({
            'error': 'MQ calibration is only supported when the sensor is directly connected to this backend',
            'sensorUpstreamBaseUrl': SENSOR_UPSTREAM_BASE_URL,
        }), 501

    sensor = get_sensor()
    if not sensor.is_connected():
        return jsonify({'error': 'Sensors are not connected'}), 503

    try:
        with open(MQ_CONFIG_PATH, 'r', encoding='utf-8') as config_file:
            config = json.load(config_file)
    except Exception as e:
        return jsonify({'error': f'Failed to read MQ config: {e}'}), 500

    safe_ranges = config.get('safeRanges')
    if not isinstance(safe_ranges, dict) or not safe_ranges:
        return jsonify({'error': 'Invalid MQ config format: safeRanges missing'}), 500

    default_min_offset = config.get('defaultMinOffset', 100)
    try:
        default_min_offset = int(default_min_offset)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid MQ config format: defaultMinOffset must be numeric'}), 500

    updated_max_values = {}
    updated_min_values = {}
    missing_readings = []
    for sensor_id_str in safe_ranges.keys():
        try:
            sensor_id = int(sensor_id_str)
        except (TypeError, ValueError):
            return jsonify({'error': f'Invalid sensor id in config: {sensor_id_str}'}), 500

        reading = sensor.get_mq_reading(sensor_id)
        if reading is None:
            missing_readings.append(sensor_id)
            continue
        current_reading = int(reading)
        updated_min_values[sensor_id_str] = current_reading - default_min_offset
        updated_max_values[sensor_id_str] = current_reading + default_min_offset

    if missing_readings:
        return jsonify({
            'error': 'Missing live readings for one or more sensors',
            'missingSensorIds': sorted(missing_readings)
        }), 409

    for sensor_id_str, calibrated_max in updated_max_values.items():
        safe_range = safe_ranges.get(sensor_id_str)
        if not isinstance(safe_range, dict):
            safe_range = {}
            safe_ranges[sensor_id_str] = safe_range

        calibrated_min = updated_min_values[sensor_id_str]
        safe_range['min'] = calibrated_min
        safe_range['max'] = calibrated_max

    try:
        with open(MQ_CONFIG_PATH, 'w', encoding='utf-8') as config_file:
            json.dump(config, config_file, indent=2)
            config_file.write('\n')
    except Exception as e:
        return jsonify({'error': f'Failed to write MQ config: {e}'}), 500

    refresh_mq_sensor_config()

    return jsonify({
        'message': 'MQ sensor calibration updated',
        'defaultMinOffset': default_min_offset,
        'updatedMaxValues': {
            int(sensor_id): value for sensor_id, value in updated_max_values.items()
        },
        'updatedMinValues': {
            int(sensor_id): value for sensor_id, value in updated_min_values.items()
        }
    })

@app.route('/api/stats/outcome', methods=['POST'])
def record_outcome():
    """Record the outcome of a food item, inferring when not explicitly supplied."""
    data = request.json
    item_id = data.get('item_id')
    outcome = data.get('outcome')  # optional: 'consumed', 'wasted'
    
    if not item_id:
        return jsonify({'error': 'Invalid data'}), 400

    if outcome and outcome not in ['consumed', 'wasted']:
        return jsonify({'error': 'Invalid data'}), 400
    
    try:
        # Get food details before deletion
        foods = read_foods()
        food = next((f for f in foods if f['id'] == item_id), None)
        
        if not food:
            return jsonify({'error': 'Food not found'}), 404

        if not outcome:
            outcome = _scan_outcome_from_freshness(food.get('freshnessScore', 0))
        
        # Calculate days tracked
        try:
            entry_date = datetime.now()  # Default to now if can't parse
            days_tracked = (datetime.now() - entry_date).days
        except:
            days_tracked = 0
        
        # Record outcome
        _append_outcome_record(
            item_id=item_id,
            food_name=food['name'],
            outcome=outcome,
            freshness_at_outcome=food.get('freshnessScore', 0),
            days_tracked=days_tracked,
            source='manual'
        )
        
        # Update daily stats
        update_daily_stats()
        
        return jsonify({'message': 'Outcome recorded successfully'})
    except Exception as e:
        print(f"Error recording outcome: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats/history', methods=['GET'])
def get_waste_history():
    """Get historical waste statistics"""
    try:
        history_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'waste_history.csv')
        history = []
        
        with open(history_path, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                history.append({
                    'date': row['date'],
                    'itemsConsumed': int(row['items_consumed']),
                    'itemsWasted': int(row['items_wasted']),
                    'totalItems': int(row['total_items']),
                    'wastePercentage': float(row['waste_percentage'])
                })
        
        return jsonify(history[-7:])  # Return last 7 days
    except Exception as e:
        print(f"Error reading history: {e}")
        return jsonify([])

def update_daily_stats():
    """Update daily waste statistics and clean up old data"""
    try:
        today = datetime.now().date()
        today_str = today.isoformat()
        seven_days_ago = (today - timedelta(days=7)).isoformat()
        
        history_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'waste_history.csv')
        
        # Read and filter item_outcomes to keep only last 7 days
        recent_outcomes = []
        consumed = 0
        wasted = 0
        
        with open(OUTCOME_PATH, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            for row in reader:
                outcome_date = row['outcome_date'][:10]  # Get just the date part
                
                # Keep only records from last 7 days
                if outcome_date >= seven_days_ago:
                    recent_outcomes.append(row)
                    
                    # Count today's outcomes
                    if outcome_date == today_str:
                        if row['outcome'] == 'consumed':
                            consumed += 1
                        elif row['outcome'] == 'wasted':
                            wasted += 1
        
        # Write back only recent outcomes
        with open(OUTCOME_PATH, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(recent_outcomes)
        # Write back only recent outcomes
        with open(OUTCOME_PATH, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(recent_outcomes)
        
        total = consumed + wasted
        waste_pct = (wasted / total * 100) if total > 0 else 0
        
        # Read existing history and keep only last 7 days
        history_data = []
        try:
            with open(history_path, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                history_data = [row for row in reader if row['date'] >= seven_days_ago and row['date'] != today_str]
        except:
            pass
        
        # Add/update today's entry
        history_data.append({
            'date': today_str,
            'items_consumed': consumed,
            'items_wasted': wasted,
            'total_items': total,
            'waste_percentage': round(waste_pct, 2)
        })
        
        # Write back only last 7 days
        with open(history_path, 'w', newline='', encoding='utf-8') as file:
            fieldnames = ['date', 'items_consumed', 'items_wasted', 'total_items', 'waste_percentage']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(history_data)
            
    except Exception as e:
        print(f"Error updating daily stats: {e}")

@app.route('/api/stats/temperature', methods=['GET'])
def get_temperature_history():
    """Get temperature history from recent or 12h rolled-up data."""
    try:
        scope = (request.args.get('scope', 'long') or 'long').strip().lower()
        limit_param = request.args.get('limit')
        limit = None
        if limit_param:
            try:
                limit = max(1, int(limit_param))
            except ValueError:
                limit = None

        source_path = TEMP_RECENT_PATH if scope == 'recent' else TEMP_HISTORY_12H_PATH
        history = []

        rows = _read_csv_rows(source_path)
        if limit is not None and len(rows) > limit:
            rows = rows[-limit:]

        for row in rows:
            history.append({
                'timestamp': row.get('timestamp', ''),
                'temperature': _safe_float(row.get('temperature')),
                'humidity': _safe_float(row.get('humidity')),
            })
        
        return jsonify(history)
    except Exception as e:
        print(f"Error reading temperature history: {e}")
        return jsonify([])

@app.route('/api/stats/mq', methods=['GET'])
def get_mq_history():
    """Get MQ history from recent or 12h rolled-up data."""
    try:
        scope = (request.args.get('scope', 'long') or 'long').strip().lower()
        limit_param = request.args.get('limit')
        limit = None
        if limit_param:
            try:
                limit = max(1, int(limit_param))
            except ValueError:
                limit = None

        source_path = MQ_RECENT_PATH if scope == 'recent' else MQ_HISTORY_12H_PATH
        history = []

        rows = _read_csv_rows(source_path)
        if limit is not None and len(rows) > limit:
            rows = rows[-limit:]

        for row in rows:
            entry = {'timestamp': row.get('timestamp', '')}
            for sid in _MQ_SENSOR_IDS:
                entry[f'mq{sid}'] = _safe_float(row.get(f'mq{sid}'))
            history.append(entry)

        return jsonify(history)
    except Exception as e:
        print(f'Error reading MQ history: {e}')
        return jsonify([])


@app.route('/api/stats/gas-contributors', methods=['GET'])
def get_gas_contributors():
    """Return dominant gas severity and top suspected food contributors."""
    try:
        snapshot = _get_sensor_snapshot()
        connected = snapshot['connected']
        mq_readings = snapshot['mq_readings']

        foods = read_foods()
        confirmed_foods = [f for f in foods if f.get('status') == 'confirmed']

        result = predict_gas_contributors(confirmed_foods, mq_readings)
        severity = result.get('severity', 'low')
        dominant_sensors = result.get('dominant_sensors', [])
        dominant_sensor_label = ', '.join(dominant_sensors) if dominant_sensors else 'N/A'

        if severity == 'high':
            message = 'High levels of gas detected. Check fridge ventilation and inspect stored items immediately.'
            details = f'Dominant high signal: {dominant_sensor_label}. High threshold: safe max + {int(MQ_HIGH_THRESHOLD_OFFSET)}mV'
        elif severity == 'elevated':
            message = 'Elevated gas levels detected. Monitor conditions and review nearby food items.'
            details = f'Dominant elevated signal: {dominant_sensor_label}. Elevated range: above safe max, below safe max + {int(MQ_HIGH_THRESHOLD_OFFSET)}mV'
        else:
            message = 'No abnormal gases detected.'
            details = ''

        return jsonify({
            'connected': connected,
            'severity': severity,
            'message': message,
            'details': details,
            'dominantSensors': dominant_sensors,
            'contributors': result.get('contributors', []),
        })
    except Exception as e:
        print(f'Error computing gas contributors: {e}')
        return jsonify({
            'connected': False,
            'severity': 'low',
            'message': 'No abnormal gases detected.',
            'details': '',
            'dominantSensors': [],
            'contributors': []
        })


@app.route('/api/recipes/cache/clear', methods=['POST'])
def clear_recipe_cache():
    """Clear the recipe cache to force fresh API calls, but keep backup"""
    # Save current cache as backup in case new fetch fails
    recipe_cache['backup'] = recipe_cache['data']
    recipe_cache['data'] = None
    recipe_cache['timestamp'] = None
    recipe_cache['cache_key'] = None
    # Increment offset to get different recipes on next fetch
    recipe_cache['offset'] = recipe_cache.get('offset', 0) + 6
    return jsonify({'message': 'Recipe cache cleared'})

@app.route('/api/recipes/search', methods=['GET'])
def search_recipes():
    """Search recipes based on available ingredients using Spoonacular API"""
    try:
        # Get optional filters from query parameters
        cuisine = request.args.get('cuisine', '')
        meal_type = request.args.get('type', '')
        diet = request.args.get('diet', '')
        
        foods = read_foods()
        
        if not foods:
            return jsonify([])
        
        # Sort by days until spoilage to prioritize expiring items
        sorted_foods = sorted(foods, key=lambda x: x['daysUntilSpoilage'])
        
        # Get ingredient names (use top 10 to avoid overly restrictive searches)
        ingredient_names = [food['name'] for food in sorted_foods[:10]]
        ingredients_str = ','.join(ingredient_names)
        
        # Create cache key based on filters AND current inventory
        # This ensures cache is invalidated when inventory changes
        cache_key = f"{cuisine}|{meal_type}|{diet}|{ingredients_str}"
        
        # Check cache first - cache persists until manually cleared or inventory changes
        # Use 'is not None' to allow caching of empty lists and error objects
        if recipe_cache['data'] is not None and recipe_cache.get('cache_key') == cache_key:
            cache_age = (datetime.now() - recipe_cache['timestamp']).total_seconds() if recipe_cache['timestamp'] else 0
            print(f"✓ Using cached recipes (age: {int(cache_age)}s)")
            return jsonify(recipe_cache['data'])
        
        # Get current offset for fetching different recipes
        current_offset = recipe_cache.get('offset', 0)
        print(f"⚠ Making Spoonacular API calls ({cuisine or 'all'}/{meal_type or 'all'}/{diet or 'all'}) - offset: {current_offset}")
        
        # Call Spoonacular API - Find by Ingredients
        url = 'https://api.spoonacular.com/recipes/findByIngredients'
        params = {
            'apiKey': SPOONACULAR_API_KEY,
            'ingredients': ingredients_str,
            'number': 6,  # Return 6 recipes
            'offset': current_offset,  # Offset for pagination
            'ranking': 2,  # Maximize used ingredients
            'ignorePantry': False
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 401:
            error_response = {'error': 'Invalid API key. Please set SPOONACULAR_API_KEY environment variable.'}
            # Cache the error so we don't keep retrying
            recipe_cache['data'] = error_response
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            recipe_cache['backup'] = None
            return jsonify(error_response), 401
        
        if response.status_code == 402:
            error_response = {'error': 'Reached daily recipe generation quota. Try again tomorrow or upgrade your Spoonacular API plan.'}
            # Cache the error so we don't keep hitting the quota limit
            recipe_cache['data'] = error_response
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            recipe_cache['backup'] = None
            return jsonify(error_response), 402
        
        if not response.ok:
            error_response = {'error': f'Spoonacular API error: {response.status_code}'}
            # Cache the error
            recipe_cache['data'] = error_response
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            recipe_cache['backup'] = None
            return jsonify(error_response), 500
        
        recipes = response.json()
        
        # Filter out recipes that don't use any of our ingredients
        recipes = [r for r in recipes if r.get('usedIngredientCount', 0) > 0]
        
        if not recipes:
            # Cache empty result so we don't keep making API calls
            # Reset offset back to 0 since we've exhausted available recipes
            recipe_cache['data'] = []
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            recipe_cache['backup'] = None
            recipe_cache['offset'] = 0
            print("✓ Cached empty recipe result (no more recipes available)")
            return jsonify([])
        
        # Enrich with recipe details (instructions, time, servings, etc.)
        detailed_recipes = []
        for recipe in recipes:
            detail_url = f"https://api.spoonacular.com/recipes/{recipe['id']}/information"
            detail_params = {'apiKey': SPOONACULAR_API_KEY}
            
            try:
                detail_response = requests.get(detail_url, params=detail_params, timeout=10)
                if detail_response.ok:
                    recipe_detail = detail_response.json()
                    
                    # Apply filters on detailed recipe data
                    # Filter by cuisine
                    if cuisine:
                        cuisines = [c.lower() for c in recipe_detail.get('cuisines', [])]
                        if cuisine.lower() not in cuisines:
                            continue
                    
                    # Filter by meal type
                    if meal_type:
                        dish_types = [d.lower() for d in recipe_detail.get('dishTypes', [])]
                        if meal_type.lower() not in dish_types:
                            continue
                    
                    # Filter by diet
                    if diet:
                        diets = [d.lower() for d in recipe_detail.get('diets', [])]
                        if diet.lower() not in diets:
                            continue
                    
                    # Combine basic info with detailed info
                    detailed_recipe = {
                        'id': recipe['id'],
                        'title': recipe['title'],
                        # 'image': recipe['image'],
                        'usedIngredientCount': recipe['usedIngredientCount'],
                        'missedIngredientCount': recipe['missedIngredientCount'],
                        'usedIngredients': recipe.get('usedIngredients', []),
                        'missedIngredients': recipe.get('missedIngredients', []),
                        'readyInMinutes': recipe_detail.get('readyInMinutes', 'N/A'),
                        'servings': recipe_detail.get('servings', 'N/A'),
                        'sourceUrl': recipe_detail.get('sourceUrl', ''),
                        'summary': recipe_detail.get('summary', ''),
                        'instructions': recipe_detail.get('instructions', ''),
                        'cuisines': recipe_detail.get('cuisines', []),
                        'dishTypes': recipe_detail.get('dishTypes', []),
                        'diets': recipe_detail.get('diets', [])
                    }
                    detailed_recipes.append(detailed_recipe)
            except Exception as e:
                print(f"Error fetching recipe details for {recipe['id']}: {e}")
                # Add basic recipe info even if details fail
                detailed_recipes.append({
                    'id': recipe['id'],
                    'title': recipe['title'],
                    # 'image': recipe['image'],
                    'usedIngredientCount': recipe['usedIngredientCount'],
                    'missedIngredientCount': recipe['missedIngredientCount']
                })
        
        # Cache the results
        recipe_cache['data'] = detailed_recipes
        recipe_cache['timestamp'] = datetime.now()
        recipe_cache['cache_key'] = cache_key
        recipe_cache['backup'] = None  # Clear backup on successful fetch
        print(f"✓ Cached {len(detailed_recipes)} recipes")
        
        return jsonify(detailed_recipes)
        
    except requests.exceptions.Timeout:
        # On timeout, return backup cache if available (from failed refresh)
        if recipe_cache['backup']:
            print("⚠ Timeout - returning backup cached recipes")
            error_result = {'error': 'Request timeout. Showing cached results.', 'recipes': recipe_cache['backup']}
            # Cache this error state
            recipe_cache['data'] = error_result
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            return jsonify(error_result)
        # Otherwise return main cache if available
        if recipe_cache['data']:
            print("⚠ Timeout - returning cached recipes")
            return jsonify({'error': 'Request timeout. Showing cached results.', 'recipes': recipe_cache['data']})
        # No cache available - cache the error
        error_result = {'error': 'Request timeout. Please try again.'}
        recipe_cache['data'] = error_result
        recipe_cache['timestamp'] = datetime.now()
        recipe_cache['cache_key'] = cache_key
        return jsonify(error_result), 504
    except Exception as e:
        print(f"Error fetching recipes: {e}")
        # On error, return backup cache if available (from failed refresh)
        if recipe_cache['backup']:
            print("⚠ Error - returning backup cached recipes")
            error_result = {'error': str(e), 'recipes': recipe_cache['backup']}
            # Cache this error state
            recipe_cache['data'] = error_result
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            return jsonify(error_result)
        # Otherwise return main cache if available
        if recipe_cache['data']:
            print("⚠ Error - returning cached recipes")
            return jsonify({'error': str(e), 'recipes': recipe_cache['data']})
        # No cache available - cache the error
        error_result = {'error': str(e)}
        recipe_cache['data'] = error_result
        recipe_cache['timestamp'] = datetime.now()
        recipe_cache['cache_key'] = cache_key
        return jsonify(error_result), 500

@app.route('/api/classify-food/batch', methods=['POST'])
def classify_food_batch():
    """
    Classify multiple food images in a single Gemini call.
    Expects: image_0, image_1, ... image_N files in multipart form data
    Returns: array of classification results, one per image
    """
    try:
        # Collect all uploaded image files (image_0, image_1, ...)
        image_files = []
        i = 0
        while f'image_{i}' in request.files:
            image_files.append(request.files[f'image_{i}'])
            i += 1

        if not image_files:
            return jsonify({'error': 'No image files provided'}), 400

        n = len(image_files)
        request_deadline = time.monotonic() + _GEMINI_REQUEST_TIMEOUT_SECONDS

        def _remaining_budget_seconds():
            return max(0.0, request_deadline - time.monotonic())

        gemini_enabled = _request_gemini_enabled(default=True)
        temp_paths = []
        pil_images = []

        try:
            # Save and open all images
            for idx, f in enumerate(image_files):
                temp_path = os.path.join(os.path.dirname(__file__), f'temp_upload_{idx}.jpg')
                f.save(temp_path)
                temp_paths.append(temp_path)
                pil_images.append(Image.open(temp_path))

            # Local model is primary for resilience. Gemini is a best-effort enhancer.
            local_raw_results = []
            if _LOCAL_MODEL_AVAILABLE and _local_clf.is_available():
                for img in pil_images:
                    try:
                        local_raw_results.append(_local_clf.predict(img))
                    except Exception as local_err:
                        print(f"[classify batch] local model prediction failed: {local_err}")
                        local_raw_results.append(None)
            else:
                local_raw_results = [None] * len(pil_images)

            results = [_build_local_primary_result(local_result) for local_result in local_raw_results]

            prompt = f"""
I am sending you {n} food image(s), provided in order after this message.
For EACH image, identify the food item and extract information. If the predicted item is not consumable, DO NOT include it as an entry in the response.

Return a JSON ARRAY with exactly {n} objects — one per image, in the same order.
Each object must follow this exact format:
{{
    "predicted_class": "name of the food",
    "confidence": confidence percentage (0-100),
    "category": "one of: dairy, produce, meat, seafood, beverage, condiment, prepared, other",
    "packaging_type": "one of: sealed, opened, loose, canned, bottled, boxed, bagged, wrapped",
    "storage_location": "one of: regular, crisper, door",
    "expiration_date": "YYYY-MM-DD if visible on package, otherwise null",
    "description": "detailed visual description: brand name if visible, container colour, container shape/type, label details, size/volume if visible, any distinguishing features",
    "notes": "any relevant observations about freshness, condition, or packaging",
    "spoilage_parameters": {{
        "shelf_life_days": estimated days this specific item lasts in ideal fridge conditions (integer),
        "optimal_temp": ideal storage temperature in Celsius (e.g. 2.0 for meat, 4.0 for most, 1.0 for seafood),
        "temp_sensitivity": how quickly spoilage accelerates above optimal temp, scale 0.5-3.5 (higher = more sensitive),
        "temp_abuse_threshold": hours above safe temperature before significant quality loss (e.g. 2-96),
        "optimal_humidity": ideal relative humidity percentage (e.g. 85 for produce, 40-50 for most),
        "humidity_sensitivity": how much humidity deviation affects shelf life, scale 0.2-2.0 (higher = more sensitive),
        "optimal_packaging": "one of: sealed, opened, loose, canned, bottled, boxed, bagged, wrapped"
    }},
    "top5": [
        {{"class": "most likely food", "confidence": percentage}},
        {{"class": "second most likely", "confidence": percentage}},
        {{"class": "third most likely", "confidence": percentage}},
        {{"class": "fourth most likely", "confidence": percentage}},
        {{"class": "fifth most likely", "confidence": percentage}}
    ]
}}

Guidelines:
- For category: Choose the most appropriate category for the primary food item
- For packaging_type: Describe the current state (e.g., "sealed" for unopened, "opened" for partially used)
- For storage_location: "crisper" for fruits/vegetables, "door" for condiments/drinks, "regular" for most items
- For expiration_date: Only include if clearly visible and legible in the image
- For description: Include brand, container colour, shape, label text, size — anything that uniquely identifies this specific product
- For spoilage_parameters: Provide item-specific values (e.g. hard cheese lasts much longer than soft cheese, both are dairy)
- For notes: Mention any visible damage, freshness indicators, or important details
- For predicted_class, use the same value as the first item in top5
- If no food is detected in an image, set predicted_class to "No Food Detected" and set other fields to null

Return ONLY the JSON array, no extra text.
"""

            # Build content list: prompt then all images. If Gemini fails, keep local-only results.
            used_gemini_indices = set()
            gemini_error_message = None
            primary_gemini_failed = False
            if gemini_enabled and gemini_client:
                try:
                    remaining = _remaining_budget_seconds()
                    if remaining <= 0.0:
                        raise TimeoutError(
                            f'Batch request exceeded end-to-end timeout of {_GEMINI_REQUEST_TIMEOUT_SECONDS:.1f}s before Gemini classification'
                        )
                    content = [prompt] + pil_images
                    response = _run_with_timeout(
                        lambda: gemini_client.models.generate_content(
                            model='gemini-2.5-flash-lite',
                            contents=content
                        ),
                        remaining
                    )
                    gemini_results = json.loads(_extract_json_payload(response.text))
                    if not isinstance(gemini_results, list):
                        gemini_results = [gemini_results]

                    # Keep local fallback for each index where Gemini output is missing/invalid.
                    merged = []
                    for idx in range(len(results)):
                        candidate = gemini_results[idx] if idx < len(gemini_results) else None
                        if isinstance(candidate, dict) and candidate.get('predicted_class'):
                            merged.append(candidate)
                            used_gemini_indices.add(idx)
                        else:
                            merged.append(results[idx])
                    results = merged
                except Exception as gemini_err:
                    primary_gemini_failed = True
                    gemini_error_message = str(gemini_err)
                    print(f"[classify batch] Gemini failed, using local-only predictions: {gemini_err}")
            else:
                gemini_error_message = 'Gemini disabled' if not gemini_enabled else 'Gemini API key not configured'

            # Always attach local_result so frontend compare panel still works.
            for i, result in enumerate(results):
                result['local_result'] = local_raw_results[i] if i < len(local_raw_results) else None
                if i in used_gemini_indices:
                    result['prediction_source'] = 'gemini'
                    result['gemini_error'] = None
                else:
                    result['prediction_source'] = 'local_fallback'
                    result['gemini_error'] = gemini_error_message or 'Gemini response missing or invalid'

            allow_grounded_gemini_lookup = gemini_enabled and not primary_gemini_failed
            remaining_for_grounded = _remaining_budget_seconds()
            _attach_grounded_spoilage_params(
                results,
                allow_gemini_lookup=allow_grounded_gemini_lookup,
                timeout_seconds=remaining_for_grounded,
            )

            return jsonify(results)

        finally:
            for img in pil_images:
                img.close()
            for path in temp_paths:
                if os.path.exists(path):
                    os.remove(path)

    except Exception as e:
        print(f"Batch classification error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/classify-food', methods=['POST'])
def classify_food():
    """
    Classify a food image using Google Gemini API
    Expects: image file in 'image' field
    Returns: predicted class name, confidence, and top 5 predictions
    """
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        image_file = request.files['image']
        
        # Save temporarily
        temp_path = os.path.join(os.path.dirname(__file__), 'temp_upload.jpg')
        image_file.save(temp_path)
        
        image = None
        try:
            # Load image
            image = Image.open(temp_path)

            local_raw_result = None
            if _LOCAL_MODEL_AVAILABLE and _local_clf.is_available():
                try:
                    local_raw_result = _local_clf.predict(image)
                except Exception as local_err:
                    print(f"[classify] local model prediction failed: {local_err}")

            result = _build_local_primary_result(local_raw_result)
            
            # Use Gemini to identify the food
            # gemini-2.5-flash-lite is fastest, but can use gemini-2.5-flash if tokens are depleted
            prompt = """
Analyze this image and identify the food item shown. Extract as much information as possible.

Return your response in this exact JSON format:
{
    "predicted_class": "name of the food",
    "confidence": confidence percentage (0-100),
    "category": "one of: dairy, produce, meat, seafood, beverage, condiment, prepared, other",
    "packaging_type": "one of: sealed, opened, loose, canned, bottled, boxed, bagged, wrapped",
    "storage_location": "one of: regular, crisper, door",
    "expiration_date": "YYYY-MM-DD if visible on package, otherwise null",
    "description": "detailed visual description: brand name if visible, container colour, container shape/type, label details, size/volume if visible, any distinguishing features",
    "notes": "any relevant observations about freshness, condition, or packaging",
    "spoilage_parameters": {
        "shelf_life_days": estimated days this specific item lasts in ideal fridge conditions (integer),
        "optimal_temp": ideal storage temperature in Celsius (e.g. 2.0 for meat, 4.0 for most, 1.0 for seafood),
        "temp_sensitivity": how quickly spoilage accelerates above optimal temp, scale 0.5-3.5 (higher = more sensitive),
        "temp_abuse_threshold": hours above safe temperature before significant quality loss (e.g. 2-96),
        "optimal_humidity": ideal relative humidity percentage (e.g. 85 for produce, 40-50 for most),
        "humidity_sensitivity": how much humidity deviation affects shelf life, scale 0.2-2.0 (higher = more sensitive),
        "optimal_packaging": "one of: sealed, opened, loose, canned, bottled, boxed, bagged, wrapped"
    },
    "top5": [
        {"class": "most likely food", "confidence": percentage},
        {"class": "second most likely", "confidence": percentage},
        {"class": "third most likely", "confidence": percentage},
        {"class": "fourth most likely", "confidence": percentage},
        {"class": "fifth most likely", "confidence": percentage}
    ]
}

Guidelines:
- For category: Choose the most appropriate category for the primary food item
- For packaging_type: Describe the current state (e.g., "sealed" for unopened, "opened" for partially used)
- For storage_location: "crisper" for fruits/vegetables, "door" for condiments/drinks, "regular" for most items
- For expiration_date: Only include if clearly visible and legible in the image
- For description: Include brand, container colour, shape, label text, size — anything that uniquely identifies this specific product
- For spoilage_parameters: Provide item-specific values (e.g. hard cheese lasts much longer than soft cheese, both are dairy)
- For notes: Mention any visible damage, freshness indicators, or important details
- If unsure about any field, provide your best guess with appropriate confidence level
- For predicted_class, use the same value as the first item in top5
- If no food is detected, fill out the fields with 'No Food Detected' for food name and null for the rest
"""
            
            gemini_enabled = _request_gemini_enabled(default=True)
            prediction_source = 'local_fallback'
            gemini_error_message = None

            if gemini_enabled and gemini_client:
                try:
                    response = _run_with_timeout(
                        lambda: gemini_client.models.generate_content(
                            model='gemini-2.5-flash-lite',
                            contents=[prompt, image]
                        ),
                        _GEMINI_REQUEST_TIMEOUT_SECONDS
                    )
                    gemini_result = json.loads(_extract_json_payload(response.text))
                    if isinstance(gemini_result, dict) and gemini_result.get('predicted_class'):
                        result = gemini_result
                        prediction_source = 'gemini'
                        gemini_error_message = None
                except Exception as gemini_err:
                    gemini_error_message = str(gemini_err)
                    print(f"[classify] Gemini failed, using local-only prediction: {gemini_err}")
            else:
                gemini_error_message = 'Gemini disabled' if not gemini_enabled else 'Gemini API key not configured'

            _attach_grounded_spoilage_params([result], allow_gemini_lookup=gemini_enabled)
            result['local_result'] = local_raw_result
            result['prediction_source'] = prediction_source
            result['gemini_error'] = gemini_error_message

            return jsonify(result)
            
        finally:
            # Always clean up, even if there's an error
            if image is not None:
                image.close()
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
    except Exception as e:
        print(f"Classification error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/classify-food/compare', methods=['POST'])
def compare_classifiers():
    """
    Run the same image through both the local ResNet18 model and Gemini,
    then return both predictions side-by-side for comparison.
    Expects: image file in 'image' field (multipart/form-data)
    Returns: { local: {...}, gemini: {...}, agreement: bool }
    """
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    image_file  = request.files['image']
    src_dir     = os.path.dirname(__file__)
    temp_path   = os.path.join(src_dir, 'temp_compare.jpg')
    image_file.save(temp_path)

    local_result  = None
    gemini_result = None
    pil_image     = None

    try:
        pil_image = Image.open(temp_path)

        # ── Local model ──────────────────────────────────────────────────────
        if _LOCAL_MODEL_AVAILABLE and _local_clf.is_available():
            try:
                local_result = _local_clf.predict(pil_image)
            except Exception as e:
                local_result = {'error': str(e)}
        else:
            local_result = {
                'error': 'Local model not available (check IMAGE_CLASS/25EPOCH.pth and PyTorch install)'
            }

        # ── Gemini ───────────────────────────────────────────────────────────
        if gemini_client:
            prompt = """
Analyze this image and identify the food item shown.

Return your response in this exact JSON format:
{
    "predicted_class": "name of the food",
    "confidence": confidence percentage (0-100),
    "category": "one of: dairy, produce, meat, seafood, beverage, condiment, prepared, other",
    "packaging_type": "one of: sealed, opened, loose, canned, bottled, boxed, bagged, wrapped",
    "notes": "any relevant observations about freshness, condition, or packaging",
    "top5": [
        {"class": "most likely food",   "confidence": percentage},
        {"class": "second most likely", "confidence": percentage},
        {"class": "third most likely",  "confidence": percentage},
        {"class": "fourth most likely", "confidence": percentage},
        {"class": "fifth most likely",  "confidence": percentage}
    ]
}

Return ONLY the JSON, no extra text.
"""
            try:
                response = _run_with_timeout(
                    lambda: gemini_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[prompt, pil_image]
                    ),
                    _GEMINI_REQUEST_TIMEOUT_SECONDS
                )
                gemini_result = json.loads(_extract_json_payload(response.text))
            except Exception as e:
                gemini_result = {'error': str(e)}
        else:
            gemini_result = {'error': 'Gemini API key not configured'}

        # ── Agreement check ──────────────────────────────────────────────────
        # Compare top-1 predictions (case-insensitive, partial match is fine)
        agree = False
        if local_result and 'predicted_class' in local_result and \
           gemini_result and 'predicted_class' in gemini_result:
            l = local_result['predicted_class'].lower()
            g = gemini_result['predicted_class'].lower()
            agree = (l in g) or (g in l) or (l == g)

        return jsonify({
            'local':     local_result,
            'gemini':    gemini_result,
            'agreement': agree,
        })

    finally:
        if pil_image is not None:
            pil_image.close()
        if os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == '__main__':
    # Purge any rows older than 12 hours that may have accumulated while the
    # server was offline or sensors were disconnected.
    _data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    _trim_history_file(
        os.path.join(_data_dir, 'temperature_history.csv'),
        ['timestamp', 'temperature', 'humidity']
    )
    _trim_history_file(
        os.path.join(_data_dir, 'mq_history.csv'),
        ['timestamp', 'mq2', 'mq3', 'mq4', 'mq5', 'mq8', 'mq9', 'mq135']
    )
    # Keep debug features enabled, but disable the reloader to avoid
    # duplicate processes competing for the RFCOMM device.
    app.run(debug=True, use_reloader=False, port=5000)
