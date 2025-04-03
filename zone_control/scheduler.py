"""Schedule management for Smart Sprinklers."""
import logging
from datetime import datetime, timedelta

from homeassistant.helpers.event import async_track_state_change
from homeassistant.util import dt as dt_util

from ..const import CONF_SCHEDULE_ENTITY

_LOGGER = logging.getLogger(__name__)

class Scheduler:
    """Schedule management for watering operations."""
    
    def __init__(self, controller):
        """Initialize the scheduler."""
        self.controller = controller
        self.coordinator = controller.coordinator
        self.hass = controller.hass
        self._schedule_listener = None
        self._schedule_check_debounce = None  # Debounce timer for schedule checks
        
    def setup_schedule_monitoring(self):
        """Set up monitoring for schedule entity changes."""
        try:
            schedule_entity = self.coordinator.config_entry.data.get(CONF_SCHEDULE_ENTITY)
            if not schedule_entity:
                _LOGGER.debug("No schedule entity defined, all times allowed")
                return
                
            # Remove any existing listener
            if self._schedule_listener:
                self._schedule_listener()
                
            # Add state listener for schedule entity
            self._schedule_listener = async_track_state_change(
                self.hass,
                schedule_entity,
                self._handle_schedule_change
            )
            
            _LOGGER.debug("Set up schedule monitoring for entity %s", schedule_entity)
            
            # Check initial schedule state
            schedule_state = self.hass.states.get(schedule_entity)
            if schedule_state:
                _LOGGER.info("Initial schedule state: %s", schedule_state.state)
                if schedule_state.state == 'on':
                    _LOGGER.info("Schedule is currently active")
                else:
                    _LOGGER.info("Schedule is currently inactive")
            else:
                _LOGGER.warning("Schedule entity %s not found", schedule_entity)
                
        except Exception as e:
            _LOGGER.error("Error setting up schedule monitoring: %s", e)
    
    async def _handle_schedule_change(self, entity_id, old_state, new_state):
        """Handle changes in schedule entity state."""
        if not new_state:
            return
            
        try:
            if new_state.state == 'on' and (old_state is None or old_state.state != 'on'):
                _LOGGER.info("Schedule activated - checking zones for watering needs")
                
                # Cancel any existing debounce timer
                if self._schedule_check_debounce is not None:
                    try:
                        self._schedule_check_debounce()
                    except Exception:
                        pass
                
                # Schedule has turned on - check all zones for watering needs
                for zone_id in self.coordinator.zones:
                    await self.controller.process_zone(zone_id)
                    
            elif new_state.state == 'off' and (old_state is None or old_state.state != 'off'):
                _LOGGER.info("Schedule deactivated - stopping active watering")
                
                # Schedule has turned off - stop any active watering
                if self.controller.active_zone or self.controller.zone_queue or self.controller.soaking_zones:
                    _LOGGER.info("Stopping active watering due to schedule end")
                    await self.controller.stop_all_watering("Schedule window ended")
        except Exception as e:
            _LOGGER.error("Error handling schedule change: %s", e)
            
    def is_in_schedule(self):
        """Check if current time is within scheduled watering window."""
        # If no schedule entity is defined, always return true (no schedule restriction)
        schedule_entity = self.coordinator.config_entry.data.get(CONF_SCHEDULE_ENTITY)
        if not schedule_entity:
            return True
        
        try:
            schedule_state = self.hass.states.get(schedule_entity)
            if not schedule_state:
                _LOGGER.warning("Schedule entity %s not available", schedule_entity)
                # Default to NOT allowing watering if the schedule entity isn't available
                # This is the safer approach - better to skip watering than water when not allowed
                return False
            
            # Schedule helper's state is 'on' when the current time is within the schedule
            return schedule_state.state == 'on'
        except Exception as e:
            _LOGGER.error("Error checking schedule: %s", e)
            # Default to false (don't water) if there's an error
            return False
        
    def get_schedule_remaining_time(self):
        """Get the remaining time in minutes for the current schedule window."""
        schedule_entity = self.coordinator.config_entry.data.get(CONF_SCHEDULE_ENTITY)
        if not schedule_entity:
            return None  # No schedule entity, so no time restriction
        
        try:
            schedule_state = self.hass.states.get(schedule_entity)
            if not schedule_state or schedule_state.state != 'on':
                return 0  # Not in schedule window
            
            # Try to get next state change from attributes
            if 'next_state_change' in schedule_state.attributes:
                next_change = dt_util.parse_datetime(schedule_state.attributes['next_state_change'])
                if next_change:
                    now = dt_util.now()
                    if next_change > now:
                        # Return minutes until end of schedule
                        return (next_change - now).total_seconds() / 60
                    return 0  # Schedule about to end
                    
            # Alternative: If there's an end_time attribute
            if 'end_time' in schedule_state.attributes:
                end_time_str = schedule_state.attributes['end_time']
                
                # Parse end time - might be in various formats
                try:
                    # Try as full datetime first
                    end_time = dt_util.parse_datetime(end_time_str)
                    if not end_time:
                        # Try as time string (without date)
                        today = dt_util.now().date()
                        time_parts = end_time_str.split(':')
                        if len(time_parts) >= 2:
                            hour = int(time_parts[0])
                            minute = int(time_parts[1])
                            end_time = dt_util.as_local(datetime.combine(today, datetime.time(hour, minute)))
                    
                    if end_time:
                        now = dt_util.now()
                        if end_time > now:
                            return (end_time - now).total_seconds() / 60
                        return 0  # Schedule ending now
                except (ValueError, TypeError) as e:
                    _LOGGER.error("Error parsing end time: %s", e)
        except Exception as e:
            _LOGGER.error("Error getting schedule remaining time: %s", e)
            
        # Default to a small time if we can't determine
        return 10  # Default to 10 minutes if we can't determine
        
    async def check_schedule(self, now=None):
        """Check if the schedule state has changed."""
        try:
            # Check both: if we're in schedule AND if the system is enabled
            if self.coordinator.system_enabled and self.is_in_schedule():
                # Check if any zone needs watering - but only if no active watering
                if not self.controller.active_zone and not self.controller.zone_queue and not self.controller.soaking_zones:
                    _LOGGER.debug("Schedule check - looking for zones that need water")
                    for zone_id in self.coordinator.zones:
                        await self.controller.process_zone(zone_id)
            
            # If active watering but schedule has ended, stop immediately
            if (self.controller.active_zone or self.controller.zone_queue or self.controller.soaking_zones) and not self.is_in_schedule():
                _LOGGER.info("Schedule has ended, stopping active watering")
                await self.controller.stop_all_watering("Schedule ended")
                
            # If schedule end is coming up soon, check if we have enough time
            elif self.controller.zone_queue and self.is_in_schedule():
                remaining_minutes = self.get_schedule_remaining_time()
                if remaining_minutes is not None and remaining_minutes < 15:  # 15-minute warning
                    _LOGGER.info("Schedule ending in %.1f minutes, may not complete all zones", remaining_minutes)
                    
                    # Calculate if we need to prioritize zones
                    if remaining_minutes < 5:  # If less than 5 minutes remain, clear queue
                        _LOGGER.info("Less than 5 minutes left in schedule - clearing queue")
                        self.controller.zone_queue.clear()
        except Exception as e:
            _LOGGER.error("Error in schedule check: %s", e)