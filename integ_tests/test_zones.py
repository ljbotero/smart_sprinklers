"""Integration tests for zone management."""
import logging
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def test_zones_configured(hass: HomeAssistant) -> Optional[str]:
    """Test that zones are correctly configured."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check zones
    if not hasattr(coordinator, "zones"):
        return "Coordinator missing zones attribute"
    
    if not coordinator.zones:
        return "No zones configured"
    
    return None  # None indicates success

async def test_zone_entities_created(hass: HomeAssistant) -> Optional[str]:
    """Test that sensor entities are created for each zone."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Make sure we have zones
    if not hasattr(coordinator, "zones"):
        return "Coordinator missing zones attribute"
    
    if not coordinator.zones:
        return "No zones configured - skipping test"
    
    # Get entity registry
    entity_registry = async_get(hass)
    
    # Expected sensor types per zone
    sensor_types = ["status", "efficiency", "absorption", "last_watered"]
    
    # Check for each zone
    for zone_id, zone in coordinator.zones.items():
        zone_name = zone["name"].lower().replace(" ", "_")
        
        for sensor_type in sensor_types:
            # Look for entity IDs matching patterns
            entity_id = f"sensor.{zone_name}_{sensor_type}"
            alt_entity_id = f"sensor.{zone_id}_{sensor_type}"
            
            found = False
            for registry_id in [entity_id, alt_entity_id]:
                if entity_registry.async_get_entity_id("sensor", DOMAIN, registry_id):
                    found = True
                    break
            
            if not found:
                return f"Could not find sensor entity for {zone_name} {sensor_type}"
    
    return None  # None indicates success

async def test_zone_status_values(hass: HomeAssistant) -> Optional[str]:
    """Test that zone status sensors have valid values."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Make sure we have zones
    if not hasattr(coordinator, "zones"):
        return "Coordinator missing zones attribute"
    
    if not coordinator.zones:
        return "No zones configured - skipping test"
    
    # Check each zone's status
    for zone_id, zone in coordinator.zones.items():
        # The state should be one of the defined states
        state = zone.get("state")
        
        if state not in ["idle", "watering", "soaking", "measuring"]:
            return f"Zone {zone['name']} has invalid state: {state}"
    
    return None  # None indicates success

async def test_zone_learning_initialized(hass: HomeAssistant) -> Optional[str]:
    """Test that learning algorithms are initialized for each zone."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Make sure we have zones and absorption learners
    if not hasattr(coordinator, "zones"):
        return "Coordinator missing zones attribute"
    
    if not hasattr(coordinator, "absorption_learners"):
        return "Coordinator missing absorption_learners attribute"
    
    if not coordinator.zones:
        return "No zones configured - skipping test"
    
    # Check each zone has a corresponding absorption learner
    for zone_id in coordinator.zones:
        if zone_id not in coordinator.absorption_learners:
            return f"No absorption learner found for zone {zone_id}"
    
    return None  # None indicates success