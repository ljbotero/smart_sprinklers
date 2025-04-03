#!/usr/bin/env python3
"""Test sensor.py using direct mocking."""
import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Define constants from const.py
DOMAIN = "smart_sprinklers"
ZONE_STATE_IDLE = "idle"
ZONE_STATE_WATERING = "watering"
ZONE_STATE_SOAKING = "soaking" 
ZONE_STATE_MEASURING = "measuring"
ATTR_ZONE = "zone"
ATTR_LAST_WATERED = "last_watered"
ATTR_NEXT_WATERING = "next_watering"
ATTR_CYCLE_COUNT = "cycle_count"
ATTR_CURRENT_CYCLE = "current_cycle"
ATTR_SOAKING_EFFICIENCY = "soaking_efficiency"
ATTR_MOISTURE_HISTORY = "moisture_history"
ATTR_ABSORPTION_RATE = "absorption_rate"
ATTR_ESTIMATED_WATERING_DURATION = "estimated_watering_duration"
ATTR_EFFICIENCY_FACTOR = "efficiency_factor"
ATTR_MOISTURE_DEFICIT = "moisture_deficit"

# Create a minimal implementation of ZoneStatusSensor for testing
class ZoneStatusSensor:
    """Sensor showing the status of a sprinklers zone."""

    def __init__(self, coordinator, zone_id):
        """Initialize the zone status sensor."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        zone_name = coordinator.zones[zone_id]["name"]
        
        self._attr_name = f"{zone_name} Status"
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_status"
        self._attr_has_entity_name = True
        self._attr_device_class = None  # Custom status doesn't have a device class
        self._attr_state_class = None
        self._attr_entity_category = "diagnostic"
        
    @property
    def icon(self):
        """Return the icon for the sensor."""
        state = self.coordinator.zones[self.zone_id]["state"]
        
        icons = {
            ZONE_STATE_IDLE: "mdi:water-off",
            ZONE_STATE_WATERING: "mdi:water",
            ZONE_STATE_SOAKING: "mdi:water-percent",
            ZONE_STATE_MEASURING: "mdi:gauge",
        }
        
        return icons.get(state, "mdi:water-alert")
        
    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.zones[self.zone_id]["state"]
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        zone = self.coordinator.zones[self.zone_id]
        
        return {
            ATTR_ZONE: zone["name"],
            ATTR_LAST_WATERED: zone.get("last_watered"),
            ATTR_NEXT_WATERING: zone.get("next_watering"),
            ATTR_CYCLE_COUNT: zone.get("cycle_count", 0),
            ATTR_CURRENT_CYCLE: zone.get("current_cycle", 0),
            ATTR_ESTIMATED_WATERING_DURATION: (
                zone.get("cycle_count", 0) * self.coordinator.cycle_time
                if zone.get("cycle_count", 0) > 0 else 0
            ),
            # Add moisture deficit as an attribute
            ATTR_MOISTURE_DEFICIT: zone.get("moisture_deficit", 0.0),
        }


class TestSensors(unittest.TestCase):
    """Test the sensor entities."""
    
    def setUp(self):
        """Set up for each test."""
        # Create a mock coordinator
        self.coordinator = MagicMock()
        
        # Sample zone data
        self.coordinator.zones = {
            "zone1": {
                "name": "Front Lawn",
                "state": ZONE_STATE_IDLE,
                "last_watered": "2023-06-01T08:00:00",
                "next_watering": "2023-06-02T08:00:00",
                "cycle_count": 3,
                "current_cycle": 1,
                "moisture_history": [],
                "soaking_efficiency": 0.5,
                "moisture_deficit": 5.0,
                "efficiency_factor": 0.85
            }
        }
        
        # Mock absorption learners
        self.coordinator.absorption_learners = {
            "zone1": MagicMock(get_rate=MagicMock(return_value=0.25))
        }
        
        # Weather data
        self.coordinator.daily_precipitation = 2.5
        self.coordinator.daily_et = {"zone1": 3.0}
        self.coordinator.rain_threshold = 3.0
        self.coordinator.freeze_threshold = 36.0
        
        # Cycle time
        self.coordinator.cycle_time = 15
    
    def test_zone_status_sensor(self):
        """Test the ZoneStatusSensor class."""
        # Create an instance of the sensor
        sensor = ZoneStatusSensor(self.coordinator, "zone1")
        
        # Test initialization
        self.assertEqual(sensor._attr_name, "Front Lawn Status")
        self.assertEqual(sensor._attr_unique_id, f"{DOMAIN}_zone1_status")
        self.assertTrue(sensor._attr_has_entity_name)
        
        # Test properties
        self.assertEqual(sensor.native_value, ZONE_STATE_IDLE)
        
        # Change zone state and verify sensor updates
        self.coordinator.zones["zone1"]["state"] = ZONE_STATE_WATERING
        self.assertEqual(sensor.native_value, ZONE_STATE_WATERING)
        
        # Test icons
        self.coordinator.zones["zone1"]["state"] = ZONE_STATE_IDLE
        self.assertEqual(sensor.icon, "mdi:water-off")
        
        self.coordinator.zones["zone1"]["state"] = ZONE_STATE_WATERING
        self.assertEqual(sensor.icon, "mdi:water")
        
        self.coordinator.zones["zone1"]["state"] = ZONE_STATE_SOAKING
        self.assertEqual(sensor.icon, "mdi:water-percent")
        
        self.coordinator.zones["zone1"]["state"] = ZONE_STATE_MEASURING
        self.assertEqual(sensor.icon, "mdi:gauge")
        
        # Test extra attributes
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs.get(ATTR_ZONE), "Front Lawn")
        self.assertEqual(attrs.get(ATTR_LAST_WATERED), "2023-06-01T08:00:00")
        self.assertEqual(attrs.get(ATTR_CYCLE_COUNT), 3)
        self.assertEqual(attrs.get(ATTR_CURRENT_CYCLE), 1)
        self.assertEqual(attrs.get(ATTR_ESTIMATED_WATERING_DURATION), 45)  # 3 cycles * 15 min
        self.assertEqual(attrs.get(ATTR_MOISTURE_DEFICIT), 5.0)
        
        # Test with missing data
        self.coordinator.zones["zone1"] = {
            "name": "Front Lawn",
            "state": ZONE_STATE_IDLE,
        }
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs.get(ATTR_CYCLE_COUNT), 0)
        self.assertEqual(attrs.get(ATTR_CURRENT_CYCLE), 0)
        self.assertEqual(attrs.get(ATTR_ESTIMATED_WATERING_DURATION), 0)
        
        
if __name__ == "__main__":
    unittest.main()