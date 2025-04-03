"""Weather-related functionality for Smart Sprinklers."""
import logging
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from .const import (
    CONF_WEATHER_ENTITY,
    CONF_RAIN_SENSOR,
    CONF_RAIN_THRESHOLD,
    DEFAULT_RAIN_THRESHOLD,
)

from .util import fetch_forecast

_LOGGER = logging.getLogger(__name__)

class WeatherManager:
    """Manage weather-related functionality for Smart Sprinklers."""
    
    def __init__(self, coordinator):
        """Initialize the weather manager."""
        self.coordinator = coordinator
        self.weather_entity = None
        self.rain_sensor = None
        self.rain_threshold = DEFAULT_RAIN_THRESHOLD
        self.forecast_data = None
        self.last_forecast_update = None
        self.forecast_valid = False
        self.weather_available = False
        self.hass = coordinator.hass
        self._update_lock = coordinator.hass.loop.create_lock()
        
    async def setup(self, config):
        """Set up the weather manager with configuration."""
        # Get weather entity
        self.weather_entity = config.get(CONF_WEATHER_ENTITY)
        if not self.weather_entity:
            _LOGGER.warning("No weather entity specified, some functionality will be limited")
            
        # Get rain sensor and threshold configuration
        self.rain_sensor = config.get(CONF_RAIN_SENSOR)
        self.rain_threshold = config.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD)
        
        # Log the configuration
        _LOGGER.info("Smart Sprinklers weather configured with: Weather=%s, Rain Sensor=%s, Rain Threshold=%.1fmm",
                    self.weather_entity, self.rain_sensor, self.rain_threshold)
                    
        # Check if weather entity exists
        if self.weather_entity:
            weather_state = self.hass.states.get(self.weather_entity)
            self.weather_available = weather_state is not None
            if not self.weather_available:
                _LOGGER.warning("Weather entity %s not found - will check again later", self.weather_entity)
    
    async def check_and_update_forecast(self):
        """Check if forecast needs updating and update if needed."""
        # Update forecast if needed
        forecast_age = (
            datetime.now() - self.last_forecast_update
            if self.last_forecast_update else timedelta(hours=1)
        )
        
        if forecast_age > timedelta(hours=1):
            await self.async_update_forecast()
    
    async def async_update_forecast(self, _=None):
        """Update weather forecast data."""
        # Use lock to prevent multiple concurrent updates
        async with self._update_lock:
            try:
                if not self.weather_entity:
                    _LOGGER.warning("No weather entity configured, forecast data unavailable")
                    self.forecast_valid = False
                    return
                
                weather_state = self.hass.states.get(self.weather_entity)
                if not weather_state:
                    _LOGGER.warning("Weather entity %s not available", self.weather_entity)
                    self.weather_available = False
                    self.forecast_valid = False
                    return
                
                self.weather_available = True
                
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
                    self.forecast_valid = False
                else:
                    _LOGGER.debug("Updated forecast data with %d entries", len(self.forecast_data))
                    self.forecast_valid = True
                
            except Exception as e:
                _LOGGER.error("Error updating forecast: %s", e)
                self.forecast_valid = False
    
    def is_rain_forecasted(self, hours=24):
        """Check if rain is forecasted in the next n hours."""
        # If no forecast data or entity not available, default to False
        # This is safer than assuming rain - better to irrigate than under-water
        if not self.forecast_valid or not self.weather_available:
            _LOGGER.info("No valid forecast data - assuming no rain")
            return False
            
        if not self.forecast_data:
            return False
        
        try:
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
        except Exception as e:
            _LOGGER.error("Error checking rain forecast: %s", e)
            # Default to False (allow watering) in case of error
            return False

    def is_freezing_forecasted(self, hours=12):
        """Check if freezing temperatures are forecasted in the next n hours."""
        # If no forecast or weather entity, be cautious and return True if in winter months
        if not self.forecast_valid or not self.weather_available:
            # Check if we're in winter (Northern Hemisphere assumption)
            # For a more robust solution, this should be made configurable
            month = datetime.now().month
            if month in [11, 12, 1, 2, 3]:  # Nov-Mar
                _LOGGER.info("No valid forecast in winter month - assuming freezing risk")
                return True
            else:
                return False
            
        if not self.forecast_data or not self.weather_entity:
            return False
        
        try:
            now = dt_util.now()
            forecast_window = now + timedelta(hours=hours)
            
            # Check current temperature
            weather_state = self.hass.states.get(self.weather_entity)
            if weather_state:
                try:
                    current_temp = weather_state.attributes.get("temperature")
                    if current_temp is not None and current_temp <= self.coordinator.freeze_threshold:
                        _LOGGER.info(
                            "Current temperature %.1f°F is below freeze threshold %.1f°F",
                            current_temp, self.coordinator.freeze_threshold
                        )
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
                    temp = forecast["temperature"]
                    if temp <= self.coordinator.freeze_threshold:
                        _LOGGER.info(
                            "Freezing forecast at %s: %.1f°F (threshold: %.1f°F)",
                            forecast_time.isoformat(), temp, self.coordinator.freeze_threshold
                        )
                        return True
        except Exception as e:
            _LOGGER.error("Error checking freezing forecast: %s", e)
            # Default to True (don't water) to be safe in case of error checking freezing
            return True
            
        return False
    
    async def async_daily_update(self, now=None):
        """Handle daily update of evapotranspiration and moisture deficit."""
        _LOGGER.info("Performing daily moisture deficit update")
        
        try:
            # Calculate evapotranspiration and precipitation
            await self.async_calculate_et()
            await self.async_calculate_precipitation()
            
            # Update moisture deficits for each zone
            for zone_id, zone in self.coordinator.zones.items():
                zone_et = self.coordinator.daily_et.get(zone_id, 0.0)
                effective_rain = self.coordinator.daily_precipitation
                
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
            self.coordinator.daily_et = {zone_id: 0.0 for zone_id in self.coordinator.zones}
            self.coordinator.daily_precipitation = 0.0
            
            # Schedule next daily update
            next_midnight = (dt_util.now() + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            
            _LOGGER.info("Next daily ET update scheduled for %s", next_midnight)
            self.coordinator._unsub_daily_update = self.hass.helpers.event.async_call_later(
                (next_midnight - dt_util.now()).total_seconds(),
                self.async_daily_update
            )
        except Exception as e:
            _LOGGER.error("Error in daily update: %s", e)
            # Schedule next retry in 1 hour
            _LOGGER.info("Will retry daily update in 1 hour")
            self.coordinator._unsub_daily_update = self.hass.helpers.event.async_call_later(
                3600,  # 1 hour in seconds
                self.async_daily_update
            )

    async def async_calculate_et(self):
        """Calculate evapotranspiration based on weather data."""
        if not self.weather_entity or not self.weather_available:
            _LOGGER.warning("No weather entity or not available, using default ET values")
            # Set default ET for each zone (5mm per day is a typical reference value)
            for zone_id in self.coordinator.zones:
                self.coordinator.daily_et[zone_id] = 5.0
            return
            
        try:
            # Get weather data
            weather_state = self.hass.states.get(self.weather_entity)
            if not weather_state:
                _LOGGER.warning("Weather entity not found, using default ET values")
                for zone_id in self.coordinator.zones:
                    self.coordinator.daily_et[zone_id] = 5.0
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
                    for zone_id, zone in self.coordinator.zones.items():
                        # Default crop coefficient of 1.0
                        # Could be customized per zone type in the future
                        crop_coefficient = 1.0  
                        self.coordinator.daily_et[zone_id] = adjusted_et * crop_coefficient
                        
                    _LOGGER.info(
                        "Calculated ET: %.2fmm (temp=%.1f°C, humidity=%.1f%%)",
                        adjusted_et, t, h
                    )
                    
                except (ValueError, TypeError) as e:
                    _LOGGER.warning("Error calculating ET from weather data: %s", e)
                    for zone_id in self.coordinator.zones:
                        self.coordinator.daily_et[zone_id] = reference_et
            else:
                _LOGGER.warning("Incomplete weather data, using default ET")
                for zone_id in self.coordinator.zones:
                    self.coordinator.daily_et[zone_id] = reference_et
                    
        except Exception as e:
            _LOGGER.error("Error in ET calculation: %s", e)
            # Fallback to default
            for zone_id in self.coordinator.zones:
                self.coordinator.daily_et[zone_id] = 5.0
    
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
                else:
                    _LOGGER.warning("Rain sensor %s not found", self.rain_sensor)
            except Exception as e:
                _LOGGER.error("Error reading rain sensor: %s", e)
        
        # If no rain sensor or invalid reading, try to get precipitation from weather entity
        if precipitation <= 0 and self.weather_entity and self.weather_available:
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
                
        # Safety bounds - precipitation shouldn't be negative
        precipitation = max(0.0, precipitation)
                
        # Store the calculated precipitation
        self.coordinator.daily_precipitation = precipitation