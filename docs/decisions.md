This document records important engineering decisions, their reasons, rejected alternatives, assumptions, and consequences.

# Decision log

Record problem, decision, reason, rejected alternative, assumption, consequence, status and reviewer. Priority: correctness > reliability > maintainability > scalability > observability > efficiency.

| ID | Decision | Reason / rejected alternative | Assumption / consequence | Status |
|---|---|---|---|---|
| D01 | Databricks + class R2; GitHub for code/docs | User selected course platform; avoid introducing a second platform | Actual access and paths must be confirmed | Platform confirmed; setup pending |
| D02 | Taxi, weather, zones first | Correctness before bonus scope; current advisories do not establish March-May closures | Traffic deferred until historical/spatial coverage exists | Proposed |
| D03 | Source-version manifest with per-layer checkpoints | Reliability before a simple filename-only skip list | Need safe commit/checkpoint reconciliation | Proposed |
| D04 | Replace a revised source batch contribution when complete | Correctness before efficiency; invented trip merge keys can retain stale rows | Must confirm replacement snapshot semantics | Proposed |
| D05 | Profile before finalizing taxi deduplication | Correctness before convenient DISTINCT/hash deduplication | Unique real-world trip identity may not be provable | Required design gate |
| D06 | One representative NYC weather location initially | Maintainability once business scope accepts city-level approximation | Cannot claim zone-specific observed weather | Proposed |
| D07 | No SCD Type 2 for zones initially | Maintainability; no agreed question requires historical zone labels | Pin raw snapshot for reproducibility | Proposed |
| D08 | One branch/work item and reviewer | Reliability and maintainability of shared changes | Separate developer outputs from integration targets | Proposed |
| D09 | Request and store weather in UTC at Bronze; convert to America/New_York in Silver | Correctness/reliability: keeps Bronze source-faithful and unmodified per `docs/architecture.md`, and avoids depending on Open-Meteo's own timezone-localization behavior, which was not verified to be DST-aware per hour across the profiled window | Silver-layer conversion must use a DST-aware IANA timezone conversion (`America/New_York`), never a fixed `-4`/`-5` hour offset, given the confirmed March 8, 2026 spring-forward transition inside the March-May 2026 window; taxi's timezone still needs empirical confirmation for Issue #16 before the join logic is finalized | Proposed |
| D10 | Use a full-refresh strategy for the Taxi Zones reference dataset | The Taxi Zones source is a small static reference snapshot (265 rows) delivered as a complete lookup file rather than a transactional or append-only dataset. Full refresh provides deterministic rerun behavior and avoids unnecessary incremental logic, snapshot tracking, and merge complexity. Rejected alternative: incremental row-level processing for a static lookup table. | Rerunning the same source produces the same row count and business content. When a newer approved Taxi Zones snapshot is selected, the table is rebuilt from that complete snapshot. | Proposed for Issue #22 |

Whenever a decision changes, update the relevant canonical documents in the same PR and explicitly identify any remaining stale documents. This log explains choices; detailed implementation contracts live in ingestion/model/architecture documents.


## Databricks namespace and naming

Status: Proposed in Issue #3; revised `Sep 15 2026` after review  
Decision date: `Sep 14 2026`

The project uses the `ftw-week-08` catalog and the existing R2-backed Volume at `ftw-week-08`.`00-source`.`group_a_source`.

Persisted processing layers use separate `01-control`, `02-bronze`, `03-silver`, `05-gold`, and `06-analytics` schemas. Each schema is prefixed with its pipeline-stage number, matching the existing `00-source` schema and the numbered `sql/` folders, so schemas sort in pipeline order and the stage number means the same thing in the catalog and in the repository. Table names do not include `group_a_` because the approved schemas are dedicated to the group.

A stage number identifies a step of the pipeline, not a schema. Every step has a `sql/` folder; only steps that create tables have a schema. Stage 00 profiles source files and creates none, and stage 04 (integration) writes into Gold because resolving a trip to its zones and weather hour does not change the grain of a trip. The `04-` slot is left empty rather than renumbering Gold and Analytics, so an `04-integration` schema can be added later without renaming existing schemas.

Stage 04 would earn its own schema if integration began producing a different grain (for example a trip-to-advisory bridge table), if several Gold facts reused the same expensive join and recomputation became a measured bottleneck, or if integration output needed a separate write owner. None of these hold at the time of this decision.

Alternative rejected: unnumbered schema names (`bronze`, `silver`, `gold`). They read more cleanly in SQL but sort alphabetically in the catalog browser, which puts Analytics before Bronze and Gold before Silver, and they leave the existing `00-source` schema as the only numbered name.

Alternative rejected: numbering tables as well (`02_green_taxi_raw`). The schema already carries the layer, a numeric table prefix would repeat it, and identifiers beginning with a digit would force backticks on every table reference.

Consequence: every schema name contains a hyphen and begins with a digit, so backticks are mandatory on all catalog and schema references. This was already true of the catalog name. Table and column names must not begin with a digit.

Consequence: this rename is only free while no processing schema or table exists. Confirm in the workspace before any schema is created; after tables exist a rename means recreate and reload.

A separate `01-control` schema was selected because pipeline runs, ingestion batches, and data-quality results have different grains and lifecycles from business records.

Gold and Analytics names remain pending Issue #17 and the approved business-question outputs.

Alternative rejected: storing operational state in Bronze. This would mix pipeline-control records with source-preserving business data.

Assumption: the processing schemas are dedicated to Group A. If other groups share them, the namespace strategy must be revised before tables are created.

## Weather and taxi timezone standard

Status: Proposed for Issue #16  
Decision date: `Sep 15 2026`

Weather data is requested and stored in UTC at Bronze, matching Open-Meteo's default request behavior and the already-profiled evidence in `docs/source_profile.md` (`utc_offset_seconds: 0`, `timezone`/`timezone_abbreviation`: `GMT`/`GMT`). Conversion to `America/New_York` happens explicitly and only in Silver, using a real DST-aware timezone conversion, before joining weather hours to taxi trips by pickup hour.

Alternative rejected: requesting Open-Meteo data pre-localized to `America/New_York` via the API's own `timezone` request parameter. This was tested directly and does return a response with `utc_offset_seconds: -14400` / `timezone_abbreviation: GMT-4`, so the parameter is real and accepted. It was rejected anyway for two reasons: whether the API applies true per-hour DST-aware conversion across a multi-month window (rather than one flat current offset) was not confirmed before this decision was made, and pushing a standardization/reporting concern into the Bronze ingestion request conflicts with Bronze's role of preserving the source's own representation as received, per `docs/architecture.md`.

Assumption: taxi (`lpep_pickup_datetime`/`lpep_dropoff_datetime`) timestamps are already recorded in `America/New_York` local time. This still requires empirical confirmation via the DST-transition check tracked under Issue #16 before the join logic below is treated as final. If taxi timestamps turn out to be UTC instead, both weather and taxi receive the same Silver-layer conversion, not just weather.

Consequence: any Silver transformation touching `weather_hourly.time` must convert it using a real IANA timezone library, correctly handling the March 8, 2026 spring-forward boundary inside the profiled window — a naive fixed-offset conversion would misjoin every weather-to-trip pairing on one side of that boundary by exactly one hour. A worked 2am example spanning that boundary must be included in the same PR that implements this conversion, per Issue #16's acceptance evidence.
## Taxi Zones full-refresh ingestion

Status: Proposed for Issue #22  
Decision date: `Sep 16 2026`

The Taxi Zones dataset is a small static reference lookup containing 265 rows and delivered as a complete source snapshot.

The Bronze Taxi Zones table uses a full-refresh strategy implemented with `CREATE OR REPLACE TABLE`.

The source snapshot is loaded into:

`ftw-week-08`.`01-bronze`.`taxi_zones_raw`

### Reason

The Taxi Zones source is a complete lookup dataset rather than a stream of independent transactional records.

A full refresh is intentionally chosen because:

1. The complete dataset is available in a single source file.
2. The dataset is small and inexpensive to reload.
3. Full refresh produces deterministic rerun behavior.
4. Replacing the dataset is easier to validate than implementing row-level change tracking.
5. Incremental processing would add unnecessary complexity without providing meaningful performance benefits.

### Rerun behavior

Rerunning ingestion against the same Taxi Zones source file produces:

- The same row count.
- The same business content.
- No duplicate records.

This satisfies the project requirement that rerunning the same input produces identical results.

### Rejected alternative: incremental processing

Using `INSERT INTO`, `MERGE`, or similar row-level incremental logic was rejected because Taxi Zones is not an append-only transactional source.

An incremental approach would require additional logic to identify inserts, updates, deletes, checksum management, and snapshot version tracking. For a static 265-row reference lookup table, this complexity provides little benefit.

### Rejected alternative: COPY INTO

`COPY INTO` is appropriate for sources that arrive incrementally as new files, such as the monthly Green Taxi Parquet extracts.

Taxi Zones is currently a single reference CSV snapshot rather than a continuously arriving dataset. Using `COPY INTO` would not eliminate the need for additional snapshot-management logic and would not provide meaningful advantages over a deterministic full refresh.

### Consequences

- The Taxi Zones reference table can be rebuilt deterministically.
- Rerunning ingestion is safe and repeatable.
- Duplicate records are not introduced during reruns.
- Implementation complexity is minimized for a small static lookup dataset.
- Future ingestion logic can be revisited if the source begins publishing versioned or incremental snapshots.