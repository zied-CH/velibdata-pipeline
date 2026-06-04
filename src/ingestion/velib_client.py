"""Client pour les APIs Velib Metropole et Open-Meteo."""

from datetime import UTC, datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import api_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def fetch_station_status() -> dict:
    """Recupere le statut temps reel de toutes les stations."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(api_settings.velib_station_status_url)
        response.raise_for_status()
        payload = response.json()

    stations = payload.get("data", {}).get("stations", [])
    logger.info("station_status_fetched", count=len(stations))

    return {
        "source": "velib_station_status",
        "fetched_at": datetime.now(UTC).isoformat(),
        "station_count": len(stations),
        "stations": stations,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def fetch_station_info() -> dict:
    """Recupere les informations statiques des stations."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(api_settings.velib_station_info_url)
        response.raise_for_status()
        payload = response.json()

    stations = payload.get("data", {}).get("stations", [])
    logger.info("station_info_fetched", count=len(stations))

    return {
        "source": "velib_station_info",
        "fetched_at": datetime.now(UTC).isoformat(),
        "station_count": len(stations),
        "stations": stations,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def fetch_weather(lat: float = 48.8566, lon: float = 2.3522) -> dict:
    """Recupere la meteo actuelle pour Paris via Open-Meteo."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,windspeed_10m,weathercode",
        "hourly": "temperature_2m,precipitation,windspeed_10m,weathercode",
        "timezone": "Europe/Paris",
        "forecast_days": 1,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(api_settings.openmeteo_base_url, params=params)
        response.raise_for_status()
        payload = response.json()

    logger.info("weather_fetched", lat=lat, lon=lon)

    return {
        "source": "open_meteo",
        "fetched_at": datetime.now(UTC).isoformat(),
        "data": payload,
    }
