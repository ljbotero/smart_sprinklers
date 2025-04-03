"""Coordinator for Smart Sprinklers integration."""
import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CONF_WEATHER_ENTITY,
    CONF_FREEZE_THRESHOLD,
    CONF_CYCLE_TIME,
    CONF_SOAK_TIME,
    DEFAULT_FREEZE_THRESHOLD,
    DEFAULT_CYCLE_TIME,
    DEFAULT_SOAK_TIME,
)

from .zone_control import ZoneController
from .weather import WeatherManager

_LOGGER = logging.getLogger(__name__)

class SprinklersCoordinator:
    """Coordinator for Smart Sprinklers integration."""
    
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize the coordinator."""
        self.hass = hass
        self.config_entry = config_entry
        
        # Get configuration
        weather_entity = config_entry.data.get(CONF_WEATHER_ENTITY)
        freeze_threshold = config_entry.data.get(CONF_FREEZE_THRESHOLD, DEFAULT_FREEZE_THRESHOLD)
        self.cycle_time = config_entry.data.get(CONF_CYCLE_TIME, DEFAULT_CYCLE_TIME)
        self.soak_time = config_entry.data.get(CONF_SOAK_TIME, DEFAULT_SOAK_TIME)
        
        # State data
        self.zones = {}  # Maps zone_id to zone data
        self.absorption_learners = {}  # Maps zone_id to AbsorptionLearner
        self.daily_et = {}  # Maps zone_id to daily ET
        self.daily_precipitation = 0.0  # Daily precipitation in mm
        
        # Create component managers
        self.weather_manager = WeatherManager(self) 
        self.zone_controller = ZoneController(self)
        
        # System state
        self._system_enabled = True
        self._system_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()  # Lock to prevent concurrent operations
        self._sprinklers_active = False
        self._queue_processing_active = False
        self._manual_operation_requested = False
        self._shutdown_requested = False  # Flag for shutdown
        self._pending_tasks = []
        
        # Configuration values
        self.freeze_threshold = freeze_threshold
        self.rain_threshold = 3.0  # Default, may be overridden in setup
        self.weather_entity = weather_entity
        
    @property
    def system_enabled(self):
        """Get the system enabled state."""
        return self._system_enabled
        
    @system_enabled.setter
    def system_enabled(self, value):
        """Set the system enabled state."""
        self._system_enabled = value
        # TODO: Persist to config entry if needed
        
    async def async_initialize(self):
        """Initialize the coordinator."""
        try:
            # Set up weather manager
            await self.weather_manager.setup(self.config_entry.data)
            
            # Set up zones
            await self.zone_controller.setup_zones(self.config_entry.data)
            
            # Set up daily update for weather data
            await self.weather_manager.async_daily_update()
            
            # Update weather data
            await self.weather_manager.async_update_forecast()
            
            # Schedule regular checks
            self._schedule_regular_checks()
            
            return True
        except Exception as e:
            _LOGGER.error("Error initializing Smart Sprinklers: %s", e)
            # Make sure no zones are active in case of error
            await self.emergency_shutdown("Initialization error")
            raise
        
    def _schedule_regular_checks(self):
        """Schedule regular checks of the watering schedule."""
        # Check schedule every 15 minutes
        schedule_check_unsub = async_track_time_interval(
            self.hass, 
            self.zone_controller.scheduler.check_schedule,
            timedelta(minutes=15)
        )
        self._pending_tasks.append(schedule_check_unsub)
        
        # Check forecast every 6 hours
        forecast_check_unsub = async_track_time_interval(
            self.hass, 
            lambda _: self.weather_manager.async_update_forecast(),
            timedelta(hours=6)
        )
        self._pending_tasks.append(forecast_check_unsub)
    
    async def async_shutdown_handler(self, event):
        """Handle Home Assistant shutdown."""
        _LOGGER.info("Home Assistant is shutting down - ensuring all sprinkler zones are off")
        await self.emergency_shutdown("Home Assistant shutdown")
    
    async def emergency_shutdown(self, reason="Emergency shutdown"):
        """Perform emergency shutdown of all sprinkler zones."""
        self._shutdown_requested = True
        # Set cancel flag for any running watering cycles
        await self.zone_controller.stop_all_watering(reason)
        
        # Double-check: directly turn off all zone switches as a failsafe
        try:
            for zone_id, zone in self.zones.items():
                if "switch" in zone:
                    try:
                        _LOGGER.debug("Emergency shutdown - turning off zone %s", zone["name"])
                        await self.hass.services.async_call(
                            "switch", "turn_off", 
                            {"entity_id": zone["switch"]},
                            blocking=True
                        )
                    except Exception as e:
                        _LOGGER.error("Failed to turn off zone %s during emergency shutdown: %s", zone["name"], e)
        except Exception as e:
            _LOGGER.error("Error during emergency shutdown: %s", e)
            
        _LOGGER.info("Emergency shutdown completed: %s", reason)
    
    async def async_unload(self):
        """Unload and clean up resources."""
        # First do emergency shutdown to close any valves
        await self.emergency_shutdown("Integration unloading")
        
        # Cancel all pending tasks
        for task in self._pending_tasks:
            try:
                if callable(task):
                    task()  # Cancel the callback
            except Exception as e:
                _LOGGER.error("Error cancelling task during unload: %s", e)
        
        # Clean up zone controller
        try:
            await self.zone_controller.unload()
        except Exception as e:
            _LOGGER.error("Error unloading zone controller: %s", e)
        
        return True
        
    async def async_send_notification(self, message):
        """Send a notification."""
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {"title": "Smart Sprinklers", "message": message},
            )
        except Exception as e:
            _LOGGER.error("Failed to send notification: %s", e)

    async def execute_watering_program(self, mode="scheduled"):
        """Execute a watering program with proper locking to prevent multiple runs."""
        # Use lock to ensure only one watering operation runs at a time
        if self._operation_lock.locked():
            _LOGGER.warning("Watering program already running, ignoring %s request", mode)
            await self.async_send_notification(
                f"Watering request ({mode}) ignored - program already running"
            )
            return False
            
        async with self._operation_lock:
            # Double check we're not in shutdown
            if self._shutdown_requested:
                _LOGGER.warning("Shutdown requested, not starting watering program")
                return False
                
            _LOGGER.info("Starting %s watering program", mode)
            try:
                # Logic for running the watering program would go here
                # This is a placeholder - the actual zone watering is handled by ZoneController
                
                # For now, just call process_queue if not already processing
                if not self._queue_processing_active and self.system_enabled:
                    for zone_id in self.zones:
                        await self.zone_controller.process_zone(zone_id)
                return True
            except Exception as e:
                _LOGGER.error("Error executing watering program: %s", e)
                # Make sure to shut down all zones in case of error
                await self.zone_controller.stop_all_watering(f"Error in {mode} program")
                return False

    def is_rain_forecasted(self):
        """Check if rain is forecasted."""
        return self.weather_manager.is_rain_forecasted()
        
    def is_freezing_forecasted(self):
        """Check if freezing temperatures are forecasted."""
        return self.weather_manager.is_freezing_forecasted()