-- Jointure disponibilite des stations + meteo
-- Cle de jointure : horodatage arrondi a l heure
-- Permet d analyser l impact de la meteo sur l utilisation

with availability as (
    select
        *,
        -- Arrondir le timestamp a l heure pour matcher la meteo
        dateadd(hour, datediff(hour, 0, last_reported_at), 0) as hour_key
    from {{ ref('int_station_availability') }}
),

weather as (
    select
        *,
        -- La meteo est deja horaire, on cree la meme cle
        dateadd(hour, datediff(hour, 0, measured_at), 0) as hour_key
    from {{ ref('stg_weather') }}
),

joined as (
    select
        a.station_id,
        a.station_code,
        a.station_name,
        a.latitude,
        a.longitude,
        a.total_capacity,
        a.bikes_available,
        a.mechanical_bikes,
        a.electric_bikes,
        a.docks_available,
        a.fill_rate_pct,
        a.availability_status,
        a.is_installed,
        a.is_renting,
        a.last_reported_at,

        -- Donnees meteo
        w.temperature_celsius,
        w.precipitation_mm,
        w.wind_speed_kmh,
        w.weather_code,

        -- Features ML : classification meteo
        case
            when w.weather_code in (0, 1) then 'clear'
            when w.weather_code in (2, 3) then 'cloudy'
            when w.weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82) then 'rain'
            when w.weather_code in (71, 73, 75, 77, 85, 86) then 'snow'
            when w.weather_code in (95, 96, 99) then 'storm'
            else 'other'
        end as weather_category,

        -- Features ML : confort cycliste
        case
            when w.temperature_celsius between 15 and 25
                 and w.precipitation_mm = 0
                 and w.wind_speed_kmh < 20
            then 'ideal'
            when w.temperature_celsius between 10 and 30
                 and w.precipitation_mm < 1
            then 'good'
            when w.precipitation_mm > 5
                 or w.temperature_celsius < 5
                 or w.wind_speed_kmh > 40
            then 'bad'
            else 'moderate'
        end as cycling_conditions,

        a.hour_key,
        a.ingested_at
    from availability a
    left join weather w on a.hour_key = w.hour_key
)

select * from joined
