-- Referentiel des stations Velib (donnees statiques)
-- Source: Bronze layer (station_information)

with source as (
    select * from {{ source('bronze', 'station_info') }}
),

cleaned as (
    select
        cast(station_id as bigint) as station_id,
        cast("stationCode" as varchar(10)) as station_code,
        cast(name as varchar(200)) as station_name,
        cast(capacity as int) as total_capacity,
        cast(lat as float) as latitude,
        cast(lon as float) as longitude,
        getutcdate() as ingested_at
    from source
    where station_id is not null
      and lat is not null
      and lon is not null
)

select * from cleaned
