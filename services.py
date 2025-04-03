"""Service implementations for Smart Sprinklers."""
import logging
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    SERVICE_REFRESH_FORECAST,
    SERVICE_RESET_STATISTICS,
)

_LOGGER = logging.getLogger(__name__)

# Constants for efficiency learning
DEFAULT_EFFICIENCY_FACTOR = 1.0  # Initial efficiency factor

async def register_services(hass: HomeAssistant, coordinator):
    """Register services for Smart Sprinklers."""
    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_FORECAST,
        coordinator.weather_manager.async_update_forecast
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_STATISTICS,
        lambda call: async_service_reset_statistics(coordinator, call)
    )

    hass.services.async_register(
        DOMAIN,
        "update_moisture_deficit",
        lambda call: async_service_update_moisture_deficit(coordinator, call)
    )

    hass.services.async_register(
        DOMAIN,
        "force_et_calculation", 
        lambda call: async_service_force_et_calculation(coordinator, call)
    )

    hass.services.async_register(
        DOMAIN,
        "force_precipitation_calculation",
        lambda call: async_service_force_precipitation_calculation(coordinator, call)
    )
    
    return True

async def async_service_reset_statistics(coordinator, call: ServiceCall):
    """Service to reset statistics for all zones."""
    for zone_id, zone in coordinator.zones.items():
        zone["soaking_efficiency"] = 0
        zone["moisture_history"] = []
        zone["moisture_deficit"] = 0.0
        zone["efficiency_factor"] = DEFAULT_EFFICIENCY_FACTOR  # Reset efficiency factor
        zone["watering_expected_increase"] = 0.0  # Reset expected increase tracker
        
        # Reset absorption learner
        coordinator.absorption_learners[zone_id].reset()
        
        # Reset daily ET
        coordinator.daily_et[zone_id] = 0.0
        
    # Reset daily precipitation
    coordinator.daily_precipitation = 0.0
    
    _LOGGER.info("Reset statistics for all zones")

async def async_service_update_moisture_deficit(coordinator, call: ServiceCall):
    """Service to manually trigger moisture deficit update."""
    await coordinator.weather_manager.async_calculate_et()
    await coordinator.weather_manager.async_calculate_precipitation()
    
    # Update moisture deficits for each zone 
    for zone_id, zone in coordinator.zones.items():
        zone_et = coordinator.daily_et.get(zone_id, 0.0)
        effective_rain = coordinator.daily_precipitation
        
        # Update moisture deficit
        old_deficit = zone.get("moisture_deficit", 0.0)
        new_deficit = old_deficit + zone_et - effective_rain
        
        # Ensure deficit isn't negative
        zone["moisture_deficit"] = max(0.0, new_deficit)
        
        _LOGGER.info(
            "Zone %s: ET=%.2fmm, Rain=%.2fmm, Old deficit=%.2fmm, New deficit=%.2fmm",
            zone["name"], zone_et, effective_rain, old_deficit, zone["moisture_deficit"]
        )
    
    await coordinator.async_send_notification(
        f"Moisture deficit updated for all zones. "
        f"Daily ET: {next(iter(coordinator.daily_et.values())) if coordinator.daily_et else 0:.2f}mm, "
        f"Precipitation: {coordinator.daily_precipitation:.2f}mm"
    )

async def async_service_force_et_calculation(coordinator, call: ServiceCall):
    """Service to force ET calculation."""
    await coordinator.weather_manager.async_calculate_et()
    message = "ET calculation completed:\n"
    for zone_id, et in coordinator.daily_et.items():
        zone_name = coordinator.zones[zone_id]["name"]
        message += f"• {zone_name}: {et:.2f}mm\n"
    
    await coordinator.async_send_notification(message)

async def async_service_force_precipitation_calculation(coordinator, call: ServiceCall):
    """Service to force precipitation calculation."""
    await coordinator.weather_manager.async_calculate_precipitation()
    message = f"Precipitation calculation completed: {coordinator.daily_precipitation:.2f}mm"
    await coordinator.async_send_notification(message)