# NYC Mobility Pipeline Governance

## Purpose

This document defines the governance model for the NYC Mobility Pipeline.

Its purpose is to ensure that someone outside the project team can:

- Find the data product.
- Understand what it contains.
- Understand who owns it.
- Understand who can modify or deploy it.
- Trace lineage from source files to analytics outputs.
- Understand how data quality is enforced.
- Understand what decisions govern the platform.

This document complements:

- [Naming Conventions](naming_conventions.md)
- [Architecture](architecture.md)
- [Job Setup](job_setup.md)
- [Validation](validation.md)
- [DuckDB-Source Gate](duckdb/source_gate.md)
- [Decisions](decisions.md)

---

# Data Product Overview

The NYC Mobility Pipeline processes transportation and weather datasets and produces curated analytical datasets for reporting and analysis.

Primary source systems:

| Source | Description |
|----------|-------------|
| Green Taxi | NYC Green Taxi trip records |
| Taxi Zones | NYC taxi zone lookup data |
| Open-Meteo | Weather observations and forecasts |

The pipeline is implemented in Databricks and stores data in Unity Catalog under:

```text
ftw-week-08
```

The pipeline follows a layered architecture:

```text
Source
↓
Bronze
↓
Silver
↓
Integration
↓
Gold
↓
Analytics
↓
Dashboards

Control supports every stage through run tracking,
ingestion batches, code revision, gate status,
and data-quality results.
```

---

# Ownership

## Ownership Matrix

| Area | Owner | Contact |
|--------|--------|--------|
| Pipeline | Ina Magno | ina.magno@ftwfoundation.org |
| Pipeline Change Approval | Ina Magno | ina.magno@ftwfoundation.org |
| Green Taxi Source | Briana Capul | briana.capul@ftwfoundation.org |
| Taxi Zones Source | Hazelle Cuevas | hazelle.cuevas@ftwfoundation.org |
| Open-Meteo Source | Hazelle Cuevas | hazelle.cuevas@ftwfoundation.org |
| Databricks Platform | Crystal Manas | crystal.manas@ftwfoundation.org |
| Dashboards & Analytics | Crystal Manas | crystal.manas@ftwfoundation.org |
| Data Quality Framework | Briana Capul | briana.capul@ftwfoundation.org |
| Deployment Execution | Gabrielle Torres | gabrielle.torres@ftwfoundation.org |
| Production Deployment Approval | Gabrielle Torres | gabrielle.torres@ftwfoundation.org |

## Responsibilities

### Pipeline Owner

Responsible for:

- Overall platform direction
- Pipeline approval
- Governance approval
- Architecture decisions

### Source Owners

Responsible for:

- Source-specific business rules
- Source contracts
- Data-quality expectations
- Source documentation

### Platform Owner

Responsible for:

- Databricks workspace
- Job orchestration
- Operational platform configuration
- Workspace administration

### Data Quality Owner

Responsible for:

- Validation rules
- Source-gate policies
- Control-table quality reporting
- Quality-related governance decisions

### Deployment Owner

Responsible for:

- Deployment execution
- Release procedures
- Environment promotion

---

# Access and Permissions

## Governance Principle

Least privilege is the target access model, but the current course environment does not yet fully implement that principle.

At the time of writing:

- The Databricks group `ftw-week-09` has `ALL PRIVILEGES` and `MANAGE` on the full `ftw-week-08` catalog.
- The group can read, modify, and delete objects across the schemas, tables, and source Volume.
- All account users can `BROWSE` Unity Catalog object names, but `BROWSE` does not grant access to table data.
- The project team cannot inspect the membership of `ftw-week-09` from the current workspace.
- The repository does not enforce review through branch protection.
- The planned production bundle folder is under `/Workspace/Shared`, which is writable by workspace users.

These permissions originate from the course environment rather than a project-designed least-privilege model. The grants and deployment controls must be reviewed before production operation.

## Current Access Model

### Data Access

| Capability | Current access |
|---|---|
| Browse Unity Catalog object names | All account users |
| Read, modify, and manage the `ftw-week-08` catalog | Members of the `ftw-week-09` group |
| Inspect membership of `ftw-week-09` | Not available from the project workspace |
| Administer the Databricks workspace | Crystal Manas |

### Repository Access

The five project members are GitHub collaborators with write access:

- Briana Capul
- Ina Magno
- Gabrielle Torres
- Hazelle Cuevas
- Crystal Manas

Pull requests normally name a reviewer and are merged after review and successful CI checks. However, `main` currently has no branch-protection rule, so review and approval are team conventions rather than technically enforced controls.

## Read Access

Read access is intended for approved users requiring access to:

- Source data
- Validation results
- Reports
- Analytics outputs

## Write Access

Write access is restricted to project contributors responsible for maintaining:

- ETL logic
- Validation rules
- Data models
- Documentation

## Deployment Access

| Environment | Current capability | Governance owner |
|---|---|---|
| Development | Any project contributor with Databricks workspace access and the Databricks CLI can deploy a personal `[dev]` job | Gabrielle Torres |
| Production | No production job has been deployed at the time of writing | Gabrielle Torres |
| Production approval | Production deployment approval is assigned to Gabrielle Torres, but the technical approval control is not yet implemented | Gabrielle Torres |

Three development jobs currently exist. Development deployments are separated through the bundle’s development job naming and workspace paths.

The planned production bundle folder is `/Workspace/Shared`. Because workspace users can write to that location in the current environment, production deployment is not yet protected by least-privilege access controls.
## Future Ownership Expansion

Briana Capul owns the overall data-quality framework. [Issue #126](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/126) separately tracks assignment of named owners to individual data-quality checks.

---

# Data Product Inventory

## Source Layer

Source Volume:

```text
`ftw-week-08`.`00-source`.`group_a_source`
```

Sources:

| Source |
|----------|
| Green Taxi |
| Taxi Zones |
| Open-Meteo Weather |

---

## Control Layer

Location:

```text
`ftw-week-08`.`01-control`
```

Tables:

| Table | Purpose |
|---------|---------|
| pipeline_runs | One row per pipeline execution |
| ingestion_batches | One row per received source batch |
| data_quality_results | One row per validation result |
| gate_status | Validation reporting view |

Functions:

| Function | Purpose |
|----------|----------|
| dq_status() | Data quality status calculation |

---

## Bronze Layer

Location:

```text
`ftw-week-08`.`02-bronze`
```

Tables:

| Table | Owner |
|---------|---------|
| green_taxi_raw | Briana Capul |
| taxi_zones_raw | Hazelle Cuevas |
| open_meteo_weather_raw | Hazelle Cuevas |

Purpose:

- Preserve source records
- Record provenance
- Record lineage information

---

## Silver Layer

Location:

```text
`ftw-week-08`.`03-silver`
```

Tables:

| Table | Owner |
|---------|---------|
| green_taxi_clean | Briana Capul |
| green_taxi_quarantine | Briana Capul |
| taxi_zones_clean | Hazelle Cuevas |
| weather_hourly | Hazelle Cuevas |

Purpose:

- Type standardization
- Business rule application
- Quality remediation

---

## Integration Layer

Location:

```text
`ftw-week-08`.`04-integration`
```

Tables:

| Table |
|----------|
| trip_weather_map | Ina Magno |
| trip_zone_map | Ina Magno |

Purpose:

- Resolve trips to weather
- Resolve trips to taxi zones

---

## Gold Layer

Location:

```text
`ftw-week-08`.`05-gold`
```

Tables:

| Table | Owner |
|---|---|
| dim_date | Briana Capul |
| dim_hour | Briana Capul |
| dim_taxi_zone | Briana Capul |
| dim_weather_classification | Briana Capul |
| fact_taxi_trip | Gabrielle Torres |
| fact_weather_hourly | Gabrielle Torres |

Purpose:

- Business-approved dimensional models
- Analytical reporting structures

---

## Analytics Layer

Location:

```text
`ftw-week-08`.`06-analytics`
```

Tables:

| Table | Owner |
|---|---|
| activity_by_time_and_zone | Crystal Manas/Briana Capul |
| mobility_patterns_by_zone | Crystal Manas/Briana Capul |
| trip_behavior_by_weather | Crystal Manas/Briana Capul |
| trip_weather_coverage | Crystal Manas/Briana Capul |

Purpose:

- Business reporting
- Analytical outputs
- Dashboard consumption

---

# Data Lineage

## Green Taxi Lineage

```text
Green Taxi source files
↓
green_taxi_raw
↓
green_taxi_clean
├──→ trip_zone_map
└──→ trip_weather_map
      ↓
fact_taxi_trip
      ↓
activity_by_time_and_zone
mobility_patterns_by_zone
trip_behavior_by_weather
trip_weather_coverage
```

## Taxi Zones Lineage

```text
Taxi Zone lookup
↓
taxi_zones_raw
↓
taxi_zones_clean
├──→ trip_zone_map
└──→ dim_taxi_zone
```

## Weather Lineage

```text
Open-Meteo weather source
↓
open_meteo_weather_raw
↓
weather_hourly
├──→ trip_weather_map
└──→ fact_weather_hourly
```

---

# Traceability

## Lineage Fields

| Field | Purpose |
|---|---|
| `run_id` | Links a data-quality result to its pipeline execution in `pipeline_runs` |
| `batch_id` | Identifies an ingestion attempt or source batch |
| `source_version_id` | Identifies the source version represented by a batch |
| `content_sha256` | Identifies source content using the applicable source-specific hashing method |
| `code_revision` | Identifies the deployed Git revision used by the run |
| `evidence_location` | Records the source path or evidence artifact associated with a validation result |

## Lineage and Evidence Stores

| Object | Purpose |
|---|---|
| `pipeline_runs` | Records pipeline execution metadata |
| `ingestion_batches` | Records source discovery, source versions, processing status, and reload history |
| `data_quality_results` | Records one result per executed data-quality check |
| `gate_status` | Summarizes gate outcomes by layer and dataset |

When source content is reloaded, `ingestion_batches` preserves the earlier processing history and can record the previous successful batch as `SUPERSEDED` under D24.

These lineage fields and control objects support the following trace:

```text
Analytics output
↓
Gold row
↓
Integration mapping
↓
Silver record
↓
Bronze record
↓
Source file
↓
Ingestion batch
↓
Pipeline run
↓
Code revision
```

Since [Issue #148](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/148), the DuckDB source gates execute before the Green Taxi and Taxi Zones Bronze loaders, and since [Issue #125](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/125) before the Open-Meteo loader too.

Each source-gate check writes a row to `data_quality_results` with `layer = 'source'`. This makes source validation visible alongside Bronze, Silver, Integration, Gold, and Analytics validation results.

Source-gate rows do not yet have a Bronze `batch_id` or `source_version_id`, because the source gate runs before Bronze creates those values. The source path is recorded in `evidence_location` instead.

---
# Update Frequency

## Current Operating Model

| Environment | Current state | Schedule |
|---|---|---|
| Development | Runs are manually initiated | The development schedule is paused by design under D27 |
| Production | No production job has been deployed and no production runs have occurred | Once deployed, the planned schedule is weekly on Friday at 11:30 `America/New_York` |

Nineteen observed runs across the three development jobs were reviewed when this document was prepared. Every observed run was initiated manually.

## Deployments

Deployments use the Databricks Asset Bundle and record the deployed Git revision through `code_revision` for auditability and reproducibility.

Development deployment is currently available to project contributors with Databricks workspace and CLI access. Production deployment has not yet been implemented.

---

# Data Quality Governance

## Objective

Data quality controls exist to ensure:

- Completeness
- Accuracy
- Traceability
- Contract compliance
- Reproducibility

---

## Non-Negotiable Controls

### Source Must Not Be Empty

Reason:

Empty deliveries must not proceed into Bronze.

---

### Contract Compliance

Reason:

Sources must match approved source contracts.

---

### Required Columns Must Exist

Reason:

Schema compatibility is required throughout the pipeline.

---

### Source Reconciliation

Reason:

Loaded data must reconcile against source files and expected totals.

### Duplicate Collision Quarantine

Rule:

```text
duplicate collision policy
```

Reason:

Rows that collide under the approved duplicate-identification logic must not silently enter the clean Silver dataset.

Disposition:

```text
QUARANTINE
```

Reference:

[D10](decisions.md#d10)
---

### Trip Distance Validity

Rule:

```text
trip_distance_non_negative
```

Reason:

Negative trip distance represents invalid source data.

Severity:

```text
BLOCK
```

---

### Fare Amount Monitoring

Rule:

```text
fare_amount_non_negative
```

Reason:

Negative fares are intentionally retained and flagged.

Severity:

```text
INFO
```

Reference:

[D15](decisions.md#d15)

[D28](decisions.md#d28)

---

### Data Quality Reporting

Reason:

Every validation result must be observable and auditable.

Validation results are recorded in:

```text
data_quality_results
```
## Open Data-Quality Governance Decisions

[Issue #153](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/153) reviews whether additional source-gate checks should remain blocking.

At the time of writing:

- `trip_distance_non_negative` remains `BLOCK`.
- `fare_amount_non_negative` is `INFO` under D28.
- Other source-gate severities must follow the current approved implementation until a later decision is accepted.
---

# Key Governance Decisions

The following decisions directly affect this data product:

| Decision | Purpose |
|---|---|
| [D10](decisions.md#d10) | Duplicate collisions are kept outside clean data through quarantine |
| [D15](decisions.md#d15) | Quarantine only duplicate decisions
| [D15](decisions.md#d15) | Retention and flagging of negative fares |
| [D17](decisions.md#d17) | Source-level independence between pipeline branches |
| [D25](decisions.md#d25) | Recording deployed code revisions |
| [D27](decisions.md#d27) | Deployment and operational workflow decisions |
| [D28](decisions.md#d28) | Negative fares treated as INFO in the source gate |

---

# Dependency Map

The Data Lineage section above documents the principal source-to-output dependencies.

The authoritative task-level execution order is maintained in:

- `job_setup.md`
- `databricks.yml`

The authoritative table transformation logic is maintained in:

- `etl/`

Changes to dependency relationships must update the implementation and this document in the same pull request.

---

# Governance Maintenance

This document must be updated whenever any of the following change:

- Ownership
- Access permissions
- Deployment procedures
- Source contracts
- Pipeline lineage
- Data-quality policies
- New Gold datasets
- New Analytics outputs
- Governance decisions

Governance information must not exist only in conversations, pull requests, or individual contributor knowledge.

---

# Governance Questions Answered

This document enables a reviewer, operator, or new contributor to answer:

- What is the NYC Mobility data product?
- Where are its source files and governed tables?
- Who owns the pipeline?
- Who owns each source?
- Who owns the platform?
- Who owns data quality?
- Who owns dashboards and analytics?
- Who can deploy?
- Who approves production deployment?
- What downstream datasets depend on each source?
- How can a Gold or Analytics result be traced to its source?
- How often is the pipeline currently run?
- Which data-quality rules are non-negotiable?
- Which governance decisions define current behavior?

Any unanswered ownership or access question must be marked explicitly as `To be confirmed` rather than inferred.

---
Issue: [#120](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/120)
Document owner: Ina Magno  
Governance maintainer: Briana Capul  
Last reviewed: 2026-09-24  

# Related Issues

| Issue | Governance relevance |
|---|---|
| [#115](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/115) | Local pre-ingestion source validation |
| [#120](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/120) | Central governance documentation |
| [#123](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/123) | Bronze-to-DuckDB reconciliation evidence |
| [#126](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/126) | Named ownership of individual data-quality checks |
| [#147](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/147) | Negative-fare source-gate policy alignment |
| [#148](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/148) | Source gates executed before Bronze loaders |
| [#153](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/153) | Review of source-gate blocking policies |
