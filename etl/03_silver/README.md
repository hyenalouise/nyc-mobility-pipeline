# 03 — Silver

Silver owns explicit typing, standardization, quality disposition, and duplicate
handling without changing the declared business grain.

| File | Source | Purpose |
|---|---|---|
| `10_clean_green_taxi.sql` | Green Taxi | Builds accepted trips and duplicate-collision quarantine with quality flags |
| `20_clean_weather_hourly.sql` | Open-Meteo | Explodes and standardizes the source response to hourly weather grain |
| `30_clean_taxi_zones.sql` | Taxi Zones | Standardizes the complete zone reference snapshot |
| `90_validate_green_taxi.sql` | Green Taxi | Reconciles accepted and quarantined rows, flags, keys, and measures |
| `90_validate_weather_hourly.sql` | Open-Meteo | Checks hourly grain, continuity, ranges, classification, and source lineage |
| `90_validate_taxi_zones.sql` | Taxi Zones | Checks member count, keys, normalized fields, and sentinel members |

A source's Silver transform runs only after its Bronze gate succeeds. Integration
waits for all three Silver gates.

See [`docs/architecture/source-to-target.md`](../../docs/architecture/source-to-target.md).
