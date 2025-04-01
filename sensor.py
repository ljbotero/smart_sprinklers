"""Sensor entities for Smart Sprinklers."""
# This must be the first import
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt

from .const import (
    DOMAIN,
    ATTR_ZONE,
    ATTR_LAST_WATERED,
    ATTR_NEXT_WATERING,
    ATTR_CYCLE_COUNT,
    ATTR_CURRENT_CYCLE,
    ATTR_SOAKING_EFFICIENCY,
    ATTR_MOISTURE_HISTORY,
    ATTR_ABSORPTION_RATE,
    ATTR_ESTIMATED_WATERING_DURATION,
    ZONE_STATE_IDLE,
    ZONE_STATE_WATERING,
    ZONE_STATE_SOAKING,
    ZONE_STATE_MEASURING,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Smart Sprinklers sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    
    # Create a status sensor for each zone
    for zone_id, zone in coordinator.zones.items():
        entities.append(ZoneStatusSensor(coordinator, zone_id))
        entities.append(ZoneEfficiencySensor(coordinator, zone_id))
        entities.append(ZoneAbsorptionSensor(coordinator, zone_id))
        entities.append(ZoneLastWateredSensor(coordinator, zone_id))
        entities.append(ZoneMoistureDeficitSensor(coordinator, zone_id))    
        
    # Add the weather data sensor
    entities.append(WeatherDataSensor(coordinator))
    
    async_add_entities(entities)


class ZoneStatusSensor(SensorEntity):
    """Sensor showing the status of an sprinklers zone."""

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
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
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
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return self.coordinator.zones[self.zone_id]["state"]
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
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


class ZoneEfficiencySensor(SensorEntity):
    """Sensor showing the watering efficiency of a zone."""

    def __init__(self, coordinator, zone_id):
        """Initialize the zone efficiency sensor."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        zone_name = coordinator.zones[zone_id]["name"]
        
        self._attr_name = f"{zone_name} Efficiency"
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_efficiency"
        self._attr_has_entity_name = True
        self._attr_device_class = None  # Custom efficiency doesn't have a device class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%/h"  # Percent per hour
        
    @property
    def icon(self):
        """Return the icon for the sensor."""
        return "mdi:water-percent"  # Always use this specific icon
    
    @property
    def native_value(self) -> float:
        """Return the state of the sensor."""
        efficiency = self.coordinator.zones[self.zone_id].get(ATTR_SOAKING_EFFICIENCY, 0)
        # Convert to percent per hour
        return round(efficiency * 60, 2)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        zone = self.coordinator.zones[self.zone_id]
        
        # Include moisture history
        moisture_history = zone.get("moisture_history", [])
        
        return {
            ATTR_ZONE: zone["name"],
            ATTR_MOISTURE_HISTORY: moisture_history
        }


class ZoneAbsorptionSensor(SensorEntity):
    """Sensor showing the absorption rate of a zone."""

    def __init__(self, coordinator, zone_id):
        """Initialize the zone absorption sensor."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        zone_name = coordinator.zones[zone_id]["name"]
        
        self._attr_name = f"{zone_name} Absorption Rate"
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_absorption"
        self._attr_has_entity_name = True
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%/min"  # Percent per minute
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
    @property
    def icon(self):
        """Return the icon for the sensor."""
        return "mdi:water-sync"
        
    @property
    def native_value(self) -> float:
        """Return the state of the sensor."""
        rate = self.coordinator.absorption_learners[self.zone_id].get_rate()
        return round(rate, 4)


class ZoneLastWateredSensor(SensorEntity):
    """Sensor showing when a zone was last watered."""

    def __init__(self, coordinator, zone_id):
        """Initialize the last watered sensor."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        zone_name = coordinator.zones[zone_id]["name"]
        
        self._attr_name = f"{zone_name} Last Watered"
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_last_watered"
        self._attr_has_entity_name = True
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
    @property
    def icon(self):
        """Return the icon for the sensor."""
        return "mdi:calendar-clock"
        
    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        last_watered = self.coordinator.zones[self.zone_id].get("last_watered")
        if last_watered:
            return dt.parse_datetime(last_watered)
        return None


class WeatherDataSensor(SensorEntity):
    """Sensor showing weather data relevant for sprinklers."""

    def __init__(self, coordinator):
        """Initialize the weather data sensor."""
        self.coordinator = coordinator
        
        self._attr_name = f"Sprinklers Weather Data"
        self._attr_unique_id = f"{DOMAIN}_weather_data"
        self._attr_has_entity_name = True
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
    @property
    def icon(self):
        """Return the icon for the sensor."""
        return "mdi:weather-partly-rainy"
        
    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        if self.coordinator.is_rain_forecasted():
            return "Rain Forecasted"
        elif self.coordinator.is_freezing_forecasted():
            return "Freezing Forecasted"
        else:
            return "Clear"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes."""
        return {
            ATTR_DAILY_PRECIPITATION: self.coordinator.daily_precipitation,
            # Daily ET is per zone, so we take an average or the first zone as representative
            ATTR_DAILY_ET: next(iter(self.coordinator.daily_et.values())) if self.coordinator.daily_et else 0.0,
            "rain_threshold": self.coordinator.rain_threshold,
            "freeze_threshold": self.coordinator.freeze_threshold,
        }

class ZoneMoistureDeficitSensor(SensorEntity):
    """Sensor showing the moisture deficit of a zone."""

    def __init__(self, coordinator, zone_id):
        """Initialize the zone moisture deficit sensor."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        zone_name = coordinator.zones[zone_id]["name"]
        
        self._attr_name = f"{zone_name} Moisture Deficit"
        self._attr_unique_id = f"{DOMAIN}_{zone_id}_moisture_deficit"
        self._attr_has_entity_name = True
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "mm"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
    @property
    def icon(self):
        """Return the icon for the sensor."""
        zone = self.coordinator.zones[self.zone_id]
        deficit = zone.get("moisture_deficit", 0)
        
        if deficit <= 1.0:
            return "mdi:water-check"  # Low deficit
        elif deficit <= 5.0:
            return "mdi:water-alert"  # Medium deficit
        else:
            return "mdi:water-off"    # High deficit
        
    @property
    def native_value(self) -> float:
        """Return the state of the sensor."""
        zone = self.coordinator.zones[self.zone_id]
        return round(zone.get("moisture_deficit", 0.0), 1)