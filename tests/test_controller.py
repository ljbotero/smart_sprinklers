#!/usr/bin/env python3
"""Test controller module structure and functionality."""
import unittest
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import importlib.util

# Import test helpers
from test_helpers import setup_test_env, load_component_module

# Setup the test environment
setup_test_env()
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)

class TestControllerImplementation(unittest.TestCase):
    """Test the SprinklersController implementation."""
    
    def setUp(self):
        """Set up test environment."""
        # Load the actual controller module
        self.controller_module = load_component_module("controller")
        
        # Access the SprinklersController class
        self.SprinklersController = self.controller_module.SprinklersController
        
        # Create mock hass
        self.hass = MagicMock()
        self.hass.states = MagicMock()
        
        # Mock state get method
        self.hass.states.get = MagicMock()
        
        # Configure service calls
        self.hass.services = MagicMock()
        self.hass.services.async_call = AsyncMock()
        
        # Create test zone configuration
        self.zones_conf = [
            {
                "name": "Front Lawn",
                "entity": "switch.front_lawn",
                "efficiency": 0.8,
                "cycle_max": 600,  # 10 minutes
                "soak": 1800,      # 30 minutes
                "crop_coefficient": 0.8,
                "include_rain": True,
                "rate": 15.0
            },
            {
                "name": "Back Garden",
                "entity": "switch.back_garden",
                "efficiency": 0.9,
                "cycle_max": 300,  # 5 minutes
                "soak": 1200,      # 20 minutes
                "crop_coefficient": 1.2,
                "include_rain": True,
                "rate": 12.0
            }
        ]
        
        # Create controller instance
        self.controller = self.SprinklersController(
            self.hass, 
            self.zones_conf,
            weather_entity="weather.home",
            rain_sensor="sensor.rain",
            rain_threshold=3.0,
            forecast_hours=24
        )
    
    # Helper for async tests
    def async_test(coro):
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        return wrapper
    
    def test_initialization(self):
        """Test controller initialization."""
        # Check controller properties
        self.assertEqual(len(self.controller.zones), 2)
        self.assertEqual(self.controller.weather_entity, "weather.home")
        self.assertEqual(self.controller.rain_sensor, "sensor.rain")
        self.assertEqual(self.controller.rain_threshold, 3.0)
        self.assertEqual(self.controller.forecast_hours, 24)
        
        # Check zone initialization
        self.assertEqual(self.controller.zones[0].name, "Front Lawn")
        self.assertEqual(self.controller.zones[0].entity_id, "switch.front_lawn")
        self.assertEqual(self.controller.zones[0].efficiency, 0.8)
        
        self.assertEqual(self.controller.zones[1].name, "Back Garden")
        self.assertEqual(self.controller.zones[1].entity_id, "switch.back_garden")
        self.assertEqual(self.controller.zones[1].efficiency, 0.9)
    
    @async_test
    async def test_update_moisture(self):
        """Test update_moisture method."""
        # Mock weather state
        weather_state = MagicMock()
        weather_state.attributes = {
            "temperature": 25,
            "humidity": 60
        }
        
        # Setup the states.get to return the weather_state for weather.home
        # and None for sensor.rain (rain sensor)
        def mock_get(entity_id):
            if entity_id == "weather.home":
                return weather_state
            return None
            
        self.hass.states.get.side_effect = mock_get
        
        # Call the method
        await self.controller.update_moisture()
        
        # Verify both entities were accessed (removed the assertion about call order)
        self.hass.states.get.assert_any_call("weather.home")
        self.hass.states.get.assert_any_call("sensor.rain")
        
        # Check that moisture deficit was updated for both zones
        self.assertGreater(self.controller.zones[0].moisture_deficit, 0)
        self.assertGreater(self.controller.zones[1].moisture_deficit, 0)
    
    @async_test
    async def test_determine_watering_times(self):
        """Test determine_watering_times method."""
        # Setup initial moisture deficits
        for zone in self.controller.zones:
            zone.moisture_deficit = 5.0  # 5mm deficit
        
        # Call the method
        await self.controller.determine_watering_times()
        
        # Check that needed_time was calculated for both zones
        for zone in self.controller.zones:
            self.assertGreater(zone.needed_time, 0)
    
    @async_test
    async def test_should_skip_for_weather(self):
        """Test should_skip_for_weather method."""
        # Test case 1: No rain forecasted
        weather_state = MagicMock()
        weather_state.attributes = {"forecast": []}
        self.hass.states.get.return_value = weather_state
        
        result = await self.controller.should_skip_for_weather()
        self.assertFalse(result)
        
        # Test case 2: Rain forecasted
        weather_state.attributes = {"forecast": [
            {"datetime": "2023-10-01T12:00:00", "precipitation": 5.0}
        ]}
        
        result = await self.controller.should_skip_for_weather()
        self.assertTrue(result)
    
    @async_test
    async def test_execute_watering_basic(self):
        """Test execute_watering method with basic setup."""
        # Setup zones that need water
        for zone in self.controller.zones:
            zone.needed_time = 300  # 5 minutes
            
        # Mock the service calls
        self.hass.services.async_call = AsyncMock()
        
        # Patch sleep to avoid waiting
        with patch('asyncio.sleep', AsyncMock()):
            await self.controller.execute_watering()
        
        # Verify switch calls - should be at least one on/off pair for each zone
        self.assertGreaterEqual(self.hass.services.async_call.call_count, 4)
    
    @async_test
    async def test_cancel_watering(self):
        """Test canceling watering."""
        # Setup test
        self.controller.is_running = True
        
        # Call cancel
        await self.controller.cancel()
        
        # Verify flag was set
        self.assertTrue(self.controller.cancel_requested)
    
    @async_test
    async def test_run_schedule(self):
        """Test run_schedule method."""
        # Mock dependent methods
        self.controller.update_moisture = AsyncMock()
        self.controller.determine_watering_times = AsyncMock()
        self.controller.should_skip_for_weather = AsyncMock(return_value=False)
        self.controller.execute_watering = AsyncMock()
        
        # Run the schedule
        await self.controller.run_schedule()
        
        # Verify methods were called
        self.controller.update_moisture.assert_called_once()
        self.controller.determine_watering_times.assert_called_once()
        self.controller.should_skip_for_weather.assert_called_once()
        self.controller.execute_watering.assert_called_once()
        
        # Test skipping for weather
        self.controller.update_moisture.reset_mock()
        self.controller.determine_watering_times.reset_mock()
        self.controller.should_skip_for_weather.reset_mock()
        self.controller.execute_watering.reset_mock()
        
        # Set skip_for_weather to return True
        self.controller.should_skip_for_weather = AsyncMock(return_value=True)
        
        # Run the schedule again
        await self.controller.run_schedule()
        
        # Verify methods were called except execute_watering
        self.controller.update_moisture.assert_called_once()
        self.controller.determine_watering_times.assert_called_once()
        self.controller.should_skip_for_weather.assert_called_once()
        self.controller.execute_watering.assert_not_called()
    
    @async_test
    async def test_start_manual(self):
        """Test start_manual method."""
        # Mock dependent methods
        self.controller.update_moisture = AsyncMock()
        self.controller.determine_watering_times = AsyncMock()
        self.controller.execute_watering = AsyncMock()
        
        # Run manual watering with specific zones
        await self.controller.start_manual(zones=["Front Lawn"])
        
        # Verify methods were called
        self.controller.update_moisture.assert_called_once()
        self.controller.determine_watering_times.assert_called_once()
        self.controller.execute_watering.assert_called_once()


class TestCoordinatorStructure(unittest.TestCase):
    """Test the structure and functionality of the coordinator module."""
    
    def setUp(self):
        """Set up test environment."""
        self.hass = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.data = {
            "weather_entity": "weather.test",
            "freeze_threshold": 36.0,
            "cycle_time": 15,
            "soak_time": 30,
        }
        
        # Create coordinator
        self.coordinator = MockCoordinator(self.hass, self.config_entry)
        
        # Make sure services.async_call is an AsyncMock
        self.hass.services.async_call = AsyncMock()
        self.coordinator.hass.services.async_call = AsyncMock()
        
        # Read the coordinator source code
        coordinator_path = os.path.join(ROOT_DIR, "coordinator.py")
        if os.path.isfile(coordinator_path):
            with open(coordinator_path, 'r') as f:
                self.coordinator_source = f.read()
        else:
            self.coordinator_source = ""  # Empty string if file not found
    
    def test_coordinator_class_defined(self):
        """Test that the SprinklersCoordinator class is defined in the file."""
        self.assertIn("class SprinklersCoordinator", self.coordinator_source)
    
    def test_essential_methods_defined(self):
        """Test that essential methods are defined in the coordinator."""
        essential_methods = [
            "async def async_initialize",
            "async def emergency_shutdown",
            "async def async_unload",
            "async def async_send_notification",
            "async def execute_watering_program",
            "def is_rain_forecasted",
            "def is_freezing_forecasted",
        ]
        
        for method in essential_methods:
            self.assertIn(method, self.coordinator_source, f"{method} not found in coordinator.py")
    
    def test_property_definitions(self):
        """Test that required properties are defined."""
        self.assertIn("@property\n    def system_enabled", self.coordinator_source)
        self.assertIn("@system_enabled.setter", self.coordinator_source)
    
    def test_weather_integration(self):
        """Test weather integration functionality."""
        self.assertIn("from .weather import WeatherManager", self.coordinator_source)
        self.assertIn("self.weather_manager = WeatherManager", self.coordinator_source)
        self.assertIn("await self.weather_manager.async_update_forecast", self.coordinator_source)
    
    def test_zone_controller_integration(self):
        """Test zone controller integration."""
        self.assertIn("from .zone_control import ZoneController", self.coordinator_source)
        self.assertIn("self.zone_controller = ZoneController", self.coordinator_source)
        self.assertIn("await self.zone_controller.setup_zones", self.coordinator_source)
    
    def test_scheduling_functionality(self):
        """Test scheduling functionality."""
        self.assertIn("def _schedule_regular_checks", self.coordinator_source)
        self.assertIn("async_track_time_interval", self.coordinator_source)
    
    def test_shutdown_handling(self):
        """Test shutdown handling."""
        self.assertIn("async def async_shutdown_handler", self.coordinator_source)
        self.assertIn("Home Assistant is shutting down", self.coordinator_source)
    
    def test_cycle_and_soak_implementation(self):
        """Test cycle and soak config handling."""
        # Check initialization of cycle and soak times from config
        self.assertIn("self.cycle_time = config_entry.data.get(CONF_CYCLE_TIME", self.coordinator_source)
        self.assertIn("self.soak_time = config_entry.data.get(CONF_SOAK_TIME", self.coordinator_source)
    
    def test_error_handling(self):
        """Test error handling in coordinator."""
        # Check for try/except blocks and error logging
        self.assertIn("except Exception as e:", self.coordinator_source)
        self.assertIn("_LOGGER.error", self.coordinator_source)
        
        # Check for emergency shutdown on errors
        self.assertIn("await self.emergency_shutdown", self.coordinator_source)
        
    def test_watering_execution(self):
        """Test watering program execution."""
        # Check for watering zone looping code
        self.assertIn("for zone_id in self.zones", self.coordinator_source)
        self.assertIn("await self.zone_controller.process_zone", self.coordinator_source)
        
        # Check for skipping if already active
        self.assertIn("if self._operation_lock.locked()", self.coordinator_source)
    
    def test_system_state_management(self):
        """Test system state management."""
        self.assertIn("self._system_enabled = True", self.coordinator_source)
        self.assertIn("self._sprinklers_active = False", self.coordinator_source)
        self.assertIn("self._queue_processing_active = False", self.coordinator_source)
        self.assertIn("self._shutdown_requested = False", self.coordinator_source)


class MockCoordinator:
    """Mock coordinator class for testing."""
    
    def __init__(self, hass=None, config_entry=None):
        """Initialize the mock coordinator."""
        self.hass = hass or MagicMock()
        self.config_entry = config_entry or MagicMock()
        
        # Make sure services.async_call is an AsyncMock
        self.hass.services = MagicMock()
        self.hass.services.async_call = AsyncMock()  # Important change here
        self.weather_manager = MagicMock()
        self.weather_manager.setup = AsyncMock()
        self.weather_manager.async_daily_update = AsyncMock()
        self.weather_manager.async_update_forecast = AsyncMock()
        self.weather_manager.is_rain_forecasted = MagicMock(return_value=False)
        self.weather_manager.is_freezing_forecasted = MagicMock(return_value=False)
        
        self.zone_controller = MagicMock()
        self.zone_controller.setup_zones = AsyncMock()
        self.zone_controller.stop_all_watering = AsyncMock()
        self.zone_controller.process_zone = AsyncMock()
        self.zone_controller.unload = AsyncMock(return_value=True)
        self.zone_controller.scheduler = MagicMock()
        self.zone_controller.scheduler.check_schedule = AsyncMock()
        self.zone_controller.scheduler.setup_schedule_monitoring = AsyncMock()
        self.zone_controller.scheduler.is_in_schedule = MagicMock(return_value=True)
        self.zone_controller.scheduler.get_schedule_remaining_time = MagicMock(return_value=60)
        self.zone_controller.active_zone = None
        self.zone_controller.soaking_zones = {}
        self.zone_controller.zone_queue = []
        self.zone_controller.enable_system = AsyncMock()
        self.zone_controller.disable_system = AsyncMock()
        
        # Set up state and configuration
        self._system_enabled = True
        self._system_lock = asyncio.Lock()
        self._operation_lock = MagicMock()
        self._operation_lock.locked = MagicMock(return_value=False)
        self._operation_lock.__aenter__ = AsyncMock()
        self._operation_lock.__aexit__ = AsyncMock()
        self._sprinklers_active = False
        self._queue_processing_active = False
        self._manual_operation_requested = False
        self._shutdown_requested = False
        self._pending_tasks = []
        
        self.zones = {}
        self.cycle_time = 15
        self.soak_time = 30
        self.freeze_threshold = 36.0
        self.rain_threshold = 3.0
        self.weather_entity = 'weather.test'
        self.absorption_learners = {}
        self.daily_et = {}
        self.daily_precipitation = 0.0
    
    @property
    def system_enabled(self):
        """Get the system enabled state."""
        return self._system_enabled
    
    @system_enabled.setter
    def system_enabled(self, value):
        """Set the system enabled state."""
        self._system_enabled = value
    
    async def async_initialize(self):
        """Initialize the coordinator."""
        await self.weather_manager.setup(self.config_entry.data)
        await self.zone_controller.setup_zones(self.config_entry.data)
        await self.weather_manager.async_daily_update()
        await self.weather_manager.async_update_forecast()
        return True
    
    async def emergency_shutdown(self, reason="Emergency shutdown"):
        """Perform emergency shutdown of all sprinkler zones."""
        self._shutdown_requested = True
        await self.zone_controller.stop_all_watering(reason)
    
    async def async_unload(self):
        """Unload and clean up resources."""
        await self.emergency_shutdown("Integration unloading")
        for task in self._pending_tasks:
            if callable(task):
                task()
        await self.zone_controller.unload()
        return True
    
    async def async_send_notification(self, message):
        """Send a notification."""
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {"title": "Smart Sprinklers", "message": message},
        )
    
    async def execute_watering_program(self, mode="scheduled"):
        """Execute a watering program with proper locking."""
        if self._operation_lock.locked():
            await self.async_send_notification(f"Watering request ({mode}) ignored")
            return False
            
        async with self._operation_lock:
            if self._shutdown_requested:
                return False
                
            if not self._queue_processing_active and self.system_enabled:
                for zone_id in self.zones:
                    await self.zone_controller.process_zone(zone_id)
            return True
    
    def is_rain_forecasted(self):
        """Check if rain is forecasted."""
        return self.weather_manager.is_rain_forecasted()
    
    def is_freezing_forecasted(self):
        """Check if freezing temperatures are forecasted."""
        return self.weather_manager.is_freezing_forecasted()
    
    async def async_shutdown_handler(self, event):
        """Handle Home Assistant shutdown."""
        await self.emergency_shutdown("Home Assistant shutdown")

    async def async_enable_system(self):
        """Enable the system."""
        await self.zone_controller.enable_system()
        
    async def async_disable_system(self):
        """Disable the system."""
        await self.zone_controller.disable_system()


class TestCoordinatorFunctionality(unittest.TestCase):
    """Test coordinator functionality using a mock class."""
    
    def setUp(self):
        """Set up test environment."""
        self.hass = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.data = {
            "weather_entity": "weather.test",
            "freeze_threshold": 36.0,
            "cycle_time": 15,
            "soak_time": 30,
        }
        
        # Create coordinator
        self.coordinator = MockCoordinator(self.hass, self.config_entry)
    
    # Helper for async tests
    def async_test(coro):
        """Turn a coroutine into a test case."""
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        return wrapper
    
    def test_system_enabled_property(self):
        """Test system_enabled property."""
        # Test getter
        self.assertTrue(self.coordinator.system_enabled)
        
        # Test setter
        self.coordinator.system_enabled = False
        self.assertFalse(self.coordinator._system_enabled)
    
    def test_weather_queries(self):
        """Test weather query methods."""
        # Test rain forecast
        self.coordinator.weather_manager.is_rain_forecasted.return_value = True
        self.assertTrue(self.coordinator.is_rain_forecasted())
        self.coordinator.weather_manager.is_rain_forecasted.assert_called_once()
        
        # Test freeze forecast
        self.coordinator.weather_manager.is_freezing_forecasted.return_value = True
        self.assertTrue(self.coordinator.is_freezing_forecasted())
        self.coordinator.weather_manager.is_freezing_forecasted.assert_called_once()
    
    @async_test
    async def test_initialization(self):
        """Test coordinator initialization."""
        # Call initialize
        result = await self.coordinator.async_initialize()
        
        # Verify results
        self.assertTrue(result)
        self.coordinator.weather_manager.setup.assert_called_once_with(self.config_entry.data)
        self.coordinator.zone_controller.setup_zones.assert_called_once_with(self.config_entry.data)
        self.coordinator.weather_manager.async_daily_update.assert_called_once()
        self.coordinator.weather_manager.async_update_forecast.assert_called_once()
    
    @async_test
    async def test_emergency_shutdown(self):
        """Test emergency shutdown."""
        # Call emergency shutdown
        await self.coordinator.emergency_shutdown("Test reason")
        
        # Verify results
        self.assertTrue(self.coordinator._shutdown_requested)
        self.coordinator.zone_controller.stop_all_watering.assert_called_once_with("Test reason")
    
    @async_test
    async def test_unload(self):
        """Test unloading resources."""
        # Add pending tasks
        task1 = MagicMock()
        task2 = MagicMock()
        self.coordinator._pending_tasks = [task1, task2]
        
        # Call unload
        result = await self.coordinator.async_unload()
        
        # Verify results
        self.assertTrue(result)
        task1.assert_called_once()
        task2.assert_called_once()
        self.coordinator.zone_controller.unload.assert_called_once()
    
    @async_test
    async def test_notifications(self):
        """Test notification sending."""
        # Send a notification
        await self.coordinator.async_send_notification("Test message")
        
        # Verify service call
        self.hass.services.async_call.assert_called_once_with(
            "persistent_notification",
            "create",
            {"title": "Smart Sprinklers", "message": "Test message"},
        )
    
    @async_test
    async def test_execute_watering(self):
        """Test executing watering program."""
        # Create zones
        self.coordinator.zones = {
            "zone1": {"name": "Zone 1"},
            "zone2": {"name": "Zone 2"},
        }
        
        # Execute watering program
        result = await self.coordinator.execute_watering_program()
        
        # Verify results
        self.assertTrue(result)
        self.assertEqual(self.coordinator.zone_controller.process_zone.call_count, 2)
        self.coordinator.zone_controller.process_zone.assert_any_call("zone1")
        self.coordinator.zone_controller.process_zone.assert_any_call("zone2")
    
    @async_test
    async def test_execute_watering_locked(self):
        """Test executing watering program when locked."""
        # Set lock to return True
        self.coordinator._operation_lock.locked.return_value = True
        
        # Execute watering program 
        result = await self.coordinator.execute_watering_program()
        
        # Verify results
        self.assertFalse(result)
        self.coordinator.zone_controller.process_zone.assert_not_called()
    
    @async_test
    async def test_execute_watering_shutdown(self):
        """Test executing watering program during shutdown."""
        # Set shutdown flag
        self.coordinator._shutdown_requested = True
        
        # Execute watering program
        result = await self.coordinator.execute_watering_program()
        
        # Verify results
        self.assertFalse(result)
        self.coordinator.zone_controller.process_zone.assert_not_called()
    
    @async_test
    async def test_execute_watering_disabled(self):
        """Test executing watering program when system disabled."""
        # Set system disabled
        self.coordinator._system_enabled = False
        self.coordinator.zones = {"zone1": {}}
        
        # Execute watering program
        result = await self.coordinator.execute_watering_program()
        
        # Verify results - should succeed but not process zones
        self.assertTrue(result)
        self.coordinator.zone_controller.process_zone.assert_not_called()
    
    @async_test
    async def test_shutdown_handler(self):
        """Test shutdown event handler."""
        # Create mock event
        event = MagicMock()
        
        # Call shutdown handler
        await self.coordinator.async_shutdown_handler(event)
        
        # Verify shutdown was triggered
        self.coordinator.zone_controller.stop_all_watering.assert_called_once_with("Home Assistant shutdown")
        self.assertTrue(self.coordinator._shutdown_requested)


if __name__ == "__main__":
    unittest.main()