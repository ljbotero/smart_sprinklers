"""Integration tests for weather integration."""
import logging
from typing import Optional

from homeassistant.core import HomeAssistant

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def test_weather_entity_defined(hass: HomeAssistant) -> Optional[str]:
    """Test that weather entity is defined in config."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check if weather entity is defined
    if not hasattr(coordinator, "weather_entity"):
        return "Coordinator missing weather_entity attribute"
    
    # Weather entity may be None if not configured, that's allowed
    # But if defined, check it exists in hass
    if coordinator.weather_entity:
        weather_state = hass.states.get(coordinator.weather_entity)
        if not weather_state:
            return f"Weather entity {coordinator.weather_entity} not found in hass states"
    
    return None  # None indicates success

async def test_forecast_methods(hass: HomeAssistant) -> Optional[str]:
    """Test that weather forecast methods exist and don't error."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check forecast methods exist
    required_methods = ["is_rain_forecasted", "is_freezing_forecasted"]
    for method in required_methods:
        if not hasattr(coordinator, method):
            return f"Coordinator missing {method} method"
        
        # Try calling the method (should not raise exceptions)
        try:
            # Call the method - don't care about the result, just that it doesn't error
            getattr(coordinator, method)()
        except Exception as e:
            return f"Error calling {method}: {str(e)}"
    
    return None  # None indicates success

async def test_freeze_threshold_defined(hass: HomeAssistant) -> Optional[str]:
    """Test that freeze threshold is defined."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check freeze threshold
    if not hasattr(coordinator, "freeze_threshold"):
        return "Coordinator missing freeze_threshold attribute"
    
    if not isinstance(coordinator.freeze_threshold, (int, float)):
        return f"Freeze threshold has invalid type: {type(coordinator.freeze_threshold)}"
    
    return None  # None indicates success

async def test_fetch_forecast_service(hass: HomeAssistant) -> Optional[str]:
    """Test that forecast refresh service exists and can be called."""
    # Check service exists
    service_name = f"{DOMAIN}.refresh_forecast"
    if service_name not in hass.services.async_services().get(DOMAIN, {}):
        return f"Service {service_name} not registered"
    
    # Try calling the service (should not throw)
    try:
        await hass.services.async_call(
            DOMAIN, 
            "refresh_forecast", 
            {},
            blocking=True
        )
    except Exception as e:
        return f"Error calling refresh_forecast service: {str(e)}"
    
    return None  # None indicates success

async def test_moisture_deficit_tracking(hass: HomeAssistant) -> Optional[str]:
    """Test that moisture deficit is being tracked properly."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check if moisture_deficit is defined in zones
    for zone_id, zone in coordinator.zones.items():
        if "moisture_deficit" not in zone:
            return f"Zone {zone['name']} missing moisture_deficit attribute"
    
    # Check daily ET and precipitation attributes
    if not hasattr(coordinator, "daily_et"):
        return "Coordinator missing daily_et attribute"
    
    if not hasattr(coordinator, "daily_precipitation"):
        return "Coordinator missing daily_precipitation attribute"
    
    return None  # None indicates success

async def test_rain_threshold_functionality(hass: HomeAssistant) -> Optional[str]:
    """Test rain threshold functionality."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check if rain_threshold is defined
    if not hasattr(coordinator, "rain_threshold"):
        return "Coordinator missing rain_threshold attribute"
    
    # Check if rain threshold is a positive number
    if not isinstance(coordinator.rain_threshold, (int, float)) or coordinator.rain_threshold <= 0:
        return f"Invalid rain threshold: {coordinator.rain_threshold}"
    
    return None  # None indicates success