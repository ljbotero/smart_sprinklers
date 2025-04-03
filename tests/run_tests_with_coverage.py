#!/usr/bin/env python3
"""Run tests with coverage for smart_sprinklers."""
import os
import sys
import unittest
import coverage

# Set up the test environment
from test_helpers import setup_test_env, TEST_DIR, ROOT_DIR
setup_test_env()

# Start coverage
cov = coverage.Coverage(
    source=[ROOT_DIR],
    omit=[
        os.path.join(ROOT_DIR, "tests", "*"),
        os.path.join(ROOT_DIR, "integ_tests", "*"),
        os.path.join(ROOT_DIR, "__init__.py"),
        os.path.join(ROOT_DIR, "*", "__init__.py"),
    ]
)
cov.start()

# Create test suite
loader = unittest.TestLoader()
suite = loader.discover(TEST_DIR, pattern="test_*.py")
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

# Stop coverage
cov.stop()
cov.save()

# Print report
print("\nCoverage Summary:")
cov.report()

# Generate HTML report
cov.html_report(directory=os.path.join(TEST_DIR, "coverage_html"))
print(f"\nHTML coverage report generated in {os.path.join(TEST_DIR, 'coverage_html')}")

# Return appropriate exit code
sys.exit(not result.wasSuccessful())