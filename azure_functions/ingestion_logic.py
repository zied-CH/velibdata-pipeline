"""Logique d ingestion adaptee pour Azure Functions.

Resilience : si la meteo echoue (API down), on continue avec Velib uniquement.
"""

import json
import logging
import os
from datetime import UTC, datetime

import httpx
from azure.storage.filedatalake import DataLakeServiceClient

logger = logging.getLogger(__name__)

VELIB_STATUS_URL = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_status.json"
VELIB_INFO_URL = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_information.json"
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"


def _get_adls_client() -> DataLakeServiceClient:
    return DataLakeServiceClient(
        account_url=f"https://{os.environ['ADLS_ACCOUNT_NAME']}.dfs.core.windows.net",
        credential=os.environ["ADLS_ACCOUNT_KEY"],
    )


def _write_bronze(data: dict, source: str) -> str:
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    path = f"{source}/year={now.year}/month={now.month:02d}/day={now.day:02d}/{source}_{timestamp}.json"
    service = _get_adls_client()
    fs = service.get_file_system_client(os.environ.get("ADLS_CONTAINER_BRONZE", "bronze"))
    file_client = fs.get_file_client(path)
    json_data = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    file_client.upload_data(json_data, overwrite=True)
    logger.info(f"bronze_written: {path}")
    return path


async def fetch_station_status() -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(VELIB_STATUS_URL)
        response.raise_for_status()
        payload = response.json()
    stations = payload.get("data", {}).get("stations", [])
    return {
        "source": "velib_station_status",
        "fetched_at": datetime.now(UTC).isoformat(),
        "station_count": len(stations),
        "stations": stations,
    }


async def fetch_station_info() -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(VELIB_INFO_URL)
        response.raise_for_status()
        payload = response.json()
    stations = payload.get("data", {}).get("stations", [])
    return {
        "source": "velib_station_info",
        "fetched_at": datetime.now(UTC).isoformat(),
        "station_count": len(stations),
        "stations": stations,
    }


async def fetch_weather() -> dict:
    """Recupere la meteo - leve une exception si echec."""
    params = {
        "latitude": 48.8566, "longitude": 2.3522,
        "current": "temperature_2m,precipitation,windspeed_10m,weathercode",
        "hourly": "temperature_2m,precipitation,windspeed_10m,weathercode",
        "timezone": "Europe/Paris", "forecast_days": 1,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(OPENMETEO_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    return {
        "source": "open_meteo",
        "fetched_at": datetime.now(UTC).isoformat(),
        "data": payload,
    }


async def run_ingestion() -> dict:
    """Cycle d ingestion resilient : meteo optionnelle."""
    import asyncio
    logger.info("ingestion_cycle_start")

    # Velib est critique - si ca echoue on arrete tout
    status = await fetch_station_status()
    info = await fetch_station_info()
    _write_bronze(status, "station_status")
    _write_bronze(info, "station_info")

    # Meteo optionnelle - on continue meme si echec
    weather_status = "ok"
    try:
        weather = await fetch_weather()
        _write_bronze(weather, "weather")
    except Exception as e:
        logger.warning(f"weather_fetch_failed (continuing without): {str(e)[:200]}")
        weather_status = f"skipped: {str(e)[:100]}"

    logger.info(f"ingestion_complete: {status['station_count']} stations, weather={weather_status}")
    return {"stations": status["station_count"], "weather": weather_status}
