"""Config flow for Smart Sprinklers integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.const import (
    CONF_NAME,
)

from .const import (
    DOMAIN,
    DEFAULT_FREEZE_THRESHOLD,
    DEFAULT_CYCLE_TIME,
    DEFAULT_SOAK_TIME,
    DEFAULT_MIN_MOISTURE,
    DEFAULT_MAX_MOISTURE,
    DEFAULT_MAX_WATERING_HOURS,
    DEFAULT_MAX_WATERING_MINUTES,
    CONF_ZONES,
    CONF_ZONE_NAME,
    CONF_ZONE_SWITCH,
    CONF_ZONE_TEMP_SENSOR,
    CONF_ZONE_MOISTURE_SENSOR,
    CONF_ZONE_MIN_MOISTURE,
    CONF_ZONE_MAX_MOISTURE,
    CONF_ZONE_MAX_WATERING_HOURS,
    CONF_ZONE_MAX_WATERING_MINUTES,
    CONF_WEATHER_ENTITY,
    CONF_FREEZE_THRESHOLD,
    CONF_CYCLE_TIME,
    CONF_SOAK_TIME,
    CONF_SCHEDULE_ENTITY,
)

_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Sprinklers."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate user input
            try:
                # Create entry with basic config
                return self.async_create_entry(
                    title="Smart Sprinklers",
                    data={
                        CONF_WEATHER_ENTITY: user_input[CONF_WEATHER_ENTITY],
                        CONF_SCHEDULE_ENTITY: user_input.get(CONF_SCHEDULE_ENTITY),  # Can be None
                        CONF_FREEZE_THRESHOLD: user_input[CONF_FREEZE_THRESHOLD],
                        CONF_CYCLE_TIME: user_input[CONF_CYCLE_TIME],
                        CONF_SOAK_TIME: user_input[CONF_SOAK_TIME],
                        CONF_ZONES: [],  # Empty list, zones will be added via options flow
                    },
                )
            except Exception as ex:
                _LOGGER.exception("Unexpected exception during setup: %s", ex)
                errors["base"] = "unknown"

        # Show form for initial configuration
        weather_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="weather")
        )

        rain_sensor_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )

        schedule_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="schedule")
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WEATHER_ENTITY
                    ): weather_selector,
                    vol.Optional(
                        CONF_RAIN_SENSOR
                    ): rain_sensor_selector,
                    vol.Optional(
                        CONF_SCHEDULE_ENTITY
                    ): schedule_selector,
                    vol.Required(
                        CONF_FREEZE_THRESHOLD, default=DEFAULT_FREEZE_THRESHOLD
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_CYCLE_TIME, default=DEFAULT_CYCLE_TIME
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_SOAK_TIME, default=DEFAULT_SOAK_TIME
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_RAIN_THRESHOLD, default=DEFAULT_RAIN_THRESHOLD
                    ): vol.Coerce(float),
                }
            ),
            errors=errors,
            description_placeholders={"supported_zones": "unlimited"}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return SmartSprinklersOptionsFlow(config_entry)


class SmartSprinklersOptionsFlow(config_entries.OptionsFlow):
    """Handle options for the Smart Sprinklers integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.current_zones = list(self.config_entry.data.get(CONF_ZONES, []))
        self.options = {}
        self.zone_to_edit = None

    async def async_step_init(self, user_input=None):
        """Handle the initial options step."""
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        """Show the configuration menu."""
        zone_count = len(self.config_entry.data.get(CONF_ZONES, []))
        zone_suffix = "s" if zone_count != 1 else ""
        
        return self.async_show_menu(
            step_id="menu",
            menu_options={
                "configure_zones": f"Configure Zones ({zone_count} zone{zone_suffix} configured)",
                "configure_thresholds": "Configure System Settings",
                "run_integration_tests": "Run Integration Tests",
            },
        )

    async def async_step_configure_zones(self, user_input=None):
        """Handle the configure zones step."""
        return await self.async_step_zone_menu()

    async def async_step_zone_menu(self, user_input=None):
        """Show a menu for zone management."""
        # Get the current zones from config data
        current_zones = list(self.config_entry.data.get(CONF_ZONES, []))
        zone_count = len(current_zones)
        
        menu_options = {
            "add_zone": f"Add Zone (currently {zone_count})",
            "menu": "Return to Main Menu",
        }
        
        if current_zones:
            menu_options["edit_zones"] = f"Edit Existing Zones ({zone_count})"
            # Add option to delete zones if there are any
            menu_options["delete_zone"] = "Delete Zone"
            
        if not current_zones:
            # No zones yet, go straight to add zone
            return await self.async_step_add_zone()
            
        return self.async_show_menu(
            step_id="zone_menu",
            menu_options=menu_options,
        )

    async def async_step_add_zone(self, user_input=None):
        """Handle adding a new zone."""
        errors = {}
        description_placeholders = {}
        
        # Get the current zone count for informational purposes
        current_zones = list(self.config_entry.data.get(CONF_ZONES, []))
        zone_count = len(current_zones)
        description_placeholders["zone_count"] = str(zone_count)

        if user_input is not None:
            try:
                # Calculate total max watering time in minutes
                max_watering_time = (
                    user_input[CONF_ZONE_MAX_WATERING_HOURS] * 60 + 
                    user_input[CONF_ZONE_MAX_WATERING_MINUTES]
                )
                
                # Add the new zone
                new_zone = {
                    CONF_ZONE_NAME: user_input[CONF_ZONE_NAME],
                    CONF_ZONE_SWITCH: user_input[CONF_ZONE_SWITCH],
                    CONF_ZONE_TEMP_SENSOR: user_input[CONF_ZONE_TEMP_SENSOR],
                    CONF_ZONE_MOISTURE_SENSOR: user_input[CONF_ZONE_MOISTURE_SENSOR],
                    CONF_ZONE_MIN_MOISTURE: user_input[CONF_ZONE_MIN_MOISTURE],
                    CONF_ZONE_MAX_MOISTURE: user_input[CONF_ZONE_MAX_MOISTURE],
                    CONF_ZONE_MAX_WATERING_HOURS: user_input[CONF_ZONE_MAX_WATERING_HOURS],
                    CONF_ZONE_MAX_WATERING_MINUTES: user_input[CONF_ZONE_MAX_WATERING_MINUTES],
                    "max_watering_time": max_watering_time,  # Store calculated total
                }
                
                # Update config entry data
                new_data = dict(self.config_entry.data)
                zones = list(new_data.get(CONF_ZONES, []))
                zones.append(new_zone)
                new_data[CONF_ZONES] = zones
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                
                # Return to zones menu to potentially add more zones
                return await self.async_step_zone_menu()
            except Exception as ex:
                _LOGGER.exception("Error adding zone: %s", ex)
                errors["base"] = "unknown"

        # Form for adding a new zone
        switch_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        )
        sensor_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )

        return self.async_show_form(
            step_id="add_zone",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE_NAME): str,
                    vol.Required(CONF_ZONE_SWITCH): switch_selector,
                    vol.Required(CONF_ZONE_TEMP_SENSOR): sensor_selector,
                    vol.Required(CONF_ZONE_MOISTURE_SENSOR): sensor_selector,
                    vol.Required(
                        CONF_ZONE_MIN_MOISTURE, default=DEFAULT_MIN_MOISTURE
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_ZONE_MAX_MOISTURE, default=DEFAULT_MAX_MOISTURE
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_ZONE_MAX_WATERING_HOURS, default=DEFAULT_MAX_WATERING_HOURS
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                    vol.Required(
                        CONF_ZONE_MAX_WATERING_MINUTES, default=DEFAULT_MAX_WATERING_MINUTES
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_edit_zones(self, user_input=None):
        """Handle editing of existing zones."""
        errors = {}
        zones = self.config_entry.data.get(CONF_ZONES, [])
        
        if not zones:
            # No zones to edit, go back to zone menu
            return await self.async_step_zone_menu()

        if user_input is not None:
            try:
                # Set the zone to edit and move to the edit form
                self.zone_to_edit = int(user_input["zone_index"])
                return await self.async_step_edit_zone()
            except Exception as ex:
                _LOGGER.exception("Error selecting zone to edit: %s", ex)
                errors["base"] = "unknown"

        # Create a form to select which zone to edit
        zone_names = [zone[CONF_ZONE_NAME] for zone in zones]
        
        # Use a search selector to handle many zones better
        if len(zones) > 10:
            return self.async_show_form(
                step_id="edit_zones",
                data_schema=vol.Schema(
                    {
                        vol.Required("zone_index"): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    {"label": name, "value": str(i)} 
                                    for i, name in enumerate(zone_names)
                                ],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                custom_value=False,
                                multiple=False,
                                search_in_labels=True,
                            )
                        ),
                    }
                ),
                errors=errors,
            )
        else:
            return self.async_show_form(
                step_id="edit_zones",
                data_schema=vol.Schema(
                    {
                        vol.Required("zone_index"): vol.In(
                            {str(i): name for i, name in enumerate(zone_names)}
                        ),
                    }
                ),
                errors=errors,
            )

    async def async_step_edit_zone(self, user_input=None):
        """Edit a specific zone."""
        errors = {}
        zones = list(self.config_entry.data.get(CONF_ZONES, []))
        
        if self.zone_to_edit is None or self.zone_to_edit >= len(zones):
            # Invalid zone index, go back to zone selection
            return await self.async_step_edit_zones()
            
        zone = zones[self.zone_to_edit]

        if user_input is not None:
            try:
                # Calculate total max watering time in minutes
                max_watering_time = (
                    user_input[CONF_ZONE_MAX_WATERING_HOURS] * 60 + 
                    user_input[CONF_ZONE_MAX_WATERING_MINUTES]
                )
                
                # Update the zone
                zones[self.zone_to_edit] = {
                    CONF_ZONE_NAME: user_input[CONF_ZONE_NAME],
                    CONF_ZONE_SWITCH: user_input[CONF_ZONE_SWITCH],
                    CONF_ZONE_TEMP_SENSOR: user_input[CONF_ZONE_TEMP_SENSOR],
                    CONF_ZONE_MOISTURE_SENSOR: user_input[CONF_ZONE_MOISTURE_SENSOR],
                    CONF_ZONE_MIN_MOISTURE: user_input[CONF_ZONE_MIN_MOISTURE],
                    CONF_ZONE_MAX_MOISTURE: user_input[CONF_ZONE_MAX_MOISTURE],
                    CONF_ZONE_MAX_WATERING_HOURS: user_input[CONF_ZONE_MAX_WATERING_HOURS],
                    CONF_ZONE_MAX_WATERING_MINUTES: user_input[CONF_ZONE_MAX_WATERING_MINUTES],
                    "max_watering_time": max_watering_time,  # Store calculated total
                }
                
                # Update config entry data
                new_data = dict(self.config_entry.data)
                new_data[CONF_ZONES] = zones
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                
                # Return to zone menu
                self.zone_to_edit = None
                return await self.async_step_zone_menu()
            except Exception as ex:
                _LOGGER.exception("Error updating zone: %s", ex)
                errors["base"] = "unknown"

        # Form for editing an existing zone
        switch_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        )
        sensor_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )

        return self.async_show_form(
            step_id="edit_zone",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE_NAME, default=zone[CONF_ZONE_NAME]): str,
                    vol.Required(
                        CONF_ZONE_SWITCH, default=zone[CONF_ZONE_SWITCH]
                    ): switch_selector,
                    vol.Required(
                        CONF_ZONE_TEMP_SENSOR, default=zone[CONF_ZONE_TEMP_SENSOR]
                    ): sensor_selector,
                    vol.Required(
                        CONF_ZONE_MOISTURE_SENSOR, default=zone[CONF_ZONE_MOISTURE_SENSOR]
                    ): sensor_selector,
                    vol.Required(
                        CONF_ZONE_MIN_MOISTURE,
                        default=zone.get(CONF_ZONE_MIN_MOISTURE, DEFAULT_MIN_MOISTURE),
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_ZONE_MAX_MOISTURE,
                        default=zone.get(CONF_ZONE_MAX_MOISTURE, DEFAULT_MAX_MOISTURE),
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_ZONE_MAX_WATERING_HOURS,
                        default=zone.get(CONF_ZONE_MAX_WATERING_HOURS, DEFAULT_MAX_WATERING_HOURS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                    vol.Required(
                        CONF_ZONE_MAX_WATERING_MINUTES,
                        default=zone.get(CONF_ZONE_MAX_WATERING_MINUTES, DEFAULT_MAX_WATERING_MINUTES),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
                }
            ),
            errors=errors,
        )
        
    async def async_step_delete_zone(self, user_input=None):
        """Delete a zone."""
        errors = {}
        zones = list(self.config_entry.data.get(CONF_ZONES, []))
        
        if not zones:
            # No zones to delete, go back to zone menu
            return await self.async_step_zone_menu()

        if user_input is not None:
            try:
                # Delete the selected zone
                zone_index = int(user_input["zone_index"])
                zone_name = zones[zone_index][CONF_ZONE_NAME]
                
                # Remove the zone
                zones.pop(zone_index)
                
                # Update config entry data
                new_data = dict(self.config_entry.data)
                new_data[CONF_ZONES] = zones
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                
                # Notify user
                self.hass.components.persistent_notification.create(
                    f"Zone '{zone_name}' has been deleted.",
                    title="Smart Sprinklers"
                )
                
                # Return to zone menu
                return await self.async_step_zone_menu()
            except Exception as ex:
                _LOGGER.exception("Error deleting zone: %s", ex)
                errors["base"] = "unknown"

        # Create a form to select which zone to delete
        zone_names = [zone[CONF_ZONE_NAME] for zone in zones]
        
        # Use a search selector for many zones
        if len(zones) > 10:
            return self.async_show_form(
                step_id="delete_zone",
                data_schema=vol.Schema(
                    {
                        vol.Required("zone_index"): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[
                                    {"label": name, "value": str(i)} 
                                    for i, name in enumerate(zone_names)
                                ],
                                mode=selector.SelectSelectorMode.DROPDOWN,
                                custom_value=False,
                                multiple=False,
                                search_in_labels=True,
                            )
                        ),
                    }
                ),
                errors=errors,
                description_placeholders={"warning": "WARNING: This will permanently delete the selected zone."},
            )
        else:
            return self.async_show_form(
                step_id="delete_zone",
                data_schema=vol.Schema(
                    {
                        vol.Required("zone_index"): vol.In(
                            {str(i): name for i, name in enumerate(zone_names)}
                        ),
                    }
                ),
                errors=errors,
                description_placeholders={"warning": "WARNING: This will permanently delete the selected zone."},
            )

    async def async_step_configure_thresholds(self, user_input=None):
        """Handle system settings configuration."""
        errors = {}
        current_data = dict(self.config_entry.data)

        if user_input is not None:
            try:
                # Update all system settings
                new_data = dict(current_data)
                new_data[CONF_WEATHER_ENTITY] = user_input[CONF_WEATHER_ENTITY]
                new_data[CONF_FREEZE_THRESHOLD] = user_input[CONF_FREEZE_THRESHOLD]
                new_data[CONF_CYCLE_TIME] = user_input[CONF_CYCLE_TIME]
                new_data[CONF_SOAK_TIME] = user_input[CONF_SOAK_TIME]
                new_data[CONF_SCHEDULE_ENTITY] = user_input.get(CONF_SCHEDULE_ENTITY)
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                
                # Notify user that a restart is required
                self.hass.components.persistent_notification.create(
                    "Smart Sprinklers configuration has been updated. "
                    "Please restart Home Assistant for the changes to take effect.",
                    title="Smart Sprinklers"
                )
                
                # Return to main menu
                return await self.async_step_menu()
            except Exception as ex:
                _LOGGER.exception("Error updating configuration: %s", ex)
                errors["base"] = "unknown"

        # Create selectors for entity selection
        weather_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="weather")
        )
        schedule_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="schedule")
        )

        return self.async_show_form(
            step_id="configure_thresholds",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WEATHER_ENTITY,
                        default=current_data.get(CONF_WEATHER_ENTITY),
                    ): weather_selector,
                    vol.Required(
                        CONF_FREEZE_THRESHOLD,
                        default=current_data.get(CONF_FREEZE_THRESHOLD, DEFAULT_FREEZE_THRESHOLD),
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_RAIN_THRESHOLD,
                        default=current_data.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD),
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_CYCLE_TIME,
                        default=current_data.get(CONF_CYCLE_TIME, DEFAULT_CYCLE_TIME),
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_SOAK_TIME,
                        default=current_data.get(CONF_SOAK_TIME, DEFAULT_SOAK_TIME),
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_SCHEDULE_ENTITY,
                        default=current_data.get(CONF_SCHEDULE_ENTITY),
                    ): schedule_selector,
                    vol.Optional(
                        CONF_RAIN_SENSOR,
                        default=current_data.get(CONF_RAIN_SENSOR),
                    ): rain_sensor_selector,
                }
            ),
            errors=errors,
        )

    async def async_step_run_integration_tests(self, user_input=None):
        """Run integration tests."""
        if user_input is not None:
            # Import the test runner here to avoid circular imports
            try:
                from .integ_tests.runner import run_tests
                
                # Run the tests
                result = await run_tests(self.hass)
                
                # Show the results screen
                return self.async_show_form(
                    step_id="test_results",
                    description_placeholders={"results": result},
                )
            except Exception as e:
                _LOGGER.error("Error running integration tests: %s", str(e))
                return self.async_show_form(
                    step_id="run_integration_tests",
                    errors={"base": "unknown"},
                    description_placeholders={
                        "error": f"Error running tests: {str(e)}"
                    },
                )
        
        # Show the confirmation form
        return self.async_show_form(
            step_id="run_integration_tests",
            data_schema=vol.Schema({}),
        )

    async def async_step_test_results(self, user_input=None):
        """Show test results and return to menu."""
        if user_input is not None:
            # Return to main menu
            return await self.async_step_menu()
        
        # Should never get here directly
        return await self.async_step_menu()