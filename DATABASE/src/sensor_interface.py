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

    def __init__(self, port: str | None = None, baudrate: int = 115200):
        """
        Initialize sensor interface.

        Args:
            port:     Preferred COM port (hint only — all available ports are
                      swept if this one fails or is None).
            baudrate: Must match BluetoothSerial – typically ignored for BT but
                      kept for compatibility when switching to wired UART.
        """
        env_port = os.environ.get("SENSOR_PORT")
        self._preferred_port = env_port if env_port else port
        self._baudrate = baudrate
        self._is_connected = False
        self._serial: serial.Serial | None = None
        self._serial_timeout = max(0.05, self._env_float('SENSOR_SERIAL_TIMEOUT', 10.0))
        self._stale_timeout = max(2.0, self._env_float('SENSOR_STALE_TIMEOUT', self._STALE_TIMEOUT))
        self._max_consecutive_serial_errors = max(
            1,
            self._env_int('SENSOR_MAX_CONSECUTIVE_SERIAL_ERRORS', 3)
        )
        self._consecutive_serial_errors = 0

        # Latest sensor readings
        self._temperature: float = 4.0
        self._humidity: float = 50.0
        self._pressure: float = 1013.25
        self._altitude: float = 0.0
        self._mq_readings: dict[int, int] = {}
        self._mq_raw_readings: dict[int, int] = {}
        self._has_temperature = False
        self._has_humidity = False

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
    # Exponential moving average smoothing factor for MQ sensors.
    # Lower values reduce noise more aggressively, higher values react faster.
    _MQ_EMA_ALPHA: float = 0.2

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
        if self._preferred_port in available:
            available.remove(self._preferred_port)
            return [self._preferred_port] + available
        # Preferred not yet listed (e.g. BT pairing still in progress) — try anyway
        return [self._preferred_port] + available

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
            ser = serial.Serial(port, self._baudrate, timeout=self._serial_timeout)
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

        # Flush any bytes that accumulated in the input buffer during the settle
        # delay.  Those bytes are stale BT serial buffer data from before this
        # connection was opened.  Counting them as "valid lines" would cause a
        # false-positive probe on a dead link — the first _read_line() would then
        # immediately raise a SerialException and trigger a re-sweep.
        try:
            ser.reset_input_buffer()
        except Exception:
            pass

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
                # readline() timed out (1 s configured on port open)
                if (self._last_data_received > 0 and
                        time.time() - self._last_data_received > self._stale_timeout):
                    print(f"[SensorInterface] No data for {self._stale_timeout}s "
                          "— disconnecting")
                    self._mark_disconnected()
                return
            line = raw.decode('utf-8', errors='ignore').strip()
            self._consecutive_serial_errors = 0
            self._parse_line(line)
        except (serial.SerialException, OSError, PermissionError) as e:
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
        self._close_serial()
        print("[SensorInterface] Disconnected — will attempt reconnect")

    def _parse_line(self, line: str) -> None:
        """
        Parse one line of serial output from main.cpp and update local state.

        Args:
            line: Decoded text line from the serial stream.
        """
        with self._lock:
            if m := self._PATTERNS["temperature"].match(line):
                self._temperature = float(m.group(1))
                self._has_temperature = True
                self._last_data_received = time.time()
            elif m := self._PATTERNS["humidity"].match(line):
                self._humidity = float(m.group(1))
                self._has_humidity = True
                self._last_data_received = time.time()
            elif m := self._PATTERNS["pressure"].match(line):
                self._pressure = float(m.group(1))
                self._last_data_received = time.time()
            elif m := self._PATTERNS["altitude"].match(line):
                self._altitude = float(m.group(1))
                self._last_data_received = time.time()
            elif m := self._PATTERNS["mq"].match(line):
                sensor_id = int(m.group(1))
                value = int(m.group(2))
                self._mq_raw_readings[sensor_id] = value
                previous = self._mq_readings.get(sensor_id)
                if previous is None:
                    filtered = value
                else:
                    filtered = round(
                        self._MQ_EMA_ALPHA * value +
                        (1 - self._MQ_EMA_ALPHA) * previous
                    )
                self._mq_readings[sensor_id] = filtered
                self._last_data_received = time.time()

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
