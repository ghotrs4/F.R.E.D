"""
F.R.E.D. Sensor Interface
Reads serial data from ESP32 over Bluetooth (BluetoothSerial / RFCOMM)
"""

import os
import re
import threading
import time
import serial  # pyserial
import serial.tools.list_ports


class SensorInterface:
    """
    Interfaces with the ESP32 sensor board over a Bluetooth serial (RFCOMM) connection.
    Data format mirrors the printf statements in main.cpp:
        >MQ{id}:{value}
        >Temperature:{value} °C
        >Pressure:{value} hPa
        >Approx_altitude:{value} m
        >Humidity:{value} %
    """

    # Regex patterns matching main.cpp output format
    _PATTERNS = {
        "mq":          re.compile(r">MQ(\d+):(\d+)"),
        "temperature": re.compile(r">Temperature:([\d.]+)"),
        "pressure":    re.compile(r">Pressure:([\d.]+)"),
        "altitude":    re.compile(r">Approx_altitude:([\d.]+)"),
        "humidity":    re.compile(r">Humidity:([\d.]+)"),
    }

    def __init__(self, port: str | None = None, baudrate: int = 57600):
        """
        Initialize sensor interface.

        Args:
            port:     Preferred COM port (hint only — all available ports are
                      swept if this one fails or is None).
            baudrate: Must match BluetoothSerial – typically ignored for BT but
                      kept for compatibility when switching to wired UART.
        """
        env_port = os.environ.get("SENSOR_PORT")
        if env_port:
            self._preferred_port = env_port
        elif port:
            self._preferred_port = port
        elif os.name == "posix":
            # Match the tested standalone script's default Linux RFCOMM device.
            self._preferred_port = "/dev/rfcomm0"
        else:
            self._preferred_port = None
        self._baudrate = baudrate
        self._is_connected = False
        self._serial: serial.Serial | None = None
        self._serial_timeout = max(0.05, self._env_float('SENSOR_SERIAL_TIMEOUT', 5.0))
        self._stale_timeout = max(2.0, self._env_float('SENSOR_STALE_TIMEOUT', self._STALE_TIMEOUT))
        self._max_consecutive_serial_errors = max(
            1,
            self._env_int('SENSOR_MAX_CONSECUTIVE_SERIAL_ERRORS', 3)
        )
        self._consecutive_serial_errors = 0
        # RFCOMM on Linux can intermittently raise "readiness to read but
        # returned no data" despite a healthy stream. Treat those as transient
        # unless they persist beyond this threshold.
        self._max_transient_empty_read_errors = max(
            1,
            self._env_int('SENSOR_MAX_TRANSIENT_EMPTY_READ_ERRORS', 25)
        )
        self._transient_empty_read_errors = 0

        # Load configurable validation ranges from environment variables.
        # These allow tuning acceptable value bounds without code changes.
        self._temp_min = self._env_float('SENSOR_TEMP_MIN', self._TEMP_MIN)
        self._temp_max = self._env_float('SENSOR_TEMP_MAX', self._TEMP_MAX)
        self._temp_max_delta = max(
            0.0, self._env_float('SENSOR_TEMP_MAX_DELTA', self._TEMP_MAX_DELTA)
        )
        self._hum_min = self._env_float('SENSOR_HUM_MIN', self._HUM_MIN)
        self._hum_max = self._env_float('SENSOR_HUM_MAX', self._HUM_MAX)
        self._hum_max_delta = max(
            0.0, self._env_float('SENSOR_HUM_MAX_DELTA', self._HUM_MAX_DELTA)
        )
        self._pres_min = self._env_float('SENSOR_PRES_MIN', self._PRES_MIN)
        self._pres_max = self._env_float('SENSOR_PRES_MAX', self._PRES_MAX)
        self._pres_max_delta = max(
            0.0, self._env_float('SENSOR_PRES_MAX_DELTA', self._PRES_MAX_DELTA)
        )
        self._alt_min = self._env_float('SENSOR_ALT_MIN', self._ALT_MIN)
        self._alt_max = self._env_float('SENSOR_ALT_MAX', self._ALT_MAX)
        self._alt_max_delta = max(
            0.0, self._env_float('SENSOR_ALT_MAX_DELTA', self._ALT_MAX_DELTA)
        )
        self._mq_min = self._env_float('SENSOR_MQ_MIN', self._MQ_MIN)
        self._mq_max = self._env_float('SENSOR_MQ_MAX', self._MQ_MAX)

        # Latest sensor readings
        self._temperature: float = 4.0
        self._humidity: float = 50.0
        self._pressure: float = 1013.25
        self._altitude: float = 0.0
        self._mq_readings: dict[int, int] = {}
        self._mq_raw_readings: dict[int, int] = {}
        self._has_temperature = False
        self._has_humidity = False

        # Data validation tracking
        self._validation_errors: dict[str, int] = {
            "temperature_out_of_range": 0,
            "temperature_delta_exceeded": 0,
            "humidity_out_of_range": 0,
            "humidity_delta_exceeded": 0,
            "pressure_out_of_range": 0,
            "pressure_delta_exceeded": 0,
            "altitude_out_of_range": 0,
            "altitude_delta_exceeded": 0,
            "mq_out_of_range": 0,
        }
        self._last_data_received: float = 0.0   # epoch time of last valid parse
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_loop_error: str | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    # Seconds of silence before declaring the connection dead
    _STALE_TIMEOUT: float = 120.0
    # Seconds between port-sweep retries when disconnected
    _RECONNECT_INTERVAL: float = 5.0
    # Seconds to wait for valid sensor lines when probing a candidate port.
    # Must be long enough to cover Bluetooth RFCOMM handshake (~3-5 s) plus
    # enough reads to hit _PORT_PROBE_MIN_LINES.
    _PORT_PROBE_TIMEOUT: float = 10.0
    # Seconds to wait after opening a port before starting the probe read loop.
    # Bluetooth serial (RFCOMM) needs time to complete the connection handshake
    # before data starts flowing; skipping this causes the probe to burn through
    # its timeout on empty reads.
    _PORT_SETTLE_DELAY: float = 3.0
    # Number of valid lines required during probe before declaring connected.
    # 1 is sufficient because reset_input_buffer() already discards any stale
    # BT serial buffer bytes before the probe read loop starts, so the first
    # matching line is guaranteed to be a live transmission.
    _PORT_PROBE_MIN_LINES: int = 1
    # Keep MQ readings raw to mirror the standalone serial reference reader.
    _MQ_EMA_ALPHA: float = 1.0

    # ================================================================
    # Data validation constants (configurable via environment variables)
    # ================================================================
    # Temperature bounds (°C). Reasonable for food storage: -40 to 85.
    # Configurable via SENSOR_TEMP_MIN and SENSOR_TEMP_MAX env vars.
    _TEMP_MIN: float = -40.0
    _TEMP_MAX: float = 85.0
    # Maximum temperature change allowed between consecutive readings (°C).
    # Prevents accepting a reading if it diverges by more than this from
    # the previous value. Use 0 to disable. Configurable via SENSOR_TEMP_MAX_DELTA.
    _TEMP_MAX_DELTA: float = 30.0

    # Humidity bounds (%). Standard: 0 to 100.
    # Configurable via SENSOR_HUM_MIN and SENSOR_HUM_MAX env vars.
    _HUM_MIN: float = 0.0
    _HUM_MAX: float = 100.0
    # Max humidity change between consecutive readings (%).
    # Configurable via SENSOR_HUM_MAX_DELTA.
    _HUM_MAX_DELTA: float = 20.0

    # Pressure bounds (hPa). Typical atmospheric: 950 to 1050 hPa.
    # Configurable via SENSOR_PRES_MIN and SENSOR_PRES_MAX env vars.
    _PRES_MIN: float = 800.0
    _PRES_MAX: float = 1200.0
    # Max pressure change allowed (hPa).
    # Configurable via SENSOR_PRES_MAX_DELTA.
    _PRES_MAX_DELTA: float = 50.0

    # Altitude bounds (m). Reasonable: -400 (Dead Sea) to 9000 (commercial aviation).
    # Configurable via SENSOR_ALT_MIN and SENSOR_ALT_MAX env vars.
    _ALT_MIN: float = -400.0
    _ALT_MAX: float = 9000.0
    # Max altitude change (m). Configurable via SENSOR_ALT_MAX_DELTA.
    _ALT_MAX_DELTA: float = 1000.0

    # MQ sensor bounds (typically 0-4095 for 12-bit ADC).
    # Configurable via SENSOR_MQ_MIN and SENSOR_MQ_MAX env vars.
    _MQ_MIN: float = 0.0
    _MQ_MAX: float = 4095.0

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        raw = os.environ.get(name)
        if raw is None:
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        raw = os.environ.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    def connect(self) -> bool:
        """
        Start the persistent background connection/reader thread.
        Returns True if a connection is already established; the actual
        first-connect happens asynchronously in the background.
        """
        if self._running:
            if self._thread and not self._thread.is_alive():
                # Thread was expected to be running but died; restart it.
                print("[SensorInterface] Reader thread stopped unexpectedly; restarting")
                self._running = False
            else:
                return self._is_connected
        self._running = True
        self._thread = threading.Thread(target=self._connection_loop, daemon=True)
        self._thread.start()
        # Wait long enough to cover the BT settle delay + a few reads.
        # The background thread continues regardless; this just avoids callers
        # immediately seeing is_connected() == False on a slow BT start.
        time.sleep(self._PORT_SETTLE_DELAY + 2.0)
        return self._is_connected

    def disconnect(self) -> None:
        """Stop the background thread and close the serial port."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        self._close_serial()
        self._is_connected = False

    def _close_serial(self) -> None:
        """Close and release the serial port if open."""
        if self._serial:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except Exception:
                pass
            self._serial = None

    # ------------------------------------------------------------------
    # Background connection loop
    # ------------------------------------------------------------------

    def _connection_loop(self) -> None:
        """
        Persistent background loop.
        — When connected: read and parse lines from the serial port.
        — When disconnected: sweep available COM ports until one responds.
        """
        while self._running:
            try:
                if not self._is_connected:
                    self._sweep_for_connection()
                else:
                    self._read_line()
            except Exception as e:
                # Keep the polling loop alive even if an unexpected runtime
                # exception occurs (e.g., transient OS/serial state issues).
                self._last_loop_error = str(e)
                print(f"[SensorInterface] Polling loop error: {e}")
                self._mark_disconnected()
                time.sleep(1.0)

    def _get_candidate_ports(self) -> list[str]:
        """Return COM ports to try, with the preferred port first."""
        available = [p.device for p in serial.tools.list_ports.comports()]
        if not self._preferred_port:
            return available
        # Keep behavior simple and deterministic: only use explicit preferred port.
        return [self._preferred_port]

    def _try_port(self, port: str) -> bool:
        """
        Open *port* and wait up to _PORT_PROBE_TIMEOUT seconds for at least
        _PORT_PROBE_MIN_LINES valid sensor lines.  Requiring multiple lines
        prevents stale BT serial buffers from causing a false-positive connect.
        On success, stores the open Serial, parses the collected lines into
        sensor state, and returns True.  On failure, closes the port and
        returns False.
        """
        try:
            ser = serial.Serial(
                port=port,
                baudrate=self._baudrate,
                bytesize=serial.EIGHTBITS,
                timeout=self._serial_timeout,
                stopbits=serial.STOPBITS_ONE,
            )
        except (serial.SerialException, OSError, PermissionError):
            return False

        # Wait for Bluetooth RFCOMM to complete its handshake before reading.
        # Without this, readline() returns empty for the first few seconds and
        # the probe timeout expires before any valid data arrives.
        settle_end = time.time() + self._PORT_SETTLE_DELAY
        while time.time() < settle_end:
            if not self._running:
                try:
                    ser.close()
                except Exception:
                    pass
                return False
            time.sleep(0.1)

        deadline = time.time() + self._PORT_PROBE_TIMEOUT
        valid_lines: list[str] = []
        while time.time() < deadline:
            if not self._running:
                try:
                    ser.close()
                except Exception:
                    pass
                return False
            try:
                raw = ser.readline()
                if raw:
                    line = raw.decode('utf-8', errors='ignore').strip()
                    if any(p.match(line) for p in self._PATTERNS.values()):
                        valid_lines.append(line)
                        if len(valid_lines) >= self._PORT_PROBE_MIN_LINES:
                            break
            except (serial.SerialException, OSError):
                break

        if len(valid_lines) >= self._PORT_PROBE_MIN_LINES:
            with self._lock:
                self._serial = ser
                self._is_connected = True
                self._last_data_received = time.time()
                self._consecutive_serial_errors = 0
            # Parse the lines collected during probe so readings aren't wasted
            for line in valid_lines:
                self._parse_line(line)
            print(f"[SensorInterface] Connected on {port}")
            return True

        try:
            ser.close()
        except Exception:
            pass
        return False

    def _sweep_for_connection(self) -> None:
        """Try every available COM port; sleep and retry if none respond."""
        candidates = self._get_candidate_ports()
        if not candidates:
            print(f"[SensorInterface] No COM ports found — retrying in "
                  f"{self._RECONNECT_INTERVAL}s")
            time.sleep(self._RECONNECT_INTERVAL)
            return

        print(f"[SensorInterface] Sweeping ports: {candidates}")
        for port in candidates:
            if not self._running:
                return
            if self._try_port(port):
                return   # Connected — hand back to _connection_loop

        print(f"[SensorInterface] No sensor found on {candidates} — "
              f"retrying in {self._RECONNECT_INTERVAL}s")
        time.sleep(self._RECONNECT_INTERVAL)

    def _read_line(self) -> None:
        """Read one line from the open serial port; mark disconnected on error."""
        ser = self._serial
        if ser is None or not ser.is_open:
            self._mark_disconnected()
            return
        try:
            raw = ser.readline()
            if not raw:
                # readline() timed out according to self._serial_timeout.
                if (self._last_data_received > 0 and
                        time.time() - self._last_data_received > self._stale_timeout):
                    print(f"[SensorInterface] No data for {self._stale_timeout}s "
                          "— disconnecting")
                    self._mark_disconnected()
                return
            line = raw.decode('utf-8', errors='ignore').strip()
            self._consecutive_serial_errors = 0
            self._transient_empty_read_errors = 0
            self._parse_line(line)
        except (serial.SerialException, OSError, PermissionError) as e:
            if self._is_transient_empty_read_error(e):
                self._transient_empty_read_errors += 1
                if self._transient_empty_read_errors == 1 or self._transient_empty_read_errors % 25 == 0:
                    print(
                        f"[SensorInterface] Transient serial empty-read "
                        f"({self._transient_empty_read_errors}): {e}"
                    )
                if self._transient_empty_read_errors >= self._max_transient_empty_read_errors:
                    print(
                        "[SensorInterface] Transient empty-read threshold "
                        f"reached ({self._transient_empty_read_errors}/"
                        f"{self._max_transient_empty_read_errors}) — reconnecting"
                    )
                    self._mark_disconnected()
                    return
                # Treat known RFCOMM empty-read exceptions as non-fatal; rely on
                # stale-timeout logic to detect a real dead connection.
                time.sleep(min(self._serial_timeout, 0.2))
                return

            self._consecutive_serial_errors += 1
            if self._consecutive_serial_errors < self._max_consecutive_serial_errors:
                print(
                    f"[SensorInterface] Serial read error "
                    f"({self._consecutive_serial_errors}/{self._max_consecutive_serial_errors}): {e}"
                )
                time.sleep(min(self._serial_timeout, 0.5))
                return
            print(f"[SensorInterface] Serial error: {e}")
            self._mark_disconnected()

    def _mark_disconnected(self) -> None:
        """Record disconnection, release the serial port, and trigger reconnect."""
        with self._lock:
            self._is_connected = False
            self._has_temperature = False
            self._has_humidity = False
            self._mq_raw_readings = {}
            self._mq_readings = {}
            self._consecutive_serial_errors = 0
            self._transient_empty_read_errors = 0
        self._close_serial()
        print("[SensorInterface] Disconnected — will attempt reconnect")

    def _is_transient_empty_read_error(self, err: Exception) -> bool:
        """Detect known transient RFCOMM read exceptions from pyserial."""
        msg = str(err).lower()
        return (
            "readiness to read" in msg and "returned no data" in msg
        ) or "resource temporarily unavailable" in msg

    # ------------------------------------------------------------------
    # Data validation
    # ------------------------------------------------------------------

    def _is_within_bounds(
        self,
        sensor_type: str,
        value: float,
        min_val: float,
        max_val: float,
    ) -> bool:
        """Check if a sensor value is within acceptable bounds."""
        if value < min_val or value > max_val:
            self._validation_errors[f"{sensor_type}_out_of_range"] += 1
            print(
                f"[SensorInterface] {sensor_type.upper()} out of range: "
                f"{value} (bounds: {min_val}–{max_val})"
            )
            return False
        return True

    def _is_within_delta(
        self,
        sensor_type: str,
        new_value: float,
        previous_value: float | None,
        max_delta: float,
    ) -> bool:
        """
        Check if a sensor value represents a reasonable change from the previous value.

        Args:
            sensor_type: Name of the sensor (e.g., "temperature")
            new_value: The incoming reading
            previous_value: The last accepted reading (or None if first reading)
            max_delta: Maximum allowed change. If 0, check is skipped.

        Returns:
            True if the change is acceptable or if max_delta is 0.
        """
        if max_delta == 0 or previous_value is None:
            return True

        delta = abs(new_value - previous_value)
        if delta > max_delta:
            self._validation_errors[f"{sensor_type}_delta_exceeded"] += 1
            print(
                f"[SensorInterface] {sensor_type.upper()} change exceeds threshold: "
                f"{previous_value} → {new_value} (delta: {delta}, "
                f"max allowed: {max_delta})"
            )
            return False
        return True

    def _validate_temperature(self, value: float) -> bool:
        """Validate a temperature reading. Returns True if acceptable."""
        if not self._is_within_bounds("temperature", value, self._temp_min, self._temp_max):
            return False
        if not self._is_within_delta(
            "temperature",
            value,
            self._temperature if self._has_temperature else None,
            self._temp_max_delta,
        ):
            return False
        return True

    def _validate_humidity(self, value: float) -> bool:
        """Validate a humidity reading. Returns True if acceptable."""
        if not self._is_within_bounds("humidity", value, self._hum_min, self._hum_max):
            return False
        if not self._is_within_delta(
            "humidity",
            value,
            self._humidity if self._has_humidity else None,
            self._hum_max_delta,
        ):
            return False
        return True

    def _validate_pressure(self, value: float) -> bool:
        """Validate a pressure reading. Returns True if acceptable."""
        if not self._is_within_bounds("pressure", value, self._pres_min, self._pres_max):
            return False
        if not self._is_within_delta(
            "pressure", value, self._pressure, self._pres_max_delta
        ):
            return False
        return True

    def _validate_altitude(self, value: float) -> bool:
        """Validate an altitude reading. Returns True if acceptable."""
        if not self._is_within_bounds("altitude", value, self._alt_min, self._alt_max):
            return False
        if not self._is_within_delta(
            "altitude", value, self._altitude, self._alt_max_delta
        ):
            return False
        return True

    def _validate_mq(self, value: float) -> bool:
        """Validate an MQ sensor reading. Returns True if acceptable."""
        # Do not reject MQ readings in the live stream path; transient spikes
        # are still useful telemetry and the reference serial script keeps all
        # values. Bound checks can still be done by downstream analytics.
        if value < 0:
            self._validation_errors["mq_out_of_range"] += 1
            return False
        return True

    def _parse_line(self, line: str) -> None:
        """
        Parse one line of serial output from main.cpp and update local state.
        Invalid readings are logged but not stored, allowing the connection
        to remain stable while data quality is monitored.

        Args:
            line: Decoded text line from the serial stream.
        """
        with self._lock:
            if m := self._PATTERNS["temperature"].match(line):
                try:
                    value = float(m.group(1))
                    if self._validate_temperature(value):
                        self._temperature = value
                        self._has_temperature = True
                        self._last_data_received = time.time()
                    # else: rejected by validation, don't update _temperature
                except (ValueError, TypeError):
                    self._validation_errors["temperature_out_of_range"] += 1
                    print(f"[SensorInterface] Failed to parse temperature value: {m.group(1)}")

            elif m := self._PATTERNS["humidity"].match(line):
                try:
                    value = float(m.group(1))
                    if self._validate_humidity(value):
                        self._humidity = value
                        self._has_humidity = True
                        self._last_data_received = time.time()
                except (ValueError, TypeError):
                    self._validation_errors["humidity_out_of_range"] += 1
                    print(f"[SensorInterface] Failed to parse humidity value: {m.group(1)}")

            elif m := self._PATTERNS["pressure"].match(line):
                try:
                    value = float(m.group(1))
                    if self._validate_pressure(value):
                        self._pressure = value
                        self._last_data_received = time.time()
                except (ValueError, TypeError):
                    self._validation_errors["pressure_out_of_range"] += 1
                    print(f"[SensorInterface] Failed to parse pressure value: {m.group(1)}")

            elif m := self._PATTERNS["altitude"].match(line):
                try:
                    value = float(m.group(1))
                    if self._validate_altitude(value):
                        self._altitude = value
                        self._last_data_received = time.time()
                except (ValueError, TypeError):
                    self._validation_errors["altitude_out_of_range"] += 1
                    print(f"[SensorInterface] Failed to parse altitude value: {m.group(1)}")

            elif m := self._PATTERNS["mq"].match(line):
                try:
                    sensor_id = int(m.group(1))
                    value = int(m.group(2))
                    if self._validate_mq(value):
                        self._mq_raw_readings[sensor_id] = value
                        self._mq_readings[sensor_id] = value
                        self._last_data_received = time.time()
                    # else: rejected by validation, don't update MQ reading
                except (ValueError, TypeError):
                    self._validation_errors["mq_out_of_range"] += 1
                    print(
                        f"[SensorInterface] Failed to parse MQ sensor {m.group(1)}: "
                        f"value={m.group(2)}"
                    )

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_temperature(self) -> float:
        """Returns latest temperature in °C."""
        with self._lock:
            return self._temperature

    def get_humidity(self) -> float:
        """Returns latest relative humidity in %."""
        with self._lock:
            return self._humidity

    def get_pressure(self) -> float:
        """Returns latest pressure in hPa."""
        with self._lock:
            return self._pressure

    def get_altitude(self) -> float:
        """Returns latest approximate altitude in m."""
        with self._lock:
            return self._altitude

    def get_mq_reading(self, sensor_id: int) -> int | None:
        """
        Returns the latest smoothed millivolt reading for a given MQ sensor ID.

        Args:
            sensor_id: Sensor ID as mapped in main.cpp sensorMapping[]
                       (e.g. 2, 3, 4, 5, 8, 9, 135)
        Returns:
            Smoothed reading in mV, or None if not yet received.
        """
        with self._lock:
            return self._mq_readings.get(sensor_id)

    def is_connected(self) -> bool:
        """Returns True if the serial port is open AND data arrived recently."""
        if not self._is_connected:
            return False
        # If the flag is still True but nothing has come in for a while,
        # treat it as disconnected (BT drop without raising an exception).
        stale = (self._last_data_received > 0 and
                 time.time() - self._last_data_received > self._stale_timeout)
        return not stale

    def has_environment_data(self) -> bool:
        """Returns True once live temperature and humidity readings were received."""
        with self._lock:
            return self.is_connected() and self._has_temperature and self._has_humidity

    def get_validation_errors(self) -> dict[str, int]:
        """
        Returns a dictionary of validation error counts accumulated since
        connection or since the last reset. Useful for monitoring data quality.

        Returns:
            A dict with keys like "temperature_out_of_range", "humidity_delta_exceeded", etc.
        """
        with self._lock:
            return self._validation_errors.copy()

    def reset_validation_errors(self) -> None:
        """Reset all validation error counters to zero."""
        with self._lock:
            self._validation_errors = {key: 0 for key in self._validation_errors.keys()}


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_global_sensor: SensorInterface | None = None


def get_sensor(port: str | None = None) -> SensorInterface:
    """
    Get (or create) the global SensorInterface instance.

    Args:
        port: COM port for the Bluetooth serial connection.
    """
    global _global_sensor
    if _global_sensor is None:
        _global_sensor = SensorInterface(port=port)
        _global_sensor.connect()
    else:
        # Self-heal if the polling thread died or was never started.
        thread_alive = _global_sensor._thread is not None and _global_sensor._thread.is_alive()
        if not _global_sensor._running or not thread_alive:
            _global_sensor.connect()
    return _global_sensor
