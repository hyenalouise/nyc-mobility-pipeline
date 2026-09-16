CREATE TABLE IF NOT EXISTS `ftw-week-08`.`01-bronze`.taxi_zones_raw (
    location_id INT,
    borough STRING,
    zone STRING,
    service_zone STRING,

    source_file STRING,
    source_file_version STRING,
    batch_id STRING,
    ingested_at TIMESTAMP
);


--FULL REFRESH MODE
CREATE OR REPLACE TABLE `ftw-week-08`.`01-bronze`.taxi_zones_raw AS

SELECT
    CAST(LocationID AS INT) AS location_id,
    Borough AS borough,
    Zone AS zone,
    service_zone,

    'taxi_zone_lookup.csv' AS source_file,
    'snapshot_v1' AS source_file_version,
    '20260916' AS batch_id,
    current_timestamp() AS ingested_at

FROM read_files(
    '/Volumes/ftw-week-08/00-source/group_a_source/taxi_zones/taxi_zone_lookup.csv',
    format => 'csv',
    header => true
);

-- Because Taxi Zones is 265 rows, a refrence table and a static look up. 
-- We don't need incremental logic


