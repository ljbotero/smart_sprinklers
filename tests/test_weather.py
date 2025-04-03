#!/usr/bin/env python3
"""Test weather.py using direct mocking."""
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

# Import the test setup
from test_setup import *

# Import conftest to set up environment
import conftest

# Import the module to test
with patch('smart_sprinklers.weather.fetch_forecast', MagicMock()):
    from smart_sprinklers.weather import WeatherManager

class TestWeather(unittest.TestCase):
    """Test the weather module."""
    
    def setUp(self):
        """Set up for each test."""
        # Create a mock coordinator
        self.coordinator = MagicMock()
        self.coordinator.hass = MagicMock()
        self.coordinator.zones = {
            "zone1": {"name": "Zone 1", "moisture_deficit": 2.0},
            "zone2": {"name": "Zone 2", "moisture_deficit": 3.0}
        }
        self.coordinator.daily_et = {"zone1": 0.0, "zone2": 0.0}
        self.coordinator.daily_precipitation = 0.0
        self.coordinator.freeze_threshold = 36.0
        self.coordinator.async_send_notification = AsyncMock()
        
        # Mock fetch_forecast function
        self.mock_fetch_forecast = MagicMock()
        self.patcher = patch('smart_sprinklers.weather.fetch_forecast', self.mock_fetch_forecast)
        self.patcher.start()
    
    def tearDown(self):
        self.patcher.stop()
    
    # Helper for async tests
    def async_test(coro):
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        return wrapper
    
    def test_init(self):
        """Test initialization of WeatherManager."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        
        # Check initialization
        self.assertEqual(weather_manager.coordinator, self.coordinator)
        self.assertIsNone(weather_manager.weather_entity)
        self.assertIsNone(weather_manager.rain_sensor)
        self.assertGreater(weather_manager.rain_threshold, 0)
        self.assertIsNone(weather_manager.forecast_data)
        self.assertIsNone(weather_manager.last_forecast_update)
        self.assertFalse(weather_manager.forecast_valid)
        self.assertFalse(weather_manager.weather_available)
        self.assertEqual(weather_manager.hass, self.coordinator.hass)
    
    @async_test
    async def test_setup(self):
        """Test setup method."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        
        # Setup test data
        config = {
            "weather_entity": "weather.test_entity",
            "rain_sensor": "sensor.rain",
            "rain_threshold": 5.0
        }
        
        # Setup mock state
        self.coordinator.hass.states.get = MagicMock(return_value=MagicMock())
        
        # Call the method
        await weather_manager.setup(config)
        
        # Check results
        self.assertEqual(weather_manager.weather_entity, "weather.test_entity")
        self.assertEqual(weather_manager.rain_sensor, "sensor.rain")
        self.assertEqual(weather_manager.rain_threshold, 5.0)
        self.assertTrue(weather_manager.weather_available)
    
    @async_test
    async def test_setup_no_weather_entity(self):
        """Test setup with no weather entity."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        
        # Setup test data
        config = {
            "rain_sensor": "sensor.rain",
            "rain_threshold": 5.0
        }
        
        # Call the method
        await weather_manager.setup(config)
        
        # Check results
        self.assertIsNone(weather_manager.weather_entity)
        self.assertEqual(weather_manager.rain_sensor, "sensor.rain")
        self.assertEqual(weather_manager.rain_threshold, 5.0)
        self.assertFalse(weather_manager.weather_available)
    
    @async_test
    async def test_async_update_forecast(self):
        """Test updating forecast data."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        weather_manager.weather_entity = "weather.test_entity"
        
        # Setup mock response
        forecast_data = [{"datetime": "2023-10-01T12:00:00", "temperature": 75, "precipitation": 0}]
        self.mock_fetch_forecast.return_value = forecast_data
        
        # Setup state
        weather_state = MagicMock()
        self.coordinator.hass.states.get = MagicMock(return_value=weather_state)
        
        # Call the method
        await weather_manager.async_update_forecast()
        
        # Check results
        self.mock_fetch_forecast.assert_called_once_with(
            self.coordinator.hass, "weather.test_entity"
        )
        self.assertEqual(weather_manager.forecast_data, forecast_data)
        self.assertIsNotNone(weather_manager.last_forecast_update)
        self.assertTrue(weather_manager.forecast_valid)
        self.assertTrue(weather_manager.weather_available)
    
    @async_test
    async def test_async_update_forecast_no_weather_entity(self):
        """Test updating forecast with no weather entity."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        weather_manager.weather_entity = None
        
        # Call the method
        await weather_manager.async_update_forecast()
        
        # Check results
        self.mock_fetch_forecast.assert_not_called()
        self.assertFalse(weather_manager.forecast_valid)
    
    def test_is_rain_forecasted_no_data(self):
        """Test is_rain_forecasted with no data."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        weather_manager.forecast_valid = False
        
        # Call the method
        result = weather_manager.is_rain_forecasted()
        
        # Check results
        self.assertFalse(result)
    
    def test_is_rain_forecasted_with_rain(self):
        """Test is_rain_forecasted with rain in forecast."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        weather_manager.forecast_valid = True
        weather_manager.weather_available = True
        weather_manager.rain_threshold = 3.0
        
        # Setup forecast data with rain
        now = datetime.now()
        forecast_time = now + timedelta(hours=6)
        weather_manager.forecast_data = [
            {
                "datetime": forecast_time.isoformat(),
                "precipitation": 5.0  # Above threshold
            }
        ]
        
        # Patch datetime.now to return a consistent value
        with patch('homeassistant.util.dt.now', return_value=now), \
             patch('homeassistant.util.dt.parse_datetime', return_value=forecast_time):
            # Call the method
            result = weather_manager.is_rain_forecasted()
            
            # Check results
            self.assertTrue(result)
    
    def test_is_freezing_forecasted_with_freezing(self):
        """Test is_freezing_forecasted with freezing in forecast."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        weather_manager.forecast_valid = True
        weather_manager.weather_available = True
        
        # Setup forecast data with freezing
        now = datetime.now()
        forecast_time = now + timedelta(hours=6)
        weather_manager.forecast_data = [
            {
                "datetime": forecast_time.isoformat(),
                "temperature": 32.0  # Below freeze threshold
            }
        ]
        
        # Create weather state with current temperature
        weather_state = MagicMock()
        weather_state.attributes = {"temperature": 40.0}
        self.coordinator.hass.states.get = MagicMock(return_value=weather_state)
        
        # Patch datetime.now and parse_datetime
        with patch('homeassistant.util.dt.now', return_value=now), \
             patch('homeassistant.util.dt.parse_datetime', return_value=forecast_time):
            # Call the method
            result = weather_manager.is_freezing_forecasted()
            
            # Check results
            self.assertTrue(result)
    
    @async_test
    async def test_async_calculate_et(self):
        """Test calculating evapotranspiration."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        weather_manager.weather_entity = "weather.test_entity"
        weather_manager.weather_available = True
        
        # Setup mock weather state
        weather_state = MagicMock()
        weather_state.attributes = {"temperature": 25.0, "humidity": 50.0}
        self.coordinator.hass.states.get = MagicMock(return_value=weather_state)
        
        # Call the method
        await weather_manager.async_calculate_et()
        
        # Check results - each zone should have a non-zero ET value
        for zone_id, et_value in self.coordinator.daily_et.items():
            self.assertGreater(et_value, 0.0, f"ET value for {zone_id} should be greater than 0")
    
    @async_test
    async def test_async_calculate_precipitation(self):
        """Test calculating precipitation."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        weather_manager.rain_sensor = "sensor.rain"
        
        # Setup mock rain sensor
        rain_state = MagicMock()
        rain_state.state = "2.5"  # 2.5mm of rain
        self.coordinator.hass.states.get = MagicMock(return_value=rain_state)
        
        # Call the method
        await weather_manager.async_calculate_precipitation()
        
        # Check results
        self.assertEqual(self.coordinator.daily_precipitation, 2.5)
    
    @async_test
    async def test_async_daily_update(self):
        """Test daily update of moisture deficit."""
        # Create an instance
        weather_manager = self.WeatherManager(self.coordinator)
        
        # Mock the ET and precipitation calculations
        weather_manager.async_calculate_et = AsyncMock()
        weather_manager.async_calculate_precipitation = AsyncMock()
        
        # Setup test data
        self.coordinator.daily_et = {"zone1": 3.0, "zone2": 4.0}
        self.coordinator.daily_precipitation = 2.0
        
        # Call the method
        await weather_manager.async_daily_update()
        
        # Check results
        weather_manager.async_calculate_et.assert_called_once()
        weather_manager.async_calculate_precipitation.assert_called_once()
        
        # Check moisture deficits were updated
        # Original deficit + ET - precipitation
        self.assertEqual(self.coordinator.zones["zone1"]["moisture_deficit"], 2.0 + 3.0 - 2.0)
        self.assertEqual(self.coordinator.zones["zone2"]["moisture_deficit"], 3.0 + 4.0 - 2.0)
        
        # Check daily counters were reset
        for zone_id, et_value in self.coordinator.daily_et.items():
            self.assertEqual(et_value, 0.0, f"ET for {zone_id} should be reset to 0")
        self.assertEqual(self.coordinator.daily_precipitation, 0.0)


if __name__ == "__main__":
    unittest.main()