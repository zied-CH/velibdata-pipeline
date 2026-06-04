"""Logique de chargement Bronze vers Azure SQL pour Azure Functions."""

import json
import logging
import os
from datetime import datetime

import pyodbc
from azure.storage.filedatalake import DataLakeServiceClient

logger = logging.getLogger(__name__)

BRONZE_SCHEMAS = {
    "station_status": """
        CREATE TABLE bronze.station_status (
            station_id BIGINT, stationCode VARCHAR(10),
            num_bikes_available INT, num_docks_available INT,
            num_bikes_available_types NVARCHAR(MAX),
            is_installed BIT, is_renting BIT, is_returning BIT,
            last_reported BIGINT, ingested_at DATETIME2 DEFAULT GETUTCDATE()
        )
    """,
    "station_info": """
        CREATE TABLE bronze.station_info (
            station_id BIGINT, stationCode VARCHAR(10),
            name NVARCHAR(200), capacity INT,
            lat FLOAT, lon FLOAT,
            ingested_at DATETIME2 DEFAULT GETUTCDATE()
        )
    """,
    "weather": """
        CREATE TABLE bronze.weather (
            time DATETIME2, temperature_2m FLOAT, precipitation FLOAT,
            windspeed_10m FLOAT, weathercode INT,
            ingested_at DATETIME2 DEFAULT GETUTCDATE()
        )
    """,
}


def _get_sql_connection() -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.environ['SQL_SERVER']};"
        f"DATABASE={os.environ['SQL_DATABASE']};"
        f"UID={os.environ['SQL_USER']};PWD={os.environ['SQL_PASSWORD']};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


def _get_adls_client() -> DataLakeServiceClient:
    return DataLakeServiceClient(
        account_url=f"https://{os.environ['ADLS_ACCOUNT_NAME']}.dfs.core.windows.net",
        credential=os.environ["ADLS_ACCOUNT_KEY"],
    )


def ensure_bronze_schema(conn: pyodbc.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'bronze')
        BEGIN EXEC('CREATE SCHEMA bronze') END
    """)
    for table, create_sql in BRONZE_SCHEMAS.items():
        clean_sql = create_sql.strip().replace("'", "''")
        cursor.execute(f"""
            IF NOT EXISTS (
                SELECT * FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE s.name = 'bronze' AND t.name = '{table}'
            )
            BEGIN EXEC('{clean_sql}') END
        """)
    conn.commit()


def get_latest_file(service: DataLakeServiceClient, source: str) -> dict:
    fs = service.get_file_system_client(os.environ.get("ADLS_CONTAINER_BRONZE", "bronze"))
    paths = list(fs.get_paths(path=source, recursive=True))
    json_files = [p for p in paths if p.name.endswith(".json")]
    latest = max(json_files, key=lambda p: p.last_modified)
    file_client = fs.get_file_client(latest.name)
    return json.loads(file_client.download_file().readall())


def load_station_status(conn, data: dict) -> int:
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE bronze.station_status")
    stations = data.get("stations", [])
    rows = [
        (s.get("station_id"), s.get("stationCode"), s.get("num_bikes_available"),
         s.get("num_docks_available"), json.dumps(s.get("num_bikes_available_types", [])),
         s.get("is_installed", 0), s.get("is_renting", 0), s.get("is_returning", 0),
         s.get("last_reported"))
        for s in stations
    ]
    cursor.fast_executemany = True
    cursor.executemany("""
        INSERT INTO bronze.station_status
        (station_id, stationCode, num_bikes_available, num_docks_available,
         num_bikes_available_types, is_installed, is_renting, is_returning, last_reported)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


def load_station_info(conn, data: dict) -> int:
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE bronze.station_info")
    stations = data.get("stations", [])
    rows = [
        (s.get("station_id"), s.get("stationCode"), s.get("name"),
         s.get("capacity"), s.get("lat"), s.get("lon"))
        for s in stations
    ]
    cursor.fast_executemany = True
    cursor.executemany("""
        INSERT INTO bronze.station_info (station_id, stationCode, name, capacity, lat, lon)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


def load_weather(conn, data: dict) -> int:
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE bronze.weather")
    hourly = data.get("data", {}).get("hourly", {})
    rows = [
        (datetime.fromisoformat(t), tmp, p, w, c)
        for t, tmp, p, w, c in zip(
            hourly.get("time", []), hourly.get("temperature_2m", []),
            hourly.get("precipitation", []), hourly.get("windspeed_10m", []),
            hourly.get("weathercode", []), strict=False,
        )
    ]
    cursor.fast_executemany = True
    cursor.executemany("""
        INSERT INTO bronze.weather (time, temperature_2m, precipitation, windspeed_10m, weathercode)
        VALUES (?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


def run_load() -> dict:
    """Execute le chargement complet Bronze vers SQL Database."""
    logger.info("load_bronze_start")
    service = _get_adls_client()
    conn = _get_sql_connection()
    try:
        ensure_bronze_schema(conn)
        loaded = {
            "station_status": load_station_status(conn, get_latest_file(service, "station_status")),
            "station_info": load_station_info(conn, get_latest_file(service, "station_info")),
            "weather": load_weather(conn, get_latest_file(service, "weather")),
        }
        logger.info(f"load_bronze_complete: {loaded}")
        return loaded
    finally:
        conn.close()
