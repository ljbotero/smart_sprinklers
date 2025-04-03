"""Helper functions for testing."""
import os
import sys
import importlib.util
from unittest.mock import MagicMock

# Constants for testing
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)

def setup_test_env():
    """Set up the test environment with proper imports."""
    # Add the parent directory to Python path
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)

    # Create mock classes
    class MockSensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL = "total"
        TOTAL_INCREASING = "total_increasing"
        
    class MockSensorDeviceClass:
        TEMPERATURE = "temperature"
        HUMIDITY = "humidity"
        TIMESTAMP = "timestamp"
        
    class MockEntityCategory:
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    # Setup mock modules
    modules_to_mock = {
        'homeassistant': MagicMock(),
        'homeassistant.core': MagicMock(),
        'homeassistant.config_entries': MagicMock(),
        'homeassistant.helpers': MagicMock(),
        'homeassistant.helpers.entity': MagicMock(),
        'homeassistant.helpers.entity_platform': MagicMock(),
        'homeassistant.helpers.event': MagicMock(),
        'homeassistant.components': MagicMock(),
        'homeassistant.components.switch': MagicMock(),
        'homeassistant.components.sensor': MagicMock(),
        'homeassistant.util': MagicMock(),
        'homeassistant.util.dt': MagicMock(),
        'homeassistant.const': MagicMock(),
        'voluptuous': MagicMock(),
    }
    
    # Apply mocks
    for name, mock in modules_to_mock.items():
        sys.modules[name] = mock
    
    # Set up specific mock attributes
    sys.modules['homeassistant.components.sensor'].SensorStateClass = MockSensorStateClass
    sys.modules['homeassistant.components.sensor'].SensorDeviceClass = MockSensorDeviceClass
    sys.modules['homeassistant.helpers.entity'].EntityCategory = MockEntityCategory

def import_module_from_file(module_name, file_path):
    """Import a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def load_component_module(name):
    """Load a component module while handling relative imports."""
    module_path = os.path.join(ROOT_DIR, f"{name}.py")
    if not os.path.exists(module_path):
        raise ImportError(f"Cannot find module at {module_path}")
    
    # First load the const module which most others import
    if name != "const" and "smart_sprinklers.const" not in sys.modules:
        const_path = os.path.join(ROOT_DIR, "const.py")
        if os.path.exists(const_path):
            import_module_from_file("smart_sprinklers.const", const_path)
    
    return import_module_from_file(f"smart_sprinklers.{name}", module_path)