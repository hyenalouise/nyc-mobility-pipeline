# 05 — Gold

Gold implements the approved dimensional model. Dimensions are built before
facts, and facts resolve foreign keys against built dimensions and validated
Integration maps.

## Dimensional model

![NYC Mobility Gold star schema](../../docs/architecture/model/nyc_mobility_star_schema.png)

The diagram is maintained with the canonical
[data model](../../docs/architecture/data-model.md). It shows the two fact tables
at their separate grains and the dimensions they share.

| File | Target | Purpose |
|---|---|---|
| `10_dim_date.sql` | `dim_date` | NYC-local calendar members |
| `11_dim_hour.sql` | `dim_hour` | Hours 0–23 |
| `12_dim_taxi_zone.sql` | `dim_taxi_zone` | Validated Taxi Zone members, including documented sentinels |
| `13_dim_weather_classification.sql` | `dim_weather_classification` | Weather-code and precipitation-band combinations |
| `20_fact_weather_hourly.sql` | `fact_weather_hourly` | Hourly weather at coordinate, UTC hour, and model grain |
| `30_fact_taxi_trip.sql` | `fact_taxi_trip` | Accepted trips with deterministic identity and dimensional keys |
| `90_validate_gold.sql` | DQ results | Validates facts, dimensions, keys, relationships, grain, and measures |

Trip and weather measurements remain in separate facts. A trip carries only its
pickup-hour weather-classification key; temperature and precipitation remain at
hourly weather grain.

The implemented layer is covered by the committed full-run and rerun evidence.
See [`docs/architecture/data-model.md`](../../docs/architecture/data-model.md) and
[`evidence/pipeline-runs/README.md`](../../evidence/pipeline-runs/README.md).
