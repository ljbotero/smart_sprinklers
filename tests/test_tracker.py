#!/usr/bin/env python3
"""Test state tracker."""
import unittest
import os
from unittest.mock import MagicMock

# Import test helpers
from test_helpers import setup_test_env

# Setup the test environment
setup_test_env()

class TestStateTracker(unittest.TestCase):
    """Test the StateTracker class."""
    
    def setUp(self):
        """Set up test environment."""
        # We'll use direct file path access instead of importing
        self.zone_control_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zone_control")
        self.tracker_file = os.path.join(self.zone_control_dir, "tracker.py")
        
        # Create mocks
        self.controller = MagicMock()
        self.controller.coordinator = MagicMock()
        self.controller.coordinator.hass = MagicMock()
    
    def test_tracker_file_structure(self):
        """Test StateTracker file structure."""
        # Check that file exists
        self.assertTrue(os.path.isfile(self.tracker_file),
                       f"tracker.py file not found at {self.tracker_file}")
        
        # Check source for key methods
        with open(self.tracker_file, 'r') as f:
            source = f.read()
            
            # Check for StateTracker class
            self.assertIn("class StateTracker", source)
            
            # Check for important methods
            self.assertIn("def setup_moisture_tracking", source)
            self.assertIn("async def _handle_moisture_change", source)
            self.assertIn("async def unload", source)


if __name__ == "__main__":
    unittest.main()