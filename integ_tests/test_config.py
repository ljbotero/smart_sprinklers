"""Integration tests for configuration."""
import logging
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def test_config_entry_setup(hass: HomeAssistant) -> Optional[str]:
    """Test that config entry is set up correctly."""
    # Check if domain is set up in hass
    if DOMAIN not in hass.data:
        return f"Domain {DOMAIN} not found in hass.data"
    
    # Check if there's at least one config entry
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return f"No config entries found for {DOMAIN}"
    
    return None  # None indicates success

async def test_entities_registered(hass: HomeAssistant) -> Optional[str]:
    """Test that entities are correctly registered."""
    entity_registry = async_get(hass)
    
    # Get entities for our domain
    domain_entities = [
        entity for entity_id, entity in entity_registry.entities.items() 
        if entity.config_entry_id in [
            entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)
        ]
    ]
    
    if not domain_entities:
        return f"No entities found for {DOMAIN}"
    
    # Check for system enable switch
    enable_switch = any(
        entity.entity_id.endswith("_system_enable")
        for entity in domain_entities
    )
    
    if not enable_switch:
        return "System enable switch not found"
    
    return None  # None indicates success

async def test_services_registered(hass: HomeAssistant) -> Optional[str]:
    """Test that services are correctly registered."""
    # Check for expected services
    expected_services = ["refresh_forecast", "reset_statistics"]
    
    for service in expected_services:
        service_name = f"{DOMAIN}.{service}"
        if service_name not in hass.services.async_services().get(DOMAIN, {}):
            return f"Service {service_name} not registered"
    
    return None  # None indicates success