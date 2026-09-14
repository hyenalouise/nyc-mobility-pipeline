# Source Profile

This document records each source's schema, volume, date coverage, nulls, duplicate candidates, keys, partitions, and anomalies.

## Status

Source profiling is currently in progress. Listed source URLs are not proof of successful downloads or valid data. Each source must be profiled and supported by recorded evidence before downstream transformations begin.

## File Inventory

For each taxi month and reference snapshot, record the source URL, filename, retrieval time, file size, SHA-256 checksum, file readability, row count, schema, and observed event range.

Compare the March, April, and May schemas before accepting a source contract. Do not assume that filenames guarantee event-date coverage.

| Source | Rows | Schema | Observed Dates | Key Nulls | Duplicate Candidates | Other Anomalies | Evidence |
|---|---:|---|---|---|---|---|---|
| Taxi March 2026 | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Taxi April 2026 | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Taxi May 2026 | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Taxi zones | 265 | `LocationID`, `Borough`, `Zone`, `service_zone` | Snapshot | 0 nulls across all columns | No duplicate `LocationID` values found | Sentinel records found at `LocationID` 264 and 265; special Borough values include `EWR`, `N/A`, and `Unknown` | `notebooks/profile_taxi_zones` |

Profile null rates for every column, full-row equality, candidate-key collisions, within-file and across-file duplicate candidates, unexpected codes, negative or zero measures, missing timestamps, durations, out-of-month events, and pickup and drop-off reference coverage.

The public taxi schema does not establish a unique trip ID. Do not treat `VendorID` as a vehicle or trip key.

## Taxi Zones Source Profile

### Source Details

- **Source file:** `taxi_zone_lookup.csv`
- **Source path:** `/Volumes/ftw-week-08/00-source/group_a_source/taxi_zones/taxi_zone_lookup.csv`
- **File format:** CSV
- **Dataset type:** Reference snapshot
- **Profiling notebook:** `notebooks/profile_taxi_zones`

### Dataset Schema

| Column | Description |
|---|---|
| `LocationID` | Identifier assigned to a taxi zone |
| `Borough` | Borough or special geographic classification |
| `Zone` | Taxi zone name |
| `service_zone` | Taxi service-zone classification |

### Row Count

The Taxi Zones CSV contains **265 rows**.

### Key Validation

`LocationID` was evaluated as the candidate key for the Taxi Zones reference dataset.

The uniqueness query returned no rows, which means:

- No duplicate `LocationID` values were detected.
- All 265 records have distinct `LocationID` values.
- `LocationID` is suitable as the candidate business key for downstream reference joins, subject to the documented sentinel-value policy.

### Null Analysis

| Column | Null Count |
|---|---:|
| `LocationID` | 0 |
| `Borough` | 0 |
| `Zone` | 0 |
| `service_zone` | 0 |

No SQL `NULL` values were found in the four source columns.

Values such as `N/A` and `Unknown` are not SQL nulls. They are explicit source values and must be handled separately during Silver-layer standardization.

### Distinct Borough Values

The following eight distinct `Borough` values were identified:

- `Bronx`
- `Brooklyn`
- `EWR`
- `Manhattan`
- `N/A`
- `Queens`
- `Staten Island`
- `Unknown`

The values `EWR`, `N/A`, and `Unknown` require explicit handling because they are not standard New York City borough names.

These values should not be silently removed or automatically converted to SQL `NULL` until the team agrees on the zone-standardization policy.

### Sentinel Records

Two sentinel or special reference records were identified:

| LocationID | Borough | Zone | service_zone |
|---:|---|---|---|
| 264 | `Unknown` | `N/A` | `N/A` |
| 265 | `N/A` | `Outside of NYC` | `N/A` |

These records represent special conditions rather than ordinary NYC taxi zones:

- `LocationID` 264 represents an unknown or unavailable zone.
- `LocationID` 265 represents a location outside New York City.

The sentinel records must remain identifiable during downstream transformations so unmatched, unknown, and outside-NYC trips are not silently dropped.

### Profiling Findings

- The source file is readable as CSV.
- The file contains 265 rows.
- `LocationID` contains no null values.
- No duplicate `LocationID` values were detected.
- No SQL null values were detected in `LocationID`, `Borough`, `Zone`, or `service_zone`.
- Eight distinct Borough values were identified.
- `EWR`, `N/A`, and `Unknown` are special Borough values requiring a documented standardization rule.
- `LocationID` 264 and 265 are sentinel records.
- Sentinel records must be preserved or intentionally mapped based on the team's approved Silver-layer policy.
- Downstream joins should measure how many taxi records match regular zones, sentinel zones, and no zone record.

### Profiling Conclusion

The Taxi Zones CSV is suitable for use as a reference source for downstream processing.

`LocationID` is unique and has complete coverage within the reference file. However, the dataset contains special values that require documented treatment during Silver-layer cleaning and standardization.

The profiling task does not clean, replace, or remove these values. It records the source behavior so the team can define the transformation policy before building downstream tables.

### Recommended Downstream Rules

The following items require team agreement before Silver processing:

1. Define whether `EWR` will remain a separate geographic classification.
2. Define how `Borough = 'Unknown'` will be standardized.
3. Define how `Borough = 'N/A'` will be represented.
4. Preserve the distinction between `LocationID` 264 and 265.
5. Measure pickup and drop-off join coverage against the Taxi Zones reference.
6. Do not use an inner join if doing so silently removes unknown or unmatched trip locations.
7. Record row counts for matched zones, sentinel zones, and unmatched zone IDs.

## API Profile

Record the endpoint, full non-secret parameters, request window, response status and headers, response checksum, structure, array lengths, units, location or grid metadata, timestamp coverage, duplicates, nulls, empty-response behavior, and error bodies.

Inspect documented throttling behavior and implement bounded retries. Do not deliberately stress the service.

Determine whether pagination applies rather than inventing it.

Generate expected hourly coverage from the requested interval and timezone. Test daylight-saving-time conditions and document the request, model selection, and historical revision policy.

## Exit Gate

The source-profile exit gate passes only when the owner and reviewer agree on:

- Source schemas
- Date coverage
- Source volume
- Candidate keys and identity limitations
- Null and duplicate findings
- Special and sentinel values
- Documented anomalies
- Response contracts
- Evidence locations

Any unresolved issue affecting correctness blocks dependent transformations.