# Decision log

This document is the canonical record of important product, data, and engineering decisions for the NYC Mobility Pipeline. It records what was decided, why it was chosen, which alternatives were rejected, what assumptions remain, and what consequences follow.

**Last updated:** 2026-09-17  
**Decision priority:** correctness > reliability > maintainability > scalability > observability > efficiency

## Maintenance rule

When a decision changes, update this file and every affected canonical document in the same pull request. Explicitly identify any document that remains stale.

This log explains why choices were made. Detailed implementation contracts live in:

- `docs/architecture.md`
- `docs/ingestion.md`
- `docs/data_model.md`
- `docs/data_dictionary.md`
- `docs/source_to_target_mapping.md`
- `docs/naming_conventions.md`
- `docs/model/nyc_mobility_star_schema.dbml`

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
| D14 | Build `ingestion_batches` as a standalone control table, scoped before Bronze ingestion; `pipeline_runs` deferred | Active | The pipeline can answer "have we already processed this?" from a persisted table without requiring per-layer run tracking yet |


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

Schema numbers align with the numbered `sql/` folders and sort the catalog in pipeline order. Table names do not repeat the group name because the approved processing schemas are dedicated to Group A.

Stage 00 profiles source files and creates no processing schema. Stage 04 integration resolves trip relationships without changing the trip grain, so it writes to Gold initially. The `04-` slot remains available rather than forcing later renames.

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
approved name in `naming_conventions.md`. `pipeline_runs` (per-layer
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
`naming_conventions.md`'s Control-table grains section.

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

Because the suffix is human-assigned, `register_batch_discovered` refuses to
assign one silently. `resolve_source_version_id` compares the incoming
`content_sha256` against every `SUCCESS` batch already recorded for the same
`(source_system, source_period)`:

- No prior success, or identical content re-discovered: the default
  `_v1` label is used.
- Different content for an already-processed period: the call raises, naming
  the recorded version and both hashes, until a person passes an explicit
  `source_version_label`.
- A label already recorded against different content: the call raises rather
  than reusing an existing version identity.

Without this, a revised April file would register under the same
`source_version_id` as the original, leaving D04's "replace the prior
contribution for that logical source batch" ambiguous — two different contents
under one version identity. Covered by
`tests/test_batch_tracking_version_guard.py`.


**Files:**

- `etl/01_control/00_create_tables.sql`: table DDL
- `src/ingestion/batch_tracking.py`: reusable register and mark-status
  functions
- `etl/01_control/90_validate.sql`: reusable validation queries (stuck
  batches, retry-history integrity)

**Consequence:** Any ingestion code for Green Taxi, weather, or Taxi Zones
must call `register_batch_discovered`, `mark_batch_started`, and either
`mark_batch_success` or `mark_batch_failed` from `batch_tracking.py` rather
than writing ad hoc status tracking per source.
