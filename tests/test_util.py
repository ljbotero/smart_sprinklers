#!/usr/bin/env python3
"""Test util.py using direct mocking."""
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Import test helpers
from test_helpers import load_component_module, setup_test_env
setup_test_env()

# Load the module under test
util = load_component_module("util")
fetch_forecast = util.fetch_forecast

class TestUtil(unittest.TestCase):
    """Test the utility functions."""
    
    # Helper for async tests
    def async_test(coro):
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        return wrapper
    
    @async_test
    async def test_fetch_forecast_success(self):
        """Test successful forecast fetch."""
        # Setup mock Home Assistant
        hass = MagicMock()
        forecast_data = [{'datetime': '2023-10-01T12:00:00', 'temperature': 25, 'precipitation': 0}]
        
        # Setup the async_call response
        service_response = {'weather.test_entity': {'forecast': forecast_data}}
        hass.services.async_call = AsyncMock(return_value=service_response)
        
        # Call the function under test
        result = await fetch_forecast(hass, 'weather.test_entity')
        
        # Verify results
        hass.services.async_call.assert_called_once()
        self.assertEqual(result, forecast_data)
    
    @async_test
    async def test_fetch_forecast_no_data(self):
        """Test when no forecast data is returned."""
        hass = MagicMock()
        hass.services.async_call = AsyncMock(return_value={})
        
        result = await fetch_forecast(hass, 'weather.test_entity')
        self.assertEqual(result, [])
    
    @async_test
    async def test_fetch_forecast_exception(self):
        """Test handling exceptions during forecast fetch."""
        hass = MagicMock()
        hass.services.async_call = AsyncMock(side_effect=Exception("Service call failed"))
        
        result = await fetch_forecast(hass, 'weather.test_entity')
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()