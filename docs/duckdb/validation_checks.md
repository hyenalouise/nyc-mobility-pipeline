# Pre-Bronze Source Validation Checks

The framework (severity model, PASS/WARN/FAIL/INFO statuses, the command line
itself) is shared across sources. The individual checks below are not --
each source's business rules are different, so each has its own check list.

## Green Taxi (16 checks)

1. source_readable
2. row_count_not_empty
3. row_count_floor
4. required_columns
5. pickup_timestamp_not_null
6. dropoff_timestamp_not_null
7. trip_distance_non_negative
8. fare_amount_non_negative -- INFO: counted and reported, never blocking.
   Negative fares are retained and flagged in Silver (D15), so refusing a
   delivery for them would contradict the rest of the pipeline (D28).
9. dropoff_after_pickup
10. expected_month_coverage
11. passenger_count_gt_8
12. vendor_id_domain
13. payment_type_domain
14. ratecode_id_domain
15. location_id_range
16. full_source_row_duplicate

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

## Weather (15 checks)

Weather is a request-window source landed as one JSON response, not a flat
file. Its contract has no `row_count_floor`; instead `requested_window`
records the dates the response was requested for, pinned to the
`weather_requested_*` variables in `etl/02_bronze/20_load_open_meteo.sql`.
Its checks fall into two tiers: whether the response has the right shape at
all, and whether the hourly series inside it is complete and consistent.

1. source_readable
2. row_count_not_empty -- at least one response object landed
3. required_columns -- top-level `latitude`, `longitude`, `elevation`,
   `hourly` all present, checked by name against a plain `SELECT *` so a
   genuinely absent field is reported here rather than crashing the gate
4. required_hourly_fields -- `hourly`'s own `time`, `temperature_2m`,
   `precipitation`, `weather_code` all present, read from `hourly`'s keys
   so the failure names exactly which fields are missing; a distinct
   failure mode from #3, since `hourly` existing does not guarantee its
   own fields do. If they are all present but cannot be read as parallel
   arrays, `hourly_fields_are_arrays` fails instead, so a type problem is
   never reported as a missing field
5. hourly_series_not_empty -- `hourly` present but with empty arrays is a
   different malformation than `hourly` missing entirely (#3)
6. hourly_time_valid -- every `hourly.time` present and parseable as a
   timestamp; an unreadable value would otherwise drop out of #10-12
7. temperature_2m_not_null
8. precipitation_not_null
9. weather_code_not_null
10. no_duplicate_hourly_timestamps -- every `hourly.time` value at most
    once per response
11. hourly_series_has_no_gaps -- observed row count vs. the hour-span
    between the response's own first and last `hourly.time`; catches a
    hole in the middle
12. hourly_series_covers_requested_window -- row count equals the
    requested days x 24 (Bronze's `hourly_volume` rule), and the first and
    last hour are the window's start 00:00 and end 23:00; catches a file
    cut short at either end, which #11 cannot see. #10 stays separate from
    #11 and #12, since a duplicate that exactly replaces a missing hour
    leaves both counts looking correct
13. temperature_plausible_range -- -50 to 60°C, pinned to the Bronze gate
14. precipitation_non_negative
15. weather_code_known_domain -- against the full WMO code table
    Open-Meteo documents (the same 28 codes Silver maps to categories),
    compared as a number so a non-integer code like 1.4 does not round
    into the list

Checks 12-15 block at 0% with no tolerance, deliberately matching the
Bronze (`90_validate_open_meteo_weather.sql`) and Silver
(`90_validate_weather_hourly.sql`) gates, which FAIL on the same
conditions and stop the job. Silver's transform keeps these rows, but
Silver's own gate does not let them through, so a looser pre-Bronze gate
would only move the block later, to after the file has landed.

The source gate validates local inputs supplied through the `--input`
parameter, for any of the three sources, selected with `--source
green_taxi`, `--source taxi_zones`, or `--source weather` (default:
`green_taxi`). The validation suite does not download source files and
does not require network connectivity or credentials for any source.