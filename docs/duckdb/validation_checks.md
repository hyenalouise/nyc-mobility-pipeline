# Pre-Bronze Source Validation Checks

The framework (severity model, PASS/WARN/FAIL/INFO statuses, the command line
itself) is shared across sources. The individual checks below are not --
each source's business rules are different, so each has its own check list.

## Green Taxi (17 checks)

1. source_readable
2. row_count_not_empty
3. row_count_floor
4. required_columns
5. pickup_timestamp_not_null
6. dropoff_timestamp_not_null
7. trip_distance_non_negative -- BLOCK. A negative distance has no legitimate meaning, unlike a negative fare, so it points to a broken delivery (D29).
8. fare_amount_non_negative -- INFO: counted and reported, never blocking.
   Negative fares are retained and flagged in Silver (D15), so refusing a
   delivery for them would contradict the rest of the pipeline (D28).
9. dropoff_before_pickup -- WARN at 0.1%. The same condition as Silver's dropoff_before_pickup_flag (D29).
10. zero_length_trip -- INFO: dropoff at the same instant as pickup. Retained and flagged in Silver as implausible_duration_flag, so counted, never blocking (D29).
11. expected_month_coverage
12. passenger_count_gt_8 -- WARN at 0.1%. The worst month so far was 0.0156% (D29).
13. vendor_id_domain
14. payment_type_domain
15. ratecode_id_domain
16. location_id_range
17. full_source_row_duplicate

## Taxi Zones (8 checks)

Taxi Zones is a small, static reference snapshot (one row per LocationID),
not a per-trip fact table, so it has no reporting window and no per-trip
business rules. Its checks focus on the one thing everything downstream
depends on: LocationID being a clean, unique join key.

1. source_readable
2. row_count_not_empty
3. row_count_floor (265 -- the full snapshot, not a nominal minimum)
4. required_columns
5. location_id_not_null
6. location_id_unique
7. location_id_valid_integer -- catches a non-numeric LocationID, which
   passes not-null and uniqueness on its own since a string is still
   non-null and still unique
8. borough_not_null

The source gate validates local inputs supplied through the `--input`
parameter, for either source, selected with `--source green_taxi` or
`--source taxi_zones` (default: `green_taxi`). The validation suite does
not download source files and does not require network connectivity or
credentials for either source.