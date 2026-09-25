This document defines each source, ingestion method, incremental signal, batch identity, provenance, failure recovery, and rerun behavior.

# Sources and ingestion contracts

Status: implemented. All three sources (Green Taxi, Open-Meteo weather, Taxi Zones) are ingesting real data into Bronze.

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

## Control table

Every ingestion attempt, across all three sources, is tracked in one shared table:

```text
`ftw-week-08`.`01-control`.ingestion_batches
```

One row per batch attempt. Lifecycle: `DISCOVERED → STARTED → SUCCESS / FAILED`.

- `DISCOVERED` — the batch/file was found, not yet loaded.
- `STARTED` — written immediately before the load begins, so a crash mid-load still leaves a record.
- `SUCCESS` — written only after the load lands *and* passes validation (e.g. row-count reconciliation), not merely after the write succeeds.
- `FAILED` — the attempt did not complete. The batch stays eligible for retry; a retry registers a new `batch_id`, preserving the failed attempt's history.

`content_sha256` is what actually decides "have I already processed this" — not the filename. A file can be re-delivered under the same name with different content and still be correctly treated as new.

## Contracts

| Source | Incremental/change signal | Rerun/revision policy |
|---|---|---|
| Taxi | Source logical month + content checksum | Identical successful version is a no-op; different content is a revision. Preserve raw history; replace only that source contribution if it is confirmed a full replacement snapshot |
| Weather | Canonical request parameters/window + response content version | Fetch missing windows. Replay stored input for deterministic reruns. Refresh history explicitly; compare normalized weather content, since volatile response metadata can change raw checksums |
| Zones | Source file version / approved snapshot | Full-refresh the Taxi Zones reference table from the approved source snapshot. Rerunning the same source file produces the same row count and business content. Incremental processing and snapshot-history management are intentionally not used because Taxi Zones is a small static reference dataset (265 rows). |

Keep input identity separate from execution attempts. Proposed manifest fields: source_system, source_object, source_period, request_parameters, content_sha256, source_version_id, batch_id, raw_uri, status, discovered_at, ingested_at, row_count, schema_fingerprint. Proposed run/checkpoint fields: run_id, batch_id, layer, code_revision, configuration_version, status, timestamps, target_commit_reference, counts and error.

Skip only completed work for the applicable layer and code/configuration version. Bronze success must not skip a failed Silver step. A code change may require an explicit replay even if the source checksum is unchanged.

## Green Taxi Trip ingestion

Source: `green_tripdata_2026-03.parquet`, `-04.parquet`, `-05.parquet`

Target table: `` `ftw-week-08`.`02-bronze`.green_taxi_raw ``

Entry point: `10_load_green_taxi.sql`.

Load strategy: SQL, one `INSERT` per run covering every unprocessed file. The
folder is the source; no filename is hardcoded.

1. Read every Parquet file in the landing folder, tagging each row with the file
   it came from via `_metadata`.
2. Hash each file's content: a per-row digest, sorted and hashed per file, so the
   result does not depend on read order.
3. Select the files to process — those whose content hash has no `SUCCESS` batch,
   or whose rows are not present in the target. The second condition matters when
   Bronze is dropped but the control row survives.
4. Demote any prior `SUCCESS` batch for that content to `SUPERSEDED` (D24), then
   register one batch per file as `STARTED`.
5. Delete any orphaned rows for that content. The insert and the reconciliation
   below are separate statements, so a run can commit rows and then fail before
   its batch closes; without this a restart would append a second copy.
6. Insert the new files' rows in one statement, joined to their batch by content
   hash.
7. Reconcile: rows landed per file must equal rows in the source file, or the
   stage raises and the batches stay `STARTED`.
8. Close each batch as `SUCCESS` with the count actually landed.

Rerun behavior: a second run against the same files reports zero new files,
registers no batch and writes no rows. Proven in
`evidence/pipeline-runs/2026-09-19-idempotency.md`.

Incremental behavior: files arriving one month at a time are each loaded once,
and earlier months' batch records are never rewritten. Proven in
`evidence/pipeline-runs/2026-09-19-incremental.md`.

Known limitation: the landing path is a literal inside `read_files`, which cannot
take a variable, so staging a subset of files for a test means moving files in
the Volume rather than pointing the loader elsewhere.

## Weather ingestion

Source: Open-Meteo historical API response, landed as JSON.

Target table: `` `ftw-week-08`.`02-bronze`.open_meteo_weather_raw ``

Entry point: `20_load_open_meteo.sql`.

Load strategy: SQL `MERGE INTO`. Bronze preserves response-grain — one row per API response, with the hourly arrays kept intact rather than exploded into one row per hour.

Business key (what makes a response "new"): `(coordinate_id, requested_start_date, requested_end_date, weather_model)`. A response matching an existing key on all four is treated as already loaded and is not re-inserted.

Two separate hashes are recorded, deliberately different:
- `content_sha256` — hash of the entire landed payload, including `generationtime_ms`. This is an immutable identity for the raw file as received.
- `source_response_version` — hash of everything that describes the actual weather content and its request context (coordinates, elevation, timezone fields, hourly data), **excluding** `generationtime_ms`. This is the field used to detect a genuine content change, since `generationtime_ms` varies between otherwise-identical requests and would make `content_sha256` alone unreliable for that purpose.

`weather_model` defaults to `'api_default_unpinned'` when no model has been explicitly requested, rather than assuming one.

Rerun behavior: re-running against the same response is a no-op on the business key — no duplicate rows.

Pre-Bronze source validation:

Before Bronze ingestion runs, `src/ingestion/source_gate.py --source weather`
validates the landed JSON response locally with DuckDB — no Databricks
credentials, no network access. This mirrors the Green Taxi and Taxi Zones
gates (#115, #124), extended to the third source per #125.

Weather is a request-window source, not a fixed file, so its contract has no
`row_count_floor`. Instead it records a `requested_window` (2026-03-01 to
2026-05-31), pinned by a test to the `weather_requested_*` variables in
`20_load_open_meteo.sql`. Completeness is checked two ways:
`hourly_series_has_no_gaps` compares the row count to the span between the
response's own first and last hour, which catches a hole in the middle, and
`hourly_series_covers_requested_window` checks the count equals the requested
days × 24 (the same rule as Bronze's `hourly_volume`) and that the first and
last hour are the window's start 00:00 and end 23:00, which catches a file cut
short at either end.

Checks performed: source readable, at least one response landed, required
top-level fields present (`latitude`, `longitude`, `elevation`, `hourly`),
`hourly`'s own four fields present (`time`, `temperature_2m`, `precipitation`,
`weather_code`), hourly series not empty, `hourly.time` present and
parseable, `temperature_2m`/`precipitation`/`weather_code` not null, no
duplicate `hourly.time` values, `hourly_series_has_no_gaps`,
`hourly_series_covers_requested_window`, `temperature_2m` within -50–60°C,
`precipitation` non-negative, and `weather_code` against the full WMO code
set. The window, range, non-negative, and WMO checks all block at 0%,
matching the Bronze and Silver weather gates, which fail on the same
conditions; tolerating them here would only defer the block to Bronze.

A field entirely absent from the JSON (not merely null) is checked for by
name rather than referenced directly, so a response missing e.g. `elevation`
or `hourly.precipitation` is reported as a named `required_columns` /
`required_hourly_fields` failure instead of crashing the gate — see
`src/ingestion/source_gate.py`'s `create_weather_view` for why this needed
different handling than Green Taxi/Taxi Zones' `SELECT *`.

A clean file is `ACCEPTED` (exit code 0); a file failing any check is
`BLOCKED` (exit code 1) and Bronze must not proceed. As with the other two
sources, this validator is stateless and has no run history of its own: what
it proves is that one landed response is internally well-formed and contains
no duplicate hours, not that a rerun against Bronze produces no duplicate
rows — that guarantee is Bronze's own business key and `MERGE`, documented
above.

Both a clean response and each defect case (a missing hour, a response cut
short at either end, a duplicated hour, a null or unparseable time, a null or
out-of-range measurement, negative precipitation, an unknown or non-integer
`weather_code`, a missing required or hourly field, a non-array hourly field,
and an empty hourly series) are exercised in `tests/test_weather_gate.py`,
which generates its own JSON fixtures rather than relying on a committed
source file. The same file pins the gate's WMO codes and temperature range to
the Bronze and Silver weather gates, and its `requested_window` to the Bronze
loader.

See `docs/tools/duckdb/validation-checks.md` for the full check catalogue.

## Taxi Zones ingestion

Source:
- taxi_zone_lookup.csv

Target table:
- `ftw-week-08`.`02-bronze`.`taxi_zones_raw`

Load strategy:
- Full refresh (`CREATE OR REPLACE TABLE`)

Entry point: 
- `30_load_taxi_zones.sql`.

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

`batch_id` for this source is a manually set date stamp (e.g. `'20260916'`), not a generated UUID like the other two sources — consistent with there being no incremental logic to track here.

Known limitation: the current `CREATE OR REPLACE TABLE` rebuilds the table from the `SELECT`, so the types pinned in the earlier `CREATE TABLE IF NOT EXISTS` statement do not actually hold once the replace runs. Tracked as a follow-up (switch to `INSERT OVERWRITE` instead).

Validation:

- Expected row count: 265
- LocationID must be unique
- No duplicate LocationID values
- Source metadata retained

Pre-Bronze source validation:

Before Bronze ingestion runs, `src/ingestion/source_gate.py --source taxi_zones`
validates the raw CSV locally with DuckDB — no Databricks credentials, no
network access. This mirrors the Green Taxi gate introduced in #115, extended
to a second source per #124.

Checks performed: source readable, row count not empty, row count floor (265,
the full expected snapshot size), required columns present, `LocationID` not
null, `LocationID` unique, `Borough` not null.

A clean file is `ACCEPTED` (exit code 0); a file failing any check is `BLOCKED`
(exit code 1) and Bronze must not proceed. Evidence for both cases is recorded
under `evidence/source-validation/`.

Both a clean snapshot and each defect case (duplicate `LocationID`, blank
`Borough`, and a non-numeric or out-of-range `LocationID`) are exercised in
`tests/test_taxi_zones_gate.py`, which generates its own test data rather
than relying on a committed source file.

See `docs/tools/duckdb/validation-checks.md` for the full check catalogue. The
severity model and command line are shared across sources; the individual
checks are not, since each source's business rules differ -- see that file
for each source's specific list.

## Failures and recovery

Mark a layer complete only after its load and validation both succeed — a technically-successful write is not enough on its own.

**Green Taxi specific**: the insert and the row-count reconciliation are separate
statements, so a run can commit rows and then fail before its batch reaches
`SUCCESS`. On the next run that file correctly looks unprocessed again, so the
loader deletes any orphaned rows for that content before inserting. Without that
step a restart would append a second copy of every row.

Restart point on failure: re-run the same file for that source, or use **Repair
run** on the failed job run. Proven in
`evidence/pipeline-runs/2026-09-19-failure-restart.md`. Each source's own change-detection logic (content hash for Taxi, business key for Weather, always-on-full-refresh for Zones) determines what actually gets reloaded — already-successful work is not redone.

Bronze success does not imply Silver success. A failed Silver step does not get silently skipped just because its Bronze batch succeeded.

Surface schema or structure changes (new columns, missing fields, type changes) rather than silently coercing them — see the schema drift check (`src/ingestion/schema_drift_check.py`) for Green Taxi.

----

Download to staging; check status, completeness, parsability and contract; preserve immutable raw inputs; validate before publishing layer output. Mark a layer complete only after its corresponding commit and required checks succeed. Use atomic publication supported by the chosen table/storage system; confirm exact behavior before implementation. If a commit succeeds but its checkpoint fails, a retry must recognize or safely replay the same commit without duplication. Use one coordinated shared writer or explicit concurrency protection.

On critical schema/quality failure retain diagnostic evidence, mark the attempt failed, leave the previous good published result intact, and stop dependent layers. Resume from the failed layer. Persist warnings with explanations. Surface new columns, missing fields, type changes and structure changes rather than silently coercing them.

Discovery follows arrival/source versions, not maximum event time. Late records remain eligible even if their event month is older. A revised source batch can affect multiple event-date aggregates; recompute every affected downstream contribution and preserve unaffected data.
## Recovery runbook

This section answers the questions a developer needs when the pipeline
fails: how to run it, how to know it worked, how to find a failure, what
is safe to rerun, how to verify the resulting data, and what needs
Databricks or production access.

**Vocabulary.** These three words are not interchangeable, and using the
wrong one leads to the wrong recovery action:

- **Retry** — repeat the exact same failed thing, unchanged. Correct when
  the failure was temporary (a platform or network hiccup, a task stuck
  waiting for compute), where the same input can succeed on a second try.
  Retrying a BLOCK on bad data only fails again: useful as proof the
  failure is real, but not a recovery action.
- **Rerun** — run the job again after something has changed (a fixed file,
  a corrected configuration, a restored default). This is the normal
  recovery action once the actual problem is addressed.
- **Backfill** — process a historical period that was missed entirely,
  separate from retrying or rerunning the most recent attempt.

Backfill in this pipeline is a normal run after one deliberate change:
widening the period the pipeline expects. For Green Taxi, the loader
already discovers every file in its landing folder and loads any file
with no matching `SUCCESS` batch in `ingestion_batches`, whatever month
it covers. But both the source gate and the Bronze gate check pickups
against the declared window (`reporting_window` in
`config/source_contract.json`, and the same Mar–May dates in
`etl/02_bronze/90_validate_green_taxi.sql`), so a file from an older
month would be blocked as out of window. To backfill: widen that window
in both places through a reviewed PR, place the missing file in the
landing folder, then run the job normally. For Weather, change the
requested window in `20_load_open_meteo.sql` and the matching
`requested_window` in the contract. Nothing already loaded is reloaded,
because every loaded file is recognised by its content hash.

### How to run the pipeline

```bash
databricks bundle run NYC_Mobility_Pipeline --target dev
```

Runs the job with its default inputs, the same ones a scheduled run uses.
To point one source's gate at a different file for a controlled test (not
a real load), override that source's input parameter:

```bash
databricks bundle run NYC_Mobility_Pipeline --target dev \
  --params 'green_taxi_input=/Volumes/.../some_other_file/*.parquet'
```

The equivalent parameters exist for `taxi_zones_input` and `weather_input`.
An overridden gate can never let its loader run, even if the overridden
input happens to pass, because each gate is also given the exact path its
loader reads and fails its own task if the two differ. This makes an
override run safe to use for a deliberate test: it can prove a gate
blocks something, but it can never cause a load the run did not itself
check.

### How to know it succeeded

Check the job run's overall status. A run where every task shows
**Succeeded** completed cleanly. A run showing **Upstream failed** on later
tasks means an earlier task failed and stopped that branch on purpose —
this is the gate working as intended, not a separate bug to chase.

Beyond the run page itself, every check writes a row to
`ftw-week-08`.`01-control`.`data_quality_results`, and every gate ends
with a statement that raises an error on any blocking failure. A run that
reports success genuinely had no blocking failures; it cannot look
successful while having silently swallowed one.

### How to find a failure

1. Open the job run and look for a task marked **Failed** (not
   **Upstream failed** — that label means the task itself never ran
   because something it depends on failed first; the real failure is
   upstream of it).
2. Click into the failed task's output. A source-gate task prints which
   named check failed and how many rows were affected. A SQL gate's
   `raise_error` message names the check that blocked it.
3. Query `data_quality_results` for the run's `run_id` to see every
   check's status, not just the one that blocked: a failure is rarely
   isolated from its `WARN` and `INFO` neighbors, and the full picture
   speaks to whether this is an isolated defect or part of a wider
   problem with the delivery.

### What is safe to rerun

- **A gate run with no override** is always safe to rerun: it checks
  exactly what the loader will load, every time.
- **A repair from the CLI with no parameters returns to the default
  input.** If a run was overridden for a test, repairing it is not the
  same as retrying that test — the repaired gate checks the real landing
  folder, not the test file. To repeat a test, start a new run with the
  override passed again, rather than repairing the earlier one.
- **A blocked gate will fail again on a bare retry** if nothing about the
  input has changed, because a BLOCK on bad data is a property of the
  data, not the platform. Retrying without fixing the input is not a
  recovery action by itself, but it is useful evidence that the failure
  is real and repeatable.
- **A rerun with the real, unchanged input is a safe no-op** if that
  content was already loaded successfully: the loader's `content_sha256`
  check recognizes the file as already processed and adds nothing.
  - **A source gate that prints its verdict and then sits for minutes** is
  stuck waiting for the serverless Spark service (its driver log repeats
  `The cluster is in unexpected state Pending`). It hasn't written
  anything yet. Cancel the run and start it again; this is a platform
  hiccup, so a plain retry is the right action (see
  `evidence/pipeline-runs/2026-09-25-source-gate-blocked-run.md`).

### How to verify the resulting data

Before and after any recovery action, compare row counts directly rather
than trusting that a green run implies correct data:

```sql
SELECT COUNT(*) FROM `ftw-week-08`.`02-bronze`.green_taxi_raw;
SELECT COUNT(*) FROM `ftw-week-08`.`01-control`.ingestion_batches;
```

The same pattern applies to any other table in the affected layer. Counts
that are unchanged after a blocked run confirm nothing bad reached the
table. Counts that are unchanged after a rerun of already-loaded content
confirm the rerun did not duplicate anything.

### What requires Databricks or production credentials

- Deploying to `dev` requires Databricks workspace access and the CLI, but
  creates only the operator's own `[dev <username>]` job — no shared
  credential or approval is needed, and it cannot affect anyone else's
  sandbox or the shared landing folder.
- Deploying to `prod` and approving a production deployment currently sit
  with the role documented in `docs/governance/ownership.md`'s Deployment Access
  table. Nothing in this runbook requires prod access: every step here can
  be demonstrated safely in `dev`.
- Querying `data_quality_results`, `ingestion_batches`, or any Bronze or
  Silver table requires the same Unity Catalog read access already
  granted to the project team; no elevated access is needed to follow
  this runbook.

### Worked example

A full run through Detect, Diagnose, Assess impact, Fix, Rerun and Verify,
with real run IDs and query results, is recorded in
`evidence/pipeline-runs/2026-09-25-recovery-demonstration.md`.
