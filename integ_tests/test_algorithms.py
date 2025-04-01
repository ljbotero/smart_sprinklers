"""Integration tests for learning algorithms."""
import logging
from typing import Optional

from homeassistant.core import HomeAssistant

from ..const import DOMAIN
from ..algorithms.absorption import AbsorptionLearner
from ..algorithms.watering import calculate_watering_duration

_LOGGER = logging.getLogger(__name__)

async def test_absorption_learners_initialized(hass: HomeAssistant) -> Optional[str]:
    """Test that absorption learners are initialized for zones."""
    # Get coordinator from hass
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    coordinator = hass.data[DOMAIN].get(entries[0].entry_id)
    if not coordinator:
        return f"No coordinator found for {DOMAIN}"
    
    # Check absorption_learners attribute
    if not hasattr(coordinator, "absorption_learners"):
        return "Coordinator missing absorption_learners attribute"
    
    if not coordinator.absorption_learners:
        return "No absorption learners configured"
    
    # Check each learner has the expected methods
    for zone_id, learner in coordinator.absorption_learners.items():
        required_methods = ["get_rate", "add_data_point", "reset"]
        
        for method in required_methods:
            if not hasattr(learner, method):
                return f"Absorption learner for zone {zone_id} missing {method} method"
    
    return None  # None indicates success

async def test_absorption_learner_functionality(hass: HomeAssistant) -> Optional[str]:
    """Test basic functionality of absorption learner."""
    # Create a test learner
    learner = AbsorptionLearner()
    
    # Test default rate
    rate = learner.get_rate()
    if not isinstance(rate, float) or rate <= 0:
        return f"Default absorption rate invalid: {rate}"
    
    # Test adding data points
    try:
        learner.add_data_point(20, 25, 30)  # pre, post, duration
    except Exception as e:
        return f"Error adding data point to learner: {str(e)}"
    
    # Test retrieving rate after adding data
    try:
        new_rate = learner.get_rate()
        if not isinstance(new_rate, float) or new_rate <= 0:
            return f"Updated absorption rate invalid: {new_rate}"
    except Exception as e:
        return f"Error getting updated rate: {str(e)}"
    
    # Test reset
    try:
        learner.reset()
        reset_rate = learner.get_rate()
        if reset_rate != rate:  # Should be back to default
            return f"Rate after reset ({reset_rate}) doesn't match default ({rate})"
    except Exception as e:
        return f"Error resetting learner: {str(e)}"
    
    return None  # None indicates success

async def test_watering_calculations(hass: HomeAssistant) -> Optional[str]:
    """Test watering duration calculation functions."""
    # Test calculate_watering_duration with safe values (no actual watering)
    try:
        duration = calculate_watering_duration(
            current_moisture=20,
            target_moisture=30,
            absorption_rate=0.5,
            cycle_time=15,
        )
        
        # Check return value is a number
        if not isinstance(duration, (int, float)):
            return f"Watering duration is not a number: {duration}"
        
        if duration < 0:
            return f"Watering duration should not be negative: {duration}"
    except Exception as e:
        return f"Error calculating watering duration: {str(e)}"
    
    # Test with max time limit
    try:
        duration_limited = calculate_watering_duration(
            current_moisture=20,
            target_moisture=30,
            absorption_rate=0.5,
            cycle_time=15,
            max_watering_time=10
        )
        
        # Should respect max time (or do minimum 1 cycle)
        if duration_limited > 15:
            return f"Max watering time not properly enforced: {duration_limited}"
    except Exception as e:
        return f"Error calculating duration with max time: {str(e)}"
    
    # Test when no watering needed
    try:
        no_water = calculate_watering_duration(
            current_moisture=30,
            target_moisture=30,
            absorption_rate=0.5,
            cycle_time=15,
        )
        
        if no_water != 0:
            return f"Should not water when no moisture difference: {no_water}"
    except Exception as e:
        return f"Error calculating duration with no moisture difference: {str(e)}"
    
    return None  # None indicates success

async def test_reset_statistics_service(hass: HomeAssistant) -> Optional[str]:
    """Test the reset_statistics service."""
    # Check service exists
    service_name = f"{DOMAIN}.reset_statistics"
    if service_name not in hass.services.async_services().get(DOMAIN, {}):
        return f"Service {service_name} not registered"
    
    # Try calling the service (should not throw)
    try:
        await hass.services.async_call(
            DOMAIN, 
            "reset_statistics", 
            {},
            blocking=True
        )
    except Exception as e:
        return f"Error calling reset_statistics service: {str(e)}"
    
    return None  # None indicates success