#!/usr/bin/env python3
"""Test switch.py using direct mocking."""
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Import test helpers
from test_helpers import load_component_module, setup_test_env
setup_test_env()

# Load the module under test
switch_module = load_component_module("switch")
SystemEnableSwitch = switch_module.SystemEnableSwitch

class TestSwitch(unittest.TestCase):
    """Test the switch module."""
    
    def setUp(self):
        """Set up for each test."""
        # Create a mock coordinator
        self.coordinator = MagicMock()
        self.coordinator.system_enabled = True
        self.coordinator.async_enable_system = AsyncMock()
        self.coordinator.async_disable_system = AsyncMock()
    
    # Helper for async tests
    def async_test(coro):
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        return wrapper
    
    def test_init(self):
        """Test initialization of SystemEnableSwitch."""
        # Create an instance of the switch
        switch = SystemEnableSwitch(self.coordinator)
        
        # Check initialization
        self.assertEqual(switch.coordinator, self.coordinator)
        self.assertEqual(switch._attr_name, "Smart Sprinklers System")
        
    def test_is_on(self):
        """Test the is_on property."""
        # Create an instance of the switch
        switch = SystemEnableSwitch(self.coordinator)
        
        # Test when system is enabled
        self.coordinator.system_enabled = True
        self.assertTrue(switch.is_on)
        
        # Test when system is disabled
        self.coordinator.system_enabled = False
        self.assertFalse(switch.is_on)


if __name__ == "__main__":
    unittest.main()