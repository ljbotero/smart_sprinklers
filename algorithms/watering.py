"""Watering duration calculation algorithms."""
import logging
import math

_LOGGER = logging.getLogger(__name__)

def calculate_watering_duration(current_moisture, target_moisture, absorption_rate, cycle_time, max_watering_time=None):
    """Calculate the optimal watering duration based on soil conditions.
    
    Args:
        current_moisture: Current soil moisture level (%)
        target_moisture: Target soil moisture level (%)
        absorption_rate: Learned soil absorption rate (%/minute)
        cycle_time: Maximum cycle time (minutes)
        max_watering_time: Maximum watering duration in minutes (optional)
        
    Returns:
        float: Estimated watering duration in minutes
    """
    # Validate input parameters
    if not isinstance(current_moisture, (int, float)) or current_moisture < 0:
        _LOGGER.warning("Invalid current moisture value: %s", current_moisture)
        current_moisture = 0
    
    if not isinstance(target_moisture, (int, float)) or target_moisture <= 0:
        _LOGGER.warning("Invalid target moisture value: %s", target_moisture)
        target_moisture = 80  # Default to 80%
    
    if not isinstance(absorption_rate, (int, float)) or absorption_rate <= 0:
        _LOGGER.warning("Invalid absorption rate: %s", absorption_rate)
        absorption_rate = 0.5  # Default fallback
    
    if not isinstance(cycle_time, (int, float)) or cycle_time <= 0:
        _LOGGER.warning("Invalid cycle time: %s", cycle_time)
        cycle_time = 15  # Default to 15 minutes
    
    # Calculate moisture difference needed
    moisture_difference = max(0, target_moisture - current_moisture)
    
    # If no moisture difference or max_watering_time is 0, don't water
    if moisture_difference <= 0 or max_watering_time == 0:
        return 0
    
    # Calculate base duration
    base_duration = moisture_difference / absorption_rate if absorption_rate > 0 else cycle_time
    
    # Apply adjustment for non-linear absorption
    # As the soil gets more saturated, absorption slows down
    saturation_factor = 1.0 + (0.5 * (current_moisture / 100.0))
    adjusted_duration = base_duration * saturation_factor
    
    # Ensure we do at least one cycle if there's any moisture difference
    if moisture_difference > 0 and adjusted_duration < cycle_time:
        adjusted_duration = cycle_time
    
    # Round to the nearest cycle
    cycles_needed = math.ceil(adjusted_duration / cycle_time)
    total_duration = cycles_needed * cycle_time
    
    # Apply maximum watering time limit if specified
    if max_watering_time is not None and max_watering_time > 0:
        # Calculate max cycles that fit within limit
        max_cycles = max_watering_time // cycle_time
        if max_cycles < 1 and max_watering_time > 0:
            max_cycles = 1  # At least do one cycle if max time > 0
            
        if cycles_needed > max_cycles:
            _LOGGER.info(
                "Capping watering duration to maximum: %d cycles (%d minutes) instead of %d cycles (%d minutes)",
                max_cycles, max_cycles * cycle_time, cycles_needed, total_duration
            )
            cycles_needed = max_cycles
            total_duration = max_cycles * cycle_time

    _LOGGER.debug(
        "Calculated watering duration: %.1f minutes (%d cycles of %d minutes)",
        total_duration, cycles_needed, cycle_time
    )
    
    return total_duration

def distribute_watering_time(zones_data, available_minutes, cycle_time, min_cycle_count=1):
    """Distribute available watering time proportionally across zones.
    
    Args:
        zones_data: List of dicts with zone info, each containing:
            - current_moisture: Current moisture level
            - target_moisture: Target moisture level
            - absorption_rate: Absorption rate in %/minute
            - moisture_deficit: Moisture deficit in mm (optional)
        available_minutes: Total available time in minutes
        cycle_time: Duration of one watering cycle in minutes
        min_cycle_count: Minimum number of cycles for any zone that needs water
        
    Returns:
        dict: Zone index to cycle count mapping
    """
    # Calculate moisture deficit and required time for each zone
    total_required_minutes = 0
    required_minutes = []
    moisture_deficits = []
    
    for zone in zones_data:
        # Calculate moisture deficit (how much we need to increase)
        current = zone.get("current_moisture", 0)
        target = zone.get("target_moisture", 0)
        deficit = max(0, target - current)
        moisture_deficits.append(deficit)
        
        # Get optional moisture deficit in mm
        moisture_deficit_mm = zone.get("moisture_deficit", 0.0)
        
        # Calculate required time based on absorption rate
        absorption_rate = zone.get("absorption_rate", 0.5)  # %/minute
        if absorption_rate <= 0:
            absorption_rate = 0.5  # Default fallback
            
        # Apply saturation factor (same as in calculate_watering_duration)
        saturation_factor = 1.0 + (0.5 * (current / 100.0))
        required_time = (deficit / absorption_rate) * saturation_factor if deficit > 0 else 0
        
        # Add additional watering time for moisture deficit
        # Approximate: 1mm deficit requires about 2.5 minutes of watering
        additional_time = 0
        if moisture_deficit_mm > 5.0:  # Only add time if deficit is significant
            additional_time = moisture_deficit_mm * 2.5
            
        total_required = required_time + additional_time
        required_minutes.append(total_required)
        total_required_minutes += total_required
        
        # Log the calculated values
        _LOGGER.debug(
            "Zone needs %.1f minutes (%.1f from moisture + %.1f from deficit of %.1f mm)",
            total_required, required_time, additional_time, moisture_deficit_mm
        )
    
    
    # If the total required time is less than available, we can fulfill all needs
    if total_required_minutes <= available_minutes:
        result = {}
        for i in range(len(zones_data)):
            if moisture_deficits[i] > 0:
                # Convert minutes to cycles, minimum 1 cycle if there's a deficit
                cycles = max(min_cycle_count, math.ceil(required_minutes[i] / cycle_time))
                result[i] = cycles
            else:
                result[i] = 0
        return result
    
    # If we need to distribute proportionally
    available_ratio = available_minutes / total_required_minutes
    result = {}
    
    # First, allocate minimum cycles to any zone that needs water
    allocated_minutes = 0
    for i in range(len(zones_data)):
        if moisture_deficits[i] > 0:
            # Allocate minimum cycles
            result[i] = min_cycle_count
            allocated_minutes += min_cycle_count * cycle_time
        else:
            result[i] = 0
    
    # If we have remaining time, distribute it proportionally
    remaining_minutes = available_minutes - allocated_minutes
    if remaining_minutes > 0 and total_required_minutes > 0:
        # Calculate what portion of the remaining time each zone should get
        for i in range(len(zones_data)):
            if required_minutes[i] > 0:
                zone_ratio = required_minutes[i] / total_required_minutes
                # Add additional cycles based on the zone's proportion
                additional_minutes = remaining_minutes * zone_ratio
                additional_cycles = int(additional_minutes / cycle_time)
                result[i] += additional_cycles
    
    return result