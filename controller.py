import asyncio
import math
import time
from datetime import datetime, timedelta

class Zone:
    """Represents a single sprinklers zone with its configuration and state."""
    def __init__(self, zone_id, name, entity_id, efficiency=1.0, cycle_max=None, soak=0, kc=1.0, include_rain=True, rate=15.0):
        self.zone_id = zone_id
        self.name = name or f"Zone{zone_id}"
        self.entity_id = entity_id              # Entity ID of the switch/valve controlling this zone
        self.efficiency = efficiency           # Current sprinklers efficiency (fraction of water effectively used)
        self.cycle_max = cycle_max             # Maximum seconds to water in one cycle before soaking (None or 0 means no split)
        self.soak_time = soak                  # Soak duration in seconds between cycles
        self.kc = kc                           # Crop coefficient for the zone (relative water need)
        self.include_rain = include_rain       # Whether to count rain for this zone (False for covered zones)
        self.rate = rate                       # Sprinkler precipitation rate (mm/hour)
        self.moisture_deficit = 0.0            # Current moisture deficit (mm) – positive means water needed, negative means surplus
        self.needed_time = 0.0                 # Calculated watering time needed (seconds) to compensate current deficit

class SprinklersController:
    """Main controller that manages scheduling and watering for all zones."""
    def __init__(self, hass, zones_conf, weather_entity=None, rain_sensor=None, rain_threshold=3.0, forecast_hours=24):
        self.hass = hass
        self.weather_entity = weather_entity
        self.rain_sensor = rain_sensor
        self.rain_threshold = rain_threshold
        self.forecast_hours = forecast_hours
        # Initialize Zone objects from configuration
        self.zones = []
        for idx, zconf in enumerate(zones_conf, start=1):
            zone = Zone(
                zone_id=idx,
                name=zconf.get("name"),
                entity_id=zconf["entity"],
                efficiency=zconf.get("efficiency", 1.0),
                cycle_max=zconf.get("cycle_max"),
                soak=zconf.get("soak", 0),
                kc=zconf.get("crop_coefficient", 1.0),
                include_rain=zconf.get("include_rain", True),
                rate=zconf.get("rate", 15.0)
            )
            self.zones.append(zone)
        # State flags for concurrency control
        self.is_running = False
        self.cancel_requested = False

    async def update_moisture(self):
        """Update each zone's moisture deficit based on weather (evapotranspiration minus precipitation)."""
        # Estimate evapotranspiration (ET0) for the past day using simple climate data
        et0 = 5.0  # default estimate (mm) if no weather data
        if self.weather_entity:
            state = self.hass.states.get(self.weather_entity)
            if state:
                attrs = state.attributes
                temp = attrs.get("temperature")
                humidity = attrs.get("humidity")
                # Simple ET0 estimation: higher temp -> more ET, higher humidity -> less ET
                if temp is not None and humidity is not None:
                    try:
                        t = float(temp)
                        h = float(humidity)
                        # Scale 5 mm reference by temperature and humidity factors
                        et0 = 5.0 * (t / 25.0) * (50.0 / max(h, 1.0))
                    except Exception:
                        # If parsing fails, use default ET0
                        et0 = 5.0
        # Get precipitation (rain) amount from the rain sensor, if provided (assuming it measures daily total in mm)
        rain_amount = 0.0
        if self.rain_sensor:
            state = self.hass.states.get(self.rain_sensor)
            if state:
                try:
                    rain_amount = float(state.state)
                except Exception:
                    rain_amount = 0.0
        # Update each zone's moisture deficit
        for zone in self.zones:
            # If zone is set to ignore rain (e.g., under a roof), treat rain as 0 for that zone
            effective_rain = rain_amount if zone.include_rain else 0.0
            # Increase moisture deficit by ET0 * crop_coefficient, decrease by effective rain
            zone.moisture_deficit += et0 * zone.kc - effective_rain
            # Note: moisture_deficit can be negative (means surplus moisture), which is fine and will carry over

    async def determine_watering_times(self):
        """Compute how long each zone needs to run to compensate its moisture deficit."""
        for zone in self.zones:
            if zone.moisture_deficit > 0:
                # Calculate needed water (mm) and convert to time (s) based on zone rate and efficiency
                needed_mm = zone.moisture_deficit
                # Convert sprinkler rate from mm/hr to mm/sec
                rate_per_sec = zone.rate / 3600.0
                if rate_per_sec <= 0 or zone.efficiency <= 0:
                    zone.needed_time = 0.0
                else:
                    # Time (s) = needed mm / (mm/sec * efficiency)
                    zone.needed_time = needed_mm / (rate_per_sec * zone.efficiency)
            else:
                zone.needed_time = 0.0

    async def should_skip_for_weather(self):
        """Decide if watering should be skipped due to sufficient rain (past or forecast)."""
        # Sum up forecasted precipitation within the next forecast_hours
        total_forecast_rain = 0.0
        if self.weather_entity:
            state = self.hass.states.get(self.weather_entity)
            if state:
                forecast = state.attributes.get("forecast")
                if isinstance(forecast, list):
                    now = datetime.now()
                    for entry in forecast:
                        # Parse each forecast entry's time and precipitation
                        f_time = None
                        if "datetime" in entry:
                            # 'datetime' is typically an ISO timestamp string
                            try:
                                f_time = datetime.fromisoformat(entry["datetime"])
                            except Exception:
                                # Some weather providers might not use strict ISO format
                                try:
                                    f_time = datetime.fromisoformat(entry["datetime"] + "+00:00")
                                except Exception:
                                    f_time = None
                        elif "dt" in entry:
                            # 'dt' might be a Unix timestamp
                            try:
                                f_time = datetime.fromtimestamp(entry["dt"])
                            except Exception:
                                f_time = None
                        # Determine precipitation amount in this entry
                        precip = None
                        if "precipitation" in entry:
                            precip = entry["precipitation"]
                        elif "rain" in entry:
                            precip = entry["rain"]
                        # If within forecast window, add to total
                        if f_time is None:
                            # If no time given, assume this is a daily forecast entry; include the first day by default
                            if precip is not None:
                                try:
                                    total_forecast_rain += float(precip)
                                except Exception:
                                    pass
                            break  # assume subsequent entries are future days beyond our window
                        else:
                            if f_time <= now + timedelta(hours=self.forecast_hours):
                                if precip is not None:
                                    try:
                                        total_forecast_rain += float(precip)
                                    except Exception:
                                        pass
                    # end for
        # Decide skip based on forecast rain
        if total_forecast_rain >= self.rain_threshold:
            # Forecast indicates enough rain to skip watering
            return True
        # Also skip if recent actual rain meets threshold
        if self.rain_sensor:
            state = self.hass.states.get(self.rain_sensor)
            if state:
                try:
                    recent_rain = float(state.state)
                except Exception:
                    recent_rain = 0.0
                if recent_rain >= self.rain_threshold:
                    return True
        return False

    async def execute_watering(self):
        """Execute the watering cycles for all zones that require sprinklers, honoring cycle and soak constraints."""
        # Compile a schedule of cycles for each zone needing water
        zones_to_water = [z for z in self.zones if z.needed_time and z.needed_time > 0]
        if not zones_to_water:
            return  # nothing to water
        self.is_running = True
        self.cancel_requested = False

        # Build cycle schedule for each zone
        schedule_list = []
        for zone in zones_to_water:
            total = zone.needed_time
            if zone.cycle_max and zone.cycle_max > 0 and total > zone.cycle_max:
                # Split into multiple cycles if total time exceeds cycle_max
                cycles = []
                remaining = total
                while remaining > 0:
                    cycles.append(min(zone.cycle_max, remaining))
                    remaining -= zone.cycle_max
                soak = zone.soak_time
                schedule_list.append({
                    "zone": zone, "cycles": cycles, "soak": soak,
                    "next_cycle_index": 0, "next_available": 0.0
                })
            else:
                # No need to split into cycles (or cycle_max not set)
                schedule_list.append({
                    "zone": zone, "cycles": [total], "soak": 0,
                    "next_cycle_index": 0, "next_available": 0.0
                })

        try:
            # Loop through scheduled cycles until all are done or cancellation is requested
            while True:
                if self.cancel_requested:
                    break  # stop requested, break out of watering loop
                # Find any remaining cycles
                entries_left = [entry for entry in schedule_list if entry["next_cycle_index"] < len(entry["cycles"])]
                if not entries_left:
                    break  # all watering cycles completed
                # Choose the next zone entry that is ready to run (soak complete)
                now = time.time()
                entry_to_run = None
                for entry in schedule_list:
                    if entry["next_cycle_index"] < len(entry["cycles"]) and entry["next_available"] <= now:
                        entry_to_run = entry
                        break
                if entry_to_run is None:
                    # No zone is currently available (all are soaking). Wait until the next one is ready.
                    next_start = min(entry["next_available"] for entry in entries_left)
                    wait_seconds = next_start - time.time()
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)
                    continue  # after waiting, loop will check again for available zone
                # Run the next cycle for the chosen zone
                zone = entry_to_run["zone"]
                cycle_idx = entry_to_run["next_cycle_index"]
                cycle_duration = entry_to_run["cycles"][cycle_idx]
                # Turn on the zone's switch
                await self.hass.services.async_call("switch", "turn_on", {"entity_id": zone.entity_id})
                # Watering for the cycle duration
                await asyncio.sleep(cycle_duration)
                # Turn off the zone's switch after the cycle completes
                await self.hass.services.async_call("switch", "turn_off", {"entity_id": zone.entity_id})
                # Mark this cycle as completed
                entry_to_run["next_cycle_index"] += 1
                if entry_to_run["next_cycle_index"] < len(entry_to_run["cycles"]):
                    # Schedule next cycle for this zone after soak period
                    entry_to_run["next_available"] = time.time() + entry_to_run["soak"]
            # end while

            # Post-watering: adjust moisture deficits and efficiencies if not canceled
            if not self.cancel_requested:
                for entry in schedule_list:
                    zone = entry["zone"]
                    # If moisture_deficit was positive, assume we've now provided that water (set to 0).
                    # (If deficit remains positive, it means we under-watered due to efficiency error.)
                    if zone.moisture_deficit > 0:
                        # We keep the remaining deficit (under-watering) for learning adjustment; do not reset to zero here.
                        remaining_deficit = zone.moisture_deficit
                    else:
                        remaining_deficit = 0.0
                    zone.moisture_deficit = remaining_deficit  # surplus (negative) is retained, deficit if any is retained for next time
                # Efficiency learning: adjust efficiency based on outcome for each watered zone
                for entry in schedule_list:
                    zone = entry["zone"]
                    if zone.moisture_deficit < 0:
                        # Overshot (moisture surplus): the zone was over-watered, increase efficiency (we needed less water than thought)
                        zone.efficiency = min(1.0, zone.efficiency + 0.1)
                    elif zone.moisture_deficit > 0:
                        # Undershot (moisture still deficit): zone was under-watered, decrease efficiency (we needed more water than thought)
                        zone.efficiency = max(0.1, zone.efficiency - 0.1)
        finally:
            # Ensure any running zone is turned off if cancellation occurs and clean up state
            if self.cancel_requested:
                for entry in schedule_list:
                    zone = entry["zone"]
                    # Turn off zone if it was currently on (the loop turns it off after each cycle, so this is just a safeguard)
                    try:
                        await self.hass.services.async_call("switch", "turn_off", {"entity_id": zone.entity_id})
                    except Exception:
                        pass
                    # Partially adjust deficit for the portion of water that was delivered before cancel
                    if entry["next_cycle_index"] > 0:
                        # Calculate fraction of total scheduled water that was delivered
                        done_cycles = entry["next_cycle_index"]
                        total_cycles = len(entry["cycles"])
                        delivered_fraction = sum(entry["cycles"][:done_cycles]) / sum(entry["cycles"])
                        # Reduce the moisture deficit proportionally to the water already applied
                        zone.moisture_deficit *= (1 - delivered_fraction)
            # Reset running state
            self.is_running = False

    async def run_schedule(self):
        """Run the scheduled sprinklers check and watering sequence (called at the scheduled time each day)."""
        if self.is_running:
            # If a watering sequence is already running (should not happen with one schedule), do nothing
            return
        # Update moisture deficits from weather data and determine needed watering time for each zone
        await self.update_moisture()
        await self.determine_watering_times()
        # Decide if we should skip watering due to rain conditions
        if await self.should_skip_for_weather():
            # Skipping watering today; do not reset moisture deficit so it carries to next day
            return
        # Execute watering cycles for all zones that require water
        await self.execute_watering()

    async def start_manual(self, zones=None):
        """Manually start sprinklers immediately. Optionally specify a subset of zones to water."""
        if self.is_running:
            return  # avoid starting if already running
        # Determine which zones to run. `zones` can be a list of zone names/IDs or a single value.
        target_zones = []
        if zones:
            # Accept zone identifiers as names, entity_ids, or indices
            if not isinstance(zones, list):
                zones = [zones]
            for zid in zones:
                for zone in self.zones:
                    if isinstance(zid, str):
                        if zid == zone.name or zid == zone.entity_id:
                            target_zones.append(zone)
                    elif isinstance(zid, int):
                        if zid == zone.zone_id:
                            target_zones.append(zone)
            # Remove duplicates and preserve order
            target_zones = [*dict.fromkeys(target_zones)]
        if not zones or not target_zones:
            # If no specific zones specified, or none of the identifiers matched, default to all zones
            target_zones = [z for z in self.zones]

        # Ensure moisture update before manual run so we know current deficits (optional; can also run even if not needed)
        await self.update_moisture()
        await self.determine_watering_times()
        # If a zone has no deficit (needed_time = 0) but is requested for manual run, assign a minimal run time (for manual override)
        for zone in target_zones:
            if zone.needed_time <= 0:
                zone.needed_time = 60  # e.g. 60 seconds default for manual run if no water needed

        # Temporarily zero out other zones' needed_time to run only target zones
        saved_times = {z.zone_id: z.needed_time for z in self.zones}
        for zone in self.zones:
            if zone not in target_zones:
                zone.needed_time = 0.0

        # Execute watering for the target zones
        await self.execute_watering()

        # Restore other zone times (so their deficits carry over correctly if not watered)
        for zone in self.zones:
            if zone.zone_id in saved_times:
                zone.needed_time = saved_times[zone.zone_id]
        # (Moisture deficits were not cleared for zones we didn't water, so they remain for future schedule.)

    async def cancel(self):
        """Cancel the currently running sprinklers sequence as soon as possible."""
        if self.is_running:
            self.cancel_requested = True
