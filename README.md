# Smart Irrigation System

Smart Irrigation System is a Home Assistant custom integration designed to manage multiple irrigation zones intelligently. It uses sensor inputs, weather forecasts, and a learning algorithm to determine the optimal watering duration and cycle patterns for each zone. This system not only saves water by adjusting to environmental conditions but also ensures your garden receives precisely the right amount of hydration based on your custom settings.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Core System Requirements](#core-system-requirements)
  - [Advanced Intelligent Features](#advanced-intelligent-features)
- [Usage Examples](#usage-examples)
- [Integration Testing](#integration-testing)
- [Contributing](#contributing)
- [License](#license)

## Features

### Multiple Zone Management
- **Customizable Zones:** Supports 8+ irrigation zones with individual configuration.
- **Per-Zone Sensors and Switches:** Each zone includes a sprinkler control switch, a temperature sensor, and a soil moisture sensor.
- **Custom Moisture Thresholds:** Configure each zone with its specific minimum (trigger) and maximum (target) soil moisture levels.
- **Individual Watering Durations:** Set maximum watering hours/minutes per zone to prevent overwatering.

> **Example Use Case:**  
> *"As a homeowner with 10 different lawn and garden zones, I want to configure each zone so that my vegetable garden receives more water (25-30% moisture) than my drought-tolerant landscaping (15-20% moisture)."*

### Weather Intelligence
- **Weather Forecast Integration:** Integrates with any Home Assistant weather entity to fetch forecast data.
- **Automatic Watering Prevention:** Stops scheduled watering when rain is forecast within the next 24 hours or when the current/forecasted temperature is below the configurable freeze threshold (default 36°F).

> **Example Use Case:**  
> *"I want the system to automatically skip watering when rain or freezing temperatures are expected so that I don’t waste water or damage my irrigation system."*

### Cycle and Soak Methodology
- **Cycle and Soak Pattern:** Implements a cycle-and-soak watering pattern to maximize water absorption and prevent runoff.
- **Configurable Timings:** Set cycle time and soak time per watering cycle (default 15 minutes watering, 30 minutes soaking).
- **Moisture Feedback:** The system collects moisture readings after each soak period to adjust the subsequent watering cycle.

> **Example Use Case:**  
> *"For my clay soil, I want a cycle of 10 minutes watering followed by 45 minutes soaking repeated 3 times to ensure deep water penetration."*

### Smart Scheduling
- **Weekly Watering Schedules:** Use Home Assistant schedule helpers to define a watering schedule that applies to all zones.
- **Schedule Enforcement:** Automatically stops watering when the schedule window ends.
- **Dynamic Queue Management:** If multiple zones need water simultaneously, the system distributes the available time intelligently.

> **Example Use Case:**  
> *"I need watering only on Tuesdays and Fridays from 4:00-6:00 AM, and if watering isn’t completed by 6:00 AM, the system stops immediately."*

### Moisture-Based Control
- **Automatic Activation:** Sprinklers activate only when soil moisture falls below the minimum threshold.
- **Stop Condition:** Watering continues until the zone reaches the target moisture or the maximum duration is hit.

> **Example Use Case:**  
> *"My tomato bed should water when moisture drops below 25% and stop at 35%, while my succulent garden should only operate between 15% and 20% moisture."*

### Advanced Intelligent Features

#### Learning Algorithm
- **Soil Absorption Learning:** Uses an exponentially weighted algorithm to learn each zone’s soil absorption rates based on historical sensor readings.
- **Delayed Sensor Handling:** Models the 30-minute sensor delay to accurately adjust watering durations without manual intervention.

> **Example Use Case:**  
> *"For slow-responding soil sensors, the system learns and compensates for the delay, ensuring optimal watering without my intervention."*

#### Dynamic Watering Calculations
- **Automated Duration Calculation:** Watering duration is calculated using current moisture, target moisture, the learned absorption rate, and a saturation factor.
- **Cycle Count Adjustment:** Automatically adjusts the number of watering cycles based on required duration.

> **Example Use Case:**  
> *"The system calculates the watering time for a zone currently at 10% moisture to reach 25%, considering the absorption rate that decreases as the soil becomes saturated."*

#### Fair Distribution Algorithm
- **Time Allocation:** When the watering window is limited, available time is distributed proportionally across zones.
- **Prioritization:** Zones furthest from their target moisture receive more cycles, while ensuring every zone gets at least one cycle if water is needed.

> **Example Use Case:**  
> *"With a 2-hour watering window and 6 zones, the system distributes water based on the zones’ moisture deficits and absorption rates."*

#### Efficiency Tracking
- **Real-Time Monitoring:** Tracks the water absorption efficiency (moisture gain per hour) for each zone.
- **Historical Analysis:** Records moisture data over time to help optimize future watering schedules and landscape planning.

> **Example Use Case:**  
> *"I can view that Zone 1 gains 5% moisture per hour while Zone 3 gains 8% per hour, enabling me to plan my landscaping better."*

### System Constraints
- **Single Zone Operation:** Only one zone waters at a time, with subsequent zones starting during the previous zone’s soak period.
- **Maximum Duration Enforcement:** Configurable maximum watering time per zone ensures water conservation.
- **Fully Automated Operation:** The system operates autonomously with no manual override, though a system-wide enable/disable switch is available.
- **Robust Error Handling:** Gracefully handles sensor failures, invalid readings, and missing forecast data by using defaults or historical patterns.

> **Example Use Case:**  
> *"Even if a sensor reports 'unavailable,' the system makes intelligent watering decisions based on past data instead of skipping the zone entirely."*

## Installation

### Prerequisites
- Home Assistant installed and running.
- A working weather entity (e.g., integration with a weather provider).
- Configured Home Assistant with at least one schedule helper if scheduling restrictions are needed.

### Steps
1. **Download the Integration:**
   - Clone or download the repository from [GitHub](https://github.com/lbbotero/smart_irrigation).

2. **Copy Files:**
   - Copy the `smart_irrigation` directory into your Home Assistant configuration’s `custom_components` folder.

3. **Restart Home Assistant:**
   - Restart Home Assistant to allow the integration to load.
   
4. **Configure via UI:**
   - Use the Home Assistant configuration UI to add the Smart Irrigation integration.
   - Follow the guided setup to specify your weather entity, schedule helper (optional), and system settings.
   - Add individual zones through the options flow, specifying the name, connected switch, temperature sensor, moisture sensor, and moisture thresholds.

## Configuration

### Core System Requirements
- **Zones Configuration:** Define zones in the configuration with:
  - Name, sprinkler switch entity, temperature sensor, and moisture sensor.
  - Moisture thresholds and maximum watering durations.
  
- **Weather Setup:** Specify a weather entity for forecast data.
  - The system automatically prevents watering when rain or freezing temperatures (default 36°F) are detected.

- **Scheduling:** Use a Home Assistant schedule helper to enforce weekly watering windows.

### Advanced Intelligent Features
- **Learning Algorithm:** Each zone has an absorption learner that adjusts watering durations based on historical sensor data.
- **Dynamic Watering Calculation:** The integration calculates the watering duration automatically using current moisture levels, target moisture levels, absorption rate, and saturation factor.
- **Fair Time Distribution:** When multiple zones need watering within a limited schedule window, the system distributes the cycles based on each zone’s moisture deficit and absorption rate.

## Usage Examples

### Example 1: Basic Setup
1. **Add Integration:**
   - Go to **Configuration > Integrations** and add "Smart Irrigation System."
   - Select your weather entity and optionally a schedule helper.
   
2. **Configure Zones:**
   - Open the options flow and click "Configure Zones."
   - Add a zone for your vegetable garden with a minimum moisture of 25% and a maximum of 35%.
   - Add another zone for your succulent garden with a minimum moisture of 15% and a maximum of 20%.

### Example 2: Watering Cycle Customization
- Configure cycle time to 10 minutes and soak time to 45 minutes.
- The system will water in cycles until the soil moisture reaches the target level or the maximum watering duration is reached.
  
### Example 3: Service Calls
- **Refresh Forecast:**  
  Call the `smart_irrigation.refresh_forecast` service to update weather data immediately.
  
- **Reset Statistics:**  
  Call the `smart_irrigation.reset_statistics` service to clear all learning data and moisture history.

## Integration Testing

The integration includes comprehensive integration tests covering:
- **Configuration Entry Setup**
- **Zone Entity Registration and Status**
- **Weather Forecast Integration**
- **Scheduling Methods**
- **Learning Algorithms and Watering Calculations**

To run the integration tests, use the options flow in the integration’s configuration menu (select "Run Integration Tests"). Test results are saved in the `integ_tests/test_results.txt` file.

## Contributing

Contributions are welcome! To contribute:
1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Write tests for your changes.
4. Submit a pull request with a detailed description of your changes.

Please follow the [contributing guidelines](CONTRIBUTING.md) if available.

## License

This project is licensed under the [NonCommercial MIT License](LICENSE).

---

Smart Irrigation System is designed to be modular and easily configurable, ensuring it adapts to various landscape requirements while optimizing water usage. Enjoy smarter watering and improved garden care!
