"""
F.R.E.D. Sensor Interface
Reads serial data from ESP32 over Bluetooth (BluetoothSerial / RFCOMM)
"""

import re
import threading
import serial  # pyserial


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

    def __init__(self, port: str = "COM3", baudrate: int = 115200):
        """
        Initialize sensor interface.

        Args:
            port:     COM port of the paired Bluetooth device (e.g. 'COM3' on Windows)
            baudrate: Must match BluetoothSerial – typically ignored for BT but kept
                      for compatibility when switching to wired UART.
        """
        self._port = port
        self._baudrate = baudrate
        self._is_connected = False
        self._serial: serial.Serial | None = None

        # Latest sensor readings
        self._temperature: float = 4.0
        self._humidity: float = 50.0
        self._pressure: float = 1013.25
        self._altitude: float = 0.0
        self._mq_readings: dict[int, int] = {}

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Open the serial port and start the background reader thread.

        Returns:
            True if connection succeeded, False otherwise.
        """
        try:
            self._serial = serial.Serial(self._port, self._baudrate, timeout=1)
            self._is_connected = True
            self._running = True
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            return True
        except serial.SerialException as e:
            print(f"[SensorInterface] Failed to connect on {self._port}: {e}")
            self._is_connected = False
            return False

    def disconnect(self) -> None:
        """Stop the reader thread and close the serial port."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._is_connected = False

    # ------------------------------------------------------------------
    # Background reader
    # ------------------------------------------------------------------

    def _read_loop(self) -> None:
        """Continuously read lines from serial and parse them."""
        while self._running and self._serial and self._serial.is_open:
            try:
                raw = self._serial.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                self._parse_line(line)
            except serial.SerialException as e:
                print(f"[SensorInterface] Serial error: {e}")
                self._is_connected = False
                break

    def _parse_line(self, line: str) -> None:
        """
        Parse one line of serial output from main.cpp and update local state.

        Args:
            line: Decoded text line from the serial stream.
        """
        with self._lock:
            if m := self._PATTERNS["temperature"].match(line):
                self._temperature = float(m.group(1))

            elif m := self._PATTERNS["humidity"].match(line):
                self._humidity = float(m.group(1))

            elif m := self._PATTERNS["pressure"].match(line):
                self._pressure = float(m.group(1))

            elif m := self._PATTERNS["altitude"].match(line):
                self._altitude = float(m.group(1))

            elif m := self._PATTERNS["mq"].match(line):
                sensor_id = int(m.group(1))
                value = int(m.group(2))
                self._mq_readings[sensor_id] = value

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
        Returns the latest millivolt reading for a given MQ sensor ID.

        Args:
            sensor_id: Sensor ID as mapped in main.cpp sensorMapping[]
                       (e.g. 2, 3, 4, 5, 8, 9, 135)
        Returns:
            Reading in mV, or None if not yet received.
        """
        with self._lock:
            return self._mq_readings.get(sensor_id)

    def is_connected(self) -> bool:
        """Returns True if the serial port is open and receiving data."""
        return self._is_connected


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_global_sensor: SensorInterface | None = None


def get_sensor(port: str = "COM3") -> SensorInterface:
    """
    Get (or create) the global SensorInterface instance.

    Args:
        port: COM port for the Bluetooth serial connection.
    """
    global _global_sensor
    if _global_sensor is None:
        _global_sensor = SensorInterface(port=port)
        _global_sensor.connect()
    return _global_sensor
