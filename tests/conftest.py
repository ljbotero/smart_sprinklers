"""Configure test environment."""
import os
import sys
from unittest.mock import MagicMock

# Add proper path for imports - pointing to the parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Create mock classes we need
class MockSensorStateClass:
    MEASUREMENT = "measurement"
    
class MockSensorDeviceClass:
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    TIMESTAMP = "timestamp"
    
class MockEntityCategory:
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"

# Create a complete mock structure for homeassistant
homeassistant = MagicMock()
homeassistant.components = MagicMock()
homeassistant.components.sensor = MagicMock()
homeassistant.components.sensor.SensorStateClass = MockSensorStateClass
homeassistant.components.sensor.SensorDeviceClass = MockSensorDeviceClass
homeassistant.helpers = MagicMock()
homeassistant.helpers.entity = MagicMock()
homeassistant.helpers.entity.EntityCategory = MockEntityCategory

# Add all mock modules to sys.modules
sys.modules['homeassistant'] = homeassistant
sys.modules['homeassistant.core'] = MagicMock()
sys.modules['homeassistant.config_entries'] = MagicMock()
sys.modules['homeassistant.helpers'] = homeassistant.helpers
sys.modules['homeassistant.helpers.entity'] = homeassistant.helpers.entity
sys.modules['homeassistant.helpers.entity_platform'] = MagicMock()
sys.modules['homeassistant.helpers.event'] = MagicMock()
sys.modules['homeassistant.components'] = homeassistant.components
sys.modules['homeassistant.components.switch'] = MagicMock()
sys.modules['homeassistant.components.sensor'] = homeassistant.components.sensor
sys.modules['homeassistant.util'] = MagicMock()
sys.modules['homeassistant.util.dt'] = MagicMock()
sys.modules['homeassistant.const'] = MagicMock()
sys.modules['voluptuous'] = MagicMock()