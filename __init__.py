"""Smart Sprinklers integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP

from .const import DOMAIN
from .coordinator import SprinklersCoordinator
from .services import register_services

_LOGGER = logging.getLogger(__name__)

# Define platforms we support
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

async def async_setup(hass: HomeAssistant, config):
    """Set up the Smart Sprinklers integration."""
    # This is called when the integration is loaded from configuration.yaml (not used for config entries)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Smart Sprinklers from a config entry."""
    # Create coordinator
    coordinator = SprinklersCoordinator(hass, entry)
    
    # Store coordinator in hass data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    
    # Initialize coordinator
    await coordinator.async_initialize()
    
    # Register shutdown handler to ensure all valves close on HA shutdown
    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP, coordinator.async_shutdown_handler
    )
    
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await register_services(hass, coordinator)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    # First, make sure all zones are turned off for safety
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.emergency_shutdown("Integration unloading")
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Clean up coordinator
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_unload()
        del hass.data[DOMAIN][entry.entry_id]
    
    return unload_ok