# Contributing

This document defines how the team develops, reviews, and safely runs the NYC Mobility pipeline.

## Project tracking

GitHub Issues and the NYC Mobility Pipeline GitHub Project are the canonical work trackers.

Before starting work:

1. Confirm the issue is assigned to you.
2. Confirm its prerequisites are complete.
3. Move it to **In progress**.
4. Assign a reviewer.
5. Create one branch for the issue.

## Branch naming

Use:

```text
<type>/issue-<number>-<short-description>
```

Examples:

```text
docs/issue-3-naming-conventions
profile/issue-10-taxi-source
ingestion/issue-20-taxi-files
silver/issue-27-clean-taxi
test/issue-30-silver-validation
```

Do not combine unrelated issues in one branch.

## Databricks Git folders

Each teammate must use their own Databricks Git folder and development branch.

Do not have multiple teammates perform Git operations in the same Databricks Git folder.

Only the assigned integration owner should run approved code against shared demonstration tables.

## Databricks namespaces

The approved catalog is:

```text
ftw-week-08
```

The R2-backed source Volume is:

```text
`ftw-week-08`.`00-source`.`group_a_source`
```

Its workspace path is:

```text
/Volumes/ftw-week-08/00-source/group_a_source/
```

The proposed schemas are:

```text
`ftw-week-08`.`00-source`
`ftw-week-08`.`01-bronze`
`ftw-week-08`.`02-silver`
`ftw-week-08`.`03-gold`
`ftw-week-08`.`04-analytics`
`ftw-week-08`.`05-control`
```

The `control` schema will be created or verified by Issue #5 after Issue #3 is approved.

## Source landing folders

Use the existing folders:

```text
/Volumes/ftw-week-08/00-source/group_a_source/green_taxi/
/Volumes/ftw-week-08/00-source/group_a_source/taxi_zones/
/Volumes/ftw-week-08/00-source/group_a_source/weather/
/Volumes/ftw-week-08/00-source/group_a_source/traffic_advisory/
```

Preserve original source filenames where practical:

```text
green_tripdata_2026-03.parquet
green_tripdata_2026-04.parquet
green_tripdata_2026-05.parquet
taxi_zone_lookup.csv
```

Do not add `group_a_` to source filenames. The Volume provides group isolation.

## Fully qualified references

Every persisted table reference must use:

```text
catalog.schema.table
```

Example:

```sql
SELECT *
FROM `ftw-week-08`.`01-bronze`.`green_taxi_raw`;
```

The catalog and schema names containing hyphens must be enclosed in backticks.

SQL and notebook cells should work independently. Do not rely on a previous `USE CATALOG` or `USE SCHEMA` command.

Always inspect the actual upstream table and column names before referencing them.

## Approved table names

### Control

```text
`ftw-week-08`.`05-control`.`pipeline_runs`
`ftw-week-08`.`05-control`.`ingestion_batches`
`ftw-week-08`.`05-control`.`data_quality_results`
```

### Bronze

```text
`ftw-week-08`.`01-bronze`.`green_taxi_raw`
`ftw-week-08`.`01-bronze`.`open_meteo_weather_raw`
`ftw-week-08`.`01-bronze`.`taxi_zones_raw`
`ftw-week-08`.`01-bronze`.`dot_advisories_raw`
```

The DOT advisory table is optional.

### Silver

```text
`ftw-week-08`.`02-silver`.`green_taxi_trips`
`ftw-week-08`.`02-silver`.`weather_hourly`
`ftw-week-08`.`02-silver`.`taxi_zones`
```

### Gold and Analytics

Exact Gold and Analytics names require approval of the star schema in Issue #17.

Approved patterns are:

```text
Gold fact: fact_<business_process>
Gold dimension: dim_<business_entity>
Analytics: <measure>_by_<dimensions>
```

Do not create provisional Gold tables before Issue #17 is approved.

## Column naming

Outside source-preserving Bronze fields:

- Use lowercase `snake_case`.
- Use `_id` for identifiers.
- Use `_at` for timestamps.
- Use `_date` for dates.
- Use `_count` for counts.
- Use `_amount` for currency.
- Use `_flag` for Boolean indicators.

Preserve source column names in Bronze where practical.

Document every rename, type change, derived field, semantic change, and dropped field.

## Write ownership

Each shared table must have one accountable owner and one approved implementation path.

| Area | Owner | Reviewer |
|---|---|---|
| Control and taxi ingestion | Crystal | Gab |
| Weather ingestion and Silver weather | Gab | Bri |
| Taxi-zone ingestion and standardization | Bri | Haze |
| Silver taxi transformations | Bri | Haze |
| Gold fact implementation | Ina | Crystal |
| Gold dimensions | Assigned after Issue #17 | Assigned by review pair |
| Analytics datasets and dashboard | Gab | Bri |
| DQ contract, checks and dashboard | Haze | Ina |
| Integration and final rerun | Ina | Crystal |

Validation jobs may write through the approved `data_quality_results` contract. Haze owns that table’s contract.

Do not upload or process another owner's source without coordinating with them. Every upload must be registered through the approved batch-control process.

## Review pairs

| Author | Reviewer |
|---|---|
| Ina | Crystal |
| Crystal | Gab |
| Gab | Bri |
| Bri | Haze |
| Haze | Ina |

## Development workflow

Start from the latest `main`:

```bash
git switch main
git pull --ff-only
git switch -c <branch-name>
```

Inspect and commit only the intended files:

```bash
git diff
git status
git add <specific-paths>
git commit -m "<clear description>"
git push -u origin <branch-name>
```

The pull request must include:

```text
Closes #<issue-number>
```

It must explain:

- What changed
- Why it changed
- How it was validated
- Which documentation changed
- What remains unverified

Do not merge without the required review.

## Validation gates

Do not build downstream layers on failing upstream layers.

```text
Frame
→ Source Profile
→ Ingestion Design
→ Bronze
→ Bronze Validation
→ Silver
→ Silver Validation
→ Integration
→ Gold
→ Gold Validation
→ Analytics
→ Analytics Validation
→ Dashboards
→ Incremental and Idempotency Proof
```

Critical DQ failures stop publication of dependent trusted layers.

The DQ dashboard may display failed runs. The business dashboard must only use validated Analytics results.

## Incremental and rerun requirements

Every ingestion implementation must explain:

- What identifies a new or changed source
- How processed batches are recorded
- What prevents duplicate ingestion
- When processing state advances
- What happens after a partial failure
- How the same batch can be rerun safely

Processing state advances only after the corresponding load and required validation succeed.

Identical row counts alone do not prove idempotency.

## Security and repository hygiene

Never commit:

- R2 credentials
- Databricks tokens
- Passwords or secret values
- Downloaded source datasets
- Notebook outputs containing sensitive configuration

Commit source code, SQL, documentation, non-secret configuration examples, and validation evidence.
