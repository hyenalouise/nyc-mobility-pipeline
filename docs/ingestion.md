This document defines each source, ingestion method, incremental signal, batch identity, provenance, failure recovery, and rerun behavior.

# Sources and ingestion contracts

Status: proposed, source payloads not yet acquired or validated.

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
| Zones | Snapshot checksum | Preserve snapshots; validate and refresh selected small reference when changed; pin selected version for historical replay |

Keep input identity separate from execution attempts. Proposed manifest fields: source_system, source_object, source_period, request_parameters, content_sha256, source_version_id, batch_id, raw_uri, status, discovered_at, ingested_at, row_count, schema_fingerprint. Proposed run/checkpoint fields: run_id, batch_id, layer, code_revision, configuration_version, status, timestamps, target_commit_reference, counts and error.

Skip only completed work for the applicable layer and code/configuration version. Bronze success must not skip a failed Silver step. A code change may require an explicit replay even if the source checksum is unchanged.

## Taxi Zones ingestion

Source:
- taxi_zone_lookup.csv

Source path:
- /Volumes/ftw-week-08/00-source/group_a_source/taxi_zones/taxi_zone_lookup.csv

Target table:
- `ftw-week-08`.`01-bronze`.`taxi_zones_raw`

Load strategy:
- Full refresh

Reason:

The Taxi Zones dataset is a small static reference dataset containing 265 rows and is delivered as a complete snapshot rather than a stream of transactions.

A full refresh is intentionally chosen because:

1. The complete dataset is available in a single file.
2. The dataset is small and inexpensive to reload.
3. Full refresh is simpler to validate and maintain than row-level incremental logic.
4. Incremental processing would add unnecessary complexity without providing meaningful benefits.
5. Rerunning the load produces the same row count and content.

Validation:

- Expected row count: 265
- LocationID must be unique
- No duplicate LocationID values
- Source metadata retained

Rerun behaviour:

Running the same load multiple times produces the same row count and business content without creating duplicate records.

## Failures and recovery

Download to staging; check status, completeness, parsability and contract; preserve immutable raw inputs; validate before publishing layer output. Mark a layer complete only after its corresponding commit and required checks succeed. Use atomic publication supported by the chosen table/storage system; confirm exact behavior before implementation. If a commit succeeds but its checkpoint fails, a retry must recognize or safely replay the same commit without duplication. Use one coordinated shared writer or explicit concurrency protection.

On critical schema/quality failure retain diagnostic evidence, mark the attempt failed, leave the previous good published result intact, and stop dependent layers. Resume from the failed layer. Persist warnings with explanations. Surface new columns, missing fields, type changes and structure changes rather than silently coercing them.

Discovery follows arrival/source versions, not maximum event time. Late records remain eligible even if their event month is older. A revised source batch can affect multiple event-date aggregates; recompute every affected downstream contribution and preserve unaffected data.

Taxi identity/deduplication is pending profiling. Preventing repeated files does not settle repeated trip records. Define exact-match equivalence, deterministic serialization and provenance for every removed row. Do not claim a full-row hash proves a unique real trip, and do not use ingest time as an invented source update timestamp.
