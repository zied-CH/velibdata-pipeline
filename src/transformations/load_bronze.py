"""Charge les donnees JSON depuis ADLS Bronze vers Azure SQL Database.

Lit les derniers fichiers JSON de chaque source dans ADLS et les insere
comme tables dans le schema 'bronze' de SQL Database.

Strategie : truncate + insert (on remplace tout a chaque cycle).
Pour de l incremental, voir Azure Data Factory.
"""

import json
from datetime import datetime

import pyodbc
from azure.storage.filedatalake import DataLakeServiceClient

from src.utils.config import azure_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Schemas Bronze a creer dans SQL Database
BRONZE_SCHEMAS = {
    "station_status": """
        CREATE TABLE bronze.station_status (
            station_id BIGINT,
            stationCode VARCHAR(10),
            num_bikes_available INT,
            num_docks_available INT,
            num_bikes_available_types NVARCHAR(MAX),
            is_installed BIT,
            is_renting BIT,
            is_returning BIT,
            last_reported BIGINT,
            ingested_at DATETIME2 DEFAULT GETUTCDATE()
        )
    """,
    "station_info": """
        CREATE TABLE bronze.station_info (
            station_id BIGINT,
            stationCode VARCHAR(10),
            name NVARCHAR(200),
            capacity INT,
            lat FLOAT,
            lon FLOAT,
            ingested_at DATETIME2 DEFAULT GETUTCDATE()
        )
    """,
    "weather": """
        CREATE TABLE bronze.weather (
            time DATETIME2,
            temperature_2m FLOAT,
            precipitation FLOAT,
            windspeed_10m FLOAT,
            weathercode INT,
            ingested_at DATETIME2 DEFAULT GETUTCDATE()
        )
    """,
}


def _get_sql_connection() -> pyodbc.Connection:
    """Connexion a Azure SQL Database via les credentials du .env."""
    import os

    server = os.getenv("SQL_SERVER")
    database = os.getenv("SQL_DATABASE")
    user = os.getenv("SQL_USER")
    password = os.getenv("SQL_PASSWORD")

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};DATABASE={database};"
        f"UID={user};PWD={password};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


def _get_adls_client() -> DataLakeServiceClient:
    return DataLakeServiceClient(
        account_url=f"https://{azure_settings.adls_account_name}.dfs.core.windows.net",
        credential=azure_settings.adls_account_key,
    )


def ensure_bronze_schema(conn: pyodbc.Connection) -> None:
    """Cree le schema 'bronze' et les tables si elles n existent pas."""
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'bronze')
        BEGIN
            EXEC('CREATE SCHEMA bronze')
        END
    """)
    for table, create_sql in BRONZE_SCHEMAS.items():
        cursor.execute(f"""
            IF NOT EXISTS (
                SELECT * FROM sys.tables t
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE s.name = 'bronze' AND t.name = '{table}'
            )
            BEGIN
                EXEC('{create_sql.strip().replace("'", "''")}')
            END
        """)
    conn.commit()
    logger.info("bronze_schema_ensured")


def get_latest_file(service: DataLakeServiceClient, source: str) -> dict:
    """Recupere le fichier JSON le plus recent pour une source donnee."""
    fs = service.get_file_system_client(azure_settings.adls_container_bronze)
    paths = list(fs.get_paths(path=source, recursive=True))
    json_files = [p for p in paths if p.name.endswith(".json")]

    if not json_files:
        raise FileNotFoundError(f"Aucun fichier JSON pour la source '{source}'")

    latest = max(json_files, key=lambda p: p.last_modified)
    logger.info("latest_file_found", source=source, path=latest.name)

    file_client = fs.get_file_client(latest.name)
    content = file_client.download_file().readall()
    return json.loads(content)


def load_station_status(conn: pyodbc.Connection, data: dict) -> int:
    """Charge station_status dans bronze.station_status."""
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE bronze.station_status")

    stations = data.get("stations", [])
    rows = []
    for s in stations:
        rows.append((
            s.get("station_id"),
            s.get("stationCode"),
            s.get("num_bikes_available"),
            s.get("num_docks_available"),
            json.dumps(s.get("num_bikes_available_types", [])),
            s.get("is_installed", 0),
            s.get("is_renting", 0),
            s.get("is_returning", 0),
            s.get("last_reported"),
        ))

    cursor.fast_executemany = True
    cursor.executemany("""
        INSERT INTO bronze.station_status
        (station_id, stationCode, num_bikes_available, num_docks_available,
         num_bikes_available_types, is_installed, is_renting, is_returning, last_reported)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    logger.info("station_status_loaded", count=len(rows))
    return len(rows)


def load_station_info(conn: pyodbc.Connection, data: dict) -> int:
    """Charge station_info dans bronze.station_info."""
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE bronze.station_info")

    stations = data.get("stations", [])
    rows = []
    for s in stations:
        rows.append((
            s.get("station_id"),
            s.get("stationCode"),
            s.get("name"),
            s.get("capacity"),
            s.get("lat"),
            s.get("lon"),
        ))

    cursor.fast_executemany = True
    cursor.executemany("""
        INSERT INTO bronze.station_info
        (station_id, stationCode, name, capacity, lat, lon)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    logger.info("station_info_loaded", count=len(rows))
    return len(rows)


def load_weather(conn: pyodbc.Connection, data: dict) -> int:
    """Charge weather (hourly) dans bronze.weather."""
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE bronze.weather")

    hourly = data.get("data", {}).get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    precs = hourly.get("precipitation", [])
    winds = hourly.get("windspeed_10m", [])
    codes = hourly.get("weathercode", [])

    rows = [
        (datetime.fromisoformat(t), tmp, p, w, c)
        for t, tmp, p, w, c in zip(times, temps, precs, winds, codes, strict=False)
    ]

    cursor.fast_executemany = True
    cursor.executemany("""
        INSERT INTO bronze.weather (time, temperature_2m, precipitation, windspeed_10m, weathercode)
        VALUES (?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    logger.info("weather_loaded", count=len(rows))
    return len(rows)


def main() -> None:
    """Charge les 3 sources Bronze depuis ADLS vers SQL Database."""
    logger.info("load_bronze_start", target="azure_sql")

    service = _get_adls_client()
    conn = _get_sql_connection()

    try:
        ensure_bronze_schema(conn)

        status_data = get_latest_file(service, "station_status")
        load_station_status(conn, status_data)

        info_data = get_latest_file(service, "station_info")
        load_station_info(conn, info_data)

        weather_data = get_latest_file(service, "weather")
        load_weather(conn, weather_data)

        logger.info("load_bronze_complete")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
