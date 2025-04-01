## Features Overview

- Multiple zone management (8+ zones) with individual control
- Weather-aware watering decisions (temperature and rain forecast)
- Cycle and soak methodology for better absorption
- Weekly scheduling to comply with water restrictions
- Dynamic watering duration based on soil conditions
- Learning algorithm to adjust for sensor delays
- Efficiency tracking and historical recording
- Automated operation with no manual override
- Comprehensive notifications and logging

## File Structure


```
smart_sprinklers/
├── __init__.py           # Main integration entry point
├── const.py              # Constants
├── config_flow.py        # Configuration UI flow
├── manifest.json         # Integration metadata
├── sensor.py             # Sensor entities
├── switch.py             # Switch entities
├── services.yaml         # Service definitions
├── translations/         # UI translations
│   └── en.json
└── algorithms/           # Custom algorithms
    ├── __init__.py
    ├── absorption.py     # Soil absorption learning
    └── watering.py       # Dynamic watering calculations
```

## Weather-Based Control

The system uses a comprehensive weather-based approach:

### Moisture Deficit Tracking
- Calculates daily evapotranspiration (ET) based on temperature and humidity
- Monitors rainfall from rain sensors and weather forecasts
- Maintains a running "moisture deficit" for each zone
- Adjusts watering durations based on the calculated deficit

### Rain Forecast Integration
- Checks weather forecast for upcoming rain
- Skips scheduled watering when sufficient rain is expected
- Configurable rain threshold (mm) determines how much rain is "sufficient"

### Configuration Options
- **Weather Entity**: Provides temperature, humidity, and forecast data
- **Rain Sensor** (optional): Direct measurement of rainfall
- **Rain Threshold**: Amount of rain (mm) that will cause watering to be skipped
- **Freeze Threshold**: Temperature below which watering is skipped

### Technical Details
- Moisture deficit is measured in millimeters (mm) of water
- ET increases deficit, precipitation decreases it
- A deficit of zero means soil is at optimum moisture level
- Negative deficit (surplus) prevents watering until soil dries out