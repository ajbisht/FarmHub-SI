import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
import httpx
from agent.config import config

logger = logging.getLogger("WeatherClient")


@dataclass
class WeatherReport:
    temp_c: float
    humidity_pct: int
    description: str
    rain_expected_next_3h: bool
    rain_probability_pct: int
    is_live_data: bool


class WeatherClient:
    """Fetches local weather & precipitation forecast from OpenWeatherMap (Free Tier).
    Fails safely with offline defaults if network is unavailable or API key is unset.
    """

    BASE_URL = "https://api.openweathermap.org/data/2.5"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.openweather_api_key
        self.lat = config.latitude
        self.lon = config.longitude

    def get_forecast(self) -> WeatherReport:
        """Retrieves current weather and 3-hour precipitation probability."""
        if not self.api_key or self.api_key.startswith("your_"):
            logger.warning("OpenWeatherMap API key is not configured. Using offline fallback weather.")
            return WeatherReport(
                temp_c=28.0,
                humidity_pct=55,
                description="Clear / Simulated (No API Key)",
                rain_expected_next_3h=False,
                rain_probability_pct=0,
                is_live_data=False,
            )

        try:
            with httpx.Client(timeout=8.0) as client:
                # 1. Fetch current weather
                current_resp = client.get(
                    f"{self.BASE_URL}/weather",
                    params={
                        "lat": self.lat,
                        "lon": self.lon,
                        "appid": self.api_key,
                        "units": "metric",
                    },
                )
                current_resp.raise_for_status()
                current_data = current_resp.json()

                temp_c = current_data.get("main", {}).get("temp", 25.0)
                humidity_pct = current_data.get("main", {}).get("humidity", 50)
                description = (
                    current_data.get("weather", [{}])[0].get("description", "Clear").capitalize()
                )

                # 2. Fetch 5-day / 3-hour forecast to check next 3-6 hours for rain
                forecast_resp = client.get(
                    f"{self.BASE_URL}/forecast",
                    params={
                        "lat": self.lat,
                        "lon": self.lon,
                        "appid": self.api_key,
                        "units": "metric",
                        "cnt": 2,  # next 2 intervals (3h and 6h)
                    },
                )
                forecast_resp.raise_for_status()
                forecast_data = forecast_resp.json()

                # Check precipitation probability (pop: 0.0 to 1.0)
                first_period = forecast_data.get("list", [{}])[0]
                pop = first_period.get("pop", 0.0)
                rain_vol = first_period.get("rain", {}).get("3h", 0.0)

                # Flag rain if probability > 50% or volume > 0.5 mm
                rain_expected = (pop >= 0.5) or (rain_vol >= 0.5)

                return WeatherReport(
                    temp_c=round(temp_c, 1),
                    humidity_pct=int(humidity_pct),
                    description=description,
                    rain_expected_next_3h=rain_expected,
                    rain_probability_pct=int(pop * 100),
                    is_live_data=True,
                )

        except Exception as e:
            logger.error(f"Failed to fetch live weather from OpenWeatherMap: {e}")
            logger.info("Falling back to safe offline weather default (assume no rain).")
            return WeatherReport(
                temp_c=25.0,
                humidity_pct=50,
                description="Offline Fallback (Network/API Error)",
                rain_expected_next_3h=False,
                rain_probability_pct=0,
                is_live_data=False,
            )
