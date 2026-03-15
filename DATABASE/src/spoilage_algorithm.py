"""
F.R.E.D. Spoilage Prediction Algorithm
Core algorithm for predicting food freshness and spoilage timing
"""

from datetime import datetime
import json
import math
from pathlib import Path


_MQ_CONFIG_PATH = Path(__file__).resolve().parents[2] / 'UI' / 'src' / 'config' / 'mqSensorConfig.json'


def _load_mq_sensor_config():
    with _MQ_CONFIG_PATH.open('r', encoding='utf-8') as config_file:
        raw_config = json.load(config_file)

    safe_ranges = {
        int(sensor_id): sensor_range
        for sensor_id, sensor_range in raw_config['safeRanges'].items()
    }
    high_threshold_offset = float(raw_config['highThresholdOffset'])
    return safe_ranges, high_threshold_offset


MQ_SAFE_RANGES, MQ_HIGH_THRESHOLD_OFFSET = _load_mq_sensor_config()

MQ_SENSOR_WEIGHTS = {
    2: 1.0,
    3: 0.9,
    4: 0.9,
    5: 1.1,
    8: 0.8,
    9: 1.2,
    135: 0.7,
}

FOOD_GAS_SENSITIVITY = {
    'dairy': 1.1,
    'meat': 1.25,
    'produce': 1.2,
    'beverage': 0.7,
    'seafood': 1.35,
    'condiment': 0.55,
    'prepared': 1.15,
    'other': 1.0,
}

GAS_CATEGORY_PROFILES = {
    'produce': {2: 0.4, 3: 0.9, 4: 0.6, 5: 0.3, 8: 0.3, 9: 0.2, 135: 0.8},
    'dairy': {2: 0.3, 3: 0.7, 4: 0.5, 5: 0.2, 8: 0.2, 9: 0.4, 135: 0.8},
    'meat': {2: 0.6, 3: 0.5, 4: 0.6, 5: 0.6, 8: 0.2, 9: 0.8, 135: 0.9},
    'seafood': {2: 0.7, 3: 0.4, 4: 0.7, 5: 0.6, 8: 0.2, 9: 0.9, 135: 1.0},
    'prepared': {2: 0.5, 3: 0.6, 4: 0.6, 5: 0.5, 8: 0.2, 9: 0.7, 135: 0.9},
    'beverage': {2: 0.2, 3: 0.5, 4: 0.3, 5: 0.2, 8: 0.2, 9: 0.2, 135: 0.5},
    'condiment': {2: 0.2, 3: 0.3, 4: 0.2, 5: 0.2, 8: 0.1, 9: 0.2, 135: 0.4},
    'other': {2: 0.3, 3: 0.5, 4: 0.4, 5: 0.3, 8: 0.2, 9: 0.4, 135: 0.6},
}

PACKAGING_EXPOSURE = {
    'sealed': 0.45,
    'canned': 0.4,
    'bottled': 0.45,
    'boxed': 0.6,
    'wrapped': 0.65,
    'bagged': 0.75,
    'opened': 0.85,
    'loose': 1.0,
}

# Food database with spoilage parameters based on USDA guidelines
# Backup intial spoilage prediction if AI prediction fails
FOOD_DATABASE = {
    # DAIRY
    'dairy': {
        'name': 'Dairy',
        'shelf_life_days': 14,
        'optimal_temp': 4.0,
        'temp_sensitivity': 1.8,
        'temp_abuse_threshold': 12.0,
        'optimal_humidity': 50,
        'humidity_sensitivity': 0.8,
        'optimal_packaging': 'sealed',
    },
    
    # MEAT
    'meat': {
        'name': 'Meat',
        'shelf_life_days': 3,
        'optimal_temp': 2.0,
        'temp_sensitivity': 2.8,
        'temp_abuse_threshold': 3.0,
        'optimal_humidity': 40,
        'humidity_sensitivity': 1.4,
        'optimal_packaging': 'sealed',
    },
    
    # PRODUCE
    'produce': {
        'name': 'Produce',
        'shelf_life_days': 7,
        'optimal_temp': 4.0,
        'temp_sensitivity': 1.5,
        'temp_abuse_threshold': 12.0,
        'optimal_humidity': 85,
        'humidity_sensitivity': 1.8,
        'optimal_packaging': 'loose',
    },
    
    # BEVERAGE
    'beverage': {
        'name': 'Beverage',
        'shelf_life_days': 10,
        'optimal_temp': 4.0,
        'temp_sensitivity': 1.3,
        'temp_abuse_threshold': 24.0,
        'optimal_humidity': 50,
        'humidity_sensitivity': 0.4,
        'optimal_packaging': 'sealed',
    },
    
    # SEAFOOD
    'seafood': {
        'name': 'Seafood',
        'shelf_life_days': 2,
        'optimal_temp': 1.0,
        'temp_sensitivity': 3.0,
        'temp_abuse_threshold': 2.0,
        'optimal_humidity': 50,
        'humidity_sensitivity': 1.6,
        'optimal_packaging': 'sealed',
    },

    # CONDIMENT
    'condiment': {
        'name': 'Condiment',
        'shelf_life_days': 90,
        'optimal_temp': 4.0,
        'temp_sensitivity': 0.8,
        'temp_abuse_threshold': 72.0,
        'optimal_humidity': 50,
        'humidity_sensitivity': 0.3,
        'optimal_packaging': 'sealed',
    },
    
    # PREPARED/LEFTOVERS
    'prepared': {
        'name': 'Prepared',
        'shelf_life_days': 4,
        'optimal_temp': 4.0,
        'temp_sensitivity': 2.5,
        'temp_abuse_threshold': 4.0,
        'optimal_humidity': 45,
        'humidity_sensitivity': 1.0,
        'optimal_packaging': 'sealed',
    },
    
    # DEFAULT
    'other': {
        'name': 'Other',
        'shelf_life_days': 7,
        'optimal_temp': 4.0,
        'temp_sensitivity': 1.5,
        'temp_abuse_threshold': 12.0,
        'optimal_humidity': 50,
        'humidity_sensitivity': 0.8,
        'optimal_packaging': 'sealed',
    },
}


def calculate_temperature_factor(current_temp, optimal_temp, sensitivity):
    """
    Calculate spoilage rate based on temperature using Arrhenius equation.
    Returns a factor that multiplies shelf life (< 1 = faster spoilage)
    """
    delta_T = current_temp - optimal_temp
    
    if delta_T <= 0:
        # At or below optimal - slight benefit
        return min(1.2, 1.0 + abs(delta_T) * 0.02)
    else:
        # Above optimal - accelerated spoilage
        # Convert Celcius to Kelvin
        T_current = current_temp + 273.15
        T_optimal = optimal_temp + 273.15
        Ea_R = 3000 * sensitivity
        arrhenius = math.exp(-Ea_R * (1/T_current - 1/T_optimal))
        return max(0.1, 1.0 / arrhenius)


def calculate_humidity_factor(current_humidity, optimal_humidity, sensitivity):
    """
    Calculate spoilage rate modifier based on humidity deviation from optimal.
    Returns a factor that multiplies shelf life (< 1 = faster spoilage).
    - Above optimal: promotes mould/bacterial growth (more severe)
    - Below optimal: causes desiccation/drying (less severe, except for produce)
    """
    delta_H = current_humidity - optimal_humidity

    if abs(delta_H) < 5:
        # Within 5% of optimal - negligible effect
        return 1.0
    elif delta_H > 0:
        # Above optimal - excess moisture accelerates spoilage
        return max(0.5, 1.0 - sensitivity * (delta_H / 100) ** 1.2)
    else:
        # Below optimal - drying effect (less damaging than excess moisture)
        return max(0.7, 1.0 + sensitivity * 0.4 * (delta_H / 100))


def calculate_temp_abuse_factor(cumulative_hours, threshold_hours):
    """Calculate degradation from cumulative temperature abuse"""
    if cumulative_hours <= 0:
        return 1.0
    
    if cumulative_hours <= threshold_hours:
        # Minor abuse
        return 1.0 - (0.1 * cumulative_hours / threshold_hours)
    else:
        # Significant abuse - exponential impact
        excess = cumulative_hours - threshold_hours
        return max(0.2, 0.9 * math.exp(-excess / threshold_hours))


def calculate_packaging_factor(packaging_type, optimal_packaging):
    """
    Get packaging protection factor.
    For produce, loose packaging is beneficial (better air circulation).
    For other foods, loose packaging accelerates spoilage.
    sealed, opened, loose, canned, bottled, boxed, bagged, wrapped
    """

    # Return 1.0 factor if packaging is optimal for the type of food
    if packaging_type == optimal_packaging:
        return 1.0

    # backup values if packaging is not optimal
    factors = {
        'sealed': 1.0,
        'opened': 0.7,
        'loose': 0.5,
        'canned': 1.0,
        'bottled': 1.0,
        'boxed': 1.0,
        'bagged': 0.7,
        'wrapped': 0.7
    }
    
    pkg_type = packaging_type.lower() if packaging_type else 'sealed'
    base_factor = factors.get(pkg_type, 1.0)
    
    return base_factor


def classify_mq_reading(sensor_id, value, high_threshold_offset=MQ_HIGH_THRESHOLD_OFFSET):
    """Classify a single MQ reading using calibrated safe ranges."""
    safe_range = MQ_SAFE_RANGES.get(sensor_id)
    if safe_range is None or value is None:
        return None
    if value > safe_range['max'] + high_threshold_offset:
        return 'high'
    if value > safe_range['max']:
        return 'elevated'
    return 'low'


def calculate_gas_factor(
    mq_readings,
    food_category,
    gas_exposure_hours=0.0,
    high_threshold_offset=MQ_HIGH_THRESHOLD_OFFSET
):
    """
    Convert current MQ readings into a bounded spoilage multiplier.
    Returns a factor that multiplies shelf life (< 1 = faster spoilage)
    plus metadata describing the gas risk.
    """
    if not mq_readings:
        return {
            'factor': 1.0,
            'index': 0.0,
            'status': 'low',
            'classifications': {},
        }

    weighted_sum = 0.0
    total_weight = 0.0
    classifications = {}
    status_rank = {'low': 0, 'elevated': 1, 'high': 2}
    overall_status = 'low'

    for sensor_id, safe_range in MQ_SAFE_RANGES.items():
        value = mq_readings.get(sensor_id)
        if value is None:
            continue

        weight = MQ_SENSOR_WEIGHTS.get(sensor_id, 1.0)
        exceedance = max(0.0, float(value) - float(safe_range['max']))
        normalized = min(exceedance / high_threshold_offset, 2.0)

        weighted_sum += normalized * weight
        total_weight += weight

        reading_status = classify_mq_reading(sensor_id, value, high_threshold_offset)
        classifications[sensor_id] = reading_status
        if status_rank.get(reading_status or 'low', 0) > status_rank[overall_status]:
            overall_status = reading_status

    if total_weight == 0.0:
        return {
            'factor': 1.0,
            'index': 0.0,
            'status': 'low',
            'classifications': classifications,
        }

    gas_index = weighted_sum / total_weight
    category_sensitivity = FOOD_GAS_SENSITIVITY.get(food_category, FOOD_GAS_SENSITIVITY['other'])
    persistence_multiplier = 1.0 + min(max(gas_exposure_hours, 0.0) / 24.0, 1.0) * 0.25
    adjusted_index = gas_index * category_sensitivity * persistence_multiplier
    gas_factor = max(0.55, math.exp(-0.22 * adjusted_index))

    return {
        'factor': gas_factor,
        'index': adjusted_index,
        'status': overall_status,
        'classifications': classifications,
    }


def calculate_freshness_score(days_since_purchase, effective_shelf_life):
    """Calculate freshness score 0-100 based on shelf life consumed"""
    if effective_shelf_life <= 0:
        return 0.0
    
    life_fraction = days_since_purchase / effective_shelf_life
    score = 100 * (1 - life_fraction)
    return max(0.0, min(100.0, score))


def _clamp01(value):
    return max(0.0, min(1.0, value))


def _urgency_score(days_until_spoilage):
    d = float(days_until_spoilage)
    if d <= 0:
        return 1.0
    if d <= 1:
        return 0.9
    if d <= 2:
        return 0.75
    if d <= 4:
        return 0.55
    return 0.3


def predict_gas_contributors(foods, mq_readings, high_threshold_offset=MQ_HIGH_THRESHOLD_OFFSET, top_n=3):
    """Rank most likely gas contributors using dominant (highest) detected severity."""
    if not mq_readings:
        return {
            'severity': 'low',
            'dominant_sensors': [],
            'contributors': []
        }

    sensors = []
    for sensor_id, safe_range in MQ_SAFE_RANGES.items():
        value = mq_readings.get(sensor_id)
        if value is None:
            continue
        status = classify_mq_reading(sensor_id, value, high_threshold_offset)
        anomaly = max(0.0, (float(value) - float(safe_range['max'])) / float(high_threshold_offset))
        sensors.append({
            'id': sensor_id,
            'status': status,
            'anomaly': min(anomaly, 2.0),
        })

    if not sensors:
        return {
            'severity': 'low',
            'dominant_sensors': [],
            'contributors': []
        }

    has_high = any(s['status'] == 'high' for s in sensors)
    has_elevated = any(s['status'] == 'elevated' for s in sensors)
    severity = 'high' if has_high else 'elevated' if has_elevated else 'low'

    if severity == 'low':
        return {
            'severity': severity,
            'dominant_sensors': [],
            'contributors': []
        }

    dominant_sensors = [s for s in sensors if s['status'] == severity]

    scored = []
    for food in foods:
        category = str(food.get('foodGroup') or food.get('food_category') or 'other').lower()
        profile = GAS_CATEGORY_PROFILES.get(category, GAS_CATEGORY_PROFILES['other'])

        weighted_match = 0.0
        strongest_sensor = None
        strongest_influence = 0.0
        for sensor in dominant_sensors:
            sensor_weight = MQ_SENSOR_WEIGHTS.get(sensor['id'], 1.0)
            profile_weight = profile.get(sensor['id'], 0.0)
            influence = sensor['anomaly'] * sensor_weight * profile_weight
            weighted_match += influence
            if influence > strongest_influence:
                strongest_influence = influence
                strongest_sensor = sensor['id']

        freshness = float(food.get('freshnessScore', food.get('freshness_score', 100)) or 100)
        freshness_risk = _clamp01(1.0 - (freshness / 100.0))

        days_until = food.get('daysUntilSpoilage', food.get('days_until_spoilage', 7))
        try:
            urgency = _urgency_score(days_until)
        except Exception:
            urgency = 0.4

        spoilage_stage = 0.7 * freshness_risk + 0.3 * urgency

        packaging_type = str(food.get('packagingType') or food.get('packaging_type') or '').lower()
        packaging_exposure = PACKAGING_EXPOSURE.get(packaging_type, 0.8)

        raw_score = weighted_match * spoilage_stage * packaging_exposure
        if raw_score <= 0:
            continue

        reasons = [
            f"{round(freshness)}/100 freshness",
            f"{packaging_type or 'unknown'} packaging",
        ]
        if strongest_sensor is not None:
            reasons.append(f"matches MQ-{strongest_sensor} {severity} signal")

        scored.append({
            'foodName': food.get('name') or food.get('food_name') or 'Unknown',
            'score': raw_score,
            'reasons': reasons,
        })

    if not scored:
        return {
            'severity': severity,
            'dominant_sensors': [f"MQ-{s['id']}" for s in dominant_sensors],
            'contributors': []
        }

    total_score = sum(item['score'] for item in scored)
    ranked = sorted(scored, key=lambda x: x['score'], reverse=True)[:top_n]
    contributors = [
        {
            'foodName': item['foodName'],
            'confidence': int(round((item['score'] / total_score) * 100)) if total_score > 0 else 0,
            'reasons': item['reasons'],
        }
        for item in ranked
    ]

    return {
        'severity': severity,
        'dominant_sensors': [f"MQ-{s['id']}" for s in dominant_sensors],
        'contributors': contributors,
    }


def categorize_safety(freshness_score, days_remaining):
    """Determine safety category"""
    if freshness_score >= 75 and days_remaining > 3:
        return 'Fresh'
    elif freshness_score >= 25 and days_remaining > 1:
        return 'Good'
    elif freshness_score >= 0:
        return 'Caution'
    else:
        return 'Spoiled'


def predict_spoilage(
    food_category,
    purchase_date,
    current_temp=4.0,
    current_humidity=50.0,
    packaging_type='sealed',
    cumulative_temp_abuse=0.0,
    expiration_date=None,
    food_name='',
    storage_location='regular',
    gemini_shelf_life_days=None,
    gemini_params=None,
    mq_readings=None,
    gas_exposure_hours=0.0
):
    """
    Main spoilage prediction function.
    
    Args:
        food_category: Category from FOOD_DATABASE (lowercase)
        purchase_date: datetime when purchased
        current_temp: Current temperature in Celsius
        current_humidity: Current relative humidity %
        packaging_type: 'sealed', 'air-tight container', 'opened', 'loose', 'carton', 'bottle', or 'jar'
        cumulative_temp_abuse: Total hours above safe temperature
        expiration_date: Optional expiration date
        food_name: Name of the food item (used to detect specific items like apples)
        storage_location: 'regular' or 'humidity-controlled' (crisper drawer)
        mq_readings: Optional dict of live MQ sensor readings keyed by sensor ID
        gas_exposure_hours: Optional cumulative hours of elevated gas exposure
    
    Returns:
        dict with:
            - freshness_score: 0-100
            - days_until_spoilage: float
            - safety_category: 'Fresh', 'Good', 'Caution', or 'Spoiled'
            - warnings: list of warning messages
    """
    
    food_category = food_category.lower() if food_category else 'other'
    
    # Get food parameters
    if food_category not in FOOD_DATABASE:
        food_category = 'other'
    
    food = FOOD_DATABASE[food_category]

    # Override category defaults with Gemini's item-specific parameters where provided
    if gemini_params:
        overridable = ['optimal_temp', 'temp_sensitivity', 'temp_abuse_threshold',
                       'optimal_humidity', 'humidity_sensitivity', 'optimal_packaging']
        food = {**food, **{k: gemini_params[k] for k in overridable if k in gemini_params and gemini_params[k] is not None}}
    days_since_purchase = (datetime.now() - purchase_date).total_seconds() / 86400
    
    # Determine baseline shelf life — priority: expiration date > gemini_params > gemini_shelf_life_days > category default
    if expiration_date:
        baseline_shelf_life = (expiration_date - purchase_date).total_seconds() / 86400
    elif gemini_params and gemini_params.get('shelf_life_days'):
        baseline_shelf_life = float(gemini_params['shelf_life_days'])
    elif gemini_shelf_life_days:
        # Backward compat for items saved before gemini_params was added
        baseline_shelf_life = float(gemini_shelf_life_days)
    else:
        baseline_shelf_life = food['shelf_life_days']
    
    # Calculate environmental factors
    temp_factor = calculate_temperature_factor(
        current_temp,
        food['optimal_temp'],
        food['temp_sensitivity']
    )

    humidity_factor = calculate_humidity_factor(
        current_humidity,
        food['optimal_humidity'],
        food['humidity_sensitivity']
    )

    abuse_factor = calculate_temp_abuse_factor(
        cumulative_temp_abuse,
        food['temp_abuse_threshold']
    )

    packaging_factor = calculate_packaging_factor(packaging_type, food['optimal_packaging'])
    gas_result = calculate_gas_factor(mq_readings, food_category, gas_exposure_hours)
    gas_factor = gas_result['factor']

    # Calculate effective shelf life
    effective_shelf_life = baseline_shelf_life * temp_factor * humidity_factor * abuse_factor * packaging_factor * gas_factor
    
    # Special case: produce in humidity-controlled storage lasts longer
    if food_category == 'produce' and storage_location.lower() == 'humidity-controlled':
        effective_shelf_life *= 1.3
    
    # Calculate outputs
    freshness_score = calculate_freshness_score(days_since_purchase, effective_shelf_life)
    days_until_spoilage = max(0, effective_shelf_life - days_since_purchase)
    safety_category = categorize_safety(freshness_score, days_until_spoilage)
    
    # Generate warnings
    warnings = []
    if current_temp > food['optimal_temp'] + 3:
        warnings.append(f"Temperature too high ({current_temp}°C)")
    if cumulative_temp_abuse > food['temp_abuse_threshold']:
        warnings.append(f"Significant temperature abuse detected")
    if gas_result['status'] == 'high':
        warnings.append('High gas levels detected')
    elif gas_result['status'] == 'elevated':
        warnings.append('Elevated gas levels detected')
    if safety_category == 'Spoiled':
        warnings.append("DISCARD - Food likely spoiled")
    elif safety_category == 'Caution':
        warnings.append("Consume soon")
    
    return {
        'freshness_score': round(freshness_score, 1),
        'days_until_spoilage': round(days_until_spoilage, 1),
        'safety_category': safety_category,
        'warnings': warnings,
        'metadata': {
            'days_since_purchase': round(days_since_purchase, 1),
            'effective_shelf_life': round(effective_shelf_life, 1),
            'temp_factor': round(temp_factor, 3),
            'humidity_factor': round(humidity_factor, 3),
            'abuse_factor': round(abuse_factor, 3),
            'packaging_factor': round(packaging_factor, 3),
            'gas_factor': round(gas_factor, 3),
            'gas_index': round(gas_result['index'], 3),
            'gas_status': gas_result['status'],
            'gas_sensor_statuses': gas_result['classifications']
        }
    }
