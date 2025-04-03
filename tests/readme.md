# Install Coverage
pip install coverage

# Run a single test file with coverage
coverage run test_coordinator.py

# Generate a report
coverage report -m

# Run multiple test files
coverage run -m unittest test_coordinator.py

# Generate a report
coverage report -m

chmod +x /config/custom_components/smart_sprinklers/tests/run_tests_with_coverage.py

./run_tests_with_coverage.py