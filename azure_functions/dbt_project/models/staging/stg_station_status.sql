-- Nettoyage des donnees temps reel des stations Velib
-- Source: Bronze layer (station_status)

with source as (
    select * from {{ source('bronze', 'station_status') }}
),

cleaned as (
    select
        cast(station_id as bigint) as station_id,
        cast("stationCode" as varchar(10)) as station_code,
        cast(num_bikes_available as int) as bikes_available,
        cast(num_docks_available as int) as docks_available,
        cast(json_value(num_bikes_available_types, '$[0].mechanical') as int) as mechanical_bikes,
        cast(json_value(num_bikes_available_types, '$[1].ebike') as int) as electric_bikes,
        cast(is_installed as bit) as is_installed,
        cast(is_renting as bit) as is_renting,
        cast(is_returning as bit) as is_returning,
        dateadd(second, last_reported, '1970-01-01') as last_reported_at,
        getutcdate() as ingested_at
    from source
    where station_id is not null
)

select * from cleaned
