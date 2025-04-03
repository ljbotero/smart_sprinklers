"""Queue management for Smart Sprinklers."""
import asyncio
import logging

from ..algorithms.watering import calculate_watering_duration

_LOGGER = logging.getLogger(__name__)

class QueueManager:
    """Manage the zone queue processing."""
    
    def __init__(self, controller):
        """Initialize the queue manager."""
        self.controller = controller
        self.coordinator = controller.coordinator
        self.hass = controller.hass
        self._queue_operation_lock = asyncio.Lock()  # Lock for queue processing operations
        
    async def evaluate_zone(self, zone_id):
        """Evaluate if a zone needs watering and add to queue if needed."""
        # Skip if system is disabled, shutdown requested, or if sprinklers are already active
        if not self.coordinator.system_enabled or self.coordinator._shutdown_requested:
            return
            
        # Skip if the zone is already being processed (active or soaking)
        if self.controller.active_zone == zone_id or zone_id in self.controller.soaking_zones:
            return
        
        if zone_id not in self.coordinator.zones:
            _LOGGER.warning("Attempted to process non-existent zone: %s", zone_id)
            return
            
        zone = self.coordinator.zones[zone_id]
        
        # Skip if the zone is already in an active state
        if zone["state"] in ["watering", "soaking"]:
            return
        
        # Get current sensor readings
        try:
            moisture_state = self.hass.states.get(zone["moisture_sensor"])
            temp_state = self.hass.states.get(zone["temp_sensor"])
            
            if not moisture_state or not temp_state:
                _LOGGER.warning("Sensors not found for zone %s", zone["name"])
                return
            
            # Ensure states are convertible to float
            try:
                current_moisture = float(moisture_state.state)
                current_temp = float(temp_state.state)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Invalid sensor readings for zone %s: moisture=%s, temp=%s",
                    zone["name"], moisture_state.state, temp_state.state
                )
                return
            
            # Check if watering is needed - either based on moisture sensor or deficit
            watering_needed = False
            
            # Moisture sensor check
            if current_moisture <= zone["min_moisture"]:
                watering_needed = True
                _LOGGER.debug(
                    "Zone %s needs water due to moisture level (%.1f%% < %.1f%%)",
                    zone["name"], current_moisture, zone["min_moisture"]
                )
                
            # Moisture deficit check - if deficit exceeds threshold
            elif zone.get("moisture_deficit", 0) >= 5.0:  # 5mm deficit threshold
                watering_needed = True
                _LOGGER.debug(
                    "Zone %s needs water due to moisture deficit (%.1fmm)",
                    zone["name"], zone.get("moisture_deficit", 0)
                )
                
            if watering_needed:
                await self._handle_watering_needed(zone_id, zone, current_moisture, current_temp)
                
        except Exception as e:
            _LOGGER.error("Error processing zone %s: %s", zone["name"], e)

    async def _handle_watering_needed(self, zone_id, zone, current_moisture, current_temp):
        """Handle a zone that needs watering."""
        # Check if we can water based on weather and schedule
        scheduler = self.controller.scheduler
        if (
            scheduler.is_in_schedule()
            and not self.coordinator.weather_manager.is_rain_forecasted()
            and not self.coordinator.weather_manager.is_freezing_forecasted()
            and current_temp > self.coordinator.freeze_threshold
        ):
            # Add to queue if not already there
            if zone_id not in self.controller.zone_queue and zone_id not in self.controller.soaking_zones:
                async with self._queue_operation_lock:
                    # Double check it's not in queue (could have been added while waiting for lock)
                    if zone_id not in self.controller.zone_queue and zone_id not in self.controller.soaking_zones:
                        self.controller.zone_queue.append(zone_id)
                        _LOGGER.info(
                            "Zone %s added to watering queue (moisture: %.1f%%, deficit: %.1fmm)", 
                            zone["name"], current_moisture, zone.get("moisture_deficit", 0)
                        )
                        
                        # Send notification if not too many waiting
                        if len(self.controller.zone_queue) <= 3:  # Only notify for the first few zones
                            await self.coordinator.async_send_notification(
                                f"Zone {zone['name']} added to watering queue "
                                f"(moisture: {current_moisture}%, deficit: {zone.get('moisture_deficit', 0):.1f}mm)"
                            )
                
                # Start queue processing if not already active
                if not self.controller.active_zone and not self.coordinator._queue_processing_active and not self.coordinator._shutdown_requested:
                    asyncio.create_task(self.process_queue())
        else:
            # Log why watering is skipped
            reason = "unknown"
            if not scheduler.is_in_schedule():
                reason = "outside of schedule"
                _LOGGER.debug("Zone %s needs water but outside of schedule", zone["name"])
            elif self.coordinator.weather_manager.is_rain_forecasted():
                reason = "rain forecasted"
                _LOGGER.info(
                    "Zone %s needs water but rain is forecasted - skipping watering",
                    zone["name"]
                )
            elif self.coordinator.weather_manager.is_freezing_forecasted():
                reason = "freezing temperatures forecasted"
                _LOGGER.info(
                    "Zone %s needs water but freezing temperatures are forecasted - skipping watering",
                    zone["name"]
                )
            elif current_temp <= self.coordinator.freeze_threshold:
                reason = f"current temperature below freeze threshold ({self.coordinator.freeze_threshold}°F)"
                _LOGGER.info(
                    "Zone %s needs water but current temperature is below freeze threshold - skipping watering",
                    zone["name"]
                )
            
            # Update skip reason in zone data for UI display
            zone["watering_skipped_reason"] = reason
            zone["last_check_time"] = self.hass.core.dt_util.now().isoformat()

    async def process_queue(self):
        """Process the zone queue in a non-blocking way."""
        # First check if shutdown requested
        if self.coordinator._shutdown_requested:
            _LOGGER.warning("Shutdown requested - clearing watering queue")
            self.controller.zone_queue.clear()
            self.coordinator._queue_processing_active = False
            return
            
        # Prevent multiple queue processing instances
        if self.coordinator._queue_processing_active:
            return
            
        # Lock queue processing
        async with self.controller._process_queue_lock:
            self.coordinator._queue_processing_active = True
            
            try:
                # First, check if there are any soaking zones ready to continue
                await self._check_soaking_zones()
                
                # If no active zone and queue has entries, start next zone
                while not self.controller.active_zone and self.controller.zone_queue:
                    # Check for shutdown requested inside loop
                    if self.coordinator._shutdown_requested:
                        _LOGGER.warning("Shutdown requested during queue processing - clearing queue")
                        self.controller.zone_queue.clear()
                        self.coordinator._queue_processing_active = False
                        return
                        
                    # Check if still in schedule
                    if not self.controller.scheduler.is_in_schedule():
                        _LOGGER.info("Queue processing stopped - outside of schedule window")
                        self.controller.zone_queue.clear()
                        self.coordinator._queue_processing_active = False
                        return
                        
                    # If schedule window is ending soon, don't start new zones
                    remaining_minutes = self.controller.scheduler.get_schedule_remaining_time()
                    if remaining_minutes is not None and remaining_minutes < 10:  # 10 minute safety margin
                        _LOGGER.info("Schedule window ending soon (%d minutes) - not starting new zones", remaining_minutes)
                        self.controller.zone_queue.clear()
                        self.coordinator._queue_processing_active = False
                        return
                        
                    # Get next zone from queue
                    zone_id = self.controller.zone_queue.pop(0)
                    if zone_id not in self.coordinator.zones:
                        _LOGGER.warning("Zone %s from queue no longer exists, skipping", zone_id)
                        # Continue with next iteration through loop
                        continue
                        
                    zone = self.coordinator.zones[zone_id]
                    
                    # Get sensor readings
                    try:
                        moisture_state = self.hass.states.get(zone["moisture_sensor"])
                        if not moisture_state:
                            _LOGGER.warning("Moisture sensor not available for zone %s, skipping", zone["name"])
                            # Continue with next iteration of the loop
                            continue
                            
                        current_moisture = float(moisture_state.state)
                        
                        # Double-check if watering is still needed
                        if current_moisture > zone["min_moisture"] and zone.get("moisture_deficit", 0) < 5.0:
                            _LOGGER.info(
                                "Zone %s no longer needs water (moisture: %.1f%%, deficit: %.1fmm), skipping",
                                zone["name"], current_moisture, zone.get("moisture_deficit", 0)
                            )
                            # Continue with next iteration of the loop
                            continue
                        
                        # Calculate watering duration
                        await self._calculate_and_start_watering(zone_id, zone, current_moisture)
                        # Break the loop since a zone has started
                        break
                    except Exception as e:
                        _LOGGER.error("Error processing zone %s: %s", zone["name"], e)
                        # Continue with next iteration of the loop
                        continue
                
                # If no active zone now and no zones in queue, release the lock
                if not self.controller.active_zone and not self.controller.zone_queue and not self.controller.soaking_zones:
                    self.coordinator._queue_processing_active = False
            except Exception as e:
                _LOGGER.error("Error in queue processing: %s", e)
                self.coordinator._queue_processing_active = False
                # Ensure active zone is cleared if there was an error
                if self.controller.active_zone:
                    try:
                        await self.controller.processor.turn_off_zone(self.controller.active_zone)
                    except Exception as turn_off_error:
                        _LOGGER.error("Error turning off active zone after processing error: %s", turn_off_error)

    async def _calculate_and_start_watering(self, zone_id, zone, current_moisture):
        """Calculate watering time and start watering if needed."""
        # Check for shutdown
        if self.coordinator._shutdown_requested:
            return
            
        # Calculate watering duration based on moisture levels and learned absorption rate
        absorption_rate = self.coordinator.absorption_learners[zone_id].get_rate()
        max_watering_time = zone["max_watering_time"]
        
        # Apply efficiency factor to absorption rate
        efficiency_factor = zone.get("efficiency_factor", 1.0)
        adjusted_absorption_rate = absorption_rate * efficiency_factor
        
        watering_duration = calculate_watering_duration(
            current_moisture=current_moisture,
            target_moisture=zone["max_moisture"],
            absorption_rate=adjusted_absorption_rate,
            cycle_time=self.coordinator.cycle_time,
            max_watering_time=max_watering_time
        )
        
        if watering_duration > 0:
            # Calculate how many cycles we need
            cycles_needed = max(1, int(watering_duration / self.coordinator.cycle_time))
            zone["cycle_count"] = cycles_needed
            zone["current_cycle"] = 1
            
            # Start watering the zone
            await self.controller.processor.start_zone_cycle(zone_id, current_moisture)
        else:
            _LOGGER.info("Zone %s doesn't need water, skipping", zone["name"])
            # If queue has more entries, continue processing
            if self.controller.zone_queue and not self.coordinator._shutdown_requested:
                asyncio.create_task(self.process_queue())
            else:
                self.coordinator._queue_processing_active = False

    async def _check_soaking_zones(self):
        """Check if any soaking zones are ready to continue."""
        now = asyncio.get_event_loop().time()
        ready_zones = []
        
        # Find zones that have finished soaking
        for zone_id, data in list(self.controller.soaking_zones.items()):
            if zone_id not in self.coordinator.zones:
                # Zone was deleted, remove from soaking zones
                if "cancel_callback" in data:
                    try:
                        data["cancel_callback"]()
                    except Exception as e:
                        _LOGGER.error("Error canceling callback for deleted zone: %s", e)
                del self.controller.soaking_zones[zone_id]
                continue
                
            if data.get("ready_at", now) <= now:
                ready_zones.append(zone_id)
                
                # Remove from soaking zones dict
                if "cancel_callback" in data:
                    try:
                        data["cancel_callback"]()
                    except Exception as e:
                        _LOGGER.error("Error canceling callback for ready zone: %s", e)
                    
                del self.controller.soaking_zones[zone_id]
        
        # Add ready zones to the front of the queue
        if ready_zones:
            # Add them in reverse order to maintain original priority
            async with self._queue_operation_lock:
                for zone_id in reversed(ready_zones):
                    self.controller.zone_queue.insert(0, zone_id)
                    
    async def clear_queue(self):
        """Clear the zone queue safely."""
        async with self._queue_operation_lock:
            self.controller.zone_queue.clear()