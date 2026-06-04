"""Point d'entrée du pipeline d'ingestion VelibData.

Fetch les APIs en parallele et ecrit les donnees brutes dans Azure Data Lake Storage Gen2.
Partitionne par date : bronze/{source}/year=YYYY/month=MM/day=DD/{source}_{timestamp}.json
"""

import asyncio
import json
import time
from datetime import UTC, datetime

from azure.storage.filedatalake import DataLakeServiceClient

from src.ingestion.velib_client import fetch_station_info, fetch_station_status, fetch_weather
from src.quality.checks import validate_station_payload, validate_weather_payload
from src.utils.config import azure_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _get_adls_client() -> DataLakeServiceClient:
    """Cree le client ADLS Gen2 avec la cle du compte."""
    return DataLakeServiceClient(
        account_url=f"https://{azure_settings.adls_account_name}.dfs.core.windows.net",
        credential=azure_settings.adls_account_key,
    )


def _write_bronze(data: dict, source: str) -> str:
    """Ecrit les donnees brutes en JSON dans le Bronze layer (ADLS Gen2).

    Args:
        data: Le payload a ecrire (dictionnaire serialisable en JSON).
        source: Nom de la source (ex: 'station_status', 'weather').

    Returns:
        Le chemin du fichier ecrit dans ADLS.
    """
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    path = f"{source}/year={now.year}/month={now.month:02d}/day={now.day:02d}/{source}_{timestamp}.json"

    service = _get_adls_client()
    file_system = service.get_file_system_client(azure_settings.adls_container_bronze)
    file_client = file_system.get_file_client(path)

    json_data = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    file_client.upload_data(json_data, overwrite=True)

    size_kb = round(len(json_data) / 1024, 1)
    logger.info("bronze_written_to_adls", path=path, size_kb=size_kb)
    return path


async def run_ingestion() -> None:
    """Execute un cycle d ingestion complet vers ADLS Bronze."""
    cycle_start = time.monotonic()
    logger.info("ingestion_cycle_start", target="adls_gen2")

    try:
        fetch_start = time.monotonic()
        status, info, weather = await asyncio.gather(
            fetch_station_status(),
            fetch_station_info(),
            fetch_weather(),
        )
        fetch_duration_s = round(time.monotonic() - fetch_start, 2)
        logger.info("apis_fetched", duration_s=fetch_duration_s)

        # Controle qualite avant ecriture
        validate_station_payload(status, "station_status")
        validate_station_payload(info, "station_info")
        validate_weather_payload(weather)

        write_start = time.monotonic()
        _write_bronze(status, "station_status")
        _write_bronze(info, "station_info")
        _write_bronze(weather, "weather")
        write_duration_s = round(time.monotonic() - write_start, 2)

        total_duration_s = round(time.monotonic() - cycle_start, 2)

        logger.info(
            "ingestion_cycle_complete",
            stations=status["station_count"],
            fetch_duration_s=fetch_duration_s,
            write_duration_s=write_duration_s,
            total_duration_s=total_duration_s,
            # Alerte si > 5 min (300s) — seuil SLA ingestion
            sla_ok=total_duration_s < 300,
        )

    except Exception:
        total_duration_s = round(time.monotonic() - cycle_start, 2)
        logger.exception("ingestion_cycle_failed", duration_s=total_duration_s)
        raise


def main() -> None:
    asyncio.run(run_ingestion())


if __name__ == "__main__":
    main()
