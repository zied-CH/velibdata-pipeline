"""Transformations Bronze -> Silver -> Gold via pyodbc (logique dbt inlinee).

Reproduit les 8 modeles dbt sans dependre de dbt-core dans Azure Functions.
Les modeles sont definis dans azure_functions/dbt_project/models/.
"""

import logging
import os

import pyodbc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schemas SQL (Bronze → Silver views → Gold tables)
# Reproduit exactement la logique des modeles dbt_project/models/
# ---------------------------------------------------------------------------

_ENSURE_SCHEMAS = """
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'silver')
    EXEC('CREATE SCHEMA silver');
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'gold')
    EXEC('CREATE SCHEMA gold');
"""

_STAGING_VIEWS = {
    "silver.stg_station_status": """
        CREATE OR ALTER VIEW silver.stg_station_status AS
        WITH cleaned AS (
            SELECT
                CAST(station_id AS BIGINT) AS station_id,
                CAST(stationCode AS VARCHAR(10)) AS station_code,
                CAST(num_bikes_available AS INT) AS bikes_available,
                CAST(num_docks_available AS INT) AS docks_available,
                CAST(JSON_VALUE(num_bikes_available_types, '$[0].mechanical') AS INT) AS mechanical_bikes,
                CAST(JSON_VALUE(num_bikes_available_types, '$[1].ebike') AS INT) AS electric_bikes,
                CAST(is_installed AS BIT) AS is_installed,
                CAST(is_renting AS BIT) AS is_renting,
                CAST(is_returning AS BIT) AS is_returning,
                DATEADD(second, last_reported, '1970-01-01') AS last_reported_at,
                GETUTCDATE() AS ingested_at
            FROM bronze.station_status
            WHERE station_id IS NOT NULL
        )
        SELECT * FROM cleaned
    """,
    "silver.stg_station_info": """
        CREATE OR ALTER VIEW silver.stg_station_info AS
        WITH cleaned AS (
            SELECT
                CAST(station_id AS BIGINT) AS station_id,
                CAST(stationCode AS VARCHAR(10)) AS station_code,
                CAST(name AS VARCHAR(200)) AS station_name,
                CAST(capacity AS INT) AS total_capacity,
                CAST(lat AS FLOAT) AS latitude,
                CAST(lon AS FLOAT) AS longitude,
                GETUTCDATE() AS ingested_at
            FROM bronze.station_info
            WHERE station_id IS NOT NULL AND lat IS NOT NULL AND lon IS NOT NULL
        )
        SELECT * FROM cleaned
    """,
    "silver.stg_weather": """
        CREATE OR ALTER VIEW silver.stg_weather AS
        WITH cleaned AS (
            SELECT
                CAST(time AS DATETIME2) AS measured_at,
                CAST(temperature_2m AS FLOAT) AS temperature_celsius,
                CAST(precipitation AS FLOAT) AS precipitation_mm,
                CAST(windspeed_10m AS FLOAT) AS wind_speed_kmh,
                CAST(weathercode AS INT) AS weather_code,
                GETUTCDATE() AS ingested_at
            FROM bronze.weather
        )
        SELECT * FROM cleaned
    """,
    "silver.int_station_availability": """
        CREATE OR ALTER VIEW silver.int_station_availability AS
        SELECT
            s.station_id,
            s.station_code,
            i.station_name,
            i.latitude,
            i.longitude,
            i.total_capacity,
            s.bikes_available,
            s.mechanical_bikes,
            s.electric_bikes,
            s.docks_available,
            s.is_installed,
            s.is_renting,
            s.is_returning,
            s.last_reported_at,
            CASE
                WHEN i.total_capacity > 0
                THEN ROUND(CAST(s.bikes_available AS FLOAT) / i.total_capacity * 100, 1)
                ELSE 0
            END AS fill_rate_pct,
            CASE
                WHEN s.bikes_available = 0 THEN 'empty'
                WHEN s.docks_available = 0 THEN 'full'
                WHEN CAST(s.bikes_available AS FLOAT) / NULLIF(i.total_capacity, 0) < 0.2 THEN 'low'
                WHEN CAST(s.bikes_available AS FLOAT) / NULLIF(i.total_capacity, 0) > 0.8 THEN 'high'
                ELSE 'normal'
            END AS availability_status,
            s.ingested_at
        FROM silver.stg_station_status s
        LEFT JOIN silver.stg_station_info i ON s.station_id = i.station_id
    """,
    "silver.int_availability_weather": """
        CREATE OR ALTER VIEW silver.int_availability_weather AS
        WITH avail AS (
            SELECT *, DATEADD(hour, DATEDIFF(hour, 0, last_reported_at), 0) AS hour_key
            FROM silver.int_station_availability
        ),
        wthr AS (
            SELECT *, DATEADD(hour, DATEDIFF(hour, 0, measured_at), 0) AS hour_key
            FROM silver.stg_weather
        )
        SELECT
            a.station_id, a.station_code, a.station_name,
            a.latitude, a.longitude, a.total_capacity,
            a.bikes_available, a.mechanical_bikes, a.electric_bikes,
            a.docks_available, a.fill_rate_pct, a.availability_status,
            a.is_installed, a.is_renting, a.last_reported_at,
            w.temperature_celsius, w.precipitation_mm, w.wind_speed_kmh, w.weather_code,
            CASE
                WHEN w.weather_code IN (0, 1) THEN 'clear'
                WHEN w.weather_code IN (2, 3) THEN 'cloudy'
                WHEN w.weather_code IN (51,53,55,61,63,65,80,81,82) THEN 'rain'
                WHEN w.weather_code IN (71,73,75,77,85,86) THEN 'snow'
                WHEN w.weather_code IN (95,96,99) THEN 'storm'
                ELSE 'other'
            END AS weather_category,
            CASE
                WHEN w.temperature_celsius BETWEEN 15 AND 25
                     AND w.precipitation_mm = 0 AND w.wind_speed_kmh < 20 THEN 'ideal'
                WHEN w.temperature_celsius BETWEEN 10 AND 30
                     AND w.precipitation_mm < 1 THEN 'good'
                WHEN w.precipitation_mm > 5
                     OR w.temperature_celsius < 5
                     OR w.wind_speed_kmh > 40 THEN 'bad'
                ELSE 'moderate'
            END AS cycling_conditions,
            a.hour_key, a.ingested_at
        FROM avail a
        LEFT JOIN wthr w ON a.hour_key = w.hour_key
    """,
}

_MART_TABLES = {
    "gold.mart_station_kpis": {
        "drop": "IF OBJECT_ID('gold.mart_station_kpis', 'U') IS NOT NULL DROP TABLE gold.mart_station_kpis",
        "create": """
            SELECT
                station_id, station_code, station_name, latitude, longitude,
                total_capacity, bikes_available, mechanical_bikes, electric_bikes,
                docks_available, fill_rate_pct, availability_status,
                is_installed, is_renting, is_returning, last_reported_at,
                CASE
                    WHEN bikes_available > 0
                    THEN ROUND(CAST(electric_bikes AS FLOAT) / bikes_available * 100, 1)
                    ELSE 0
                END AS electric_ratio_pct,
                CASE
                    WHEN is_installed = 1 AND is_renting = 1 AND is_returning = 1 THEN 1
                    ELSE 0
                END AS is_active,
                GETUTCDATE() AS ingested_at
            INTO gold.mart_station_kpis
            FROM silver.int_station_availability
        """,
    },
    "gold.mart_city_overview": {
        "drop": "IF OBJECT_ID('gold.mart_city_overview', 'U') IS NOT NULL DROP TABLE gold.mart_city_overview",
        "create": """
            SELECT
                COUNT(*) AS total_stations,
                SUM(bikes_available) AS total_bikes_available,
                SUM(mechanical_bikes) AS total_mechanical,
                SUM(electric_bikes) AS total_electric,
                SUM(docks_available) AS total_docks_available,
                SUM(total_capacity) AS total_capacity,
                ROUND(AVG(CAST(fill_rate_pct AS FLOAT)), 1) AS avg_fill_rate_pct,
                SUM(CASE WHEN availability_status = 'empty' THEN 1 ELSE 0 END) AS stations_empty,
                SUM(CASE WHEN availability_status = 'full' THEN 1 ELSE 0 END) AS stations_full,
                SUM(CASE WHEN availability_status = 'low' THEN 1 ELSE 0 END) AS stations_low,
                GETUTCDATE() AS snapshot_at
            INTO gold.mart_city_overview
            FROM silver.int_station_availability
            WHERE is_installed = 1 AND is_renting = 1
        """,
    },
    "gold.mart_weather_impact": {
        "drop": "IF OBJECT_ID('gold.mart_weather_impact', 'U') IS NOT NULL DROP TABLE gold.mart_weather_impact",
        "create": """
            SELECT
                weather_category, cycling_conditions,
                temperature_celsius, precipitation_mm, wind_speed_kmh,
                COUNT(*) AS nb_observations,
                AVG(CAST(fill_rate_pct AS FLOAT)) AS avg_fill_rate_pct,
                AVG(CAST(bikes_available AS FLOAT)) AS avg_bikes_available,
                AVG(CAST(electric_bikes AS FLOAT)) AS avg_electric_bikes,
                AVG(CAST(mechanical_bikes AS FLOAT)) AS avg_mechanical_bikes,
                ROUND(
                    CAST(SUM(CASE WHEN availability_status = 'empty' THEN 1 ELSE 0 END) AS FLOAT)
                    / NULLIF(COUNT(*), 0) * 100, 1
                ) AS pct_stations_empty,
                ROUND(
                    CAST(SUM(CASE WHEN availability_status = 'full' THEN 1 ELSE 0 END) AS FLOAT)
                    / NULLIF(COUNT(*), 0) * 100, 1
                ) AS pct_stations_full,
                hour_key AS snapshot_hour
            INTO gold.mart_weather_impact
            FROM silver.int_availability_weather
            WHERE is_installed = 1 AND is_renting = 1 AND weather_category IS NOT NULL
            GROUP BY weather_category, cycling_conditions, temperature_celsius,
                     precipitation_mm, wind_speed_kmh, hour_key
        """,
    },
}

_QUALITY_TESTS = [
    ("station_id not null in kpis", "SELECT COUNT(*) FROM gold.mart_station_kpis WHERE station_id IS NULL"),
    ("city overview has rows", "SELECT COUNT(*) FROM gold.mart_city_overview"),
    ("no negative bikes", "SELECT COUNT(*) FROM gold.mart_station_kpis WHERE bikes_available < 0"),
    ("fill rate 0-100", "SELECT COUNT(*) FROM gold.mart_station_kpis WHERE fill_rate_pct < 0 OR fill_rate_pct > 100"),
    ("silver stg_station_status has rows", "SELECT COUNT(*) FROM silver.stg_station_status"),
    ("silver stg_station_info has rows", "SELECT COUNT(*) FROM silver.stg_station_info"),
]


def _get_sql_connection() -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.environ['SQL_SERVER']};"
        f"DATABASE={os.environ['SQL_DATABASE']};"
        f"UID={os.environ['SQL_USER']};PWD={os.environ['SQL_PASSWORD']};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


def run_dbt_transformations() -> dict:
    """Execute les transformations Bronze -> Silver -> Gold."""
    logger.info("dbt_run_start")
    conn = _get_sql_connection()
    nodes_passed = 0
    nodes_failed = 0
    statuses = []
    try:
        cursor = conn.cursor()
        for stmt in _ENSURE_SCHEMAS.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                cursor.execute(stmt)
        conn.commit()

        for name, sql in _STAGING_VIEWS.items():
            try:
                cursor.execute(sql.strip())
                conn.commit()
                nodes_passed += 1
                statuses.append(f"{name}=success")
                logger.info(f"view_created: {name}")
            except Exception as e:
                nodes_failed += 1
                statuses.append(f"{name}=error: {str(e)[:100]}")
                logger.error(f"view_failed: {name}: {e}")

        for name, ddl in _MART_TABLES.items():
            try:
                cursor.execute(ddl["drop"])
                cursor.execute(f"SELECT {ddl['create']}" if "INTO" not in ddl["create"] else ddl["create"])
                conn.commit()
                nodes_passed += 1
                statuses.append(f"{name}=success")
                logger.info(f"table_created: {name}")
            except Exception as e:
                nodes_failed += 1
                statuses.append(f"{name}=error: {str(e)[:100]}")
                logger.error(f"table_failed: {name}: {e}")

        return {
            "models_executed": nodes_passed + nodes_failed,
            "nodes_executed": nodes_passed + nodes_failed,
            "nodes_passed": nodes_passed,
            "nodes_failed": nodes_failed,
            "diagnostics": {"statuses": statuses},
        }
    finally:
        conn.close()


def run_dbt_tests() -> dict:
    """Valide les tables Gold : tests de qualite."""
    logger.info("dbt_test_start")
    conn = _get_sql_connection()
    passed = 0
    failed = 0
    statuses = []
    try:
        cursor = conn.cursor()
        for test_name, query in _QUALITY_TESTS:
            try:
                cursor.execute(query)
                row = cursor.fetchone()
                count = row[0] if row else 0
                if "not null" in test_name or "no negative" in test_name or "0-100" in test_name:
                    ok = count == 0
                else:
                    ok = count > 0
                status = "pass" if ok else "fail"
                if ok:
                    passed += 1
                else:
                    failed += 1
                statuses.append(f"{test_name}={status} (count={count})")
            except Exception as e:
                failed += 1
                statuses.append(f"{test_name}=error: {str(e)[:100]}")
        return {
            "nodes_executed": passed + failed,
            "nodes_passed": passed,
            "nodes_failed": failed,
            "diagnostics": {"statuses": statuses},
        }
    finally:
        conn.close()
