"""The Smart Sprinklers integration."""
import asyncio
import logging
from datetime import datetime, timedelta


import voluptuous as vol


from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval, async_call_later
from homeassistant.helpers import entity_registry
from homeassistant.util import dt as dt_util


from .const import (
   DOMAIN,
   # Configuration constants
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
   CONF_SYSTEM_ENABLED,
   CONF_RAIN_SENSOR,
   CONF_RAIN_THRESHOLD,
   # Default values
   DEFAULT_FREEZE_THRESHOLD,
   DEFAULT_MIN_MOISTURE,
   DEFAULT_MAX_MOISTURE,
   DEFAULT_CYCLE_TIME,
   DEFAULT_SOAK_TIME,
   DEFAULT_RAIN_THRESHOLD,
   # Service names
   SERVICE_REFRESH_FORECAST,
   SERVICE_RESET_STATISTICS,
   # Attribute names - critical for the tests
   ATTR_ZONE,
   ATTR_LAST_WATERED,
   ATTR_NEXT_WATERING,
   ATTR_CYCLE_COUNT,
   ATTR_CURRENT_CYCLE,
   ATTR_SOAKING_EFFICIENCY,
   ATTR_MOISTURE_HISTORY,
   ATTR_ABSORPTION_RATE,
   ATTR_ESTIMATED_WATERING_DURATION,
   ATTR_MAX_WATERING_TIME,
   ATTR_MOISTURE_DEFICIT,
   ATTR_DAILY_ET,
   ATTR_DAILY_PRECIPITATION,
   # States
   STATE_ENABLED,
   STATE_DISABLED,
   # Zone states
   ZONE_STATE_IDLE,
   ZONE_STATE_WATERING,
   ZONE_STATE_SOAKING,
   ZONE_STATE_MEASURING,
   DEFAULT_MAX_WATERING_HOURS,
   DEFAULT_MAX_WATERING_MINUTES,
)


from .algorithms.absorption import AbsorptionLearner
from .algorithms.watering import calculate_watering_duration


_LOGGER = logging.getLogger(__name__)


PLATFORMS = ["sensor", "switch"]


SCAN_INTERVAL = timedelta(minutes=5)
DAILY_UPDATE_HOUR = 0  # Midnight update for ET and precipitation calculations


async def async_setup(hass: HomeAssistant, config: dict):
   """Set up the Smart Sprinklers component."""
   hass.data.setdefault(DOMAIN, {})
   return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
   """Set up Smart Sprinklers from a config entry."""
   hass.data.setdefault(DOMAIN, {})


   # Create coordinator instance for this entry
   coordinator = SprinklersCoordinator(hass, entry)


   try:
       await coordinator.async_setup()
       hass.data[DOMAIN][entry.entry_id] = coordinator
   except Exception as err:
       _LOGGER.error("Failed to set up Smart Sprinklers: %s", err)
       return False


   # Set up platforms using the non-deprecated method
   await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


   # Register services
   hass.services.async_register(
       DOMAIN,
       SERVICE_REFRESH_FORECAST,
       coordinator.async_service_refresh_forecast
   )


   hass.services.async_register(
       DOMAIN,
       SERVICE_RESET_STATISTICS,
       coordinator.async_service_reset_statistics
   )

   hass.services.async_register(
       DOMAIN,
       "update_moisture_deficit",
       coordinator.async_service_update_moisture_deficit
   )

   hass.services.async_register(
       DOMAIN,
       "force_et_calculation", 
       coordinator.async_service_force_et_calculation
   )

   hass.services.async_register(
       DOMAIN,
       "force_precipitation_calculation",
       coordinator.async_service_force_precipitation_calculation
   )


   return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
   """Unload a config entry."""
   # Unload platforms using the non-deprecated method
   unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


   # Cancel any scheduled tasks and clean up
   if unload_ok:
       coordinator = hass.data[DOMAIN].pop(entry.entry_id)
       await coordinator.async_unload()


   return unload_ok


async def fetch_forecast(hass, weather_entity, forecast_type='daily'):
   """Fetch forecast data using weather.get_forecasts service."""
   try:
       response = await hass.services.async_call(
           'weather',
           'get_forecasts',
           {
               'entity_id': weather_entity,
               'type': forecast_type
           },
           blocking=True,
           return_response=True
       )
       if response and isinstance(response, dict):
           return response.get(weather_entity, {}).get('forecast', [])
       return []
   except Exception as e:
       _LOGGER.error("Error fetching forecast data: %s", e)
       return []


class SprinklersCoordinator:
   """Class to coordinate sprinklers activities."""


   def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
       """Initialize the sprinklers coordinator."""
       self.hass = hass
       self.config_entry = config_entry
       self.zones = {}
       
       # Modified zone tracking to support interleaving
       self.active_zone = None  # The zone that is currently watering
       self.soaking_zones = {}  # Dict of zone_id -> {"ready_at": timestamp, "pre_soak_moisture": value}
       
       self.weather_entity = None
       self.schedule_entity = None
       self.rain_sensor = None
       self.rain_threshold = DEFAULT_RAIN_THRESHOLD
       self.forecast_data = None
       self.last_forecast_update = None
       self._unsub_interval = None
       self._unsub_schedule_check = None
       self._unsub_daily_update = None
       self.zone_queue = []
       self.absorption_learners = {}
      
       # Get system enabled state from config, default to True if not present
       self._system_enabled = config_entry.data.get(CONF_SYSTEM_ENABLED, True)
       self._pending_tasks = []
       
       # Enhanced concurrency control
       self._system_lock = asyncio.Lock()  # Global lock for system-wide operations
       self._process_queue_lock = asyncio.Lock()  # Specific lock for queue processing
       self._queue_processing_active = False
       self._sprinklers_active = False  # Flag to track if any sprinklers is active
       self._manual_operation_requested = False  # Track if manual operation is in progress
       
       # For tracking weather/moisture deficit
       self.daily_et = {}  # Daily evapotranspiration by zone
       self.daily_precipitation = 0.0  # Daily precipitation in mm


   async def async_setup(self):       
       """Set up the coordinator."""
       config = dict(self.config_entry.data)
        
       # Get weather entity
       self.weather_entity = config.get(CONF_WEATHER_ENTITY)
       if not self.weather_entity:
           _LOGGER.warning("No weather entity specified, some functionality will be limited")
        
       # Get schedule entity
       self.schedule_entity = config.get(CONF_SCHEDULE_ENTITY)
       if self.schedule_entity and not self.hass.states.get(self.schedule_entity):
           _LOGGER.warning("Schedule entity %s not found, will retry later", self.schedule_entity)
            
       # Get rain sensor and threshold configuration
       self.rain_sensor = config.get(CONF_RAIN_SENSOR)
       self.rain_threshold = config.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD)
        
       # Log the configuration
       _LOGGER.info("Smart Sprinklers configured with: Weather=%s, Rain Sensor=%s, Rain Threshold=%.1fmm",
                    self.weather_entity, self.rain_sensor, self.rain_threshold)
                          
       # Configure zones
       for zone_config in config.get(CONF_ZONES, []):
           zone_id = zone_config[CONF_ZONE_NAME].lower().replace(" ", "_")
          
           # Calculate total max watering time in minutes
           max_watering_hours = zone_config.get(CONF_ZONE_MAX_WATERING_HOURS, DEFAULT_MAX_WATERING_HOURS)
           max_watering_minutes = zone_config.get(CONF_ZONE_MAX_WATERING_MINUTES, DEFAULT_MAX_WATERING_MINUTES)
           max_watering_time = max_watering_hours * 60 + max_watering_minutes
          
           # Configure the zone even if sensors aren't available yet
           self.zones[zone_id] = {
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
               "state": "idle",
               "last_watered": None,
               "next_watering": None,
               "cycle_count": 0,
               "current_cycle": 0,
               "moisture_history": [],
               "soaking_efficiency": 0,
               "moisture_deficit": 0.0,  # Added: tracks moisture deficit over time
           }
           
           # Initialize daily ET for this zone
           self.daily_et[zone_id] = 0.0
          
           # Initialize absorption learner for this zone
           self.absorption_learners[zone_id] = AbsorptionLearner()
      
       # Get configuration values
       self.freeze_threshold = config.get(CONF_FREEZE_THRESHOLD, DEFAULT_FREEZE_THRESHOLD)
       self.cycle_time = config.get(CONF_CYCLE_TIME, DEFAULT_CYCLE_TIME)
       self.soak_time = config.get(CONF_SOAK_TIME, DEFAULT_SOAK_TIME)
      
       # Get initial forecast data - this won't raise an error anymore
       await self.async_update_forecast()
      
       # Schedule regular updates
       self._unsub_interval = async_track_time_interval(
           self.hass, self.async_update, SCAN_INTERVAL
       )
      
       # Start schedule checker
       self._unsub_schedule_check = async_track_time_interval(
           self.hass, self.async_check_schedule, timedelta(minutes=1)
       )
       
       # Schedule daily ET and moisture deficit updates
       now = dt_util.now()
       next_midnight = now.replace(hour=DAILY_UPDATE_HOUR, minute=0, second=0, microsecond=0)
       if next_midnight < now:
           next_midnight = next_midnight + timedelta(days=1)
           
       _LOGGER.info("Scheduling daily ET update at %s", next_midnight)
       self._unsub_daily_update = async_call_later(
           self.hass,
           (next_midnight - now).total_seconds(),
           self.async_daily_update
       )
      
       return True


   async def async_unload(self):
       """Cancel all scheduled tasks."""
       # First acquire system lock to prevent any new operations
       async with self._system_lock:
           if self._unsub_interval:
               self._unsub_interval()
          
           if self._unsub_schedule_check:
               self._unsub_schedule_check()
               
           if self._unsub_daily_update:
               self._unsub_daily_update()
          
           # Cancel any pending tasks properly
           for cancel_callback in self._pending_tasks:
               cancel_callback()  # This calls the cancel function
          
           self._pending_tasks = []
          
           # Turn off all zones
           for zone_id, zone in self.zones.items():
               await self.async_turn_off_zone(zone_id)
           
           # Reset all operational flags
           self._queue_processing_active = False
           self._sprinklers_active = False
           self._manual_operation_requested = False
           self.active_zone = None
           self.soaking_zones = {}


   @property
   def system_enabled(self):
       """Return whether the system is enabled."""
       return self._system_enabled


   @system_enabled.setter
   def system_enabled(self, value):
       """Set the system enabled state."""
       if self._system_enabled != value:
           self._system_enabled = value
           _LOGGER.info("Smart Sprinklers system is now %s", STATE_ENABLED if value else STATE_DISABLED)
          
           # Persist the state in config entry data
           new_data = dict(self.config_entry.data)
           new_data[CONF_SYSTEM_ENABLED] = value
           self.hass.config_entries.async_update_entry(
               self.config_entry, data=new_data
           )


   async def async_enable_system(self):
       """Enable the sprinklers system."""
       async with self._system_lock:
           if not self._system_enabled:
               self.system_enabled = True  # Use the property setter to persist the state
              
               # Restart processing if there's a queue and no active processing
               if self.zone_queue and not self._sprinklers_active:
                   await self.async_process_queue()


   async def async_disable_system(self):
       """Disable the sprinklers system."""
       async with self._system_lock:
           if self._system_enabled:
               self.system_enabled = False  # Use the property setter to persist the state
              
               # If there's an active zone, stop it
               if self.active_zone:
                   zone_id = self.active_zone
                   await self.async_turn_off_zone(zone_id)
                  
                   # Set zone state to idle
                   zone = self.zones[zone_id]
                   zone["state"] = ZONE_STATE_IDLE
                  
                   # Clear active zone
                   self.active_zone = None
               
               # Also clean up any soaking zones
               for zone_id in list(self.soaking_zones.keys()):
                   self.zones[zone_id]["state"] = ZONE_STATE_IDLE
               
               # Clear soaking zones dictionary
               self.soaking_zones.clear()
                   
               # Reset operational flags
               self._queue_processing_active = False
               self._sprinklers_active = False
               self._manual_operation_requested = False
                  
               # Send notification
               await self.async_send_notification(
                   f"Sprinklers system disabled - all zones stopped"
               )

   async def async_daily_update(self, now=None):
       """Handle daily update of evapotranspiration and moisture deficit."""
       _LOGGER.info("Performing daily moisture deficit update")
       
       # Calculate evapotranspiration and precipitation
       await self.async_calculate_et()
       await self.async_calculate_precipitation()
       
       # Update moisture deficits for each zone
       for zone_id, zone in self.zones.items():
           zone_et = self.daily_et.get(zone_id, 0.0)
           effective_rain = self.daily_precipitation
           
           # Update moisture deficit
           # ET increases deficit, precipitation decreases it
           # Negative deficit means surplus moisture
           old_deficit = zone.get("moisture_deficit", 0.0)
           new_deficit = old_deficit + zone_et - effective_rain
           
           # Ensure deficit isn't negative (would mean excess water beyond field capacity)
           zone["moisture_deficit"] = max(0.0, new_deficit)
           
           _LOGGER.info(
               "Zone %s: ET=%.2fmm, Rain=%.2fmm, Old deficit=%.2fmm, New deficit=%.2fmm",
               zone["name"], zone_et, effective_rain, old_deficit, zone["moisture_deficit"]
           )
       
       # Reset daily counters
       self.daily_et = {zone_id: 0.0 for zone_id in self.zones}
       self.daily_precipitation = 0.0
       
       # Schedule next daily update
       next_midnight = (dt_util.now() + timedelta(days=1)).replace(
           hour=DAILY_UPDATE_HOUR, minute=0, second=0, microsecond=0
       )
       
       _LOGGER.info("Next daily ET update scheduled for %s", next_midnight)
       self._unsub_daily_update = async_call_later(
           self.hass,
           (next_midnight - dt_util.now()).total_seconds(),
           self.async_daily_update
       )

   async def async_calculate_et(self):
       """Calculate evapotranspiration based on weather data."""
       if not self.weather_entity:
           _LOGGER.warning("No weather entity, using default ET values")
           # Set default ET for each zone (5mm per day is a typical reference value)
           for zone_id in self.zones:
               self.daily_et[zone_id] = 5.0
           return
           
       try:
           # Get weather data
           weather_state = self.hass.states.get(self.weather_entity)
           if not weather_state:
               _LOGGER.warning("Weather entity not found, using default ET values")
               for zone_id in self.zones:
                   self.daily_et[zone_id] = 5.0
               return
               
           # Use weather data to estimate ET
           attrs = weather_state.attributes
           temp = attrs.get("temperature")
           humidity = attrs.get("humidity")
           
           # Simple ET calculation based on temperature and humidity
           # This is a simplification - a real implementation would use the 
           # Penman-Monteith equation or similar, but that requires more data
           reference_et = 5.0  # Default reference ET (mm/day)
           
           if temp is not None and humidity is not None:
               try:
                   t = float(temp)
                   h = float(humidity)
                   
                   # Adjust reference ET based on temperature and humidity
                   # Higher temp -> more ET, higher humidity -> less ET
                   temp_factor = 1.0
                   if t < 10:
                       temp_factor = 0.6  # Low temperature reduces ET
                   elif t > 25:
                       temp_factor = 1.3  # High temperature increases ET
                       
                   humidity_factor = 1.0
                   if h > 70:
                       humidity_factor = 0.8  # High humidity reduces ET
                   elif h < 40:
                       humidity_factor = 1.2  # Low humidity increases ET
                       
                   adjusted_et = reference_et * temp_factor * humidity_factor
                   
                   # Apply to each zone with crop coefficient
                   for zone_id, zone in self.zones.items():
                       # Default crop coefficient of 1.0
                       # Could be customized per zone type in the future
                       crop_coefficient = 1.0  
                       self.daily_et[zone_id] = adjusted_et * crop_coefficient
                       
                   _LOGGER.info(
                       "Calculated ET: %.2fmm (temp=%.1f°C, humidity=%.1f%%)",
                       adjusted_et, t, h
                   )
                   
               except (ValueError, TypeError) as e:
                   _LOGGER.warning("Error calculating ET from weather data: %s", e)
                   for zone_id in self.zones:
                       self.daily_et[zone_id] = reference_et
           else:
               _LOGGER.warning("Incomplete weather data, using default ET")
               for zone_id in self.zones:
                   self.daily_et[zone_id] = reference_et
                   
       except Exception as e:
           _LOGGER.error("Error in ET calculation: %s", e)
           # Fallback to default
           for zone_id in self.zones:
               self.daily_et[zone_id] = 5.0
   
   async def async_calculate_precipitation(self):
       """Calculate precipitation from rain sensor and forecast."""
       precipitation = 0.0
       
       # Check rain sensor if configured
       if self.rain_sensor:
           try:
               rain_state = self.hass.states.get(self.rain_sensor)
               if rain_state:
                   # Try to parse the rain value (mm)
                   try:
                       precipitation = float(rain_state.state)
                       _LOGGER.info("Rain sensor reports %.2fmm precipitation", precipitation)
                   except (ValueError, TypeError):
                       _LOGGER.warning("Could not parse rain sensor value: %s", rain_state.state)
           except Exception as e:
               _LOGGER.error("Error reading rain sensor: %s", e)
       
       # If no rain sensor or invalid reading, try to get precipitation from weather entity
       if precipitation <= 0 and self.weather_entity:
           try:
               weather_state = self.hass.states.get(self.weather_entity)
               if weather_state:
                   # Some weather entities provide recent precipitation
                   if "precipitation" in weather_state.attributes:
                       try:
                           precip = weather_state.attributes.get("precipitation")
                           if precip is not None:
                               precipitation = float(precip)
                               _LOGGER.info(
                                   "Weather entity reports %.2fmm precipitation", 
                                   precipitation
                               )
                       except (ValueError, TypeError):
                           pass
           except Exception as e:
               _LOGGER.error("Error getting precipitation from weather entity: %s", e)
               
       # Store the calculated precipitation
       self.daily_precipitation = precipitation

   async def async_update(self, now=None):
       """Update sensor data and make sprinklers decisions."""
       # Use system lock to ensure update doesn't interfere with other operations
       async with self._system_lock:
           # Skip if system is disabled or if sprinklers is already active
           if not self._system_enabled or self._sprinklers_active:
               return
          
           # Update forecast if needed
           forecast_age = (
               datetime.now() - self.last_forecast_update
               if self.last_forecast_update else timedelta(hours=1)
           )
          
           if forecast_age > timedelta(hours=1):
               await self.async_update_forecast()
          
           # Process each zone
           for zone_id, zone in self.zones.items():
               await self.async_process_zone(zone_id)


   async def async_update_forecast(self):
       """Update weather forecast data."""
       try:
           if not self.weather_entity:
               _LOGGER.warning("No weather entity configured, forecast data unavailable")
               return
          
           weather_state = self.hass.states.get(self.weather_entity)
           if not weather_state:
               _LOGGER.warning("Weather entity %s not yet available", self.weather_entity)
               return
          
           # Try new API method first
           forecast_data = await fetch_forecast(self.hass, self.weather_entity)
          
           # If new method fails, try legacy method as fallback
           if not forecast_data:
               _LOGGER.debug("Using legacy method to get forecast data")
               forecast_data = weather_state.attributes.get("forecast", [])
          
           self.forecast_data = forecast_data
           self.last_forecast_update = datetime.now()
          
           if not self.forecast_data:
               _LOGGER.warning("Weather entity %s has no forecast data", self.weather_entity)
           else:
               _LOGGER.debug("Updated forecast data with %d entries", len(self.forecast_data))
          
       except Exception as e:
           _LOGGER.error("Error updating forecast: %s", e)


   def is_rain_forecasted(self, hours=24):
        """Check if rain is forecasted in the next n hours."""
        if not self.forecast_data:
            return False
        
        now = dt_util.now()
        forecast_window = now + timedelta(hours=hours)
        total_forecast_rain = 0.0
        
        for forecast in self.forecast_data:
            if "datetime" not in forecast:
                continue
            
            forecast_time = dt_util.parse_datetime(forecast["datetime"])
            if not forecast_time:
                continue
            
            if now <= forecast_time <= forecast_window:
                # Check if precipitation is forecasted
                if forecast.get("precipitation") is not None:
                    try:
                        precipitation = float(forecast["precipitation"])
                        total_forecast_rain += precipitation
                        if precipitation > 0:
                            _LOGGER.debug(
                                "Rain forecasted at %s: %.2fmm", 
                                forecast_time.isoformat(), precipitation
                            )
                    except (ValueError, TypeError):
                        pass
        
        # Return True if the total forecasted rain exceeds the threshold
        exceeds_threshold = total_forecast_rain >= self.rain_threshold
        if exceeds_threshold:
            _LOGGER.info(
                "Total forecasted rain (%.2fmm) exceeds threshold (%.2fmm)",
                total_forecast_rain, self.rain_threshold
            )
        return exceeds_threshold


   def is_freezing_forecasted(self, hours=12):
       """Check if freezing temperatures are forecasted in the next n hours."""
       if not self.forecast_data:
           return False
      
       if not self.weather_entity:
           return False
      
       now = dt_util.now()
       forecast_window = now + timedelta(hours=hours)
      
       # Check current temperature
       weather_state = self.hass.states.get(self.weather_entity)
       if weather_state:
           try:
               current_temp = weather_state.attributes.get("temperature")
               if current_temp is not None and current_temp <= self.freeze_threshold:
                   return True
           except (TypeError, ValueError):
               pass  # Skip if current temperature isn't available
      
       for forecast in self.forecast_data:
           if "datetime" not in forecast or "temperature" not in forecast:
               continue
          
           forecast_time = dt_util.parse_datetime(forecast["datetime"])
           if not forecast_time:
               continue
          
           if now <= forecast_time <= forecast_window:
               if forecast["temperature"] <= self.freeze_threshold:
                   return True
          
       return False


   async def async_process_zone(self, zone_id):
       """Process a zone to determine if it needs watering."""
       # Skip if system is disabled or if sprinklers is already active
       if not self._system_enabled:
           return
           
       # Skip if the zone is already being processed (active or soaking)
       if self.active_zone == zone_id or zone_id in self.soaking_zones:
           return
      
       zone = self.zones[zone_id]
      
       # Skip if the zone is already in an active state
       if zone["state"] in [ZONE_STATE_WATERING, ZONE_STATE_SOAKING]:
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
          
           # Record moisture for learning
           zone["moisture_history"].append({
               "timestamp": datetime.now().isoformat(),
               "value": current_moisture
           })
          
           # Keep history manageable (last 30 days)
           max_history = 30 * 24 * 12  # 30 days at 5-minute intervals
           if len(zone["moisture_history"]) > max_history:
               zone["moisture_history"] = zone["moisture_history"][-max_history:]
               
           # NEW: Update moisture deficit based on sensor reading if moisture level dropped
           # This helps keep deficit tracking in sync with sensor data
           if len(zone["moisture_history"]) >= 2:
               previous_reading = zone["moisture_history"][-2]["value"]
               moisture_drop = previous_reading - current_moisture
               if moisture_drop > 0:
                   # Convert moisture percentage drop to mm equivalent using a conversion factor
                   # Approximate: 1% moisture change = ~1mm water depth
                   mm_equivalent = moisture_drop * 1.0
                   zone["moisture_deficit"] += mm_equivalent
                   _LOGGER.debug(
                       "Zone %s: Moisture drop of %.1f%% (%.1fmm), adjusted deficit to %.1fmm",
                       zone["name"], moisture_drop, mm_equivalent, zone["moisture_deficit"]
                   )
          
           # Check if watering is needed - either based on moisture sensor or deficit
           watering_needed = False
           
           # Moisture sensor check
           if current_moisture <= zone["min_moisture"]:
               watering_needed = True
               _LOGGER.debug(
                   "Zone %s needs water due to moisture level (%.1f%% < %.1f%%)",
                   zone["name"], current_moisture, zone["min_moisture"]
               )
               
           # Moisture deficit check - if deficit exceeds threshold (e.g. 5mm)
           # This provides a fallback if moisture sensor is unreliable
           elif zone.get("moisture_deficit", 0) >= 5.0:  # 5mm deficit threshold
               watering_needed = True
               _LOGGER.debug(
                   "Zone %s needs water due to moisture deficit (%.1fmm)",
                   zone["name"], zone.get("moisture_deficit", 0)
               )
               
           if watering_needed:
               # Check if we can water based on weather and schedule
               if (
                   self.is_in_schedule()
                   and not self.is_rain_forecasted()
                   and not self.is_freezing_forecasted()
                   and current_temp > self.freeze_threshold
               ):
                   # Add to queue if not already there
                   if zone_id not in self.zone_queue and zone_id not in self.soaking_zones:
                       self.zone_queue.append(zone_id)
                       _LOGGER.info(
                           "Zone %s added to watering queue (moisture: %.1f%%, deficit: %.1fmm)", 
                           zone["name"], current_moisture, zone.get("moisture_deficit", 0)
                       )
                      
                       # Send notification
                       await self.async_send_notification(
                           f"Zone {zone['name']} added to watering queue "
                           f"(moisture: {current_moisture}%, deficit: {zone.get('moisture_deficit', 0):.1f}mm)"
                       )
                      
                       # Start queue processing if not already active
                       # We can process the queue if:
                       # 1. No zone is currently being watered (active_zone is None)
                       # 2. Queue processing isn't actively running
                       if not self.active_zone and not self._queue_processing_active:
                           await self.async_process_queue()
               else:
                   # Log why watering is skipped
                   if not self.is_in_schedule():
                       _LOGGER.debug("Zone %s needs water but outside of schedule", zone["name"])
                   elif self.is_rain_forecasted():
                       _LOGGER.info(
                           "Zone %s needs water but rain is forecasted - skipping watering",
                           zone["name"]
                       )
                   elif self.is_freezing_forecasted() or current_temp <= self.freeze_threshold:
                       _LOGGER.info(
                           "Zone %s needs water but freezing temperatures are forecasted - skipping watering",
                           zone["name"]
                       )
              
       except Exception as e:
           _LOGGER.error("Error processing zone %s: %s", zone["name"], e)


   def is_in_schedule(self):
       """Check if current time is within scheduled watering window."""
       # If no schedule entity is defined, always return true (no schedule restriction)
       if not self.schedule_entity:
           return True
      
       schedule_state = self.hass.states.get(self.schedule_entity)
       if not schedule_state:
           _LOGGER.debug("Schedule entity %s not available", self.schedule_entity)
           return True  # Default to allowing watering if the schedule entity isn't available
      
       # Schedule helper's state is 'on' when the current time is within the schedule
       return schedule_state.state == 'on'


   def is_schedule_active(self):
       """Check if current time is within scheduled watering window and system is enabled."""
       # First check if system is enabled
       if not self._system_enabled:
           return False
      
       # Then check if we're in the schedule window
       return self.is_in_schedule()


   def get_schedule_remaining_time(self):
       """Get the number of minutes remaining in the current schedule window."""
       if not self.schedule_entity:
           return None  # No schedule constraint
      
       schedule_state = self.hass.states.get(self.schedule_entity)
       if not schedule_state or schedule_state.state != 'on':
           return 0  # Not in schedule or schedule entity not found
      
       # Try to get the next state change from the attributes
       next_change = schedule_state.attributes.get("next_change")
       if not next_change:
           return None  # Can't determine remaining time
      
       try:
           next_change_time = dt_util.parse_datetime(next_change)
           if not next_change_time:
               return None
          
           now = dt_util.now()
           time_diff = next_change_time - now
          
           # Convert to minutes
           minutes_remaining = time_diff.total_seconds() / 60
           return max(0, minutes_remaining)
       except Exception as e:
           _LOGGER.warning("Error calculating schedule remaining time: %s", e)
           return None  # Can't determine remaining time


   async def async_process_queue(self):
       """Process the zone queue, ensuring optimal interleaving during soak periods."""
       # Skip if system is disabled
       if not self._system_enabled:
           _LOGGER.debug("System disabled, skipping queue processing")
           return

       # Check if we're still in the watering schedule
       if not self.is_in_schedule():
           _LOGGER.debug("Outside of watering schedule, queue processing skipped")
           self.zone_queue.clear()  # Clear queue if outside schedule
           self.soaking_zones.clear()  # Clean up soaking zones too
           return
      
       # Use a lock to prevent concurrent queue processing
       if not await self._process_queue_lock.acquire(timeout=1):
           _LOGGER.debug("Queue processing lock could not be acquired, another process may be running")
           return
       
       try:
           # Set flag to indicate processing is active
           self._queue_processing_active = True
           self._sprinklers_active = True
          
           # Check if there's any zone currently being watered
           if self.active_zone:
               _LOGGER.debug("Already watering zone %s, queue processing skipped",
                           self.zones[self.active_zone]["name"])
               return
          
           # Handle soaking zones that are ready to continue watering
           now = datetime.now().timestamp()
           ready_soaking_zones = []
           
           # Find any soaking zones that are ready to continue their cycle
           for zone_id, info in list(self.soaking_zones.items()):
               if info["ready_at"] <= now:
                   ready_soaking_zones.append((zone_id, info["pre_soak_moisture"]))
                   # Remove from soaking but don't modify dict during iteration
           
           # Remove ready zones from soaking_zones dict
           for zone_id, _ in ready_soaking_zones:
               self.soaking_zones.pop(zone_id)
           
           # Add ready soaking zones to the front of the queue for priority
           for zone_id, pre_soak_moisture in ready_soaking_zones:
               # Ensure no duplicates when adding back to queue
               if zone_id in self.zone_queue:
                   self.zone_queue.remove(zone_id)
               # Add to front of queue to continue interrupted cycle
               self.zone_queue.insert(0, zone_id)
               
               _LOGGER.info("Zone %s finished soaking, adding back to queue for next cycle",
                           self.zones[zone_id]["name"])
          
           # If there's still nothing in the queue after processing soaking zones
           if not self.zone_queue:
               _LOGGER.debug("No zones in queue after processing soaking zones")
               self._queue_processing_active = False
               self._sprinklers_active = False
               return

           # Check how much time we have available based on schedule end time
           remaining_time = self.get_schedule_remaining_time()
           if remaining_time is not None and remaining_time <= 0:
               _LOGGER.debug("No time remaining in schedule")
               self.zone_queue.clear()  # Clear queue if no time remaining
               return
              
           # If multiple zones are waiting, calculate optimal distribution
           if len(self.zone_queue) > 1 and remaining_time is not None:
               # Prepare data for distribute_watering_time
               zones_data = []
               for zone_id in self.zone_queue:
                   zone = self.zones[zone_id]
                   try:
                       moisture_state = self.hass.states.get(zone["moisture_sensor"])
                       current_moisture = float(moisture_state.state) if moisture_state else 0
                   except (ValueError, TypeError):
                       _LOGGER.warning("Invalid moisture reading for zone %s", zone["name"])
                       current_moisture = 0
                  
                   # NEW: Include moisture deficit in distribution calculation
                   zones_data.append({
                       "current_moisture": current_moisture,
                       "target_moisture": zone["max_moisture"],
                       "absorption_rate": self.absorption_learners[zone_id].get_rate(),
                       "moisture_deficit": zone.get("moisture_deficit", 0.0)
                   })
              
               # Import here to avoid circular imports
               from .algorithms.watering import distribute_watering_time
              
               # Distribute watering time
               distributed_cycles = distribute_watering_time(
                   zones_data,
                   remaining_time,
                   self.cycle_time
               )
              
               # Update zone cycle counts based on distribution
               new_queue = []
               for i, zone_id in enumerate(self.zone_queue):
                   zone = self.zones[zone_id]
                   cycles = distributed_cycles.get(i, 0)
                  
                   if cycles > 0:
                       zone[ATTR_CYCLE_COUNT] = cycles
                       new_queue.append(zone_id)  # Keep this zone in queue
                   else:
                       _LOGGER.info(
                           "Zone %s skipped due to time constraints",
                           zone["name"]
                       )
                       # Don't add to new queue (effectively removing from queue)
              
               # Replace queue with filtered version
               self.zone_queue = new_queue
          
           # Get the next zone from the queue
           if not self.zone_queue:
               self._queue_processing_active = False
               self._sprinklers_active = len(self.soaking_zones) > 0  # Still active if zones are soaking
               return
          
           zone_id = self.zone_queue.pop(0)  # Remove from queue as we're processing it
           zone = self.zones[zone_id]
          
           # Get current moisture reading
           try:
               moisture_state = self.hass.states.get(zone["moisture_sensor"])
               if not moisture_state:
                   _LOGGER.warning("Moisture sensor not found for zone %s", zone["name"])
                   # Skip this zone
                   self._queue_processing_active = False
                   # Process the next zone in queue immediately
                   await self.async_process_queue()
                   return
              
               current_moisture = float(moisture_state.state)
              
               # If continuing a cycle after soaking, use the stored cycle count
               if "current_cycle" in zone and zone["current_cycle"] > 0:
                   # We're continuing from a previous cycle, so start from where we left off
                   cycles_needed = zone[ATTR_CYCLE_COUNT] 
                   current_cycle = zone["current_cycle"]
               else:
                   # New watering session, calculate cycles needed
                   
                   # Get the absorption rate from learning
                   absorption_rate = self.absorption_learners[zone_id].get_rate()
                  
                   # Calculate watering duration
                   from .algorithms.watering import calculate_watering_duration
                  
                   # NEW: Include moisture deficit in watering calculation
                   # If deficit is > 5mm (significant), increase watering time
                   additional_time = 0
                   if zone.get("moisture_deficit", 0) > 5.0:
                       # Convert mm deficit to additional watering minutes
                       # Approximate: 1mm deficit requires about 2-3 minutes of watering
                       moisture_deficit = zone.get("moisture_deficit", 0)
                       additional_time = moisture_deficit * 2.5
                       _LOGGER.info(
                           "Zone %s: Adding %.1f minutes watering time due to %.1fmm moisture deficit",
                           zone["name"], additional_time, moisture_deficit
                       )
                  
                   estimated_duration = calculate_watering_duration(
                       current_moisture=current_moisture,
                       target_moisture=zone["max_moisture"],
                       absorption_rate=absorption_rate,
                       cycle_time=self.cycle_time,
                       max_watering_time=zone.get("max_watering_time")
                   ) + additional_time
                  
                   # Calculate number of cycles needed
                   cycles_needed = max(1, round(estimated_duration / self.cycle_time))
                   current_cycle = 1  # Starting from first cycle
                  
                   # If we have schedule time constraint, check if we have enough time
                   if remaining_time is not None:
                       # Total time needed for this zone
                       total_time_needed = cycles_needed * self.cycle_time + (cycles_needed - 1) * self.soak_time
                      
                       if total_time_needed > remaining_time:
                           # Adjust cycles to fit within remaining time
                           max_cycles_with_soaking = int(remaining_time / (self.cycle_time + self.soak_time))
                           # Ensure at least one cycle if we have enough time for it
                           if max_cycles_with_soaking < 1 and remaining_time >= self.cycle_time:
                               cycles_needed = 1
                           else:
                               cycles_needed = max_cycles_with_soaking
                          
                           _LOGGER.info(
                               "Adjusted watering cycles for zone %s from %d to %d due to schedule constraints",
                               zone["name"], round(estimated_duration / self.cycle_time), cycles_needed
                           )
              
               _LOGGER.info(
                   "Starting watering for zone %s: cycle %d of %d (%d minutes)",
                   zone["name"], current_cycle, cycles_needed, self.cycle_time
               )
              
               # Update zone info
               self.active_zone = zone_id
               zone["state"] = ZONE_STATE_WATERING
               zone[ATTR_LAST_WATERED] = datetime.now().isoformat()
               zone[ATTR_CYCLE_COUNT] = cycles_needed
               zone[ATTR_CURRENT_CYCLE] = current_cycle
              
               # Start the watering
               await self.async_turn_on_zone(zone_id)
              
               # Send notification
               await self.async_send_notification(
                   f"Starting watering for zone {zone['name']} "
                   f"(cycle {current_cycle} of {cycles_needed}, {self.cycle_time} minutes)"
               )
              
               # Schedule the end of the watering cycle
               _LOGGER.debug("Scheduling end of watering cycle %d in %d minutes for zone %s",
                           current_cycle, self.cycle_time, zone["name"])
              
               cancel_callback = async_call_later(
                   self.hass,
                   self.cycle_time * 60,  # Convert minutes to seconds
                   self.async_end_watering_cycle
               )
               self._pending_tasks.append(cancel_callback)
              
           except Exception as e:
               _LOGGER.error("Error starting watering for zone %s: %s", zone["name"], e)
               self.active_zone = None
               zone["state"] = ZONE_STATE_IDLE
               
               # Process next zone immediately
               await self.async_process_queue()
       finally:
           # Reset queue processing flag but not sprinklers active flag
           # as we might still have active watering or soaking zones
           self._queue_processing_active = False
           
           # Release the lock when done
           self._process_queue_lock.release()


   async def async_turn_on_zone(self, zone_id):
       """Turn on a zone's switch."""
       zone = self.zones[zone_id]
       _LOGGER.debug("Turning ON switch %s for zone %s", zone["switch"], zone["name"])
      
       await self.hass.services.async_call(
           "switch", "turn_on", {"entity_id": zone["switch"]}
       )


   async def async_turn_off_zone(self, zone_id):
       """Turn off a zone's switch."""
       zone = self.zones[zone_id]
       _LOGGER.debug("Turning OFF switch %s for zone %s", zone["switch"], zone["name"])
      
       await self.hass.services.async_call(
           "switch", "turn_off", {"entity_id": zone["switch"]}
       )


   async def async_end_watering_cycle(self, _):
       """End the current watering cycle."""
       # Skip if system is disabled
       if not self._system_enabled:
           _LOGGER.debug("System disabled during watering cycle, stopping")
           return
      
       if not self.active_zone:
           _LOGGER.warning("End watering cycle called but no active zone")
           return
      
       zone_id = self.active_zone
       zone = self.zones[zone_id]
      
       _LOGGER.debug("Ending watering cycle %d for zone %s",
                   zone[ATTR_CURRENT_CYCLE], zone["name"])
      
       # Turn off the zone
       await self.async_turn_off_zone(zone_id)
      
       # Record moisture before soaking
       try:
           moisture_state = self.hass.states.get(zone["moisture_sensor"])
           if not moisture_state:
               _LOGGER.warning("Moisture sensor not found for zone %s", zone["name"])
               pre_soak_moisture = 0
           else:
               pre_soak_moisture = float(moisture_state.state)
       except (ValueError, TypeError):
           _LOGGER.warning("Invalid moisture reading for zone %s", zone["name"])
           pre_soak_moisture = 0
      
       # Check if we're still in schedule
       if not self.is_in_schedule():
           _LOGGER.info(
               "Stopping watering for zone %s because schedule has ended",
               zone["name"]
           )
          
           # Set to idle state
           zone["state"] = ZONE_STATE_IDLE
           self.active_zone = None
          
           # Send notification
           await self.async_send_notification(
               f"Stopped watering zone {zone['name']} because schedule has ended"
           )
          
           # Process next in queue if available
           await self.async_process_queue()
           return
      
       # Check if we need more cycles
       if zone[ATTR_CURRENT_CYCLE] < zone[ATTR_CYCLE_COUNT]:
           # Move to soaking state
           zone["state"] = ZONE_STATE_SOAKING
          
           # Calculate when soaking will end
           ready_time = datetime.now().timestamp() + (self.soak_time * 60)
           
           # Add to soaking zones
           self.soaking_zones[zone_id] = {
               "ready_at": ready_time,
               "pre_soak_moisture": pre_soak_moisture
           }
          
           _LOGGER.info(
               "Zone %s cycle %d completed, starting soak period of %d minutes",
               zone["name"], zone[ATTR_CURRENT_CYCLE], self.soak_time
           )

           # Clear active zone since we're now soaking
           self.active_zone = None
           
           # Schedule callback for when soaking ends
           soaking_callback = async_call_later(
               self.hass,
               self.soak_time * 60,  # Convert minutes to seconds
               self.async_check_soaking_complete(zone_id, pre_soak_moisture)
           )
           self._pending_tasks.append(soaking_callback)
           
           # Immediately process the queue to start watering another zone while this one soaks
           await self.async_process_queue()
           
       else:
           # All cycles completed
           _LOGGER.info(
               "Zone %s watering completed (%d cycles)",
               zone["name"], zone[ATTR_CYCLE_COUNT]
           )
          
           # Move to idle state after final moisture measurement
           zone["state"] = ZONE_STATE_MEASURING
          
           # Schedule final moisture measurement after soaking
           _LOGGER.debug("Scheduling final moisture measurement in %d minutes for zone %s",
                       self.soak_time, zone["name"])
          
           final_check_cb = self.async_final_moisture_check(pre_soak_moisture)
           cancel_callback = async_call_later(
               self.hass,
               self.soak_time * 60,  # Convert minutes to seconds
               final_check_cb
           )
           self._pending_tasks.append(cancel_callback)
          
           # Clear the active zone
           self.active_zone = None
           
           # Process next in queue if available
           await self.async_process_queue()


   def async_check_soaking_complete(self, zone_id, pre_soak_moisture):
       """Return a callback that checks if a zone has completed soaking."""
       
       async def _check_soaking(_):
           # This will be called when the soak timer expires
           # However, the zone might have already been removed from soaking_zones
           # if process_queue was called before this callback ran
           
           if zone_id in self.soaking_zones:
               # If still in soaking_zones, record moisture and update learning
               try:
                   zone = self.zones[zone_id]
                   
                   # Get moisture after soaking
                   try:
                       moisture_state = self.hass.states.get(zone["moisture_sensor"])
                       if moisture_state:
                           post_soak_moisture = float(moisture_state.state)
                           
                           # Calculate soaking efficiency
                           moisture_increase = max(0, post_soak_moisture - pre_soak_moisture)
                           zone[ATTR_SOAKING_EFFICIENCY] = moisture_increase / self.soak_time if self.soak_time > 0 else 0
                          
                           # Update absorption model with this data
                           self.absorption_learners[zone_id].add_data_point(
                               pre_moisture=pre_soak_moisture,
                               post_moisture=post_soak_moisture,
                               duration=self.soak_time
                           )
                   except (ValueError, TypeError):
                       pass  # Ignore errors in moisture reading
                       
                   # Increment cycle counter for next time
                   zone[ATTR_CURRENT_CYCLE] += 1
                   
                   # Soaking is done, call process_queue to continue
                   await self.async_process_queue()
               except Exception as e:
                   _LOGGER.error("Error processing end of soak for zone %s: %s",
                               self.zones[zone_id]["name"], str(e))
           
       return _check_soaking


   def async_final_moisture_check(self, pre_soak_moisture):
       """Return a callback to check final moisture after last soak."""
      
       async def _check_final_moisture(_):
           if not self.active_zone:
               _LOGGER.warning("Final moisture check called but no active zone")
               return
          
           zone_id = self.active_zone
           zone = self.zones[zone_id]
          
           _LOGGER.debug("Performing final moisture check for zone %s", zone["name"])
          
           # Get final moisture reading
           try:
               moisture_state = self.hass.states.get(zone["moisture_sensor"])
               if not moisture_state:
                   _LOGGER.warning("Moisture sensor not found for zone %s", zone["name"])
                   final_moisture = pre_soak_moisture  # Use pre-soak as fallback
               else:
                   final_moisture = float(moisture_state.state)
           except (ValueError, TypeError):
               _LOGGER.warning("Invalid moisture reading for zone %s", zone["name"])
               final_moisture = pre_soak_moisture  # Use pre-soak as fallback
          
           # Calculate and record soaking efficiency
           moisture_increase = max(0, final_moisture - pre_soak_moisture)
           zone[ATTR_SOAKING_EFFICIENCY] = moisture_increase / self.soak_time if self.soak_time > 0 else 0
          
           # Update absorption model
           self.absorption_learners[zone_id].add_data_point(
               pre_moisture=pre_soak_moisture,
               post_moisture=final_moisture,
               duration=self.soak_time
           )
           
           # NEW: Reset moisture deficit based on watering
           # If we reached target moisture level, reset deficit
           if final_moisture >= zone["max_moisture"]:
               old_deficit = zone.get("moisture_deficit", 0.0)
               zone["moisture_deficit"] = 0.0
               _LOGGER.info(
                   "Zone %s reached target moisture (%.1f%%), resetting moisture deficit from %.1fmm to 0.0mm",
                   zone["name"], final_moisture, old_deficit
               )
           else:
               # Partially reduce deficit based on percentage of target reached
               old_deficit = zone.get("moisture_deficit", 0.0)
               if old_deficit > 0:
                   moisture_gain_pct = (final_moisture - pre_soak_moisture) / (zone["max_moisture"] - pre_soak_moisture)
                   moisture_gain_pct = min(max(moisture_gain_pct, 0.0), 1.0)  # Clamp to 0-100%
                   new_deficit = old_deficit * (1.0 - moisture_gain_pct)
                   zone["moisture_deficit"] = new_deficit
                   _LOGGER.info(
                       "Zone %s: Partially reduced moisture deficit from %.1fmm to %.1fmm (%.1f%% of target moisture reached)",
                       zone["name"], old_deficit, new_deficit, moisture_gain_pct * 100
                   )
          
           # Set to idle state
           zone["state"] = ZONE_STATE_IDLE
          
           # Clear active zone (should already be None, but just to be sure)
           self.active_zone = None
           
           # Reset cycle tracking
           zone[ATTR_CURRENT_CYCLE] = 0
           
           # Send notification about completion
           await self.async_send_notification(
               f"Zone {zone['name']} watering completed. "
               f"Final moisture: {final_moisture}%, "
               f"Efficiency: {zone[ATTR_SOAKING_EFFICIENCY] * 60:.2f}%/hour, "
               f"Remaining deficit: {zone.get('moisture_deficit', 0):.1f}mm"
           )
          
           _LOGGER.info(
               "Final moisture for zone %s: %.1f%%, Efficiency: %.2f%%/hour, Remaining deficit: %.1fmm",
               zone["name"], final_moisture, zone[ATTR_SOAKING_EFFICIENCY] * 60, zone.get("moisture_deficit", 0)
           )
           
           # Check if there are no more active zones
           if not self.active_zone and not self.soaking_zones and not self.zone_queue:
               self._sprinklers_active = False
           
           # Process next zone in queue if available
           await self.async_process_queue()
          
       return _check_final_moisture


   async def async_check_schedule(self, now):
       """Check if we should be watering according to schedule."""
       # Skip if system is disabled or sprinklers is already active
       if not self._system_enabled:
           return
      
       # This runs every minute to check the schedule
       if self.is_in_schedule():
           # Trigger an update if we're in the schedule window
           await self.async_update()
           
           # If there are zones in the queue but nothing active, start processing
           if self.zone_queue and not self.active_zone and not self._queue_processing_active:
               await self.async_process_queue()


   async def async_send_notification(self, message):
       """Send a notification through Home Assistant."""
       await self.hass.services.async_call(
           "persistent_notification",
           "create",
           {
               "title": "Smart Sprinklers",
               "message": message,
           }
       )


   async def async_service_refresh_forecast(self, call: ServiceCall):
       """Service to refresh weather forecast data."""
       await self.async_update_forecast()


   async def async_service_reset_statistics(self, call: ServiceCall):
       """Service to reset statistics for all zones."""
       for zone_id, zone in self.zones.items():
           zone["soaking_efficiency"] = 0
           zone["moisture_history"] = []
           zone["moisture_deficit"] = 0.0
          
           # Reset absorption learner
           self.absorption_learners[zone_id].reset()
           
           # Reset daily ET
           self.daily_et[zone_id] = 0.0
          
       # Reset daily precipitation
       self.daily_precipitation = 0.0
       
       _LOGGER.info("Reset statistics for all zones")


   async def async_start_manual_watering(self, zone_ids=None):
       """Start manual watering for specified zones or all zones if none specified."""
       # Use system lock to prevent conflicts with scheduled operations
       async with self._system_lock:
           # Check if system is enabled and not already watering
           if not self._system_enabled:
               _LOGGER.warning("Cannot start manual watering, system is disabled")
               return False
           
           # Set manual operation flag
           self._manual_operation_requested = True
           
           try:
               # If no specific zones, water all zones
               if not zone_ids:
                   zone_ids = list(self.zones.keys())
               
               # Clear existing queue and add requested zones
               self.zone_queue.clear()
               for zone_id in zone_ids:
                   if zone_id in self.zones:
                       self.zone_queue.append(zone_id)
               
               if self.zone_queue:
                   # Start the watering process
                   await self.async_process_queue()
                   return True
               else:
                   _LOGGER.warning("No valid zones specified for manual watering")
                   return False
                   
           finally:
               # Reset manual operation flag when done
               self._manual_operation_requested = False


    async def async_service_update_moisture_deficit(self, call: ServiceCall):
        """Service to manually trigger moisture deficit update."""
        await self.async_calculate_et()
        await self.async_calculate_precipitation()
        
        # Update moisture deficits for each zone 
        for zone_id, zone in self.zones.items():
            zone_et = self.daily_et.get(zone_id, 0.0)
            effective_rain = self.daily_precipitation
            
            # Update moisture deficit
            old_deficit = zone.get("moisture_deficit", 0.0)
            new_deficit = old_deficit + zone_et - effective_rain
            
            # Ensure deficit isn't negative
            zone["moisture_deficit"] = max(0.0, new_deficit)
            
            _LOGGER.info(
                "Zone %s: ET=%.2fmm, Rain=%.2fmm, Old deficit=%.2fmm, New deficit=%.2fmm",
                zone["name"], zone_et, effective_rain, old_deficit, zone["moisture_deficit"]
            )
        
        await self.async_send_notification(
            f"Moisture deficit updated for all zones. "
            f"Daily ET: {next(iter(self.daily_et.values())) if self.daily_et else 0:.2f}mm, "
            f"Precipitation: {self.daily_precipitation:.2f}mm"
        )

    async def async_service_force_et_calculation(self, call: ServiceCall):
        """Service to force ET calculation."""
        await self.async_calculate_et()
        message = "ET calculation completed:\n"
        for zone_id, et in self.daily_et.items():
            zone_name = self.zones[zone_id]["name"]
            message += f"• {zone_name}: {et:.2f}mm\n"
        
        await self.async_send_notification(message)

    async def async_service_force_precipitation_calculation(self, call: ServiceCall):
        """Service to force precipitation calculation."""
        await self.async_calculate_precipitation()
        message = f"Precipitation calculation completed: {self.daily_precipitation:.2f}mm"
        await self.async_send_notification(message)