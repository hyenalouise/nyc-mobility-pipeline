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
Control
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

The pipeline follows the principle of least privilege.

Users should receive only the level of access required for their responsibilities.

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

Current deployment authority:

| Activity | Responsible Party |
|-----------|-----------|
| Execute deployment | Gabrielle Torres |
| Approve production deployment | Gabrielle Torres |

## Future Ownership Expansion

Briana Capul owns the overall data-quality framework. Issue#126 separately
tracks assignment of named owners to individual data-quality checks.

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
| trip_weather_map |
| trip_zone_map |

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

| Table |
|----------|
| dim_date |
| dim_hour |
| dim_taxi_zone |
| dim_weather_classification |
| fact_taxi_trip |
| fact_weather_hourly |

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

| Table |
|----------|
| activity_by_time_and_zone |
| mobility_patterns_by_zone |
| trip_behavior_by_weather |
| trip_weather_coverage |

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

The pipeline supports traceability using the following fields:

| Field | Purpose |
|---------|----------|
| batch_id | Tracks ingestion activity |
| source_version_id | Tracks source version lineage |
| content_sha256 | Tracks source-content identity |
| code_revision | Tracks deployed code version |
| evidence_location | Tracks validation evidence |
| data_quality_results | Tracks quality outcomes |

These fields allow users to trace:

```text
Analytics Output
↓
Gold Row
↓
Integration Data
↓
Silver Data
↓
Bronze Data
↓
Source File
↓
Pipeline Run
↓
Code Revision
```

---

# Update Frequency

## Current Operating Model

At the time of writing:

```text
All pipeline runs have been initiated by a human operator.
```

No automated production schedule is currently documented as the operational standard.

## Deployments

Deployments occur through controlled deployment procedures and record the deployed code version through:

```text
code_revision
```

for auditability and reproducibility.

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

---

# Key Governance Decisions

The following decisions directly affect this data product:

| Decision | Purpose |
|-----------|-----------|
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
Issue: [#120](https://github.com/hyenalouise/nyc-mobility-pipeline)
Document owner: Ina Magno  
Governance maintainer: Briana Capul  
Last reviewed: 2026-09-24  

# Related Issues

| Issue | Governance relevance |
|---|---|
| [#115](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/115) | Local pre-ingestion source validation |
| [#120](https://github.com/hyenalouise/nyc-mobility-pipeline) | Central governance documentation |
| [#123](https://github.com/hyenalouise/nyc-mobility-pipeline) | Bronze-to-DuckDB reconciliation evidence |
| [#126](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/126) | Named ownership of individual data-quality checks |
| [#147](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/147) | Negative-fare source-gate policy alignment |
| [#148](https://github.com/hyenalouise/nyc-mobility-pipeline/issues/148) | Source gates executed before Bronze loaders |
