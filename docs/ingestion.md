This document defines each source, ingestion method, incremental signal, batch identity, provenance, failure recovery, and rerun behavior.

# Sources and ingestion contracts

Status: all three sources profiled (see `docs/source_profile.md`). Ingestion contracts below are approved; no source has completed official Bronze ingestion yet. Earlier loads into personal dev/sandbox schemas were exploratory profiling, not Bronze (D14).

## Official sources

- [TLC source index](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
- [March 2026 Green Taxi Parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2026-03.parquet)
- [April 2026 Green Taxi Parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2026-04.parquet)
- [May 2026 Green Taxi Parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2026-05.parquet)
- [Taxi-zone CSV](https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv)
- [Green Taxi dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_green.pdf)
- [Open-Meteo historical API](https://open-meteo.com/en/docs/historical-weather-api)

Weather endpoint: `https://archive-api.open-meteo.com/v1/archive`. Use date-bounded historical requests, not the current-weather classroom example. Initial proposed variables: temperature_2m, precipitation, weather_code. Proposed coordinates 40.7128, -74.0060 are a city-level representative point, subject to team review. Preserve returned grid coordinates, units and model metadata. Select and pin a model after confirming variable support.

For a first profile request use 2026-03-01 through 2026-03-02 with the proposed coordinates, hourly variables and explicit timezone UTC. A sample is only a response-profile check, not the required monthly coverage. For final coverage, derive UTC bounds from the approved NYC local-time interval and retain enough boundary hours. The API start/end dates are date windows; filter the intended interval explicitly downstream without deleting raw responses.

## Acquisition and shared storage

One source owner acquires each immutable input; everyone uses the same recorded source versions. Store source files and JSON under the team's confirmed R2 prefix, not GitHub. Record a checksum and retrieval metadata before promotion. Download all taxi months for profiling; release/process March, then April, then May for the incremental proof.

## Contracts

| Source | Incremental/change signal | Rerun/revision policy |
|---|---|---|
| Taxi | Source logical month + content checksum | Identical successful version is a no-op; different content is a revision. Preserve raw history; replace only that source contribution if it is confirmed a full replacement snapshot |
| Weather | Canonical request parameters/window + response content version | Fetch missing windows. Replay stored input for deterministic reruns. Refresh history explicitly; compare normalized weather content, since volatile response metadata can change raw checksums |
| Zones | Source file version / approved snapshot | Full-refresh the Taxi Zones reference table from the approved source snapshot. Rerunning the same source file produces the same row count and business content. Incremental processing and snapshot-history management are intentionally not used because Taxi Zones is a small static reference dataset (265 rows). |

Keep input identity separate from execution attempts. Proposed manifest fields: source_system, source_object, source_period, request_parameters, content_sha256, source_version_id, batch_id, raw_uri, status, discovered_at, ingested_at, row_count, schema_fingerprint. Proposed run/checkpoint fields: run_id, batch_id, layer, code_revision, configuration_version, status, timestamps, target_commit_reference, counts and error.

Skip only completed work for the applicable layer and code/configuration version. Bronze success must not skip a failed Silver step. A code change may require an explicit replay even if the source checksum is unchanged.

## Taxi Zones ingestion

Source:
- taxi_zone_lookup.csv

Target table:
- `ftw-week-08`.`02-bronze`.`taxi_zones_raw`

Load strategy:
- Full refresh (`CREATE OR REPLACE TABLE`)

Reason:

The Taxi Zones dataset is a small static reference lookup containing 265 rows and delivered as a complete source snapshot rather than a transactional or append-only source.

A full refresh is intentionally chosen because:

1. The complete dataset is available in a single file.
2. The dataset is small and inexpensive to reload.
3. Full refresh produces deterministic rerun behavior.
4. Incremental processing would introduce unnecessary complexity without meaningful performance benefits.

Rerun behavior:

Rerunning the same source file produces:

- The same row count.
- The same business content.
- No duplicate business records.

Operational metadata such as `ingested_at` is expected to change between runs because it records the timestamp of the ingestion execution.

Provenance columns (`batch_id`, `source_file_version`, `content_sha256`) are supplied by `src/ingestion/batch_tracking.register_batch_discovered()` and passed into the Bronze SQL as parameters. They are never written as literals, so the row-level stamp and `01-control`.`ingestion_batches` always describe the same batch.

Validation:

- Expected row count: 265
- LocationID must be unique
- No duplicate LocationID values
- Source metadata retained

## Failures and recovery

Download to staging; check status, completeness, parsability and contract; preserve immutable raw inputs; validate before publishing layer output. Mark a layer complete only after its corresponding commit and required checks succeed. Use atomic publication supported by the chosen table/storage system; confirm exact behavior before implementation. If a commit succeeds but its checkpoint fails, a retry must recognize or safely replay the same commit without duplication. Use one coordinated shared writer or explicit concurrency protection.

On critical schema/quality failure retain diagnostic evidence, mark the attempt failed, leave the previous good published result intact, and stop dependent layers. Resume from the failed layer. Persist warnings with explanations. Surface new columns, missing fields, type changes and structure changes rather than silently coercing them.

Discovery follows arrival/source versions, not maximum event time. Late records remain eligible even if their event month is older. A revised source batch can affect multiple event-date aggregates; recompute every affected downstream contribution and preserve unaffected data.

Taxi identity/deduplication is pending profiling. Preventing repeated files does not settle repeated trip records. Define exact-match equivalence, deterministic serialization and provenance for every removed row. Do not claim a full-row hash proves a unique real trip, and do not use ingest time as an invented source update timestamp.
