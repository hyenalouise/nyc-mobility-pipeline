# 02 — Bronze

Bronze preserves received source values and adds provenance. It does not silently
clean, deduplicate, or discard source records.

| File | Source | Purpose |
|---|---|---|
| `10_load_green_taxi.sql` | Green Taxi | Loads previously unseen Parquet content and records batch identity |
| `20_load_open_meteo.sql` | Open-Meteo | Merges the approved response window and model into raw weather storage |
| `30_load_taxi_zones.sql` | Taxi Zones | Synchronizes the validated 265-row reference snapshot |
| `90_validate_green_taxi.sql` | Green Taxi | Reconciles source files, Bronze rows, provenance, schema, and known traits |
| `90_validate_open_meteo_weather.sql` | Open-Meteo | Validates response identity, hourly alignment, coverage, and observations |
| `90_validate_taxi_zones.sql` | Taxi Zones | Validates count, required columns, keys, sentinel members, and reconciliation |

Each loader waits for its matching pre-Bronze source gate. A source then advances
only after its own Bronze gate passes. The other source lanes may continue
independently.

See [`docs/data/ingestion.md`](../../docs/data/ingestion.md) and
[`docs/data/validation.md`](../../docs/data/validation.md).
