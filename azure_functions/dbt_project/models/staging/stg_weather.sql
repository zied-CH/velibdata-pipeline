-- Donnees meteo horaires pour Paris
-- Source: Bronze layer (Open-Meteo)

with source as (
    select * from {{ source('bronze', 'weather') }}
),

cleaned as (
    select
        cast(time as datetime2) as measured_at,
        cast(temperature_2m as float) as temperature_celsius,
        cast(precipitation as float) as precipitation_mm,
        cast(windspeed_10m as float) as wind_speed_kmh,
        cast(weathercode as int) as weather_code,
        getutcdate() as ingested_at
    from source
)

select * from cleaned
