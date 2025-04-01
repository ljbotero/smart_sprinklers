"""Switch entities for Smart Sprinklers."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    STATE_ENABLED,
    STATE_DISABLED,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Smart Sprinklers switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    
    # Create a main enable/disable switch for the entire system
    entities.append(SystemEnableSwitch(coordinator))
    
    async_add_entities(entities)


class SystemEnableSwitch(SwitchEntity):
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_name = "Smart Sprinklers System"
        self._attr_unique_id = f"{DOMAIN}_system_enable"
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def icon(self):
        return "mdi:water" if self.is_on else "mdi:water-off"

    @property
    def is_on(self) -> bool:
        return self.coordinator.system_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_enable_system()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_disable_system()
        self.async_write_ha_state()
