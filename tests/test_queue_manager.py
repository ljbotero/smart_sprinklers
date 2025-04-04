#!/usr/bin/env python3
"""Test queue manager."""
import unittest
import os
from unittest.mock import MagicMock

# Import test helpers
from test_helpers import setup_test_env

# Setup the test environment
setup_test_env()

class TestQueueManager(unittest.TestCase):
    """Test the QueueManager class."""
    
    def setUp(self):
        """Set up test environment."""
        # We'll use direct file path access instead of importing
        self.zone_control_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zone_control")
        self.queue_manager_file = os.path.join(self.zone_control_dir, "queue_manager.py")
        
        # Create mocks
        self.controller = MagicMock()
        self.controller.coordinator = MagicMock()
        self.controller.coordinator.hass = MagicMock()
    
    def test_queue_manager_file_structure(self):
        """Test QueueManager file structure."""
        # Check that file exists
        self.assertTrue(os.path.isfile(self.queue_manager_file),
                       f"queue_manager.py file not found at {self.queue_manager_file}")
        
        # Check source for key methods
        with open(self.queue_manager_file, 'r') as f:
            source = f.read()
            
            # Check for QueueManager class
            self.assertIn("class QueueManager", source)
            
            # Check for important methods
            self.assertIn("async def evaluate_zone", source)
            self.assertIn("async def process_queue", source)
            self.assertIn("async def clear_queue", source)


if __name__ == "__main__":
    unittest.main()