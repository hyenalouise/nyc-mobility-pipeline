# Decision log

This document is the canonical record of important product, data, and engineering decisions for the NYC Mobility Pipeline. It records what was decided, why it was chosen, which alternatives were rejected, what assumptions remain, and what consequences follow.

Decision entries preserve the context that existed when the decision was made.
Their original “reason” and “consequences” sections are historical, not a
current deployment-status page. When later implementation changes an outcome,
add a dated subsequent-outcome note and use repository configuration plus
run-specific evidence for current claims.

**Last updated:** 2026-09-24
**Decision priority:** correctness > reliability > maintainability > scalability > observability > efficiency

## Maintenance rule

When a decision changes, update this file and every affected canonical document in the same pull request. Explicitly identify any document that remains stale.

This log explains why choices were made. Detailed implementation contracts live in:

- `docs/architecture/overview.md`
- `docs/data/ingestion.md`
- `docs/architecture/data-model.md`
- `docs/architecture/data-dictionary.md`
- `docs/architecture/source-to-target.md`
- `docs/standards/naming.md`
- `docs/architecture/model/nyc_mobility_star_schema.png`

## Decision register

| ID | Decision | Status | Primary consequence |
|---|---|---|---|
| D01 | Use Databricks and the class R2 storage environment; use GitHub for code and documentation | Platform confirmed; setup tracked separately | Do not introduce another processing or storage platform without a new decision |
| D02 | Prioritize Taxi, Weather, and Taxi Zones; defer traffic advisories | Active | Optional traffic analysis creates no model dependency until historical and spatial coverage is validated |
| D03 | Use a source-version manifest with per-layer checkpoints | Proposed | File discovery alone is not sufficient proof that a source version completed every layer |
| D04 | Replace a complete revised source-batch contribution | Proposed | Do not append a revised contribution beside stale rows from the same logical source version |
| D05 | Profile before finalizing taxi duplicate handling | Resolved by D10 and Issue #14 | Do not use `DISTINCT` or an invented trip identifier without collision evidence |
| D06 | Use one representative NYC weather coordinate initially | Active | Weather results are citywide associations and not zone-specific observations |
| D07 | Do not use SCD Type 2 for Taxi Zones initially | Final candidate under Issue #17 | Pin the selected reference snapshot; add historical versions only for a future approved requirement |
| D08 | Use one branch per work item and assign a reviewer | Proposed team workflow | Keep individual work isolated from shared integration targets |
| D09 | Store weather in UTC in Bronze and convert to `America/New_York` in Silver | Approved through Issue #16 | All conversions must be DST-aware; never use a fixed UTC offset |
| D10 | Identify taxi duplicate collisions with the approved composite hash and quarantine every colliding row | Approved through Issue #14 | Collision groups do not enter the clean Silver or Gold trip tables |
| D11 | Full-refresh the selected Taxi Zone reference snapshot | Approved through Issue #22 | Identical input produces identical business content without incremental row-level complexity |
| D12 | Approve three core business questions, defer optional traffic analysis, and use the two-fact Gold model | Final candidate for Issue #17 | Pickup and drop-off roles remain separate; trip and hourly-weather measurements remain at their natural grains |
| D13 | Use numbered Databricks schemas aligned with pipeline stages | Approved through Issue #3 | Persisted objects use `01-control`, `02-bronze`, `03-silver`, `05-gold`, and `06-analytics` |
| D14 | Build `ingestion_batches` as a standalone control table, scoped before Bronze ingestion; `pipeline_runs` deferred | Approved | The pipeline can answer "have we already processed this?" from a persisted table without requiring per-layer run tracking yet |
| D15 | Retain quality-flagged Green Taxi rows in the clean Silver table instead of quarantining them; quarantine only duplicate collisions | Active | `green_taxi_clean` requires explicit flag filtering per measure; only D10 duplicates are excluded from it |
| D16 | Standardize Taxi Zones in Silver and preserve sentinel records | Approved through Issue #29 | Taxi Zone IDs 264 and 265 remain explicit Silver members and location_id uniqueness is validated on every load |
| D17 | Validate Bronze and Silver per source with a shared result contract; remove `etl/00_source_profile/` | Proposed | Each source has its own gate and may advance independently; Integration requires every source's Silver gate |
| D18 | Build both Gold facts from validated upstream results with deterministic keys and convergent MERGE publication | Proposed through Issue #38 | Facts preserve their declared grains; Gold validation blocks publication on grain, FK, lineage, quarantine, or reconciliation failures |
| D19 | Publish Silver's `trip_hash` as the trip identity and carry it into Gold as `trip_key` | Approved | One definition of trip identity; Integration keys its maps on it and Gold stops recomputing a second hash |
| D20 | Accept the weather coverage gap and report weather measures against their own denominator | Approved | Q2 and Q3 describe 133,173 of 133,353 trips; the shortfall is concentrated on the evening of 2026-05-31 |
| D21 | Treat `passenger_count = 0` as not recorded rather than implausible | Approved | Passenger measures must exclude `passenger_count_missing_flag` rows and state their denominator |
| D22 | Rebuild every layer above Bronze in full; keep incremental processing at Bronze | Approved | Late-arriving rows and global duplicate detection stay correct without watermark state below Bronze |
| D23 | Store wall-clock business timestamps as `TIMESTAMP_NTZ` and convert with `convert_timezone` | Approved | No stored timestamp depends on the cluster's session timezone |
| D24 | Add a `SUPERSEDED` batch status for content that was later reloaded | Approved | A reload no longer reads as double processing, and the earlier attempt stays auditable |
| D25 | Supply `code_revision` to every gate from one job-level parameter, assigned to the existing session variable | Approved | Every quality result traces to the commit that produced it, with a one-line change per gate |
| D26 | Add a `no_stuck_runs` check to the Control gate, detecting abandoned pipeline runs | Approved | A run left STARTED past `stuck_after_hours` now fails the gate instead of going unnoticed |
| D27 | Run the job weekly, Monday 06:00 New York time, and let the target decide whether the schedule is paused | Approved | The job runs without someone starting it, and freshness has an interval to be measured against |
| D28 | Report negative fares in the pre-ingestion source gate as INFO instead of blocking on a threshold | Approved through Issue #147 | The gate accepts the March–May delivery the pipeline already loads; negative fares are still counted in its evidence |
| D29 | Block on trips that end before they start, not on zero-length trips; keep the distance and passenger checks as they are | Approved through Issue #153 | A month with a few more zero-length trips no longer stops the scheduled run, and a delivery with reversed timestamps still does |


## Foundational decisions

### D01: Platform and repository

Use Databricks with the class R2 storage environment for processing and storage. Use GitHub for version-controlled code and documentation.

**Reason:** These are the selected course and team platforms. Introducing another platform would increase setup, access, and support risk without serving an approved requirement.

**Consequence:** Actual access, catalog paths, Volume paths, and permissions must be verified in the workspace rather than assumed from documentation.

### D02: Source scope and deferred traffic analysis

Implement the pipeline first with:

- NYC TLC Green Taxi trip records
- Open-Meteo archive weather
- NYC Taxi Zones

NYC DOT traffic advisories remain optional and deferred.

**Reason:** The currently available advisory evidence does not establish reliable historical and spatial coverage for March–May 2026. Correctness takes priority over bonus scope.

**Consequence:** Q4 does not justify a traffic fact, disruption dimension, bridge table, or trip-to-advisory relationship. Traffic modeling requires a later source-validation result and a separate approved design decision.

### D03: Source-version manifest and checkpoints

Track immutable source versions and their progress through each pipeline layer in a control manifest.

**Reason:** A filename-only skip list cannot safely distinguish discovery, partial processing, failed writes, completed commits, or an explicit replay.

**Consequence:** The design must support safe reconciliation between checkpoints and committed tables. A source version is considered complete only when its required layer checkpoint is successful.

### D04: Revised source-batch replacement

When a complete source contribution is revised, replace the prior contribution for that logical source batch rather than appending the revision beside stale rows.

**Reason:** Appending revisions can retain obsolete records. Inventing row-level merge keys where real-world identity is not provable can also preserve the wrong row.

**Consequence:** Replacement must be scoped through the source-version manifest, reconciled by row counts and content checks, and committed atomically where practical.

### D05: Profile before duplicate handling

Taxi duplicate handling must be based on observed collision evidence rather than convenience operations such as blanket `DISTINCT`.

**Status:** Resolved by D10 and Issue #14.

### D06: Representative citywide weather coordinate

Use one documented representative NYC coordinate for the initial Open-Meteo series.

**Reason:** This supports the approved weather-association questions without claiming a spatial resolution the source request does not provide.

**Consequence:** Weather results must be described as citywide associations. A Taxi Zone comparison does not mean weather was separately measured in every zone.

### D07: No initial SCD Type 2 for Taxi Zones

Use the selected validated Taxi Zone snapshot as a current reference dimension. Do not implement SCD Type 2 history initially.

**Reason:** None of the approved questions requires historical zone descriptions.

**Rejected alternative:** Adding effective dates and multiple historical versions without a business requirement.

**Consequence:** Pin the source snapshot and retain its checksum and retrieval metadata for reproducibility. Reconsider historical dimension versions only if a future approved question requires them.

### D08: Branch and review workflow

Use one branch per work item and identify a reviewer for shared changes.

**Reason:** Isolated branches make ownership, review, rollback, and integration clearer for a multi-person project.

**Consequence:** Developers should not use a shared integration branch as their personal working branch.

## Data and ingestion decisions

### D09: Weather and taxi timezone standard

**Status:** Approved through Issue #16  
**Decision date:** 2026-09-15

Request and store Open-Meteo weather in UTC in Bronze. Convert weather timestamps to `America/New_York` explicitly in Silver using a DST-aware IANA timezone conversion. Join weather to taxi trips using the trip pickup hour after both timestamps have been reconciled correctly.

The profiled weather response supports the UTC interpretation:

- `utc_offset_seconds = 0`
- `timezone = GMT`
- `timezone_abbreviation = GMT`

**Rejected alternative:** Requesting Open-Meteo data pre-localized with the API `timezone` parameter. Although the parameter is accepted, its per-hour DST behavior across the complete multi-month window was not validated before this decision. Pre-localizing the acquisition request would also move a Silver standardization concern into source-preserving Bronze.

**Assumption requiring validation:** Source taxi timestamps in `lpep_pickup_datetime` and `lpep_dropoff_datetime` represent `America/New_York` local time. If profiling proves that they are UTC instead, both taxi and weather must receive the appropriate explicit Silver conversion.

**Consequence:** Never convert with a fixed `-4` or `-5` hour offset. The March 8, 2026 spring-forward transition falls inside the reporting window. The implementation must include the worked DST-boundary example required by Issue #16.

### D10: Green Taxi duplicate-identification and quarantine policy

**Status:** Approved through Issue #14  
**Decision date:** 2026-09-15

Green Taxi has no verified natural trip ID. Construct a deterministic SHA-256 fingerprint from:

- `VendorID`
- `lpep_pickup_datetime`
- `lpep_dropoff_datetime`
- `PULocationID`
- `DOLocationID`
- `trip_distance`
- `fare_amount`

Exclude highly nullable fields such as `passenger_count`, `payment_type`, `RatecodeID`, `trip_type`, and `congestion_surcharge` from the fingerprint because they would make matching unstable.

Profiling across March–May 2026 found:

- 133,367 total rows
- 7 collision groups
- 14 colliding rows
- approximately 0.010% of rows affected

Manual inspection showed reversal or correction-like pairs with identical identity inputs and sign-flipped charge fields.

**Rejected alternative:** Automatically choosing a survivor such as the row where `total_amount > 0`. The observed examples do not prove that the rule would remain correct for future collision types.

**Policy:**

- Route every row in a collision group to the Silver quarantine table.
- Do not place a selected survivor from that group into the clean Silver table or Gold trip fact.
- Tag quarantined records for investigation and preserve their complete lineage.
- Halt publication of the clean Silver contribution if the quarantine rate exceeds 1%, while still writing the quarantine output for investigation.
- Use deterministic full Bronze rereads and overwrite/replacement behavior so identical input produces identical clean and quarantine business content.

**Consequence:** The Gold `trip_key` can use the approved fingerprint inputs after collision groups have been removed. It must not include `batch_id`, `run_id`, or ingestion time merely to manufacture uniqueness.

### D11: Taxi Zones full-refresh ingestion

**Status:** Approved through Issue #22  
**Decision date:** 2026-09-16

Taxi Zones is a small complete reference snapshot containing 265 profiled rows. Preserve each received source artifact with checksum and retrieval metadata, then rebuild the selected reference table from the complete validated snapshot.

The Bronze target is:

```text
`ftw-week-08`.`02-bronze`.taxi_zones_raw
```

The selected normalized reference is rebuilt deterministically for downstream use.

**Reason:**

- The complete dataset arrives as one lookup snapshot.
- The dataset is small and inexpensive to reload.
- Full refresh naturally captures inserts, updates, and removals within the selected snapshot.
- Replacement is easier to validate than unnecessary row-level change tracking.

**Rejected alternatives:**

- `INSERT INTO` or row-level `MERGE`, which would require extra insert/update/delete detection and snapshot-version logic.
- `COPY INTO` as the sole incremental mechanism, which is better suited to independently arriving files such as monthly Taxi extracts and does not solve selected-snapshot replacement.

**Rerun behavior:** Identical input produces the same row count and business content with no duplicate business records. Operational metadata such as `ingested_at` may reflect the latest execution.

**Consequence:** If Taxi Zones later becomes a versioned incremental source, revisit this decision before changing the load strategy.

## Business and model decision

### D12: Final business questions and Gold model

**Status:** Approved through Issue #17  
**Decision date:** 2026-09-17  

#### Final business questions

##### Q1. When and where is recorded Green Taxi activity highest?

**Measure:** Trip count  
**By:** Pickup date, day of week, hour, and Taxi Zone

Pickup and drop-off zones are analyzed separately.

##### Q2. How is weather associated with taxi activity and trip behavior?

**Measures:**

- Trip count
- Average trip duration
- Average trip distance
- Average fare amount

**By:** Weather condition and precipitation band

##### Q3. Which areas show the strongest mobility patterns?

**Measures:**

- Pickup count
- Drop-off count
- Average trip duration
- Average trip distance
- Average fare amount

**By:** Taxi Zone, time, and weather condition

Pickup and drop-off roles remain separate.

##### Q4. Optional: Do traffic disruptions affect taxi activity?

This question remains deferred unless reliable historical and spatial coverage can be validated from the NYC DOT advisory source.

#### Qualifications

- Recorded trip count is a proxy for demand.
- Weather comparisons show association, not causation.
- Source fields and coverage remain unverified until profiling is complete.

#### Assumptions requiring validation

- Reporting timezone is `America/New_York`.
- Weather is attributed using the trip pickup hour.
- Open-Meteo represents one documented citywide NYC coordinate.
- Q2 and Q3 describe association, not causation.
- Trip count measures recorded taxi activity and is only a proxy for demand.
- Fare analysis uses `fare_amount`, excluding tolls, surcharges, and tips.
- Weather-code and precipitation-band mappings will be documented.
- Fare, duration, and distance validity rules will be based on profiling.
- Invalid values will remain traceable through quality flags or quarantine records.
- March–May 2026 files contain the expected fields and usable date coverage.

#### Model choice

Use a two-fact Gold design:

- `fact_taxi_trip`: one row per accepted Green Taxi trip after the approved duplicate policy.
- `fact_weather_hourly`: one row per configured coordinate, UTC observation hour, and selected weather model.
- `dim_date`: one row per NYC-local calendar date.
- `dim_hour`: one row per hour of day from 0 through 23.
- `dim_taxi_zone`: one row per Taxi Zone `LocationID` in the selected validated snapshot.
- `dim_weather_classification`: one row per weather-code and precipitation-band combination.

Trip and weather measurements remain at their natural grains. Many trips can occur during one weather hour. Copying precipitation or temperature to every trip would create a double-counting risk. The separate weather fact also preserves the complete hourly series, including hours with no recorded trips.

A trip receives only the weather-classification key from its unique pickup-hour match. Temperature and precipitation remain exclusively in `fact_weather_hourly`. The facts are not joined through a fact-to-fact foreign key.

**Rejected alternative:** One trip fact with measured hourly weather stored as a dimension attached to trips. Although queryable with care, that structure blurs the weather grain and makes repeated-measure aggregation errors easier.

#### Keys and relationships

- `fact_taxi_trip.trip_key` is the deterministic non-null primary key created from the D10 identity inputs after collision groups are quarantined.
- `fact_weather_hourly.weather_observation_key` is deterministic from `coordinate_id`, `observation_timestamp_utc`, and `weather_model`.
- `dim_taxi_zone.zone_key` is the surrogate primary key; `location_id` is the unique source business key.
- `dim_weather_classification.weather_classification_key` is deterministic from `weather_code` and `precipitation_band`.
- `dim_date.date_key` uses `YYYYMMDD`.
- `dim_hour.hour_key` equals the hour value from 0 through 23.
- Pickup and drop-off use separate role-playing Date, Hour, and Taxi Zone foreign keys.
- `fact_taxi_trip.pickup_weather_classification_key` references the classification dimension and is not a foreign key to the weather fact.
- No Gold fact resolves a relationship directly against a Silver lookup table.

#### Nullable relationships and unknown handling

- `pickup_zone_key` and `dropoff_zone_key` are nullable for missing or unmatched source IDs. Preserve the original location ID and a match-status field.
- Taxi Zone IDs 264 and 265 remain valid members representing `unknown` and `outside_nyc`. Do not convert an unrelated unmatched ID to either member.
- `pickup_weather_classification_key` is nullable for `no_match` or `invalid_pickup_timestamp`.
- An ambiguous weather match blocks Gold publication.
- An unrecognized non-null WMO code maps to an explicit `unknown_code` classification and creates a data-quality review item.
- Do not create generic unknown Date or Hour members.

#### Measure rules

- **Trip count:** `SUM(trip_count)`, where `trip_count = 1` for every accepted trip inside the reporting window.
- **Pickup count:** trip count grouped through the pickup Taxi Zone role.
- **Drop-off count:** trip count grouped through the drop-off Taxi Zone role.
- **Average trip duration:** average `trip_duration_seconds / 60.0` only when drop-off is strictly later than pickup.
- **Average trip distance:** average non-null distance greater than or equal to zero.
- **Average fare amount:** average non-null, non-negative `fare_amount_usd`. This represents `fare_amount` and excludes tolls, surcharges, and tips.

Q1 uses pickup date, day of week, and hour as its time context while presenting pickup-zone and drop-off-zone results separately. Q2 groups measures by the weather classification matched at pickup hour. Q3 produces separate pickup-role and drop-off-role results; weather in both remains the pickup-hour classification.

An invalid value for one measure does not automatically remove the row from unrelated measures. Preserve the row through quality flags or quarantine according to the applicable policy.

#### Incremental and rerun behavior

- Trip and weather fact keys are deterministic; rerunning identical approved input must not create extra fact rows.
- A complete revised source contribution replaces the prior contribution rather than being appended beside stale rows.
- `dim_taxi_zone` uses a deterministic full refresh from the selected complete snapshot.
- `dim_date`, `dim_hour`, and `dim_weather_classification` are reproducible from deterministic seeds and rules.
- Operational fields such as `run_id` and `ingested_at` may change on replay; business content and row counts remain stable for identical input.

#### Consequences

- Q4 creates no traffic-model dependency while deferred.
- Pickup and drop-off roles must not be collapsed into one ambiguous zone or time field.
- Analytics must not sum hourly weather measurements through trip rows.
- The six Gold tables form the implementation contract after Issue #17 approval.
- A change to a table, grain, key, relationship, classification, or analytical measure must update the data model, dictionary, source-to-target mapping, this log, DBML source, and exported diagram together.

## Namespace and workflow decision

### D13: Databricks namespace and naming

**Status:** Approved through Issue #3  
**Decision date:** 2026-09-14  
**Revised:** 2026-09-15 after review

Use the `ftw-week-08` catalog and the existing R2-backed Volume:

```text
`ftw-week-08`.`00-source`.group_a_source
```

Persisted processing objects use these schemas:

| Pipeline responsibility | Schema |
|---|---|
| Control state | `01-control` |
| Bronze | `02-bronze` |
| Silver | `03-silver` |
| Integration step | No dedicated schema initially; writes approved integrated outputs to Gold |
| Gold | `05-gold` |
| Analytics | `06-analytics` |

Schema numbers align with the numbered `etl/` folders and sort the catalog in pipeline order. Table names do not repeat the group name because the approved processing schemas are dedicated to Group A.

Stage 00 is the source Volume; profiling happens in `notebooks/` and creates no processing schema. Stage 04 integration resolves trip relationships without changing the trip grain, so it writes to Gold initially. The `04-` slot remains available rather than forcing later renames.

A dedicated `04-integration` schema requires a new decision if integration begins producing a different grain, several Gold facts reuse an expensive persisted join, or the output requires separate write ownership.

**Rejected alternatives:**

- Unnumbered schemas such as `bronze`, `silver`, and `gold`, because they sort alphabetically rather than in pipeline order and would leave `00-source` as the only numbered stage.
- Numbering table names as well, because the schema already identifies the layer and identifiers beginning with digits would require additional quoting.
- Storing control state in Bronze, because pipeline runs, source batches, checkpoints, and data-quality results have different grains and lifecycles from source-preserving business data.

**Consequences:**

- Catalog and schema identifiers containing hyphens or beginning with digits require backticks in SQL.
- Table and column names must not begin with digits.
- The processing schemas are assumed to be dedicated to Group A. Revisit the namespace before implementation if another group must share them.
- Gold table names are governed by D12 and the approved model documents.


### D14: Ingestion batch tracking

**Status:** Active
**Decision date:** 2026-09-17

Implement Issue #19 as the `ingestion_batches` control table only, per the
approved name in `docs/standards/naming.md`. `pipeline_runs` (per-layer
execution tracking) is deferred to a separate future issue.

**Reason:** The issue's stated outcome — "the pipeline can answer 'have we
already processed this?' from a persisted table" — is fully answerable by
batch-level tracking alone. Per-layer run tracking (`pipeline_runs`) answers
a narrower, separate question and is not required to satisfy this outcome.

This work is scoped to sit before official Bronze ingestion (Issue #20). Data
previously loaded into personal dev/sandbox schemas during earlier profiling
and deduplication work (Issue #14) was exploratory and is not treated as
official Bronze ingestion.

**Table grain:** One row per external source batch or source version, per
`docs/standards/naming.md`'s Control-table grains section.

**Lifecycle:** `DISCOVERED` → `STARTED` → `SUCCESS` / `FAILED`. Status
advances to `SUCCESS` only after the load lands and passes validation (for
example, row-count reconciliation), not merely after the write technically
succeeds. A failed batch does not block retry: a retry registers a new
`batch_id` against the same file, preserving the failed attempt's history
rather than overwriting it.

**Two distinct hashing fields:**

- `content_sha256`: hashes the batch's actual content, to detect whether it
  changed independent of filename. For Green Taxi and Taxi Zones, this is a
  whole-file hash.
- `schema_fingerprint`: a separate hash of the column name-and-type
  signature, to detect structural drift independently of content changes.
  Not to be confused with `trip_hash` (D10, Issue #14), which is unrelated
  row-level deduplication logic at the Silver layer.

**`source_version_id`:** a human-readable label
(`<source_system>_<source_period>_v1`), distinct from `content_sha256`. Only
incremented by a person who has confirmed a genuine content change for an
already-processed period, not auto-incremented.


**Files:**

- `etl/01_control/00_create_control_tables.sql`: table DDL
- `src/ingestion/batch_tracking.py`: reusable register and mark-status
  functions
- `etl/01_control/90_validate_control.sql`: reusable validation queries (stuck
  batches, retry-history integrity)

**Consequence:** Any ingestion code for Green Taxi, weather, or Taxi Zones
must call `register_batch_discovered`, `mark_batch_started`, and either
`mark_batch_success` or `mark_batch_failed` from `src/ingestion/batch_tracking.py` rather
than writing ad hoc status tracking per source.

### D15: Silver quality-flag policy for Green Taxi trips

**Status:** Active
**Decision date:** 2026-09-17

Only duplicate hash collisions (per D10) are quarantined out of
`green_taxi_clean`. Negative fares, negative distances,
dropoff-before-pickup, and implausible passenger counts remain on
`green_taxi_clean`, tagged with boolean flag columns
(`negative_fare_flag`, `negative_distance_flag`,
`dropoff_before_pickup_flag`, `implausible_passenger_count_flag`)
rather than being excluded.

**Reason:** D12's measure eligibility rule states an invalid value for
one measure does not automatically remove the row from unrelated
measures. A trip with a negative fare still has a valid pickup,
dropoff, and location for trip-count purposes (Q1); fully quarantining
it would discard legitimate data that unrelated measures still need.
D10 is the only decision requiring full quarantine, and it covers
duplicate collisions only.

**Rejected alternative:** Quarantining every flagged row, as
Issue #27's initial acceptance-evidence wording suggested
("quantified, not silently dropped" was read as requiring quarantine
for negative fares, bad durations, and implausible passenger counts).
Rejected because no decision requires exclusion for these specific
conditions, and doing so would conflict with D12's measure-eligibility
rule.

**Also computed:** `trip_hash` (D10's composite fingerprint) is
computed in the same step as typing, from raw Bronze values before any
casting — so rounding introduced by casting `trip_distance`/`fare_amount`
to `DECIMAL` cannot change the hash or diverge from the fingerprint
tested in Issue #14.

**Consequence:** Any query using `fare_amount_usd`, `trip_distance_miles`,
or duration-derived measures must filter on the relevant flag
explicitly (e.g. `WHERE NOT negative_fare_flag`) rather than assuming
`green_taxi_clean` contains only valid values for every measure.

**Files:**

- `etl/03_silver/10_clean_green_taxi.sql`
- `etl/03_silver/90_validate_green_taxi.sql`

### D16: Taxi Zones Silver standardization and key-validation policy

**Status:** Approved through Issue #29  
**Decision date:** 2026-09-17

Standardize Taxi Zones in the Silver layer while preserving every valid source record from the selected reference snapshot.

Silver processing applies to:

- Zone-name cleanup
- Service-zone standardization
- Zone classification derivation
- Sentinel-record handling
- LocationID validation

Borough values remain explicit source values and are not converted to lowercase or rewritten.

Examples:

- Bronx → Bronx
- Brooklyn → Brooklyn
- Manhattan → Manhattan
- Queens → Queens
- Staten Island → Staten Island
- EWR → EWR
- N/A → N/A
- Unknown → Unknown

Classification logic is handled separately through zone_classification.


## Validation structure decision

### D17: Validation gates per source, and no source-profile folder

**Status:** Proposed
**Decision date:** 2026-09-17

**Decision:**

1. Bronze and Silver are validated per source. Each layer folder holds one
   `90_validate_<source>` file per source instead of a single
   `90_validate_<layer>` file. Integration, Gold and Analytics keep one
   validation file each, because they combine sources.
2. A source may advance from Bronze to Silver when its own gate passes.
   Integration requires the Silver gates of Green Taxi, weather and Taxi Zones.
3. All gates share one result contract, defined in `docs/data/validation.md`: one
   `01-control`.`data_quality_results` table, percentage units, one status rule,
   and lineage fields.
4. `etl/00_source_profile/` is removed. Source profiling lives in `notebooks/`
   and is recorded in `docs/data/source-profile.md`. The README repository structure
   is the reference layout.

**Reason:**

- The sources define good data differently: Green Taxi needs duplicate and
  duration rules, weather needs complete hourly coverage, and Taxi Zones needs
  key uniqueness and special-member rules. One combined file mixes unrelated
  rules and ownership.
- Sources are ingested on different schedules. Green Taxi Bronze is loaded while
  weather and Taxi Zones ingestion are still in progress; one layer gate would
  block Green Taxi on unrelated work.
- The profiling folder duplicated the profiling notebooks and
  `docs/data/source-profile.md`.
- Without a shared result contract, per-source notebooks had already diverged:
  different status rules, fractional thresholds compared with percentage
  failure rates, and separate results tables in Bronze with names starting with
  a digit.

**Rejected alternatives:**

- One `90_validate_<layer>` file per layer: couples unrelated sources and blocks
  finished sources.
- Per-source results tables (for example `02-bronze`.`90_validate_green_taxi`):
  cannot be combined into one gate or DQ dashboard, place control data in a
  business schema, and break D13's rule that table names must not begin with a
  digit.
- Allowing Integration to start when only some sources pass: trips would be
  resolved against unvalidated zones or weather.

**Assumptions:**

- Every source's checks can be expressed in the shared result format.
- `data_quality_results` is created in `01-control` before the per-source
  notebooks are migrated to it.

**Consequences:**

- Existing files were moved to the README layout in the same pull request as
  this decision (for example, `etl/01_control/validate_taxi_zones.ipynb`
  became `etl/02_bronze/90_validate_taxi_zones.sql`). Notebooks are committed
  in Databricks source format, and `.py` is used only where a step needs Python.
- Each Bronze load file creates its own table with `CREATE TABLE IF NOT EXISTS`, so
  it runs on its own; only shared control tables have a separate `00` setup file.
- `src/ingestion/batch_tracking.py` and `src/ingestion/schema_drift_check.py`
  keep their descriptive names; the README tree lists them instead of a single
  `common.py`, because the file name should say what the module does.
- The results tables `02-bronze`.`90_validate_taxi_zones` and
  `02-bronze`.`90_validate_green_taxi` (PR #82) should write to
  `01-control`.`data_quality_results` instead.
- The Silver weather table was built before a Bronze weather gate existed; it
  must be revalidated once that gate passes.
- `docs/standards/naming.md` and `etl/README.md` now point to `etl/`, not
  `sql/`, and no longer list `00_source_profile/`.


## Gold fact build decision

### D18: Deterministic facts and a blocking Gold gate

**Status:** Proposed through Issue #38
**Decision date:** 2026-09-18

**Decision:**

1. `fact_weather_hourly` reuses Silver's deterministic observation key and
   resolves Date, Hour, and Weather Classification keys only from built Gold
   dimensions.
2. `fact_taxi_trip` reads Silver `green_taxi_clean` joined to the validated
   `04-integration`.`trip_zone_map` and `trip_weather_map` on `trip_hash`.
   It resolves role-playing dimension keys in Gold and copies only the matched
   weather classification key; hourly temperature and precipitation remain on
   the weather fact.
3. `trip_key` is Silver's published `trip_hash` (D19), which is the deterministic
   hash of the approved D10 identity inputs and excludes batch, run, and
   ingestion metadata. Gold carries it rather than recomputing its own.
4. Both facts use `MERGE` on their deterministic keys. Because the current
   Silver and Integration inputs are complete accepted snapshots, the delete
   arm makes a revised contribution converge without leaving stale rows.
5. Pre-write guards block join fan-out, duplicate trip keys, unresolved required
   FKs, ambiguous weather matches, and non-unique source-version lineage.
6. `90_validate_gold.sql` writes one row per check to the shared control table
   and raises an error if any blocking check fails.

**Known contract gap:** `requested_timezone` is specified in the data
dictionary, but the request parameter is not persisted in Bronze or Silver.
Gold does not fabricate it. It must be captured upstream before the column can
be published and validated.

**Consequence:** The files are implementation-ready but are not proof of a
passing Gold layer until the Integration branch is merged and the Databricks
proof run records counts, reconciled measures, and an identical-input rerun.

### D20: Accept the weather coverage gap rather than re-requesting the series

**Status:** Approved
**Decision date:** 2026-09-18

**Decision:**

Weather-based measures (Q2, Q3) are reported against the trips that have a
weather match, not against all accepted trips. The denominator is stated
wherever such a measure appears: **133,173 of 133,353 accepted trips, 99.87%**.

**Reason:**

The Open-Meteo series was requested for 2026-03-01 to 2026-05-31 in **UTC**,
while trips are recorded in `America/New_York`. The two windows do not align at
either end, so 180 trips have no weather hour to match:

| | trips |
|---|---:|
| Inside the reporting window but past the weather window | 175 |
| Outside the reporting window entirely (2008-12, 2009-01, 2026-02) | 11 |

The 175 are all late on **2026-05-31**: the last weather hour is 23:00 UTC,
which is 19:00 local, so pickups after 20:00 that evening have no match.

**Rejected alternative:** re-requesting the series for 2026-02-28 to 2026-06-01
and reloading. This is the better fix and remains the recommendation for any
future run — the source window was specified wrongly, not the pipeline. It was
rejected for this iteration on time, not on merit: it needs the superseded
Bronze response deleted first (a wider request is a different business key, so
it inserts beside the old one rather than replacing it, and two responses
covering the same hour break Silver's MERGE), then a full reload through
Integration and Gold.

**Consequence:**

- Any by-date weather view understates **2026-05-31**. The shortfall is
  systematic, not random, and must not be read as a finding about that day.
- `weather_match_status` on `fact_taxi_trip` carries the reason per row, so the
  excluded trips stay identifiable rather than silently absent.
- 11 of the 180 can never be covered by any request for this period; they are
  permanently out of scope for Q2 and Q3.

### D19: Publish Silver's `trip_hash` as the trip identity

**Status:** Approved
**Decision date:** 2026-09-18

**Decision:**

`green_taxi_clean` publishes `trip_hash` instead of dropping it. Integration keys
its maps on it, and Gold carries it as `fact_taxi_trip.trip_key` rather than
computing a hash of its own.

**Reason:**

The hash is unique within the clean set by construction: that is exactly what
`collision_count = 1` means under D10. Dropping it left Silver with no key, so
Gold recomputed one over the **typed** Silver columns while Silver had hashed the
**raw** Bronze values. Two serializations of one identity existed, over values of
different precision, with nothing keeping them in step. Integration also had
nothing to hang a key map on, which is why stage 04 had no workable shape.

**Rejected alternatives:**

- Keep recomputing in Gold: two definitions that agree today only because the
  source carries at most two decimal places. A future month with three would let
  two rows distinct in Silver round into one `trip_key`, breaking the fact's
  primary key in a way the Silver gate structurally cannot see.
- Join Integration maps on the seven identity columns instead of a key: works,
  but puts a seven-column join in every downstream query.

**Assumptions:**

- The D10 collision policy continues to quarantine whole groups, which is what
  makes the hash unique in the clean set.

**Consequences:**

- Every `trip_key` value changed; `fact_taxi_trip` had to be rebuilt.
- The Silver gate proves the key is usable: non-null, unique, 64 characters, and
  disjoint from the quarantine table.

### D21: `passenger_count = 0` means not recorded, not implausible

**Status:** Approved
**Decision date:** 2026-09-18

**Decision:**

`passenger_count = 0` sets `passenger_count_missing_flag`, alongside null. It does
not set `implausible_passenger_count_flag`, which stays for counts below zero or
above eight.

**Reason:**

Profiling the three source files shows it is a vendor reporting convention rather
than a data error:

| VendorID | Trips | `= 0` | NULL | % zero |
|---:|---:|---:|---:|---:|
| 2 | 108,531 | 205 | 4,396 | 0.19% |
| 6 | 14,181 | 0 | 14,181 | 0% |
| 1 | 10,655 | 1,522 | 177 | 14.28% |

Vendor 6 reports null for every one of its trips; vendor 1 writes `0` on 14.28% of
its. The trips themselves are ordinary: median fare $14.90 against $14.20 for
trips with a recorded count, median distance 1.7 miles against 1.9.

**Rejected alternative:**

Flagging zero as implausible. The trip is not implausible; only the passenger
count is unknown, and the two statements belong in different columns.

**Consequences:**

- 20,481 rows carry `passenger_count_missing_flag`, 15.35% of the clean table.
- **Any passenger measure in Gold or Analytics must exclude those rows and state
  its denominator.** Leaving zero unflagged would average the zeros in while
  dropping the nulls, biasing every passenger average low.
- None of the three approved business questions currently uses passenger count,
  so nothing downstream depends on this yet.

### D22: Full deterministic rebuild above Bronze

**Status:** Approved
**Decision date:** 2026-09-19

**Decision:**

Bronze is the only incremental layer. Silver, Integration, Gold and Analytics are
rebuilt in full from the layer below on every run. No watermark, processed-batch
marker or row-level merge state exists below Bronze.

**Reason:**

1. **Late-arriving rows are real and cross-month.** Counted on the three source
   files: the May file carries 8 pickups dated April 2026 and 2 dated December
   2008; the April file carries 1 dated March and 2 dated May. Rebuilding only the
   arriving month, or advancing a watermark on pickup date, leaves April wrong by
   eight trips and reports success.
2. **The duplicate rule is global by construction.** `collision_count` partitions
   over the whole trip population. An incremental Silver would have to detect
   collisions between an arriving batch and already-published rows, then
   retroactively move a clean row into quarantine. Verified: all 7 collision
   groups fall inside a single source file, so that machinery would cover a case
   that does not occur.
3. **Volume does not justify it.** 133,367 rows over three months.
4. **It makes the idempotency proof simpler**: rerunning reduces to Bronze
   skipping on content hash plus every layer above being a function of Bronze.

**Rejected alternatives:**

- Batch-scoped append into Silver: breaks D10, since duplicate detection would see
  one batch at a time.
- Partition-scoped rebuild of Gold by pickup month: correct only if the affected
  partitions come from the arriving batch's actual pickup dates rather than the
  file's month, which the table above shows differ. Recorded as the upgrade path.

**Assumptions:**

- Monthly volume stays near 50,000 rows. Revisit past roughly 2 million rows in
  Silver, or a rebuild over ten minutes.
- Cross-batch hash collisions remain absent. This is a property of the data, not a
  guarantee, so the Silver gate counts collision groups every run rather than
  assuming zero.

### D23: Wall-clock business timestamps are `TIMESTAMP_NTZ`

**Status:** Approved
**Decision date:** 2026-09-19

**Decision:**

Business timestamps that represent a wall-clock reading are stored as
`TIMESTAMP_NTZ` in Silver, Integration and Gold. Timezone conversion uses
`convert_timezone(from, to, ts)` with both ends named. `to_timestamp`,
`from_utc_timestamp`, `to_utc_timestamp` and `unix_timestamp` are not used on
these columns. Operational timestamps (`ingested_at`, `silver_processed_at`,
`executed_at`) remain `TIMESTAMP`, since they record an instant.

**Reason:**

Those functions resolve a zoneless value through the **session** timezone, so the
same input produced different stored data depending on a cluster setting nobody
had written down. Three cases were found:

- Open-Meteo sends a zoneless ISO8601 string. `to_timestamp` then
  `from_utc_timestamp` was correct on a UTC cluster and silently cancelled itself
  out on an `America/New_York` one: `2026-03-01T00:00Z` became midnight on 1 March
  instead of 19:00 on 28 February.
- `unix_timestamp` differences for trip duration were wrong across the 8 March DST
  transition on a New York cluster.
- A plain `TIMESTAMP` column in Gold would have converted Silver's values on
  insert, undoing the fix one layer down.

**Rejected alternative:**

Pinning the cluster's session timezone. That makes correctness depend on
configuration outside the repository, which no gate can check.

**Consequences:**

- The Silver weather gate asserts every interior local day holds 23 to 25 distinct
  hours, which detects a conversion that is not shifting at all.
- Boundary days are excluded from that check: a UTC request window cuts the first
  and last local days short by construction.

### D24: `SUPERSEDED` batch status

**Status:** Approved
**Decision date:** 2026-09-19

**Decision:**

`ingestion_batches.status` gains `SUPERSEDED`. A loader demotes a prior `SUCCESS`
batch to it before registering a replacement for the same content.

**Reason:**

Reloading content that already succeeded, usually because its Bronze table was
dropped, left two `SUCCESS` rows for one content hash. The control gate reads that
as the same bytes processed twice, which is exactly what it should flag. Deleting
the earlier row would hide a real attempt, so it is demoted instead and keeps its
own `batch_id`, `row_count` and timestamps.

**Rejected alternatives:**

- Deleting the earlier batch: destroys the audit trail the control table exists for.
- Exempting reloads from the duplicate check: removes the only check that answers
  "what prevents this batch being processed twice?".

**Consequences:**

- The demotion is guarded by the same condition that decides whether a replacement
  is registered, so the two cannot disagree.
- `source_systems_registering_batches` counts only `SUCCESS`, so coverage
  reporting is unaffected.
- `supersedes_batch_id` exists on the table but is **not yet populated**; the link
  between a batch and the one it replaces is currently inferable only from
  `content_sha256` and timestamps.

### D25: `code_revision` from a job-level parameter

**Status:** Approved
**Decision date:** 2026-09-22

**Decision:**

Every gate keeps its `code_revision` session variable and assigns it from the SQL
parameter of the same name:

    SET VARIABLE code_revision = COALESCE(NULLIF(:code_revision, ''), 'UNSET');

The value is supplied once, as a job-level parameter in `databricks.yml`,
defaulting to `${bundle.git.commit}` so it resolves at deploy time. Gold keeps its
own variable name, `gold_code_revision`; only the assignment changed.

**Reason:**

All ten gates hardcoded a sentinel, so `data_quality_results` and `pipeline_runs`
recorded a constant as the code version. Lineage reached the source file and the
run but not the logic, which is the link needed when a number is wrong. Gold
spelled its sentinel `'not_provided'` while the others used `'UNSET'`, so "no
revision recorded" had two values while `gate_status` aggregates with
`MAX(code_revision)`.

`git_source` tracks a ref, so a run executes whatever that ref points at when it
starts. Without a recorded revision, two runs described as "from main" can be
different code and nothing says which.

**Verified on the workspace, 2026-09-22:**

- `SET VARIABLE x = :marker` binds when a value is supplied. An earlier attempt
  returned `UNBOUND_SQL_PARAMETER`, but the parameter was empty at the time: that
  error means "no value supplied", not "unsupported".
- A **job-level** parameter reaches a `sql_task` file with no per-task wiring.
- After deploying and running `90_validate_control`, `pipeline_runs` recorded the
  deployed commit rather than a sentinel.

**Rejected alternatives:**

- **Removing the variable and using the marker inline at each usage site.** Works,
  but touches every reference rather than one line, and an earlier mechanical
  substitution of exactly that shape put an expression into an `INSERT` column
  list and broke the Gold gate with `PARSE_SYNTAX_ERROR`. More edits, more risk,
  no gain now that `SET VARIABLE` is known to accept a marker.
- **Ten per-task parameters.** Equivalent, but ten entries are ten things to get
  wrong when one suffices.
- **Renaming `gold_code_revision` to match the other nine.** Gold's `INSERT` names
  a target column `code_revision`, and how a bare reference resolves there when a
  column of that name is in scope was not verified. The name is a local variable
  that is never stored; what had to match across gates was the value.
- **Writing the revision into a control table for gates to read.** Avoids
  parameters entirely, but adds an ordering dependency between tasks to solve a
  problem the parameter already solves.

**Consequences:**

- A gate run by hand with no parameter records `'UNSET'`. An empty value is
  recorded honestly rather than claiming a revision the run cannot prove.
- A gate run by hand with **no parameter defined at all** fails with
  `UNBOUND_SQL_PARAMETER`. This is inherent to parameter markers — there is no
  optional form — and it makes the untraceable run the awkward one.
- The recorded revision is the **deployed** commit, not the latest commit on the
  branch. Picking up new code requires a deploy, which is the point of a
  controlled deployment rather than a limitation of it.


## Monitoring decisions

### D26: `no_stuck_runs` check for pipeline_runs

**Status:** Approved
**Decision date:** 2026-09-24

**Decision:**

`90_validate_control.sql` gains an eighth check, `no_stuck_runs`, mirroring
check 4 (`no_stuck_batches`): a run still `STARTED` past `stuck_after_hours`
is flagged as abandoned rather than in progress. It reads only the existing
`pipeline_runs` columns (`status`, `started_at`); no schema change is
required.

Of the classroom monitoring framework's five execution signals (STATUS,
DURATION, FAILURES, RECENCY, RETRIES), STATUS, DURATION, FAILURES, and
RECENCY are all directly answerable from `pipeline_runs`'s existing columns.
RETRIES — linking a run to the failed attempt it replaces — would need a
schema change and is explicitly deferred; see Rejected alternatives.

**Reason:**

A run that crashes or hangs mid-execution leaves a row permanently in
`STARTED`, which explains nothing and blocks nothing on its own. This check
surfaces that condition the same way `no_stuck_batches` already does for
`ingestion_batches`.

**Rejected alternatives:**

- **Adding a `previous_attempt_run_id` column to `pipeline_runs`** to
  support a RETRIES signal. Attempted and reverted, including on the live table (see Operational note below). Populating it required
  either a manual `UPDATE` after every retry or a job-level parameter a
  person must remember to supply — both depend on a human step with nothing
  to catch a missed or wrong value, so the column would sit at `NULL`
  indefinitely with no proof it was ever used correctly. It also introduced
  real migration risk: Databricks SQL's `ALTER TABLE ... ADD COLUMN` does
  not support an `IF NOT EXISTS` modifier (confirmed via
  `PARSE_SYNTAX_ERROR`), and the idempotent workaround added meaningful
  complexity for a column with no functioning consumer. Deferred until
  there is a way to populate it automatically, without a human step.
- **Whole-pipeline execution tracking**, writing `pipeline_runs` rows from
  every `90_validate_*` gate rather than Control alone. Out of scope for
  this pass; `pipeline_runs` remains written to only by
  `90_validate_control.sql`. The last gate in the chain (Gold) could stand
  in as a proxy for "did the whole pipeline run" if this is revisited, or
  Databricks' own native job-run history could be used instead of
  expanding `pipeline_runs`.

**Consequences:**

- `no_stuck_runs` participates in the same blocking logic as
  `no_stuck_batches` (`WARN` severity, `threshold_pct = 0.0`), so a stuck
  run fails the gate, not just warns.
- RETRIES remains an open signal for the Execution layer; a future
  decision should revisit it once an automatic, non-human-dependent way to
  link a retry to its failed attempt exists.
- STATUS, DURATION, FAILURES, and RECENCY require no further schema work;
  all four are already answerable from `pipeline_runs`'s existing columns.

**Operational note (2026-09-24):**

The live `pipeline_runs` table still carried `previous_attempt_run_id` from
the reverted attempt described above — the column's own `ALTER TABLE ADD
COLUMNS` had already run against the shared table before that attempt was
rolled back in code, so removing the code did not remove the column. This
surfaced as `DELTA_INSERT_COLUMN_ARITY_MISMATCH` on the Control gate's insert
into `pipeline_runs`, which expects the 6 columns this decision assumes.

Databricks SQL's `DROP COLUMN` requires column mapping (`delta.columnMapping.mode
= 'name'`), which is not enabled by default and cannot later be reverted to
`none`. Column mapping was enabled and the leftover column was dropped:

    ALTER TABLE `ftw-week-08`.`01-control`.pipeline_runs
    SET TBLPROPERTIES ('delta.columnMapping.mode' = 'name');

    ALTER TABLE `ftw-week-08`.`01-control`.pipeline_runs
    DROP COLUMN previous_attempt_run_id;

This is a permanent property of the table going forward. It does not change
query behavior or require any reader/writer on current Databricks compute to
change anything, but it is a one-way change worth knowing about if the
table's properties are inspected later.

A seeded test row (`demo-stuck-run-001`), used earlier to produce evidence of
a failing gate run, was also deleted directly from the live table (table
version 21) as part of this same cleanup.

**Files:**

- `etl/01_control/90_validate_control.sql`


## Scheduling decision

### D27: A weekly schedule, Monday 06:00 New York time

**Status:** Approved
**Decision date:** 2026-09-23

**Decision:**

The job runs on a time-based schedule, weekly on Monday at 06:00
`America/New_York`, declared in `databricks.yml`:

    schedule:
      quartz_cron_expression: "0 0 6 ? * MON"
      timezone_id: America/New_York

The schedule sets no `pause_status`. The target decides: `dev` deploys it paused
and `prod` deploys it running.

**Reason:**

Every run so far was started by hand, so "how does it run tomorrow" had no
answer, and freshness had no expected interval to be measured against.

Green Taxi arrives monthly. A daily run would find nothing new on almost every
day, and each one still costs a full pipeline run of about five and a half
minutes of warehouse time, even though files already loaded are skipped by
content hash. Weekly bounds how long a newly landed file waits to one week, and
gives freshness a definition: no successful run in 8 days means the data is
stale.

**Verified with `databricks bundle validate`, 2026-09-23:**

- With no `pause_status` on the job, `dev` resolves the schedule to `PAUSED` and
  `prod` to `UNPAUSED`.
- With `pause_status: UNPAUSED` set on the job, `dev` also resolves to
  `UNPAUSED`. An explicit value overrides development mode, so every sandbox
  would run on the timer. `tests/test_bundle_contract.py` fails if one is added.
- Those validate runs also reported an error for `prod` that the resolved
  values above do not show: production mode requires `workspace.root_path`, and
  the `prod` target had never set one, so it could not deploy at all. Added on
  2026-09-24 as one fixed folder under `/Workspace/Shared` (per-user folders
  would let a second deploy create a duplicate prod job). `prod` now validates
  with one warning, that the folder is writable by all workspace users, which
  is accepted so any of us can redeploy.

**Verified on the deployed dev job, 2026-09-23:**

Deployed from `f5ae6e8` with `databricks bundle deploy --target dev`. On
`[dev ina_magno] NYC Mobility Pipeline` (job `224133189973974`),
`databricks jobs get` then showed:

    schedule: pause_status PAUSED, quartz_cron_expression "0 0 6 ? * MON",
              timezone_id America/New_York
    git_commit and code_revision default: f5ae6e82002168d949c2efa1d1501711cc8746d4

No run was started by the deploy; the latest run was still the one from before
it.

**Rejected alternatives:**

- **A file arrival trigger.** The more accurate trigger for a monthly source,
  since the job would run when a file lands rather than on a guess. Rejected for
  now: files reach the Volume by hand upload rather than from a feed, so it would
  fire on a person's upload anyway, and it has not been tried on this workspace.
  Worth revisiting if delivery is automated.
- **Daily.** Picks up a new file within a day, at the cost of about thirty runs a
  month, nearly all of which find nothing new.
- **Monthly.** Matches the source's cadence, but a file that lands the day after a
  run waits almost a month.

**Consequences:**

- Nothing fires in `dev`. The schedule only produces runs once the bundle is
  deployed to `prod`, which has not been done yet. `prod` now validates, but
  going live waits on #122, so the first scheduled runs are not all failures.
- Until #122 is fixed, every run ends `FAILED` on the dashboard tasks. A running
  schedule would report a failure every week, and failure alerting (#131) would
  fire each time.
- Freshness monitoring (#119, #131) can use 8 days as its staleness threshold.
- 06:00 is New York local time, so the run moves by an hour in UTC terms when
  daylight saving changes. The local time stays the same.

**Subsequent repository outcome, 2026-09-25:**

The bundle now declares all three dashboard resources and their job tasks, and
the contract tests cover those references. The earlier statements that every
run would fail on dashboard tasks and that production was waiting on #122
describe the state when D27 was accepted; they are not current implementation
status. Live production deployment and run state must still be verified in
Databricks.


## Source gate decision

### D28: Negative fares are reported by the source gate, not blocked

**Status:** Approved through Issue #147
**Decision date:** 2026-09-24

**Decision:**

`fare_amount_non_negative` in `src/ingestion/source_gate.py` has severity
`INFO` and no threshold. The gate still counts negative fares and records the
count in its evidence, but a delivery is never refused because of them.

**Reason:**

The check was `WARN` with a 0.1% threshold. On the March–May 2026 source files
the gate found 384 negative fares out of 133,367 rows, 0.288% (111 in March,
153 in April, 120 in May), so the check failed and the gate returned
`BLOCKED`, exit 1. That was the delivery Bronze had already loaded and
reconciled to the cent.

The rest of the pipeline accepts those rows on purpose:

- D15 keeps negative fares in `green_taxi_clean`, tagged with
  `negative_fare_flag`, and rejects quarantining them.
- `etl/02_bronze/90_validate_green_taxi.sql` reports the same count as
  `negative_fare_amount`, severity `INFO`.

A pre-ingestion gate that refuses what every later layer is designed to keep
would stop the scheduled run (D27) for no data-quality benefit. The gate
exists to stop deliveries the pipeline cannot use, not to restate Silver's
flags as refusals.

The committed evidence did not show the problem. `results.json` was generated
before the fare check was added, ran 15 checks, and listed `https://` inputs
that the current code refuses with exit 2.

**Verified 2026-09-24**, with DuckDB 1.1.3 as pinned in `requirements-dev.txt`,
against local copies of the three files whose SHA-256 checksums match the
Volume:

- Before: `fare_amount_non_negative` FAIL, 384 rows; gate `BLOCKED`, exit 1.
- After: `fare_amount_non_negative` INFO, 384 rows; gate `ACCEPTED`, exit 0,
  16 checks.

**Rejected alternatives:**

- **Raise the threshold until the files pass.** `data_quality_results`
  defines `threshold_pct` as a documented tolerance, not one tuned to today's
  data. A number picked to make 0.288% pass would block again on a month
  with slightly more refunds, and still contradict D15.
- **Keep blocking, and quarantine negative fares in Silver.** Rejected by
  D15: a negative fare still has a valid pickup, dropoff and zone for
  trip-count measures.

**Open for review:**

Three other gate checks cover conditions D15 also keeps and flags in Silver,
and were left unchanged here:

- `trip_distance_non_negative`: `BLOCK`, 0 rows today. D15 keeps negative
  distances with `negative_distance_flag`. CI's bad-delivery case relies on it
  blocking.
- `dropoff_after_pickup`: `WARN` at 0.1%, currently 0.075%. It counts
  zero-length trips as well as dropoff before pickup, so it is not the same
  condition as `dropoff_before_pickup_flag`.
- `passenger_count_gt_8`: `WARN` at 0.1%, currently 0.0097%.

Whether they follow the same rule is a separate decision, tracked in #153 together with a wording fix in `docs/data/validation.md`, which calls INFO checks "measurements with a tolerance" although every INFO check records `threshold_pct` as NULL.

Resolved in D29.

**Consequences:**

- `evidence/proof/source-validation/results.json` must be regenerated from
  the current code against the Volume paths.
- `docs/tools/duckdb/validation-checks.md` and `docs/tools/duckdb/evidence.md` are updated
  in the same pull request.
- `evidence/proof/2026-09-23-bronze-duckdb-reconciliation.md` still records
  the 15-check run of Issue #115. It is left unchanged as a record of that run.
- Issue #148, which runs the gate as a job task, is unblocked by this.

### D29: The gates block on reversed trips, not zero-length ones

**Status:** Approved through Issue #153
**Decision date:** 2026-09-24

**Decision:**

The three checks D28 left open for review:

| Check | Before | After |
|---|---|---|
| `trip_distance_non_negative` | `BLOCK` | `BLOCK`, unchanged |
| `dropoff_after_pickup` | `WARN` at 0.1%, counting dropoff at **or** before pickup | Split into `dropoff_before_pickup`, `WARN` at 0.1%, and `zero_length_trip`, `INFO` |
| `passenger_count_gt_8` | `WARN` at 0.1% | `WARN` at 0.1%, unchanged |

The dropoff split applies to both the source gate (`src/ingestion/source_gate.py`) and the Bronze SQL gate (`etl/02_bronze/90_validate_green_taxi.sql`). `docs/data/validation.md` now says INFO checks have no threshold.

**Reason:**

Silver keeps all four conditions and flags them (D15). Each check still got its own answer, because the data and the meaning differ.

- **Negative distance stays BLOCK.** It had 0 rows in March, April and May 2026. A negative fare can be a refund or a void, which is why D28 reports it. A negative distance has no legitimate meaning, so it points to a broken delivery rather than a source trait. The Bronze SQL gate also treats it as `FAIL`, and CI's bad-delivery step keeps a real blocking check to exercise.
- **The dropoff check is split.** It counted 100 rows: 99 zero-length trips (dropoff at the same instant as pickup) and 1 trip that ended before it started. By month that was 35, 38 and 27 against a limit of 45, so April was 7 rows from blocking the scheduled run (D27) over trips Silver keeps: zero-length trips carry `implausible_duration_flag`. Only the one reversed trip matches Silver's `dropoff_before_pickup_flag`. After the split, the blocking check uses Silver's own condition, and zero-length trips are counted as INFO. Reversed timestamps up to 0.1% are treated as isolated row-level source anomalies and retained with a Silver flag; a rate above 0.1% is treated as systemic timestamp corruption, such as swapped pickup and drop-off columns, and blocks the delivery.
- **Both gates change.** The Bronze SQL gate had the identical at-or-before rule. Changing only the source gate would have left the same risk one step later in the same run.
- **Passenger count stays WARN.** 13 rows; the worst month was 0.0156%. Rates up to 0.1% are treated as isolated row-level source anomalies and retained with a Silver flag. A rate above 0.1%, more than six times the highest observed monthly rate, is treated as a material departure from the established source baseline and evidence of a broader source-quality, schema, or column-mapping problem, so it blocks the delivery.

**Exploratory local decision analysis verified 2026-09-24**, with DuckDB 1.4.5, against local copies of the three Green Taxi files whose SHA-256 checksums match the Volume:

- Before: 16 checks, `ACCEPTED`; `dropoff_after_pickup` `WARN`, 100 rows (0.075%).
- After: 17 checks, `ACCEPTED`, exit 0; `dropoff_before_pickup` `WARN`, 1 row (0.0007%); `zero_length_trip` `INFO`, 99 rows. Each month on its own is also `ACCEPTED`.
- `tests/test_source_gate_severities.py` pins each severity, and checks the effect: a delivery with 2% zero-length trips is `ACCEPTED`, and one with 2% reversed trips is `BLOCKED` on `dropoff_before_pickup`. All four tests fail against the previous code.

DuckDB 1.4.5 was used only for the exploratory local decision analysis above. The committed `evidence/proof/source-validation/results.json` and the executed Databricks evidence were generated with DuckDB 1.1.3, the version pinned in `requirements-dev.txt` on this branch.

**Verified on the dev job, 2026-09-24:** deployed `9bc870e` and ran it (run `1115563914656407`): all 32 tasks succeeded. The source-gate task read the three files on the Volume with DuckDB 1.1.3 and recorded 17 Green Taxi checks, 0 failed. In both the `source` and `bronze` layers, `data_quality_results` shows `dropoff_before_pickup` `WARN` with 1 row, `zero_length_trip` `INFO` with 99 rows, and no `dropoff_after_pickup`. `gate_status` is `PASS` for every layer, and Bronze still holds 133,367 rows.

**Rejected alternatives:**

- **Report the whole dropoff check as INFO.** It would never block, so a delivery with reversed timestamps would load without a signal.
- **Raise the dropoff threshold.** The same objection as in D28: a number tuned to today's data, which still counts zero-length trips as defects.
- **Change only the source gate.** The Bronze SQL gate would block on the same rows one step later.
- **Report negative distance as INFO.** It follows D28 literally, but removes a check that has no legitimate trigger, and CI would need another blocking check.
- **Report passenger count as INFO.** It removes a signal that costs nothing today.

**Consequences:**

- The source gate runs 17 Green Taxi checks. `data_quality_results` rows written before this change keep the name `dropoff_after_pickup`; runs after it write `dropoff_before_pickup` and `zero_length_trip`.
- CI's bad-delivery step is unchanged, since `trip_distance_non_negative` still blocks.
- `negative_distance_flag` in Silver stays defensive: with both gates blocking, a negative distance never reaches Silver.
- `evidence/proof/source-validation/results.json` and `docs/tools/duckdb/evidence.md` are regenerated from the Volume in the same pull request.
- D28's "Open for review" list is resolved here.
