-- Analyse de l impact de la meteo sur l utilisation des Velib
-- Alimente les dashboards Power BI et les features ML

with data as (
    select * from {{ ref('int_availability_weather') }}
    where is_installed = 1
      and is_renting = 1
      and weather_category is not null
),

weather_impact as (
    select
        weather_category,
        cycling_conditions,
        temperature_celsius,
        precipitation_mm,
        wind_speed_kmh,

        -- Metriques d utilisation par condition meteo
        count(*) as nb_observations,
        avg(cast(fill_rate_pct as float)) as avg_fill_rate_pct,
        avg(cast(bikes_available as float)) as avg_bikes_available,
        avg(cast(electric_bikes as float)) as avg_electric_bikes,
        avg(cast(mechanical_bikes as float)) as avg_mechanical_bikes,

        -- Taux de stations vides (indicateur de forte demande)
        round(
            cast(sum(case when availability_status = 'empty' then 1 else 0 end) as float)
            / nullif(count(*), 0) * 100,
            1
        ) as pct_stations_empty,

        -- Taux de stations pleines (indicateur de faible demande)
        round(
            cast(sum(case when availability_status = 'full' then 1 else 0 end) as float)
            / nullif(count(*), 0) * 100,
            1
        ) as pct_stations_full,

        hour_key as snapshot_hour
    from data
    group by
        weather_category,
        cycling_conditions,
        temperature_celsius,
        precipitation_mm,
        wind_speed_kmh,
        hour_key
)

select * from weather_impact
