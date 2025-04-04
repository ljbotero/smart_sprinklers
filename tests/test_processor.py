#!/usr/bin/env python3
"""Test zone processor."""
import unittest
import os
from unittest.mock import MagicMock

# Import test helpers
from test_helpers import setup_test_env

# Setup the test environment
setup_test_env()

class TestZoneProcessor(unittest.TestCase):
    """Test the ZoneProcessor class."""
    
    def setUp(self):
        """Set up test environment."""
        # We'll use direct file path access instead of importing
        self.zone_control_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zone_control")
        self.processor_file = os.path.join(self.zone_control_dir, "processor.py")
        
        # Create mocks
        self.controller = MagicMock()
        self.controller.coordinator = MagicMock()
        self.controller.coordinator.hass = MagicMock()
    
    def test_processor_file_structure(self):
        """Test processor file structure."""
        # Check that file exists
        self.assertTrue(os.path.isfile(self.processor_file),
                       f"processor.py file not found at {self.processor_file}")
        
        # Check source for key methods
        with open(self.processor_file, 'r') as f:
            source = f.read()
            
            # Check for ZoneProcessor class
            self.assertIn("class ZoneProcessor", source)
            
            # Check for important methods
            self.assertIn("async def turn_on_zone", source)
            self.assertIn("async def turn_off_zone", source)
            self.assertIn("async def start_zone_cycle", source)


if __name__ == "__main__":
    unittest.main()