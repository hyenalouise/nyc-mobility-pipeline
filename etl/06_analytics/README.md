# 06 — Analytics

Analytics publishes one validated dataset per approved business question or
required coverage explanation.

| File | Output | Purpose |
|---|---|---|
| `10_activity_by_time_and_zone.sql` | `activity_by_time_and_zone` | Trip activity by date, hour, and pickup-zone dimensions |
| `20_trip_behavior_by_weather.sql` | `trip_behavior_by_weather`, `trip_weather_coverage` | Weather-associated trip measures and explicit matched/unmatched coverage |
| `30_mobility_patterns_by_zone.sql` | `mobility_patterns_by_zone` | Separate pickup and drop-off mobility patterns by zone |
| `90_validate_analytics.sql` | DQ results | Validates grain, freshness, reconciliation, denominators, and selected outputs |

The business dashboard depends on the Analytics gate and must not refresh from
unvalidated output. Data-quality and pipeline-execution dashboards have separate
operational dependencies.
