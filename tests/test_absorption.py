#!/usr/bin/env python3
"""Test absorption learning algorithm."""
import unittest
from unittest.mock import MagicMock
from datetime import datetime

# Import test helpers
from test_helpers import setup_test_env, load_component_module

# Setup the test environment
setup_test_env()

class TestAbsorptionLearner(unittest.TestCase):
    """Test the AbsorptionLearner class."""
    
    def setUp(self):
        """Set up test environment."""
        # Load the module
        self.absorption = load_component_module("algorithms/absorption")
        self.AbsorptionLearner = self.absorption.AbsorptionLearner
    
    def test_absorption_learner_initialization(self):
        """Test initialization of AbsorptionLearner."""
        # Create a learner
        learner = self.AbsorptionLearner()
        
        # Test initial state
        self.assertEqual(len(learner._data_points), 0)
        self.assertGreater(learner._default_rate, 0)
        
        # Test get_rate with no data
        rate = learner.get_rate()
        self.assertIsInstance(rate, float)
        self.assertGreater(rate, 0)
        
        # Test reset
        learner.reset()
        self.assertEqual(len(learner._data_points), 0)


if __name__ == "__main__":
    unittest.main()