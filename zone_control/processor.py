"""Zone processing for Smart Sprinklers."""
import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.helpers.event import async_call_later

from ..const import (
    ZONE_STATE_IDLE,
    ZONE_STATE_WATERING,
    ZONE_STATE_SOAKING,
    ZONE_STATE_MEASURING,
)
from ..algorithms.watering import calculate_watering_duration

_LOGGER = logging.getLogger(__name__)

# Constants for efficiency learning
DEFAULT_EFFICIENCY_FACTOR = 1.0
MIN_EFFICIENCY_FACTOR = 0.5
MAX_EFFICIENCY_FACTOR = 1.0
EFFICIENCY_ADJUST_STEP = 0.05

class ZoneProcessor:
    """Process zone watering cycles."""
    
    def __init__(self, controller):
        """Initialize the zone processor."""
        self.controller = controller
        self.coordinator = controller.coordinator
        self.hass = controller.hass
        
        # Track callback handles for proper cleanup
        self._callback_handles = []
        
    async def turn_on_zone(self, zone_id):
        """Turn on a zone's switch."""
        if zone_id not in self.coordinator.zones:
            _LOGGER.warning("Attempted to turn on non-existent zone: %s", zone_id)
            return False
            
        # Check for shutdown requested
        if self.coordinator._shutdown_requested:
            _LOGGER.warning("Shutdown requested - not turning on zone %s", zone_id)
            return False
            
        zone = self.coordinator.zones[zone_id]
        try:
            # Store the timestamp before turning on to track watering duration
            zone["watering_start_time"] = datetime.now().isoformat()
            
            await self.hass.services.async_call(
                "switch", "turn_on", 
                {"entity_id": zone["switch"]},
                blocking=True
            )
            
            # Update state
            zone["state"] = ZONE_STATE_WATERING
            self.controller.active_zone = zone_id
            self.coordinator._sprinklers_active = True
            
            # Log the successful activation
            _LOGGER.info("Zone %s turned ON successfully", zone["name"])
            return True
        except Exception as e:
            _LOGGER.error("Failed to turn on zone %s: %s", zone["name"], e)
            # Reset zone state if we failed to turn on
            zone["state"] = ZONE_STATE_IDLE
            return False

    async def turn_off_zone(self, zone_id):
        """Turn off a zone's switch."""
        if zone_id not in self.coordinator.zones:
            _LOGGER.warning("Attempted to turn off non-existent zone: %s", zone_id)
            return False
            
        zone = self.coordinator.zones[zone_id]
        try:
            await self.hass.services.async_call(
                "switch", "turn_off", 
                {"entity_id": zone["switch"]},
                blocking=True
            )
            
            # Log watering duration for analysis
            if "watering_start_time" in zone:
                start_time = datetime.fromisoformat(zone["watering_start_time"])
                duration = (datetime.now() - start_time).total_seconds() / 60.0  # in minutes
                _LOGGER.info("Zone %s watered for %.1f minutes", zone["name"], duration)
            
            # If this was the active zone, clear it
            if self.controller.active_zone == zone_id:
                self.controller.active_zone = None
                
                # If we're not watering any other zones, update the system state
                if not self.controller.soaking_zones:
                    self.coordinator._sprinklers_active = False
            return True
        except Exception as e:
            _LOGGER.error("Failed to turn off zone %s: %s", zone["name"], e)
            # Safety measure - set active_zone to None even if turn-off failed
            if self.controller.active_zone == zone_id:
                self.controller.active_zone = None
            return False

    async def start_zone_cycle(self, zone_id, current_moisture):
        """Start a watering cycle for a zone."""
        # First check for shutdown 
        if self.coordinator._shutdown_requested:
            _LOGGER.warning("Shutdown requested - not starting zone cycle for %s", zone_id)
            # Continue with next zone in queue if appropriate
            if not self.controller.zone_queue:
                self.coordinator._queue_processing_active = False
            return
            
        if zone_id not in self.coordinator.zones:
            _LOGGER.warning("Attempted to start cycle for non-existent zone: %s", zone_id)
            # Continue with next zone in queue
            if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                asyncio.create_task(self.controller.queue_manager.process_queue())
            else:
                self.coordinator._queue_processing_active = False
            return
            
        zone = self.coordinator.zones[zone_id]
        
        # Calculate cycle time
        cycle_minutes = self.coordinator.cycle_time
        
        # Record pre-watering moisture level
        zone["pre_watering_moisture"] = current_moisture
        
        # Update expected moisture increase based on absorption rate and cycle time
        absorption_rate = self.coordinator.absorption_learners[zone_id].get_rate()
        expected_increase = absorption_rate * cycle_minutes
        zone["watering_expected_increase"] = expected_increase
        
        # Update timestamps
        now = datetime.now()
        zone["last_watered"] = now.isoformat()
        
        # Turn on the zone
        success = await self.turn_on_zone(zone_id)
        if not success:
            _LOGGER.error("Failed to start watering for zone %s", zone["name"])
            # Continue with next zone in queue
            if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                asyncio.create_task(self.controller.queue_manager.process_queue())
            else:
                self.coordinator._queue_processing_active = False
            return
        
        _LOGGER.info(
            "Started watering zone %s (Cycle %d/%d, duration: %d minutes)",
            zone["name"], zone["current_cycle"], zone["cycle_count"], cycle_minutes
        )
        
        try:
            # Schedule the end of this cycle with a non-blocking timer
            # Store the callback so it can be cancelled if needed
            callback = async_call_later(
                self.hass,
                cycle_minutes * 60,  # Convert to seconds
                self.handle_cycle_end,
                zone_id
            )
            self._callback_handles.append(callback)
        except Exception as e:
            _LOGGER.error("Failed to schedule cycle end for zone %s: %s", zone["name"], e)
            # Safety measure - turn off zone if we couldn't schedule the end
            await self.turn_off_zone(zone_id)
            
            # Continue with next zone
            if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                asyncio.create_task(self.controller.queue_manager.process_queue())
            else:
                self.coordinator._queue_processing_active = False

    async def handle_cycle_end(self, _now, zone_id):
        """Handle the end of a watering cycle."""
        try:
            # Remove the callback from handles
            self._callback_handles = [
                handle for handle in self._callback_handles
                if handle and handle.data != zone_id
            ]
                    
            # Check if shutdown was requested
            if self.coordinator._shutdown_requested:
                _LOGGER.info("Shutdown requested during cycle - ending all watering")
                await self.turn_off_zone(zone_id)
                return
                
            if zone_id not in self.coordinator.zones:
                _LOGGER.warning("Zone %s no longer exists, skipping cycle end", zone_id)
                # Continue with next zone in queue
                if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                    asyncio.create_task(self.controller.queue_manager.process_queue())
                else:
                    self.coordinator._queue_processing_active = False
                return
                
            zone = self.coordinator.zones[zone_id]
            
            # Turn off the zone
            await self.turn_off_zone(zone_id)
            
            # If this was the last cycle, we're done with this zone
            if zone["current_cycle"] >= zone["cycle_count"]:
                _LOGGER.info(
                    "Completed all watering cycles for zone %s",
                    zone["name"]
                )
                
                # Update zone state to measuring
                zone["state"] = ZONE_STATE_MEASURING
                
                # Schedule moisture check after soaking
                measure_callback = async_call_later(
                    self.hass,
                    30 * 60,  # 30 minutes in seconds
                    self.handle_final_measurement,
                    zone_id
                )
                self._callback_handles.append(measure_callback)
                
                # If there are other zones in the queue, process the next one
                if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                    asyncio.create_task(self.controller.queue_manager.process_queue())
                else:
                    # No more zones in queue, check if all zones are done
                    if not self.controller.active_zone and not self.controller.soaking_zones:
                        self.coordinator._queue_processing_active = False
                        self.coordinator._sprinklers_active = False
                        _LOGGER.info("All zones watered, queue processing complete")
            else:
                # We need to soak and then do another cycle
                await self.start_soak_cycle(zone_id)
        except Exception as e:
            _LOGGER.error("Error handling cycle end for zone %s: %s", zone_id, e)
            # Safety: try to turn off the zone if there was an error
            try:
                await self.turn_off_zone(zone_id)
            except Exception:
                pass
            
            # Try to recover by processing next zone
            if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                asyncio.create_task(self.controller.queue_manager.process_queue())
            else:
                self.coordinator._queue_processing_active = False

    async def start_soak_cycle(self, zone_id):
        """Start a soak cycle for a zone."""
        # Check for shutdown
        if self.coordinator._shutdown_requested:
            _LOGGER.warning("Shutdown requested - not starting soak cycle for %s", zone_id)
            return
            
        zone = self.coordinator.zones[zone_id]
        
        # Move to soaking state
        zone["state"] = ZONE_STATE_SOAKING
        
        # Increment cycle counter for next time
        zone["current_cycle"] += 1
        
        # Get current moisture reading
        try:
            moisture_state = self.hass.states.get(zone["moisture_sensor"])
            if not moisture_state:
                _LOGGER.warning(
                    "Moisture sensor unavailable for zone %s after watering cycle", 
                    zone["name"]
                )
                current_moisture = zone.get("pre_watering_moisture", 0)
            else:
                current_moisture = float(moisture_state.state)
            
            # Store pre-soak moisture level
            pre_soak_moisture = current_moisture
            
            # Calculate when soaking will be done
            ready_at = datetime.now() + timedelta(minutes=self.coordinator.soak_time)
            
            _LOGGER.info(
                "Zone %s soaking until %s (cycle %d/%d)",
                zone["name"], ready_at.strftime("%H:%M:%S"),
                zone["current_cycle"], zone["cycle_count"]
            )
            
            # Schedule callback for when soaking is done
            soak_callback = async_call_later(
                self.hass,
                self.coordinator.soak_time * 60,  # Convert to seconds
                self.handle_soak_end,
                zone_id
            )
            self._callback_handles.append(soak_callback)
            
            # Add to soaking zones dict
            self.controller.soaking_zones[zone_id] = {
                "ready_at": ready_at,
                "pre_soak_moisture": pre_soak_moisture,
                "cancel_callback": soak_callback
            }
            
            # Process next zone in queue while this one soaks
            if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                asyncio.create_task(self.controller.queue_manager.process_queue())
            
        except (ValueError, TypeError) as e:
            _LOGGER.error("Error reading moisture for zone %s: %s", zone["name"], e)
            # Move to next zone anyway
            if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                asyncio.create_task(self.controller.queue_manager.process_queue())

    async def handle_soak_end(self, _now, zone_id):
        """Handle the end of a soaking period."""
        try:
            # Remove the callback from handles
            self._callback_handles = [
                handle for handle in self._callback_handles
                if handle and handle.data != zone_id
            ]
            
            # Check for shutdown
            if self.coordinator._shutdown_requested:
                _LOGGER.warning("Shutdown requested - not continuing after soak for %s", zone_id)
                # Remove from soaking zones dict
                if zone_id in self.controller.soaking_zones:
                    del self.controller.soaking_zones[zone_id]
                return
                    
            # Remove from soaking zones dict
            if zone_id in self.controller.soaking_zones:
                del self.controller.soaking_zones[zone_id]
                
            # Check if zone still exists
            if zone_id not in self.coordinator.zones:
                _LOGGER.warning("Zone %s no longer exists, skipping soak end", zone_id)
                
                # Process queue to continue with other zones
                if not self.controller.active_zone and not self.coordinator._shutdown_requested:
                    asyncio.create_task(self.controller.queue_manager.process_queue())
                return
                
            zone = self.coordinator.zones[zone_id]
            _LOGGER.info(
                "Soak period ended for zone %s, continuing with cycle %d/%d",
                zone["name"], zone["current_cycle"], zone["cycle_count"]
            )
            
            # Add back to queue for next cycle, at the front of the line
            self.controller.zone_queue.insert(0, zone_id)
            
            # Process queue to start next cycle
            if not self.coordinator._shutdown_requested:
                asyncio.create_task(self.controller.queue_manager.process_queue())
            
        except Exception as e:
            _LOGGER.error("Error handling soak end for zone %s: %s", zone_id, e)
            # Try to recover by processing queue
            if not self.coordinator._shutdown_requested:
                asyncio.create_task(self.controller.queue_manager.process_queue())

    async def handle_final_measurement(self, _now, zone_id):
        """Handle the final moisture measurement after watering and soaking."""
        try:
            # Remove the callback from handles
            self._callback_handles = [
                handle for handle in self._callback_handles
                if handle and handle.data != zone_id
            ]
                    
            # Check if zone still exists
            if zone_id not in self.coordinator.zones:
                _LOGGER.warning("Zone %s no longer exists, skipping final measurement", zone_id)
                return
                
            zone = self.coordinator.zones[zone_id]
            
            # Get current moisture reading
            try:
                moisture_state = self.hass.states.get(zone["moisture_sensor"])
                if not moisture_state:
                    _LOGGER.warning(
                        "Moisture sensor unavailable for zone %s during final measurement", 
                        zone["name"]
                    )
                    current_moisture = zone.get("pre_watering_moisture", 0)
                else:
                    current_moisture = float(moisture_state.state)
                
                # Calculate moisture increase
                pre_moisture = zone.get("pre_watering_moisture", current_moisture)
                moisture_increase = current_moisture - pre_moisture
                
                # Calculate efficiency
                if zone.get("watering_expected_increase", 0) > 0:
                    efficiency_ratio = moisture_increase / zone["watering_expected_increase"]
                    self._update_efficiency_factor(zone, efficiency_ratio)
                
                # Update soaking efficiency in % per hour
                hours = (zone["cycle_count"] * self.coordinator.cycle_time) / 60
                if hours > 0:
                    zone["soaking_efficiency"] = moisture_increase / hours
                
                # Add data point to absorption learner
                cycles_run = zone["cycle_count"] 
                if cycles_run > 0:
                    watering_minutes = cycles_run * self.coordinator.cycle_time
                    self.coordinator.absorption_learners[zone_id].add_data_point(
                        pre_moisture, current_moisture, watering_minutes
                    )
                
                # Update moisture deficit
                self._update_moisture_deficit(zone, moisture_increase)
                
                # Reset zone state
                zone["state"] = ZONE_STATE_IDLE
                
                # Send notification
                await self.coordinator.async_send_notification(
                    f"Zone {zone['name']} watering complete: "
                    f"Moisture increased from {pre_moisture:.1f}% to {current_moisture:.1f}% "
                    f"(efficiency: {zone.get('soaking_efficiency', 0):.2f}%/h)"
                )
                
            except (ValueError, TypeError) as e:
                _LOGGER.error("Error reading final moisture for zone %s: %s", zone["name"], e)
                zone["state"] = ZONE_STATE_IDLE
                
        except Exception as e:
            _LOGGER.error("Error handling final measurement for zone %s: %s", zone_id, e)
            
        finally:
            # Make sure flags are reset if this was the last zone
            if not self.controller.active_zone and not self.controller.soaking_zones and not self.controller.zone_queue:
                self.coordinator._queue_processing_active = False
                self.coordinator._sprinklers_active = False

    def _update_efficiency_factor(self, zone, efficiency_ratio):
        """Update the efficiency factor based on watering results."""
        old_factor = zone.get("efficiency_factor", DEFAULT_EFFICIENCY_FACTOR)
        
        if efficiency_ratio > 1:
            # Better than expected, increase factor
            new_factor = min(MAX_EFFICIENCY_FACTOR, old_factor + EFFICIENCY_ADJUST_STEP)
        elif efficiency_ratio < 0.8:
            # Worse than expected, decrease factor
            new_factor = max(MIN_EFFICIENCY_FACTOR, old_factor - EFFICIENCY_ADJUST_STEP)
        else:
            # Close to expected, small adjustment
            new_factor = old_factor + (EFFICIENCY_ADJUST_STEP/2) * (efficiency_ratio - 1)
        
        # Apply bounds
        new_factor = max(MIN_EFFICIENCY_FACTOR, min(MAX_EFFICIENCY_FACTOR, new_factor))
        zone["efficiency_factor"] = new_factor
        
        _LOGGER.info(
            "Zone %s efficiency: Expected +%.1f%%, Actual +%.1f%%, Factor adjusted from %.2f to %.2f",
            zone["name"], zone.get("watering_expected_increase", 0), efficiency_ratio * zone.get("watering_expected_increase", 0), 
            old_factor, new_factor
        )

    def _update_moisture_deficit(self, zone, moisture_increase):
        """Update the moisture deficit based on watering results."""
        if moisture_increase > 0:
            # Convert moisture percentage increase to mm equivalent
            mm_equivalent = moisture_increase * 1.0
            old_deficit = zone.get("moisture_deficit", 0.0)
            new_deficit = max(0.0, old_deficit - mm_equivalent)
            zone["moisture_deficit"] = new_deficit
            _LOGGER.info(
                "Zone %s: Moisture increased by %.1f%% (%.1fmm), deficit reduced from %.1fmm to %.1fmm",
                zone["name"], moisture_increase, mm_equivalent, old_deficit, new_deficit
            )
            
    async def cancel_all_callbacks(self):
        """Cancel all active callbacks."""
        # Cancel any active callbacks
        for handle in self._callback_handles:
            try:
                handle()  # Cancel the callback
            except Exception as e:
                _LOGGER.error("Error cancelling callback: %s", e)
                
        self._callback_handles = []