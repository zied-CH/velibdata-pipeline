-- Vue globale de la ville pour le dashboard principal
-- Metriques agregees sur toutes les stations actives

with stations as (
    select * from {{ ref('int_station_availability') }}
    where is_installed = 1
      and is_renting = 1
),

overview as (
    select
        count(*) as total_stations,
        sum(bikes_available) as total_bikes_available,
        sum(mechanical_bikes) as total_mechanical,
        sum(electric_bikes) as total_electric,
        sum(docks_available) as total_docks_available,
        sum(total_capacity) as total_capacity,
        round(avg(cast(fill_rate_pct as float)), 1) as avg_fill_rate_pct,
        sum(case when availability_status = 'empty' then 1 else 0 end) as stations_empty,
        sum(case when availability_status = 'full' then 1 else 0 end) as stations_full,
        sum(case when availability_status = 'low' then 1 else 0 end) as stations_low,
        getutcdate() as snapshot_at
    from stations
)

select * from overview
