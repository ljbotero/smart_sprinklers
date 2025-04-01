"""Constants for the Smart Sprinklers integration."""
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature

DOMAIN = "smart_sprinklers"

# Default Settings
DEFAULT_FREEZE_THRESHOLD = 36.0  # °F
DEFAULT_CYCLE_TIME = 15  # minutes
DEFAULT_SOAK_TIME = 30  # minutes
DEFAULT_MIN_MOISTURE = 20  # percentage
DEFAULT_MAX_MOISTURE = 25  # percentage
DEFAULT_MAX_WATERING_HOURS = 0
DEFAULT_MAX_WATERING_MINUTES = 20
DEFAULT_RAIN_THRESHOLD = 3.0  # mm of rain above which watering is skipped

# Configuration keys
CONF_ZONES = "zones"
CONF_ZONE_NAME = "name"
CONF_ZONE_SWITCH = "switch"
CONF_ZONE_TEMP_SENSOR = "temperature_sensor"
CONF_ZONE_MOISTURE_SENSOR = "moisture_sensor"
CONF_ZONE_MIN_MOISTURE = "min_moisture"
CONF_ZONE_MAX_MOISTURE = "max_moisture"
CONF_ZONE_MAX_WATERING_HOURS = "max_watering_hours"
CONF_ZONE_MAX_WATERING_MINUTES = "max_watering_minutes"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_FREEZE_THRESHOLD = "freeze_threshold"
CONF_CYCLE_TIME = "cycle_time"
CONF_SOAK_TIME = "soak_time"
CONF_SCHEDULE_ENTITY = "schedule_entity"  # Schedule helper entity ID
CONF_SYSTEM_ENABLED = "system_enabled"  # Added to persist system enabled state
CONF_RAIN_SENSOR = "rain_sensor"  # Entity ID of rain sensor (optional)
CONF_RAIN_THRESHOLD = "rain_threshold"  # mm of rain above which watering is skipped

# Services
SERVICE_REFRESH_FORECAST = "refresh_forecast"
SERVICE_RESET_STATISTICS = "reset_statistics"

# Entity attributes
ATTR_ZONE = "zone"
ATTR_LAST_WATERED = "last_watered"
ATTR_NEXT_WATERING = "next_watering"
ATTR_CYCLE_COUNT = "cycle_count"
ATTR_CURRENT_CYCLE = "current_cycle"  # Added missing constant
ATTR_SOAKING_EFFICIENCY = "soaking_efficiency"
ATTR_MOISTURE_HISTORY = "moisture_history"
ATTR_ABSORPTION_RATE = "absorption_rate"
ATTR_ESTIMATED_WATERING_DURATION = "estimated_watering_duration"
ATTR_MAX_WATERING_TIME = "max_watering_time"
ATTR_MOISTURE_DEFICIT = "moisture_deficit"  # Track moisture deficit in mm
ATTR_DAILY_ET = "daily_et"  # Daily evapotranspiration in mm
ATTR_DAILY_PRECIPITATION = "daily_precipitation"  # Daily precipitation in mm

# System states
STATE_ENABLED = "enabled"
STATE_DISABLED = "disabled"

# Zone states
ZONE_STATE_IDLE = "idle"
ZONE_STATE_WATERING = "watering"
ZONE_STATE_SOAKING = "soaking"
ZONE_STATE_MEASURING = "measuring"