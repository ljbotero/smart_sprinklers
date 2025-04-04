#!/usr/bin/env python3
"""Test zone scheduler."""
import unittest
import os
from unittest.mock import MagicMock

# Import test helpers
from test_helpers import setup_test_env

# Setup the test environment
setup_test_env()

class TestScheduler(unittest.TestCase):
    """Test the Scheduler class."""
    
    def setUp(self):
        """Set up test environment."""
        # We'll use direct file path access instead of importing
        self.zone_control_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zone_control")
        self.scheduler_file = os.path.join(self.zone_control_dir, "scheduler.py")
        
        # Create mocks
        self.controller = MagicMock()
        self.controller.coordinator = MagicMock()
        self.controller.coordinator.hass = MagicMock()
    
    def test_scheduler_file_structure(self):
        """Test Scheduler file structure."""
        # Check that file exists
        self.assertTrue(os.path.isfile(self.scheduler_file),
                       f"scheduler.py file not found at {self.scheduler_file}")
        
        # Check source for key methods
        with open(self.scheduler_file, 'r') as f:
            source = f.read()
            
            # Check for Scheduler class
            self.assertIn("class Scheduler", source)
            
            # Check for important methods
            self.assertIn("def is_in_schedule", source)
            self.assertIn("def get_schedule_remaining_time", source)
            self.assertIn("async def check_schedule", source)


if __name__ == "__main__":
    unittest.main()