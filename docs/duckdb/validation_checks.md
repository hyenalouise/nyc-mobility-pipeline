# Pre-Bronze Source Validation Checks

The framework (severity model, PASS/WARN/FAIL statuses, the command line
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
8. fare_amount_non_negative
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

## Weather (14 checks)

Weather is a request-window source landed as one JSON response, not a flat
file, so its contract has no `row_count_floor` or fixed `reporting_window`
the way Green Taxi's does -- a landed response can cover any span. Its
checks fall into two tiers: whether the response has the right shape at
all, and whether the hourly series inside it is internally consistent.

1. source_readable
2. row_count_not_empty -- at least one response object landed
3. required_columns -- top-level `latitude`, `longitude`, `elevation`,
   `hourly` all present, checked by name against a plain `SELECT *` so a
   genuinely absent field is reported here rather than crashing the gate
4. required_hourly_fields -- `hourly`'s own `time`, `temperature_2m`,
   `precipitation`, `weather_code` all present; a distinct failure mode
   from #3, since `hourly` existing does not guarantee its own fields do
5. hourly_series_not_empty -- `hourly` present but with empty arrays is a
   different malformation than `hourly` missing entirely (#3)
6. hourly_time_not_null
7. temperature_2m_not_null
8. precipitation_not_null
9. weather_code_not_null
10. no_duplicate_hourly_timestamps -- every `hourly.time` value at most
    once per response
11. hourly_series_has_no_gaps -- observed row count vs. the hour-span
    implied by the response's own min/max `hourly.time`; this and #10 are
    deliberately separate checks, since a duplicate that exactly replaces
    a missing hour leaves the count-vs-span arithmetic looking correct
12. temperature_plausible_range -- -50 to 60°C
13. precipitation_non_negative
14. weather_code_known_domain -- against the full WMO code table
    Open-Meteo documents (the same 28 codes Silver maps to categories)

Checks 12-14 block at 0% with no tolerance, deliberately matching the
Bronze (`90_validate_open_meteo_weather.sql`) and Silver
(`90_validate_weather_hourly.sql`) gates, which FAIL on the same three
conditions and stop the job. Silver's transform keeps these rows, but
Silver's own gate does not let them through, so a looser pre-Bronze gate
would only move the block later, to after the file has landed.

The source gate validates local inputs supplied through the `--input`
parameter, for any of the three sources, selected with `--source
green_taxi`, `--source taxi_zones`, or `--source weather` (default:
`green_taxi`). The validation suite does not download source files and
does not require network connectivity or credentials for any source.