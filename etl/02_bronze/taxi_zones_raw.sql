-- ============================================================
-- Bronze: taxi_zones_raw
--
-- Load strategy: full refresh (D11). Taxi Zones is a small, complete
-- reference snapshot (265 rows), so the whole table is rebuilt from the
-- approved source file rather than tracked incrementally.
--
-- Namespace per D13: catalog `ftw-week-08`, Bronze schema `02-bronze`.
--
-- Provenance values are NOT literals. They are produced by
-- src/ingestion/batch_tracking.register_batch_discovered() and passed in,
-- so that the row-level stamp and `01-control`.ingestion_batches always
-- describe the same batch.
--
-- Required parameters:
--   :batch_id           batch_id returned by register_batch_discovered()
--   :source_version_id  source_version_id recorded for this batch
--   :content_sha256     content hash recorded for this batch
--
-- Invocation (from a notebook or job, after registering the batch):
--   spark.sql(
--       Path("etl/02_bronze/taxi_zones_raw.sql").read_text(),
--       args={
--           "batch_id": batch_id,
--           "source_version_id": source_version_id,
--           "content_sha256": content_sha256,
--       },
--   )
--
-- Call mark_batch_success() only after Bronze validation passes (D14):
-- the write technically succeeding is not sufficient.
-- ============================================================

CREATE OR REPLACE TABLE `ftw-week-08`.`02-bronze`.taxi_zones_raw AS
SELECT
    CAST(LocationID AS INT)      AS location_id,
    CAST(Borough AS STRING)      AS borough,
    CAST(Zone AS STRING)         AS zone,
    CAST(service_zone AS STRING) AS service_zone,

    -- provenance
    'nyc_tlc_taxi_zones'  AS source_system,
    _metadata.file_name   AS source_file,          -- the file actually read, not an assumed name
    :content_sha256       AS content_sha256,
    :source_version_id    AS source_file_version,
    :batch_id             AS batch_id,
    current_timestamp()   AS ingested_at
FROM read_files(
    '/Volumes/ftw-week-08/00-source/group_a_source/taxi_zones/taxi_zone_lookup.csv',
    format => 'csv',
    header => true
);

-- Bronze preserves what arrived, including LocationID 264 and 265.
-- Sentinel handling belongs in Silver, not here.
