-- KPIs par station pour Power BI
-- Agregations et metriques cles

with availability as (
    select * from {{ ref('int_station_availability') }}
),

kpis as (
    select
        station_id,
        station_code,
        station_name,
        latitude,
        longitude,
        total_capacity,
        bikes_available,
        mechanical_bikes,
        electric_bikes,
        docks_available,
        fill_rate_pct,
        availability_status,
        is_installed,
        is_renting,
        is_returning,
        last_reported_at,
        -- Ratio electrique vs mecanique
        case
            when bikes_available > 0
            then round(cast(electric_bikes as float) / bikes_available * 100, 1)
            else 0
        end as electric_ratio_pct,
        -- Flag station active
        case
            when is_installed = 1 and is_renting = 1 and is_returning = 1
            then 1 else 0
        end as is_active,
        ingested_at
    from availability
)

select * from kpis
