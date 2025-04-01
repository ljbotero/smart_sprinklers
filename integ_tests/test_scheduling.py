"""Integration tests for scheduling functionality."""
import logging
from typing import Optional

from homeassistant.core import HomeAssistant

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def test_schedule_methods_exist(hass: HomeAssistant) -> Optional[str]:
    """Test that schedule-related methods exist."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check scheduling methods exist
    required_methods = [
        "is_in_schedule", 
        "is_schedule_active", 
        "get_schedule_remaining_time"
    ]
    
    for method in required_methods:
        if not hasattr(coordinator, method):
            return f"Coordinator missing {method} method"
    
    return None  # None indicates success

async def test_schedule_entity_handling(hass: HomeAssistant) -> Optional[str]:
    """Test that schedule entity is handled correctly if defined."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check if schedule entity is defined
    if not hasattr(coordinator, "schedule_entity"):
        return "Coordinator missing schedule_entity attribute"
    
    # Test is_in_schedule method without actually activating any sprinklers
    result = coordinator.is_in_schedule()
    
    # Check if the result makes sense based on schedule entity state
    if coordinator.schedule_entity:
        schedule_state = hass.states.get(coordinator.schedule_entity)
        if not schedule_state:
            # Entity not found but method should handle gracefully
            if result is not True:  # Should default to True if entity not found
                return f"is_in_schedule returned {result} when schedule entity not found"
        # Otherwise, the result could be True or False depending on schedule state
        # but we don't need to test that specifically
    else:
        # No schedule entity defined, should default to True
        if result is not True:
            return f"is_in_schedule returned {result} when no schedule entity defined"
    
    return None  # None indicates success

async def test_get_schedule_remaining_time(hass: HomeAssistant) -> Optional[str]:
    """Test get_schedule_remaining_time method."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Call the method - it should not raise exceptions
    try:
        remaining_time = coordinator.get_schedule_remaining_time()
        
        # Check return type - should be None, 0, or a positive number
        if remaining_time is not None:
            if not isinstance(remaining_time, (int, float)):
                return f"get_schedule_remaining_time returned invalid type: {type(remaining_time)}"
            
            if remaining_time < 0:
                return f"get_schedule_remaining_time returned negative value: {remaining_time}"
        
    except Exception as e:
        return f"Error calling get_schedule_remaining_time: {str(e)}"
    
    return None  # None indicates success