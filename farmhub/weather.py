"""Weather Service Integration for FarmHub AI using Open-Meteo API."""

import logging
from typing import Dict, Any, Optional
import urllib.request
import json

logger = logging.getLogger("farmhub.weather")

class WeatherService:
    def __init__(self, latitude: float = 29.60, longitude: float = 79.45):
        """Default coordinates: Himalayan foothills (Uttarakhand / Nainital area)."""
        self.latitude = latitude
        self.longitude = longitude
        self.cached_weather: Optional[Dict[str, Any]] = None

    def fetch_forecast(self) -> Dict[str, Any]:
        """Fetch real-time weather & 12h precipitation probability from Open-Meteo."""
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={self.latitude}&longitude={self.longitude}&"
            f"current=temperature_2m,relative_humidity_2m,weather_code&"
            f"hourly=precipitation_probability,rain&forecast_hours=12"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FarmHub/2.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

            current = data.get("current", {})
            hourly = data.get("hourly", {})

            # Max rain probability in the next 6-12 hours
            rain_probs = hourly.get("precipitation_probability", [0])
            max_rain_prob = max(rain_probs[:6]) if rain_probs else 0

            weather_info = {
                "temperature_c": current.get("temperature_2m", 24.0),
                "humidity_pct": current.get("relative_humidity_2m", 60),
                "weather_code": current.get("weather_code", 0),
                "rain_probability_pct": max_rain_prob,
                "rain_expected_soon": max_rain_prob >= 60,
                "status": "LIVE"
            }
            self.cached_weather = weather_info
            return weather_info
        except Exception as e:
            logger.warning(f"Failed to fetch live weather from Open-Meteo: {e}. Using cached/fallback.")
            if self.cached_weather:
                return self.cached_weather
            # Fallback dry weather default
            return {
                "temperature_c": 24.5,
                "humidity_pct": 55,
                "weather_code": 0,
                "rain_probability_pct": 10,
                "rain_expected_soon": False,
                "status": "OFFLINE_FALLBACK"
            }
