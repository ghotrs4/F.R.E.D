"""
F.R.E.D. Sensor Interface
Parses and stores current environmental sensor data (BME280)
"""

import re
from datetime import datetime
from typing import Optional, Dict


class SensorData:
    """Stores current sensor readings"""
    def __init__(self):
        self.temperature = 4.0      # °C
        self.pressure = 1013.25     # hPa
        self.altitude = 0.0         # m
        self.humidity = 50.0        # %
        self.last_update = None     # datetime of last reading
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'temperature': self.temperature,
            'pressure': self.pressure,
            'altitude': self.altitude,
            'humidity': self.humidity,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }


class SensorInterface:
    """
    Interface for reading and parsing BME280 sensor data.
    Maintains current environmental readings.
    """
    
    def __init__(self):
        self.current_data = SensorData()
    
    def parse_sensor_output(self, sensor_string: str) -> bool:
        """
        Parse sensor output string and update current readings.
        
        Args:
            sensor_string: Raw sensor output (e.g., from serial port or Arduino)
            
        Example input:
            Temperature = 19.11 °C
            Pressure = 1001.48 hPa
            Approx. Altitude = 98.48 m
            Humidity = 42.86 %
            
        Returns:
            True if successfully parsed, False otherwise
        """
        try:
            # Parse temperature (match number before °C)
            temp_match = re.search(r'Temperature\s*=\s*([\d.]+)\s*°C', sensor_string)
            if temp_match:
                self.current_data.temperature = float(temp_match.group(1))
            
            # Parse pressure (match number before hPa)
            pressure_match = re.search(r'Pressure\s*=\s*([\d.]+)\s*hPa', sensor_string)
            if pressure_match:
                self.current_data.pressure = float(pressure_match.group(1))
            
            # Parse altitude (match number before m)
            altitude_match = re.search(r'Altitude\s*=\s*([\d.]+)\s*m', sensor_string)
            if altitude_match:
                self.current_data.altitude = float(altitude_match.group(1))
            
            # Parse humidity (match number before %)
            humidity_match = re.search(r'Humidity\s*=\s*([\d.]+)\s*%', sensor_string)
            if humidity_match:
                self.current_data.humidity = float(humidity_match.group(1))
            
            # Update timestamp
            self.current_data.last_update = datetime.now()
            
            return True
            
        except Exception as e:
            print(f"Error parsing sensor data: {e}")
            return False
    
    def update_from_values(self, temperature: float, humidity: float, 
                          pressure: Optional[float] = None, 
                          altitude: Optional[float] = None):
        """
        Directly update sensor readings with values.
        
        Args:
            temperature: Temperature in °C
            humidity: Relative humidity in %
            pressure: Atmospheric pressure in hPa (optional)
            altitude: Altitude in meters (optional)
        """
        self.current_data.temperature = temperature
        self.current_data.humidity = humidity
        
        if pressure is not None:
            self.current_data.pressure = pressure
        if altitude is not None:
            self.current_data.altitude = altitude
        
        self.current_data.last_update = datetime.now()
    
    def get_temperature(self) -> float:
        """Get current temperature in °C"""
        return self.current_data.temperature
    
    def get_humidity(self) -> float:
        """Get current humidity in %"""
        return self.current_data.humidity
    
    def get_pressure(self) -> float:
        """Get current pressure in hPa"""
        return self.current_data.pressure
    
    def get_altitude(self) -> float:
        """Get current altitude in m"""
        return self.current_data.altitude
    
    def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last sensor update"""
        return self.current_data.last_update
    
    def get_all_readings(self) -> Dict:
        """Get all current sensor readings as dictionary"""
        return self.current_data.to_dict()
    
    def is_data_fresh(self, max_age_seconds: int = 60) -> bool:
        """
        Check if sensor data is recent.
        
        Args:
            max_age_seconds: Maximum age in seconds to consider data fresh
            
        Returns:
            True if data is fresh, False if stale or never updated
        """
        if self.current_data.last_update is None:
            return False
        
        age = (datetime.now() - self.current_data.last_update).total_seconds()
        return age <= max_age_seconds


# Global sensor instance (singleton pattern)
# This allows any part of the code to access current sensor readings
_global_sensor = None

def get_sensor() -> SensorInterface:
    """Get the global sensor interface instance"""
    global _global_sensor
    if _global_sensor is None:
        _global_sensor = SensorInterface()
    return _global_sensor


# Example usage
if __name__ == "__main__":
    # Create sensor interface
    sensor = SensorInterface()
    
    # Example 1: Parse sensor output string
    sensor_output = """
    Temperature = 19.11 °C
    Pressure = 1001.48 hPa
    Approx. Altitude = 98.48 m
    Humidity = 42.86 %
    """
    
    if sensor.parse_sensor_output(sensor_output):
        print("✓ Sensor data parsed successfully")
        print(f"Temperature: {sensor.get_temperature()}°C")
        print(f"Humidity: {sensor.get_humidity()}%")
        print(f"Pressure: {sensor.get_pressure()} hPa")
        print(f"Altitude: {sensor.get_altitude()} m")
    
    print("\n" + "="*50 + "\n")
    
    # Example 2: Direct value update
    sensor.update_from_values(temperature=4.5, humidity=55.0)
    print("✓ Sensor updated with direct values")
    print(f"Temperature: {sensor.get_temperature()}°C")
    print(f"Humidity: {sensor.get_humidity()}%")
    
    print("\n" + "="*50 + "\n")
    
    # Example 3: Get all readings
    all_data = sensor.get_all_readings()
    print("All sensor readings:")
    for key, value in all_data.items():
        print(f"  {key}: {value}")
    
    print("\n" + "="*50 + "\n")
    
    # Example 4: Check if data is fresh
    if sensor.is_data_fresh(max_age_seconds=60):
        print("✓ Sensor data is fresh (< 60 seconds old)")
    else:
        print("⚠ Sensor data is stale")
