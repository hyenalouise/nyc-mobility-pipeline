-- Bronze landing for the Open-Meteo historical weather source.

CREATE TABLE IF NOT EXISTS `ftw-week-08`.`01-bronze`.weather_raw (
    -- Raw value as returned when requested with timezone=UTC (per D09).
    observation_timestamp_utc TIMESTAMP,
    temperature_2m DOUBLE,
    precipitation_mm DOUBLE,
    weather_code INT,
    requested_latitude DOUBLE,
    requested_longitude DOUBLE,
    requested_start_date STRING,
    requested_end_date STRING,
    weather_model STRING,
    returned_latitude DOUBLE,
    returned_longitude DOUBLE,
    elevation_m DOUBLE,
    utc_offset_seconds INT,
    timezone STRING,
    timezone_abbreviation STRING,
    source_url STRING,
    source_file STRING,
    source_file_version STRING,
    batch_id STRING,
    ingested_at TIMESTAMP
);

INSERT INTO `ftw-week-08`.`01-bronze`.weather_raw
SELECT
    CAST(exploded.observation_time AS TIMESTAMP)   AS observation_timestamp_utc,
    hourly.temperature_2m[exploded.pos]             AS temperature_2m,
    hourly.precipitation[exploded.pos]              AS precipitation_mm,
    CAST(hourly.weather_code[exploded.pos] AS INT)  AS weather_code,
    CAST(40.7128 AS DOUBLE)  AS requested_latitude,
    CAST(-74.0060 AS DOUBLE) AS requested_longitude,
    '2026-03-01' AS requested_start_date,
    '2026-05-31' AS requested_end_date,
    'era5' AS weather_model,
    latitude               AS returned_latitude,
    longitude              AS returned_longitude,
    elevation              AS elevation_m,
    CAST(utc_offset_seconds AS INT) AS utc_offset_seconds,
    timezone,
    timezone_abbreviation,
    'https://archive-api.open-meteo.com/v1/archive' AS source_url,
    'open_meteo_mar_may_2026_sample.json' AS source_file,
    'archive_api_v1' AS source_file_version,
    CAST(NULL AS STRING) AS batch_id,
    current_timestamp() AS ingested_at
FROM read_files(
    '/Volumes/ftw-week-08/00-source/group_a_source/weather/open_meteo_mar_may_2026_sample.json',
    format => 'json',
    multiLine => true
)
LATERAL VIEW POSEXPLODE(hourly.time) exploded AS pos, observation_time;

-- Row-count sanity check against the landed response, mirroring the
-- notebook's own expected-vs-actual hourly-coverage check
-- (docs/source_profile.md: 2,208 expected rows for the full March-May
-- window, 92 days x 24 hours, 0 gaps).
-- SELECT COUNT(*) FROM `ftw-week-08`.`01-bronze`.weather_raw
-- WHERE batch_id = '20260916';