"""Controles qualite des donnees ingérees avant ecriture en bronze."""

from src.utils.logger import get_logger

logger = get_logger(__name__)

_MIN_STATIONS = 100  # Velib Paris compte ~1400 stations actives


def validate_station_payload(data: dict, source: str) -> None:
    """Valide un payload station (status ou info) avant ecriture bronze.

    Raises:
        ValueError: si row_count == 0 (aucune donnee recue).
    """
    station_count = data.get("station_count", 0)

    if station_count == 0:
        raise ValueError(f"[{source}] Aucune donnee recue — row_count = 0")

    if station_count < _MIN_STATIONS:
        logger.warning(
            "data_quality_warning",
            source=source,
            station_count=station_count,
            threshold=_MIN_STATIONS,
            message="Nombre de stations anormalement bas",
        )
    else:
        logger.info("data_quality_ok", source=source, station_count=station_count)


def validate_weather_payload(data: dict) -> None:
    """Valide le payload meteo avant ecriture bronze.

    Raises:
        ValueError: si le payload est vide.
    """
    if not data.get("data"):
        raise ValueError("[weather] Payload meteo vide — aucune donnee recue")

    logger.info("data_quality_ok", source="weather")
