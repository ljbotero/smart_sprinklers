"""Soil absorption learning algorithm."""
import logging
import math
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)

class AbsorptionLearner:
    """Class to learn soil absorption rates over time."""
    
    def __init__(self):
        """Initialize the absorption learner."""
        self._data_points = []
        self._default_rate = 0.5  # Default absorption rate (% per minute)
        self._max_valid_rate = 5.0  # Maximum valid absorption rate (% per minute)
        
    def add_data_point(self, pre_moisture, post_moisture, duration):
        """Add a data point for learning."""
        if duration <= 0:
            _LOGGER.warning("Cannot add data point with zero or negative duration")
            return
            
        # Calculate observed absorption rate
        moisture_change = post_moisture - pre_moisture
        rate = moisture_change / duration if duration > 0 else 0
        
        # Don't record negative rates (moisture decrease)
        if rate <= 0:
            _LOGGER.warning("Negative absorption rate detected (%.2f%%/min), skipping", rate)
            return
            
        # Don't record unrealistically high rates
        if rate > self._max_valid_rate:
            _LOGGER.warning("Unrealistically high absorption rate detected (%.2f%%/min), skipping", rate)
            return
        
        # Store the data point with timestamp
        self._data_points.append({
            "timestamp": datetime.now().isoformat(),
            "pre_moisture": pre_moisture,
            "post_moisture": post_moisture,
            "duration": duration,
            "rate": rate
        })
        
        # Limit data points to last 100
        if len(self._data_points) > 100:
            self._data_points = self._data_points[-100:]
            
        _LOGGER.debug("Added absorption data point: %.2f%% over %d minutes (rate: %.4f%%/min)",
                     moisture_change, duration, rate)
    
    def get_rate(self):
        """Get the learned absorption rate using weighted trailing average."""
        if not self._data_points:
            return self._default_rate
            
        # Remove data points older than 30 days
        cutoff_date = datetime.now() - timedelta(days=30)
        self._data_points = [
            point for point in self._data_points 
            if datetime.fromisoformat(point["timestamp"]) >= cutoff_date
        ]
        
        if not self._data_points:
            return self._default_rate
        
        # Sort data points by timestamp (newest last)
        sorted_points = sorted(self._data_points, 
                               key=lambda x: datetime.fromisoformat(x["timestamp"]))
        
        # Calculate exponentially weighted moving average
        # Recent points get higher weight
        alpha = 0.3  # Smoothing factor (0.3 gives good balance between stability and responsiveness)
        weights_sum = 0
        weighted_sum = 0
        
        for i, point in enumerate(sorted_points):
            # Exponential weight: higher for more recent points
            # The most recent point (i = len-1) gets weight = 1
            # Earlier points get exponentially smaller weights
            weight = math.exp(alpha * (i - (len(sorted_points) - 1)))
            weighted_sum += point["rate"] * weight
            weights_sum += weight
        
        if weights_sum > 0:
            return weighted_sum / weights_sum
        else:
            return self._default_rate
    
    def get_confidence(self):
        """Return a confidence score (0-1) for the learned rate."""
        # More data points = higher confidence, up to a reasonable maximum
        max_confidence_points = 20  # After 20 data points, we reach max confidence
        
        if not self._data_points:
            return 0.0
            
        # Remove old data points for confidence calculation too
        cutoff_date = datetime.now() - timedelta(days=30)
        recent_points = [
            point for point in self._data_points 
            if datetime.fromisoformat(point["timestamp"]) >= cutoff_date
        ]
        
        # Count recent points (last 7 days have higher weight)
        very_recent_cutoff = datetime.now() - timedelta(days=7)
        very_recent_points = [
            point for point in recent_points
            if datetime.fromisoformat(point["timestamp"]) >= very_recent_cutoff
        ]
        
        # Calculate confidence based on number of data points
        # Very recent points count double
        effective_points = len(recent_points) + len(very_recent_points)
        confidence = min(1.0, effective_points / max_confidence_points)
        
        return confidence
    
    def reset(self):
        """Reset the learner."""
        self._data_points = []
    
    def get_statistics(self):
        """Get statistics about the absorption data."""
        if not self._data_points:
            return {
                "count": 0,
                "min_rate": None,
                "max_rate": None,
                "avg_rate": None,
                "current_rate": self._default_rate,
                "confidence": 0.0
            }
            
        rates = [p["rate"] for p in self._data_points]
        return {
            "count": len(rates),
            "min_rate": min(rates),
            "max_rate": max(rates),
            "avg_rate": sum(rates) / len(rates),
            "current_rate": self.get_rate(),
            "confidence": self.get_confidence()
        }