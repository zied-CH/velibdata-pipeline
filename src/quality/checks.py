"""Controles qualite des donnees ingérees avant ecriture en bronze."""

from src.utils.logger import get_logger

logger = get_logger(__name__)

_MIN_STATIONS = 100
_MAX_NULL_RATE = 0.05  # 5% max de valeurs nulles tolerees

# Champs obligatoires par source
_REQUIRED_STATION_STATUS_FIELDS = {"station_id", "num_bikes_available", "is_renting"}
_REQUIRED_STATION_INFO_FIELDS = {"station_id", "name", "lat", "lon", "capacity"}
_REQUIRED_PAYLOAD_KEYS = {"source", "fetched_at", "station_count", "stations"}
_REQUIRED_WEATHER_KEYS = {"source", "fetched_at", "data"}


def validate_station_payload(data: dict, source: str) -> None:
    """Valide un payload station (status ou info) avant ecriture bronze.

    Verifie : schema, row_count, doublons, champs nulls critiques.

    Raises:
        ValueError: si donnees absentes, schema invalide ou doublons detectes.
    """
    _validate_schema(data, _REQUIRED_PAYLOAD_KEYS, source)

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

    stations = data.get("stations", [])
    required_fields = _REQUIRED_STATION_STATUS_FIELDS if source == "station_status" else _REQUIRED_STATION_INFO_FIELDS
    _validate_no_duplicates(stations, source)
    _validate_critical_fields(stations, required_fields, source)

    logger.info("data_quality_ok", source=source, station_count=station_count)


def validate_weather_payload(data: dict) -> None:
    """Valide le payload meteo avant ecriture bronze.

    Raises:
        ValueError: si le payload est vide ou le schema invalide.
    """
    _validate_schema(data, _REQUIRED_WEATHER_KEYS, "weather")

    if not data.get("data"):
        raise ValueError("[weather] Payload meteo vide — aucune donnee recue")

    logger.info("data_quality_ok", source="weather")


def _validate_schema(data: dict, required_keys: set, source: str) -> None:
    """Verifie que les cles obligatoires sont presentes dans le payload.

    Raises:
        ValueError: si des cles obligatoires sont manquantes (changement de schema API).
    """
    missing = required_keys - set(data.keys())
    if missing:
        raise ValueError(
            f"[{source}] Schema invalide — cles manquantes : {missing}. " "L'API a peut-etre change sa structure."
        )


def _validate_no_duplicates(stations: list, source: str) -> None:
    """Verifie l'absence de doublons sur station_id.

    Raises:
        ValueError: si des doublons sont detectes.
    """
    ids = [s.get("station_id") for s in stations if s.get("station_id") is not None]
    if len(ids) != len(set(ids)):
        duplicates = len(ids) - len(set(ids))
        raise ValueError(f"[{source}] {duplicates} doublon(s) detecte(s) sur station_id")


def _validate_critical_fields(stations: list, required_fields: set, source: str) -> None:
    """Verifie les valeurs nulles sur les champs critiques.

    Log un warning si le taux de nulls depasse 5%.

    Raises:
        ValueError: si un champ critique est absent de tous les enregistrements.
    """
    if not stations:
        return

    for field in required_fields:
        null_count = sum(1 for s in stations if s.get(field) is None)
        null_rate = null_count / len(stations)

        if null_rate == 1.0:
            raise ValueError(f"[{source}] Champ critique '{field}' absent de tous les enregistrements")

        if null_rate > _MAX_NULL_RATE:
            logger.warning(
                "data_quality_null_warning",
                source=source,
                field=field,
                null_count=null_count,
                null_rate=round(null_rate * 100, 1),
                threshold_pct=_MAX_NULL_RATE * 100,
            )
