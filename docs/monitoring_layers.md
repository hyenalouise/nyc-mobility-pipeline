# Monitoring: what we watch, the threshold, and the response

A dashboard shows numbers. It cannot say "duration above eight minutes
usually means the warehouse did not autoscale, check X first." This
document is where that judgment lives: every signal we watch, where it
comes from, the threshold worth acting on, and what to do when it trips.

## Different Layers of Monitoring

``` mermaid
flowchart TD
    M["MONITORING"]
    M --> E
    M --> D

    E["EXECUTION<br/>-----------<br/>Run Status<br/>Fails<br/>Duration<br/>Recency"]
    D["DATA<br/>-----------<br/>Blocking failures<br/>Warnings vs. tolerance<br/>Row-count anomalies<br/>Join coverage"]
```

Kept separate because they answer different questions:

- **Execution** — did it run: status, failures, duration, recency of the runs. Read from `pipeline_runs` and the Pipeline
  Execution dashboard.
- **Data** — is it correct: blocking failures, warnings trending toward
  tolerance, row-count anomalies, join coverage. Read from
  `data_quality_results` and the Data Quality dashboard.


## Execution layer: did it run?

| Signal | Where it's read | Threshold | Response |
|---|---|---|---|
| Run Status | `pipeline_runs.status` via the "Latest Control Gate Status," "Recent Control Gate Runs," and "Success Rate % (Last 20 Runs)" widgets | Anything other than `SUCCESS` (`FAILED`, or `STARTED` past the stuck window below); a success rate meaningfully below 100% over the last 20 runs | Open the run in the Databricks Jobs UI, find the failed task, read its error. The failure email already reached the deployer (dev) or the whole team (prod) — this is about diagnosing, not discovering. |
| Fails | `gate_status` per layer, "Recent Control Gate Runs," "Stuck Runs Detected" (the `no_stuck_runs` check) | Any gate `FAILED`; for stuck runs specifically, any run still `STARTED` more than 6 hours after it began (`stuck_after_hours`, `etl/01_control/90_validate_control.sql`) | This is the gate design working as intended, not an anomaly. Every task depending on the failed gate is skipped by task dependency (`docs/job_setup.md`'s Tasks table). Find the failed gate, then look at its own `FAIL` rows in the Data Quality dashboard for why it blocked. A stuck run usually means a crash or a hung job rather than something genuinely in progress. |
| Duration | "Latest Control Gate Duration," "Average Duration (Last 20 Runs)," "Control Gate Duration Trend" | None set. `docs/job_setup.md` already states no duration threshold is configured. | No automatic action. A person watching the trend chart is how a slow warehouse, a serverless cold start, or a growing dataset gets noticed today. |
| Recency | "Hours Since Last Control Gate Run," "Date of Last Control Gate Run" | None automated. The job runs weekly (Monday 06:00 `America/New_York`), so meaningfully more than 168 hours since the last run, with no known schedule change, is worth a look. | Check the job's schedule is still enabled and not paused in that target (`dev` is paused by design; `prod` should not be). |


## Data layer: is it correct?

| Signal | Where it's read | Threshold | Response |
|---|---|---|---|
| Blocking failures | "Open Issues — Failures & Warnings," "FAIL Checks" counter, "Datasets Validated," "PASS Checks Trend Over Time," "Latest Run Timestamp by Layer" | `severity = 'FAIL'`: any `fail_count > 0` blocks the gate immediately (0% tolerance). The three context widgets carry no threshold of their own — they support diagnosis, not alerting: "Datasets Validated" and "PASS Checks Trend Over Time" show whether a drop in passing checks lines up with the failure, and "Latest Run Timestamp by Layer" shows whether every layer actually ran this cycle. | The gate has already stopped the pipeline. Open the failing row's `details` column, find the check in its source file (`docs/job_setup.md`'s Tasks table maps task key to file), fix the upstream data or logic, rerun. If "Latest Run Timestamp by Layer" shows a layer missing entirely, the pipeline stopped before reaching it — check the earlier gate instead. |
| Warnings trending toward tolerance | "WARN Checks" counter, "Failures By Check Type" | `severity = 'WARN'` checks each carry their own `threshold_pct` — mostly known one-off anomalies at 0.1% (e.g. `dropoff_before_pickup`, `passenger_count_gt_8`, `vendor_id_domain`), a few lifecycle checks at 0.0%. If `fail_pct` exceeds `threshold_pct`, the check becomes `FAIL` and blocks the gate exactly like a hard failure — a WARN is not a free pass, it's a budget. | Watch "Failures By Check Type" for a check's `fail_count` climbing across runs, not just its current value. A WARN sitting near its tolerance is the leading indicator that the next run could block. |
| Row-count anomalies | Reconciliation checks (`source_to_bronze_row_count`, `bronze_to_silver_row_reconciliation`, `row_count_reconciles_to_silver`, etc.), "Data Quality Checks By Dataset," "Failure Checks By Dataset" | `severity = 'FAIL'`, 0% tolerance — any mismatch at any layer boundary blocks | Identify which layer boundary failed from the `layer`/`dataset` columns, then rerun the loader or transform for that stage. To test a fix without touching landing data, use the gate's input-parameter override (`docs/job_setup.md`, #158). |
| Join coverage | Integration gate: `zone_map_covers_every_trip`, `weather_map_covers_every_trip`, `no_ambiguous_weather_match`; unmatched volumes are `INFO` measurements (`pickup_zone_unmatched`, `weather_unmatched`) | Coverage gaps themselves are measured, not failed — an unmatched trip is a real fact (missing source id, unresolved location, etc.), not an error. What blocks is fan-out, a changed grain, or an *ambiguous* weather match. | An unmatched count is expected in normal operation. There is currently no trend view for these `INFO` measurements — see "Not monitored." An ambiguous-match or grain failure blocks the gate the same way a data-layer failure does: treat it as a blocking failure above. |

## Future considerations / What's not monitored

- **Run Retries Signal.** A retry-count column was considered — tracking how many
  times a run had to be retried before succeeding — but was reverted. As
  designed, it depended on a person to actually initiate and label each
  retry consistently, which made the count only as reliable as whoever
  was operating it that day. Worth revisiting if retries move to something
  automated rather than human-triggered.
- **Business layer.** A monitoring layer that watches the Analytics tables
  for anomalies, not just answers business questions, could catch problems
  today's checks miss — for example:
    - `SUM(trip_count)` dropping or spiking sharply vs. a prior run
    - `avg_fare_amount_usd` moving sharply outside its historical range for
      a zone
    - The unattributed-trip share in `trip_weather_coverage` (D20) growing
      over time
    - Zone activity rankings (`activity_rank_overall`, `pickup_rank`)
      churning abruptly between runs
- **Duration-based alerting.** No threshold is configured for run
  duration; a slow run is currently only visible if someone happens to
  look at the trend chart.