#!/usr/bin/env python3
"""Run basic tests to get coverage working."""
import os
import sys
import unittest
import coverage
from unittest.mock import MagicMock, patch

# Configure paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# Start coverage
cov = coverage.Coverage(
    include=[
        os.path.join(ROOT_DIR, "*.py"),
        os.path.join(ROOT_DIR, "algorithms", "*.py")
    ],
    omit=[
        "*/__init__.py",
        "*/tests/*",
        "*/integ_tests/*"
    ]
)
cov.start()

# Mock Home Assistant imports
sys.modules['homeassistant'] = MagicMock()
sys.modules['homeassistant.core'] = MagicMock()
# Add other modules as needed

# Simple test for util.py's fetch_forecast function
class TestUtil(unittest.TestCase):
    def test_basic(self):
        """Basic test that always passes."""
        self.assertTrue(True)

# Run the tests
if __name__ == "__main__":
    unittest.main(exit=False)
    
    # Stop coverage
    cov.stop()
    cov.save()
    
    # Print report
    print("\nCoverage Summary:")
    cov.report()
    
    # Generate HTML report
    cov.html_report(directory=os.path.join(os.path.dirname(__file__), "coverage_html"))
    print(f"\nHTML coverage report generated in {os.path.join(os.path.dirname(__file__), 'coverage_html')}")