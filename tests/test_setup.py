#!/usr/bin/env python3
"""Test services.py using direct mocking."""
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Import test helpers
from test_helpers import load_component_module, setup_test_env
setup_test_env()

# Load the module under test
services = load_component_module("services")
register_services = services.register_services
async_service_reset_statistics = services.async_service_reset_statistics

class TestServices(unittest.TestCase):
    """Test the services module."""
    
    def setUp(self):
        """Set up for each test."""
        # Create a mock coordinator
        self.coordinator = MagicMock()
        self.coordinator.hass = MagicMock()
        self.coordinator.hass.services = MagicMock()
        
        # Use a regular MagicMock instead of AsyncMock to avoid coroutine warnings
        self.coordinator.hass.services.async_register = MagicMock()
        
        self.coordinator.weather_manager = MagicMock()
        self.coordinator.weather_manager.async_update_forecast = AsyncMock()
        self.coordinator.absorption_learners = {}
        self.coordinator.zones = {}
        self.coordinator.daily_et = {}
        self.coordinator.daily_precipitation = 0.0
        self.coordinator.async_send_notification = AsyncMock()
    
    # Helper for async tests
    def async_test(coro):
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        return wrapper
    
    @async_test
    async def test_register_services(self):
        """Test registering services."""
        # Call the function under test
        result = await register_services(self.coordinator.hass, self.coordinator)
        
        # Assert results
        self.assertTrue(result)
        # Check that services were registered
        expected_calls = 5  # Total number of services registered
        self.assertEqual(self.coordinator.hass.services.async_register.call_count, expected_calls)


if __name__ == "__main__":
    unittest.main()