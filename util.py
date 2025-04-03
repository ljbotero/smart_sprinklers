"""Utility functions for Smart Sprinklers."""
import logging

_LOGGER = logging.getLogger(__name__)

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