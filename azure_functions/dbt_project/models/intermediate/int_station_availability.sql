-- Jointure station_status + station_info
-- Enrichit la disponibilite avec les infos de la station

with status as (
    select * from {{ ref('stg_station_status') }}
),

info as (
    select * from {{ ref('stg_station_info') }}
),

joined as (
    select
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
        -- Calcul du taux de remplissage
        case
            when i.total_capacity > 0
            then round(cast(s.bikes_available as float) / i.total_capacity * 100, 1)
            else 0
        end as fill_rate_pct,
        -- Classification de la disponibilite
        case
            when s.bikes_available = 0 then 'empty'
            when s.docks_available = 0 then 'full'
            when cast(s.bikes_available as float) / nullif(i.total_capacity, 0) < 0.2 then 'low'
            when cast(s.bikes_available as float) / nullif(i.total_capacity, 0) > 0.8 then 'high'
            else 'normal'
        end as availability_status,
        s.ingested_at
    from status s
    left join info i on s.station_id = i.station_id
)

select * from joined
