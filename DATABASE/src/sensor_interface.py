"""
F.R.E.D. Sensor Interface Template
Placeholder for future sensor integration
"""


class SensorInterface:
    """
    Template for sensor interface.
    Will be implemented when hardware is connected.
    """
    
    def __init__(self):
        """Initialize sensor interface"""
        self._is_connected = False  # Set to True when real hardware is connected
    
    def get_temperature(self) -> float:
        """
        Get current temperature reading.
        
        Returns:
            Temperature in °C (default: 4.0 for fridge temp)
        """
        return 4.0
    
    def get_humidity(self) -> float:
        """
        Get current humidity reading.
        
        Returns:
            Relative humidity in % (default: 50.0)
        """
        return 50.0
    
    def is_connected(self) -> bool:
        """
        Check if physical sensors are connected.
        
        Returns:
            True if real hardware sensors are connected, False if using defaults
        """
        return self._is_connected


# Global sensor instance
_global_sensor = None

def get_sensor() -> SensorInterface:
    """Get the global sensor interface instance"""
    global _global_sensor
    if _global_sensor is None:
        _global_sensor = SensorInterface()
    return _global_sensor
