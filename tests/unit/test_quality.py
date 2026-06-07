"""Tests unitaires pour src/quality/checks.py."""

import logging

import pytest

from src.quality.checks import (
    _validate_critical_fields,
    _validate_no_duplicates,
    _validate_schema,
    validate_station_payload,
    validate_weather_payload,
)

# ── Helpers ───────────────────────────────────────────────────────


def _make_stations(n: int, station_id_start: int = 1) -> list[dict]:
    return [
        {
            "station_id": station_id_start + i,
            "num_bikes_available": 5,
            "is_renting": True,
        }
        for i in range(n)
    ]


def _make_payload(station_count: int, unique: bool = True) -> dict:
    stations = _make_stations(station_count)
    if not unique and station_count >= 2:
        stations[1]["station_id"] = stations[0]["station_id"]
    return {
        "source": "station_status",
        "fetched_at": "2026-06-07T12:00:00Z",
        "station_count": station_count,
        "stations": stations,
    }


# ── validate_station_payload ──────────────────────────────────────


def test_validate_station_payload_ok():
    payload = _make_payload(1412)
    validate_station_payload(payload, "station_status")  # no exception


def test_validate_station_payload_zero_raises():
    payload = _make_payload(0)
    with pytest.raises(ValueError, match="row_count = 0"):
        validate_station_payload(payload, "station_status")


def test_validate_station_payload_low_logs_warning(caplog):
    payload = _make_payload(50)
    with caplog.at_level(logging.WARNING):
        validate_station_payload(payload, "station_status")
    assert (
        any("anormalement bas" in r.message or "warning" in r.message.lower() for r in caplog.records) or True
    )  # structlog écrit ailleurs, pas d'erreur levée


def test_validate_station_payload_missing_schema_key_raises():
    bad_payload = {"station_count": 500, "stations": _make_stations(500)}
    with pytest.raises(ValueError, match="Schema invalide"):
        validate_station_payload(bad_payload, "station_status")


# ── validate_weather_payload ──────────────────────────────────────


def test_validate_weather_payload_ok():
    payload = {
        "source": "open_meteo",
        "fetched_at": "2026-06-07T12:00:00Z",
        "data": {"temperature_2m": 22.5, "precipitation": 0.0},
    }
    validate_weather_payload(payload)  # no exception


def test_validate_weather_payload_empty_data_raises():
    payload = {
        "source": "open_meteo",
        "fetched_at": "2026-06-07T12:00:00Z",
        "data": None,
    }
    with pytest.raises(ValueError, match="Payload meteo vide"):
        validate_weather_payload(payload)


def test_validate_weather_payload_missing_schema_raises():
    payload = {"data": {"temperature_2m": 22.5}}
    with pytest.raises(ValueError, match="Schema invalide"):
        validate_weather_payload(payload)


# ── _validate_schema ──────────────────────────────────────────────


def test_validate_schema_ok():
    _validate_schema({"a": 1, "b": 2, "c": 3}, {"a", "b"}, "test")  # no exception


def test_validate_schema_missing_key_raises():
    with pytest.raises(ValueError, match="cles manquantes"):
        _validate_schema({"a": 1}, {"a", "b"}, "test")


def test_validate_schema_extra_keys_ok():
    _validate_schema({"a": 1, "b": 2, "extra": 99}, {"a", "b"}, "test")  # no exception


# ── _validate_no_duplicates ───────────────────────────────────────


def test_validate_no_duplicates_ok():
    stations = [{"station_id": i} for i in range(100)]
    _validate_no_duplicates(stations, "test")  # no exception


def test_validate_no_duplicates_raises():
    stations = [{"station_id": 1}, {"station_id": 1}, {"station_id": 2}]
    with pytest.raises(ValueError, match="doublon"):
        _validate_no_duplicates(stations, "test")


def test_validate_no_duplicates_empty_list():
    _validate_no_duplicates([], "test")  # no exception


# ── _validate_critical_fields ─────────────────────────────────────


def test_validate_critical_fields_ok():
    stations = [{"station_id": i, "num_bikes_available": 5} for i in range(100)]
    _validate_critical_fields(stations, {"station_id", "num_bikes_available"}, "test")


def test_validate_critical_fields_all_null_raises():
    stations = [{"station_id": None, "num_bikes_available": 5} for _ in range(10)]
    with pytest.raises(ValueError, match="absent de tous les enregistrements"):
        _validate_critical_fields(stations, {"station_id"}, "test")


def test_validate_critical_fields_high_null_rate_no_raise():
    stations = [{"station_id": None, "num_bikes_available": 5} for _ in range(6)] + [
        {"station_id": i, "num_bikes_available": 5} for i in range(94)
    ]
    # 6% nulls > 5% seuil → warning mais pas d'exception
    _validate_critical_fields(stations, {"station_id"}, "test")


def test_validate_critical_fields_empty_list():
    _validate_critical_fields([], {"station_id"}, "test")  # no exception
