#!/usr/bin/env python3
"""Test services.py without RuntimeWarnings."""
import unittest
import asyncio
from unittest.mock import MagicMock, patch

# Import test helpers
from test_helpers import load_component_module, setup_test_env
setup_test_env()

class TestServices(unittest.TestCase):
    """Test the services module."""
    
    def setUp(self):
        """Set up for each test."""
        # Load the module
        self.services = load_component_module("services")
        
        # Create a mock coordinator
        self.coordinator = MagicMock()
        self.coordinator.hass = MagicMock()
        self.coordinator.hass.services = MagicMock()
        
        # Use regular MagicMock for async_register
        self.coordinator.hass.services.async_register = MagicMock()
        
        self.coordinator.weather_manager = MagicMock()
        self.coordinator.absorption_learners = {}
        self.coordinator.zones = {}
        self.coordinator.daily_et = {}
        self.coordinator.daily_precipitation = 0.0
    
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
        with patch.object(self.services, 'register_services', wraps=self.services.register_services):
            result = await self.services.register_services(self.coordinator.hass, self.coordinator)
            
            # Assert results
            self.assertTrue(result)
            
            # Verify services were registered
            self.assertTrue(self.coordinator.hass.services.async_register.called)
            
            # Should register at least these main services 
            expected_minimum_calls = 2  # refresh_forecast and reset_statistics at minimum
            self.assertGreaterEqual(self.coordinator.hass.services.async_register.call_count, 
                                   expected_minimum_calls)


if __name__ == "__main__":
    unittest.main()