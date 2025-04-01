"""Integration test runner for Smart Sprinklers."""
import os
import asyncio
import inspect
import importlib
import traceback
from datetime import datetime
from typing import Dict, List, Any

from homeassistant.core import HomeAssistant

# Path to the integration test directory
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
# Path to the results file
RESULTS_FILE = os.path.join(TEST_DIR, "test_results.txt")

# Test modules - import all tests
TEST_MODULES = [
    "test_config",
    "test_zones",
    "test_weather",
    "test_scheduling",
    "test_algorithms",
]

def write_to_file(message: str, append: bool = True):
    """Write a message to the results file."""
    # Make sure directory exists
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    
    mode = "a" if append else "w"
    with open(RESULTS_FILE, mode) as f:
        f.write(message + "\n")

async def run_tests(hass: HomeAssistant) -> str:
    """Run all integration tests and return a summary."""
    # Clean start - clear the results file
    write_to_file("", append=False)
    write_to_file(f"Smart Sprinklers Integration Tests - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    write_to_file("-" * 70)
    
    results = {}
    total_tests = 0
    passed_tests = 0
    
    try:
        for module_name in TEST_MODULES:
            # Import the module from relative path
            try:
                # Construct absolute module path
                absolute_module = f"custom_components.smart_sprinklers.integ_tests.{module_name}"
                module = importlib.import_module(absolute_module)
                
                write_to_file(f"\nRunning tests from {module_name}")
                write_to_file("-" * 50)
                
                # Find all test functions (async functions starting with "test_")
                test_funcs = []
                for name, obj in inspect.getmembers(module):
                    if name.startswith("test_") and inspect.iscoroutinefunction(obj):
                        test_funcs.append((name, obj))
                
                # Execute each test function
                for name, func in test_funcs:
                    total_tests += 1
                    try:
                        write_to_file(f"Running {name}... ", append=True)
                        
                        # Create a clean context for each test
                        test_context = {"hass": hass}
                        
                        # Run the test
                        result = await func(hass)
                        if result is None or result is True:
                            write_to_file("PASSED")
                            passed_tests += 1
                            results[name] = "PASSED"
                        else:
                            write_to_file(f"FAILED: {result}")
                            results[name] = f"FAILED: {result}"
                    except Exception as e:
                        error_text = f"ERROR: {str(e)}\n{traceback.format_exc()}"
                        write_to_file(error_text)
                        results[name] = f"ERROR: {str(e)}"
            
            except ImportError as e:
                write_to_file(f"Could not import module {module_name}: {str(e)}")
                continue
    
    except Exception as e:
        write_to_file(f"Error running tests: {str(e)}\n{traceback.format_exc()}")
    
    # Write summary
    write_to_file("\n" + "=" * 50)
    write_to_file(f"Test Summary: {passed_tests}/{total_tests} tests passed")
    write_to_file("=" * 50)
    
    # Return a shorter summary for the UI
    return f"{passed_tests}/{total_tests} tests passed. Full results in {RESULTS_FILE}"

def get_test_results() -> str:
    """Read the test results file and return the contents."""
    try:
        with open(RESULTS_FILE, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "No test results found."