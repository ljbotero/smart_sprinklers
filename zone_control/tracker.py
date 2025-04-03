"""State tracking for Smart Sprinklers."""
import asyncio
import logging
from datetime import datetime

from homeassistant.helpers.event import async_track_state_change

_LOGGER = logging.getLogger(__name__)

class StateTracker:
    """Track state changes for zones and sensors."""
    
    def __init__(self, controller):
        """Initialize the state tracker."""
        self.controller = controller
        self.coordinator = controller.coordinator
        self.hass = controller.hass
        
        # Track state change listeners for cleanup
        self._unsub_state_listeners = {}
        
    def setup_moisture_tracking(self, zone_id):
        """Set up moisture sensor change monitoring."""
        try:
            zone = self.coordinator.zones[zone_id]
            moisture_sensor = zone["moisture_sensor"]
            
            # Remove any existing listener
            if zone_id in self._unsub_state_listeners:
                self._unsub_state_listeners[zone_id]()
                
            # Add state listener for moisture sensor to react immediately to changes
            self._unsub_state_listeners[zone_id] = async_track_state_change(
                self.hass,
                moisture_sensor,
                self._handle_moisture_change,
                lambda _, __, new_state: zone_id  # Pass zone_id to the callback
            )
            
            _LOGGER.debug("Set up moisture tracking for zone %s using sensor %s", 
                        zone["name"], moisture_sensor)
        except Exception as e:
            _LOGGER.error("Error setting up moisture tracking for zone %s: %s", zone_id, e)
        
    async def _handle_moisture_change(self, entity_id, old_state, new_state, zone_id):
        """Handle changes in moisture sensor readings."""
        if not new_state or not zone_id:
            return
            
        try:
            # Get the new moisture value
            new_moisture = float(new_state.state)
            zone = self.coordinator.zones.get(zone_id)
            
            if not zone:
                _LOGGER.warning("Zone %s not found in coordinator zones", zone_id)
                return
                
            # Record moisture for learning
            zone["moisture_history"].append({
                "timestamp": datetime.now().isoformat(),
                "value": new_moisture
            })
            
            # Keep history manageable (last 30 days)
            max_history = 30 * 24 * 12  # 30 days assuming readings every 5 minutes
            if len(zone["moisture_history"]) > max_history:
                zone["moisture_history"] = zone["moisture_history"][-max_history:]
                
            # If we have a previous reading, check for moisture drop
            if len(zone["moisture_history"]) >= 2:
                previous_reading = zone["moisture_history"][-2]["value"]
                moisture_drop = previous_reading - new_moisture
                if moisture_drop > 0:
                    # Convert moisture percentage drop to mm equivalent
                    mm_equivalent = moisture_drop * 1.0
                    zone["moisture_deficit"] += mm_equivalent
                    _LOGGER.debug(
                        "Zone %s: Moisture drop of %.1f%% (%.1fmm), adjusted deficit to %.1fmm",
                        zone["name"], moisture_drop, mm_equivalent, zone["moisture_deficit"]
                    )
            
            # Process the zone if moisture is below threshold and not already watering
            if new_moisture <= zone["min_moisture"] and zone["state"] == "idle":
                # Avoiding recursive calls within state changes by creating a task
                asyncio.create_task(self.controller.process_zone(zone_id))
                
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Invalid moisture reading for %s: %s", entity_id, e)
            
    async def unload(self):
        """Unload and clean up all resources."""
        # Remove all state listeners
        for zone_id, unsub in list(self._unsub_state_listeners.items()):
            try:
                unsub()
            except Exception:
                pass
        self._unsub_state_listeners = {}
        
        return True