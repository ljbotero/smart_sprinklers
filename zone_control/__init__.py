"""Zone control functionality for Smart Sprinklers."""
import asyncio
import logging
from datetime import datetime

from ..const import (
    CONF_ZONES,
    CONF_ZONE_NAME,
    CONF_ZONE_SWITCH,
    CONF_ZONE_TEMP_SENSOR,
    CONF_ZONE_MOISTURE_SENSOR,
    CONF_ZONE_MIN_MOISTURE,
    CONF_ZONE_MAX_MOISTURE,
    CONF_ZONE_MAX_WATERING_HOURS,
    CONF_ZONE_MAX_WATERING_MINUTES,
    DEFAULT_MIN_MOISTURE,
    DEFAULT_MAX_MOISTURE,
    DEFAULT_MAX_WATERING_HOURS,
    DEFAULT_MAX_WATERING_MINUTES,
    ZONE_STATE_IDLE,
)

from ..algorithms.absorption import AbsorptionLearner
from .processor import ZoneProcessor
from .scheduler import Scheduler
from .queue_manager import QueueManager
from .tracker import StateTracker

_LOGGER = logging.getLogger(__name__)

class ZoneController:
    """Manage zone control for Smart Sprinklers."""
    
    def __init__(self, coordinator):
        """Initialize the zone controller."""
        self.coordinator = coordinator
        self.hass = coordinator.hass
        
        # Modified zone tracking to support interleaving
        self.active_zone = None  # The zone that is currently watering
        self.soaking_zones = {}  # Dict of zone_id -> {"ready_at": timestamp, "pre_soak_moisture": value, "cancel_callback": func}
        self.zone_queue = []
        self._process_queue_lock = asyncio.Lock()  # Lock for queue processing
        self._stop_requested = False  # Flag to signal stopping was requested
        
        # Initialize sub-components
        self.processor = ZoneProcessor(self)
        self.scheduler = Scheduler(self)
        self.queue_manager = QueueManager(self)
        self.tracker = StateTracker(self)
        
    async def setup_zones(self, config):
        """Set up zones from configuration."""
        # Configure zones
        for zone_config in config.get(CONF_ZONES, []):
            zone_id = zone_config[CONF_ZONE_NAME].lower().replace(" ", "_")
            
            # Calculate total max watering time in minutes
            max_watering_hours = zone_config.get(CONF_ZONE_MAX_WATERING_HOURS, DEFAULT_MAX_WATERING_HOURS)
            max_watering_minutes = zone_config.get(CONF_ZONE_MAX_WATERING_MINUTES, DEFAULT_MAX_WATERING_MINUTES)
            max_watering_time = max_watering_hours * 60 + max_watering_minutes
            
            # Configure the zone
            self.coordinator.zones[zone_id] = {
                "name": zone_config[CONF_ZONE_NAME],
                "switch": zone_config[CONF_ZONE_SWITCH],
                "temp_sensor": zone_config[CONF_ZONE_TEMP_SENSOR],
                "moisture_sensor": zone_config[CONF_ZONE_MOISTURE_SENSOR],
                "min_moisture": zone_config.get(
                    CONF_ZONE_MIN_MOISTURE, DEFAULT_MIN_MOISTURE
                ),
                "max_moisture": zone_config.get(
                    CONF_ZONE_MAX_MOISTURE, DEFAULT_MAX_MOISTURE
                ),
                "max_watering_hours": max_watering_hours,
                "max_watering_minutes": max_watering_minutes,
                "max_watering_time": max_watering_time,
                "state": ZONE_STATE_IDLE,
                "last_watered": None,
                "next_watering": None,
                "cycle_count": 0,
                "current_cycle": 0,
                "moisture_history": [],
                "soaking_efficiency": 0,
                "moisture_deficit": 0.0,
                "efficiency_factor": 1.0,  # Default efficiency factor
                "watering_expected_increase": 0.0,
                "last_check_time": datetime.now().isoformat(),  # Track last evaluation time
            }
            
            # Initialize daily ET for this zone
            self.coordinator.daily_et[zone_id] = 0.0
            
            # Initialize absorption learner for this zone
            self.coordinator.absorption_learners[zone_id] = AbsorptionLearner()
            
            # Set up moisture sensor state tracking for this zone
            self.tracker.setup_moisture_tracking(zone_id)
            
        # Set up schedule monitoring if schedule entity is defined
        self.scheduler.setup_schedule_monitoring()
        
        return True

    async def enable_system(self):
        """Enable the sprinklers system."""
        async with self.coordinator._system_lock:
            if not self.coordinator.system_enabled:
                self.coordinator.system_enabled = True
                self._stop_requested = False
                
                # Restart processing if there's a queue and no active processing
                if self.zone_queue and not self.coordinator._queue_processing_active:
                    asyncio.create_task(self.queue_manager.process_queue())
                    
                _LOGGER.info("Sprinklers system enabled")
                await self.coordinator.async_send_notification("Sprinklers system enabled")

    async def disable_system(self):
        """Disable the sprinklers system."""
        async with self.coordinator._system_lock:
            if self.coordinator.system_enabled:
                self.coordinator.system_enabled = False
                self._stop_requested = True
                
                # If there's an active zone or soaking zones, stop everything
                await self.stop_all_watering("System disabled by user")
                
                _LOGGER.info("Sprinklers system disabled by user")
                # Send notification
                await self.coordinator.async_send_notification(
                    "Sprinklers system disabled - all zones stopped"
                )

    async def stop_all_watering(self, reason="Manual stop"):
        """Stop all watering activities with a given reason."""
        self._stop_requested = True
        
        # Clear queue first to prevent new activations
        await self.queue_manager.clear_queue()
        
        # If there's an active zone, stop it
        if self.active_zone:
            zone_id = self.active_zone
            try:
                await self.processor.turn_off_zone(zone_id)
                
                # Set zone state to idle
                if zone_id in self.coordinator.zones:
                    zone = self.coordinator.zones[zone_id]
                    zone["state"] = ZONE_STATE_IDLE
                
                # Clear active zone
                self.active_zone = None
            except Exception as e:
                _LOGGER.error("Error turning off active zone %s: %s", zone_id, e)
                # Still clear active zone to avoid getting stuck
                self.active_zone = None
        
        # Cancel all soaking timers and clean up soaking zones
        for zone_id, data in list(self.soaking_zones.items()):
            if "cancel_callback" in data and data["cancel_callback"] is not None:
                try:
                    data["cancel_callback"]()
                except Exception as e:
                    _LOGGER.error("Error cancelling callback for zone %s: %s", zone_id, e)
                    
            if zone_id in self.coordinator.zones:
                self.coordinator.zones[zone_id]["state"] = ZONE_STATE_IDLE
        
        # Clear soaking zones dictionary
        self.soaking_zones.clear()
        
        # Cancel all scheduled callbacks in processor
        try:
            await self.processor.cancel_all_callbacks()
        except Exception as e:
            _LOGGER.error("Error cancelling callbacks: %s", e)
            
        # Reset operational flags
        self.coordinator._queue_processing_active = False
        self.coordinator._sprinklers_active = False
        self.coordinator._manual_operation_requested = False
        
        _LOGGER.info("All watering stopped: %s", reason)

    async def turn_off_all_zones(self):
        """Turn off all zones as a failsafe."""
        _LOGGER.info("Emergency turning off all zone switches")
        
        # First set the stop flag
        self._stop_requested = True
        
        # Try to turn off the active zone switch through the processor
        if self.active_zone:
            try:
                await self.processor.turn_off_zone(self.active_zone)
            except Exception as e:
                _LOGGER.error("Error turning off active zone in emergency shutdown: %s", e)
            
        # As a failsafe, directly turn off all zone switches
        for zone_id, zone in self.coordinator.zones.items():
            try:
                # Direct switch turn off bypassing processor
                await self.hass.services.async_call(
                    "switch", "turn_off", 
                    {"entity_id": zone["switch"]},
                    blocking=True
                )
                zone["state"] = ZONE_STATE_IDLE
                _LOGGER.debug("Emergency turned off zone switch: %s", zone["name"])
            except Exception as e:
                _LOGGER.error("Failed to emergency turn off zone %s: %s", zone["name"], e)
        
        # Clear all state flags and tracking
        self.active_zone = None
        self.soaking_zones.clear()
        self.zone_queue.clear()
        self.coordinator._queue_processing_active = False
        self.coordinator._sprinklers_active = False
        self.coordinator._manual_operation_requested = False

    async def unload(self):
        """Unload and clean up all resources."""
        _LOGGER.info("Unloading zone controller")
        
        # Stop all watering
        await self.stop_all_watering("System unloading")
        
        # Extra failsafe - directly turn off all zone switches
        await self.turn_off_all_zones()
        
        # Clean up tracker resources
        await self.tracker.unload()
        
        # Save learned data before unloading if needed
        # TODO: Implement persistent storage for learner data
        
        _LOGGER.debug("Zone controller unloaded successfully")
        return True

    async def process_zone(self, zone_id):
        """Process a zone to determine if it needs watering."""
        # Skip if stop requested
        if self._stop_requested or self.coordinator._shutdown_requested:
            _LOGGER.debug("Stop requested - not processing zone %s", zone_id)
            return
            
        # Skip if system disabled
        if not self.coordinator.system_enabled:
            return
        
        # Delegate to queue manager
        try:
            await self.queue_manager.evaluate_zone(zone_id)
        except Exception as e:
            _LOGGER.error("Error processing zone %s: %s", zone_id, e)