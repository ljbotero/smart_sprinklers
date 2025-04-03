#!/usr/bin/env python3
"""Test weather.py using direct testing."""
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Import test helpers
from test_helpers import setup_test_env, load_component_module

# Setup the test environment
setup_test_env()

class TestWeatherFunctions(unittest.TestCase):
    """Test basic weather module functionality."""
    
    def setUp(self):
        """Set up test environment."""
        # Load the module
        self.weather = load_component_module("weather")
        
        # Create mocks
        self.coordinator = MagicMock()
        self.coordinator.hass = MagicMock()
        self.coordinator.freeze_threshold = 36.0
        self.coordinator.async_send_notification = MagicMock()
    
    def test_weather_module_structure(self):
        """Test the structure of the weather module."""
        # Check that WeatherManager class exists
        self.assertTrue(hasattr(self.weather, "WeatherManager"))
        
        # Check source for key methods
        with open(self.weather.__file__, 'r') as f:
            source = f.read()
            
            # Check for important methods
            self.assertIn("def is_rain_forecasted", source)
            self.assertIn("def is_freezing_forecasted", source)
            self.assertIn("async def async_update_forecast", source)
            self.assertIn("async def async_calculate_et", source)
    
    def test_weather_manager_initialization(self):
        """Test WeatherManager initialization."""
        # Create a basic instance
        weather_manager = self.weather.WeatherManager(self.coordinator)
        
        # Check initial properties
        self.assertEqual(weather_manager.coordinator, self.coordinator)
        self.assertIsNone(weather_manager.weather_entity)
        self.assertIsNone(weather_manager.rain_sensor)
        self.assertIsNotNone(weather_manager.rain_threshold)
        self.assertFalse(weather_manager.forecast_valid)
    
    # Helper for async tests
    def async_test(coro):
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        return wrapper
    
    @async_test
    async def test_forecast_with_empty_data(self):
        """Test forecast handling with empty data."""
        weather_manager = self.weather.WeatherManager(self.coordinator)
        
        # Test with empty forecast data
        weather_manager.forecast_data = []
        weather_manager.forecast_valid = False
        
        # This should not raise exceptions
        result = weather_manager.is_rain_forecasted()
        self.assertFalse(result)
        
        result = weather_manager.is_freezing_forecasted()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()