#!/usr/bin/env python3
"""Direct test for smart sprinklers algorithms."""
import sys
import os
import unittest
from unittest.mock import MagicMock

# We need to add the parent directory (custom_components) to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# We also need to mock Home Assistant
sys.modules['homeassistant'] = MagicMock()
sys.modules['homeassistant.config_entries'] = MagicMock()
sys.modules['homeassistant.core'] = MagicMock()
sys.modules['homeassistant.helpers'] = MagicMock()
sys.modules['homeassistant.const'] = MagicMock()

# Now directly import the modules we want to test
absorption_module_path = os.path.join(os.path.dirname(__file__), '../algorithms/absorption.py')
watering_module_path = os.path.join(os.path.dirname(__file__), '../algorithms/watering.py')

# Use execfile-like functionality to load the modules
absorption_namespace = {}
watering_namespace = {}

with open(absorption_module_path, 'r') as f:
    exec(f.read(), absorption_namespace)
    
with open(watering_module_path, 'r') as f:
    exec(f.read(), watering_namespace)

# Extract the classes/functions we want to test
AbsorptionLearner = absorption_namespace['AbsorptionLearner']
calculate_watering_duration = watering_namespace['calculate_watering_duration']


class TestAlgorithms(unittest.TestCase):
    """Test the algorithm modules."""

    def test_absorption_learner(self):
        """Test basic absorption learner functionality."""
        learner = AbsorptionLearner()
        
        # Check initial state
        self.assertEqual(len(learner._data_points), 0)
        
        # Get default rate
        rate = learner.get_rate()
        self.assertIsInstance(rate, float)
        self.assertGreater(rate, 0)
        
        # Add a data point
        learner.add_data_point(20, 25, 30)  # pre, post, duration
        self.assertEqual(len(learner._data_points), 1)
        
        # Check point was added correctly
        point = learner._data_points[0]
        self.assertEqual(point["pre_moisture"], 20)
        self.assertEqual(point["post_moisture"], 25)
        self.assertEqual(point["duration"], 30)
        self.assertAlmostEqual(point["rate"], (25-20)/30)  # 0.1667
        
        # Test reset
        learner.reset()
        self.assertEqual(len(learner._data_points), 0)
        
    def test_watering_calculations(self):
        """Test watering duration calculations."""
        # Basic calculation
        duration = calculate_watering_duration(
            current_moisture=20,
            target_moisture=30,
            absorption_rate=0.5,
            cycle_time=15
        )
        
        # Should be at least one cycle
        self.assertGreaterEqual(duration, 15)
        
        # Should be proportional to moisture difference
        self.assertGreaterEqual(duration, (30-20)/0.5)  # Base time without saturation factor
        
        # Test no watering needed
        duration = calculate_watering_duration(
            current_moisture=30,
            target_moisture=30,
            absorption_rate=0.5,
            cycle_time=15
        )
        self.assertEqual(duration, 0)
        
        # Test with max watering time
        duration = calculate_watering_duration(
            current_moisture=10,
            target_moisture=50,
            absorption_rate=0.1,  # Very slow absorption
            cycle_time=15,
            max_watering_time=30  # Cap at 30 minutes
        )
        self.assertLessEqual(duration, 30)  # Should respect max


if __name__ == "__main__":
    unittest.main()