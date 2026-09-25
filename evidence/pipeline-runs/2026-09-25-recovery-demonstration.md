# Proof: detect, diagnose, assess, fix, rerun, verify

Issue #121 · captured 2026-09-25

## What was demonstrated

A Green Taxi delivery with 5 negative trip distances was pointed at by the
deployed job's Green Taxi source gate. The gate refused it, the Green Taxi
loader and everything after it were skipped, and Taxi Zones and Weather
still loaded and passed their gates. Bronze, `ingestion_batches` and the
landing folder were unchanged afterwards. Databricks automatically retried
the same failed task once, and it failed identically. A rerun with the
default (real) inputs then succeeded on all 33 tasks with the same before
counts, confirming the rerun was a safe no-op rather than a duplicate load.

This exercises the full loop the runbook in `docs/data/ingestion.md` describes:

```text
Detect → Diagnose → Assess impact → Fix → Rerun → Verify
```

## How the bad delivery was staged

Copies of the three real Green Taxi files, with 5 April rows set to
`trip_distance = -1`, staged outside the landing folder at
`/Volumes/ftw-week-08/00-source/group_a_source/_test/green_taxi_blocked/`.

The override was passed as a job parameter (`green_taxi_input`), which lets
a gate be pointed at a test delivery without a bad file ever touching the
shared landing folder. Because each gate is also given the exact path its
loader reads (`--load-input`) independently of the override, an overridden
run cannot let its loader run even if the test input happened to pass — it
only matters here because this input was designed to fail.

## Run identity

| | |
|---|---|
| Job | `[dev] NYC Mobility Pipeline` (id `178459730086434`) |
| Target | `dev` (development mode, schedule paused) |
| Detect / Diagnose run | `375998903023945`, `green_taxi_input` overridden to the test folder |
| Retry (automatic) | Task run `263912288053109`, launched "By retry scheduler" |
| Rerun (Fix applied, defaults restored) | `822445838947042`, 23m 15s, 33/33 succeeded |

## 1. Detect

Run `375998903023945` was started with:

```bash
databricks bundle run NYC_Mobility_Pipeline --target dev \
  --params 'green_taxi_input=/Volumes/ftw-week-08/00-source/group_a_source/_test/green_taxi_blocked/*.parquet'
```

`05_source_gate_green_taxi` failed. Every task depending on it
(`10_load_green_taxi` and everything downstream in that branch) showed
**Upstream failed** and never ran. `05_source_gate_taxi_zones` and
`05_source_gate_weather` both ran on their real defaults and succeeded, so
the refusal stayed scoped to the one source that was actually overridden
(D17).

<img width="657" height="312" alt="Job run details for the Detect run, showing the failed task, launch by retry scheduler, and resolved parameters" src="https://github.com/user-attachments/assets/91962275-b708-42f3-bcfe-e40d21b1abe3" />

## 2. Diagnose

```text
DUCKDB PRE-INGESTION GATE: green_taxi
========================================================================
...
FAIL  trip_distance_non_negative       failures=5        fail_pct=0.0037%
INFO  fare_amount_non_negative         failures=384      fail_pct=0.2879%
WARN  dropoff_before_pickup            failures=1        fail_pct=0.0007%
INFO  zero_length_trip                 failures=99       fail_pct=0.0742%
WARN  expected_month_coverage          failures=11       fail_pct=0.0082%
WARN  passenger_count_gt_8             failures=13       fail_pct=0.0097%
...
========================================================================

Gate result: BLOCKED
Test input: this run checked ['/Volumes/ftw-week-08/00-source/group_a_source/_test/green_taxi_blocked/*.parquet'],
but the loader reads /Volumes/ftw-week-08/00-source/group_a_source/green_taxi/*.parquet. Nothing will be loaded.
Exit code: 1
Recorded 17 rows in `ftw-week-08`.`01-control`.data_quality_results
```

Only `trip_distance_non_negative` is `FAIL`; every neighboring check is
`PASS`, `WARN`, or `INFO`. The diagnosis is specific: 5 rows with a
negative trip distance, not a general "the file looks wrong."

Databricks also retried this same task once on its own ("By retry
scheduler", task run `263912288053109`), with no retry configured on the
job. It read the same test folder and failed the same way: same check,
same 5 rows, exit 1. A retry of identical bad input failing identically is
the correct, expected outcome — a BLOCK on bad data cannot change on retry
alone.

<img width="1282" height="837" alt="The gate's own printed output, showing FAIL on trip_distance_non_negative with 5 failures, and every neighboring check PASS, WARN, or INFO" src="https://github.com/user-attachments/assets/687f6421-addf-4adc-bafd-bf23f9e1081b" />

## 3. Assess impact

```sql
SELECT COUNT(*) FROM `ftw-week-08`.`02-bronze`.green_taxi_raw;
SELECT COUNT(*) FROM `ftw-week-08`.`01-control`.ingestion_batches;
```

| | Before this run | After the blocked run and its retry |
|---|---:|---:|
| `green_taxi_raw` | 133,367 | 133,367 |
| `ingestion_batches` | 8 | 8 |

<img width="449" height="370" alt="green_taxi_raw row count, 133367" src="https://github.com/user-attachments/assets/35e3c90a-819d-4483-bfc0-eab2db7b5553" />
<img width="678" height="295" alt="ingestion_batches row count, 8" src="https://github.com/user-attachments/assets/d8266375-d66b-4ebf-b516-beec53ed533f" />

Nothing from the test folder reached Bronze, and no new ingestion batch was
registered for it. The previously-published good data was never touched.
Taxi Zones and Weather, not overridden in this run, loaded and passed
their gates normally, confirming the outage stayed scoped to Green Taxi
alone.

## 4. Fix

The override was not passed on the next run, so the gate checked the real
landing folder again — the same action a real bad delivery would need
(replace or correct the file) rather than a retry of the same test input.
No code or configuration changed.

## 5. Rerun

```bash
databricks bundle run NYC_Mobility_Pipeline --target dev
```

Run `822445838947042`: **33 of 33 tasks succeeded**, in 23m 15s. All three
source gates were `ACCEPTED` on their real landing inputs, and every
Bronze, Silver, Integration, Gold and Analytics gate passed. The resolved
job parameters for this run carried no override on any of the three
source inputs, confirming this was a plain default run, not another test.

<img width="1812" height="693" alt="Full 33-task list for the rerun, all Succeeded, with the resolved job parameters (code_revision and the three unmodified source input paths) shown on the right" src="https://github.com/user-attachments/assets/bb0f8a4c-f75e-4765-958e-ef3227fd6755" />

<img width="1455" height="806" alt="Timeline view of the rerun showing the 33 tasks executing, with Green Taxi, Weather and Taxi Zones running in parallel before converging at Integration, then Gold, then Analytics" src="https://github.com/user-attachments/assets/969b0205-2106-48a3-881b-85bf9e67c1f8" />

## 6. Verify

| | Before | After the rerun |
|---|---:|---:|
| `green_taxi_raw` | 133,367 | 133,367 |
| `ingestion_batches` | 8 | 8 |

Identical counts. The rerun did not duplicate the Green Taxi data already
correctly loaded before this exercise began — it reconfirmed the existing
content was already current and added nothing new, the expected, safe
outcome for a rerun against unchanged real files.

## What this proves

- A deliberately bad delivery is refused before Bronze, and the refusal
  names the specific failing check and the specific affected rows.
- An automatic retry of the identical bad input fails identically, which
  is the correct, expected behavior for a BLOCK — not a bug to work
  around.
- The refused source's loader and everything after it are skipped, while
  unrelated sources continue and pass independently (D17).
- Nothing from a refused delivery reaches any table, and a subsequent
  rerun with the real, unchanged input reproduces the same counts rather
  than duplicating anything.
- Detect, Diagnose, Assess impact, Fix, Rerun and Verify are each backed by
  a real run ID, a real query result, or the gate's own printed evidence.

## What this does not prove

- **Backfill was not executed live.** Doing so safely would require either
  a historical period genuinely missing from Bronze, or placing a test
  file in the real landing folder — the second of which this project
  deliberately avoids. Backfilling an older month also requires widening
  the declared reporting window in both the source gate's contract and
  the Bronze validation gate first (see the runbook in
  `docs/data/ingestion.md`), since both currently block anything outside
  March–May 2026. This demonstration exercises Retry and Rerun only.
- **`prod` was not used.** Only the `dev` job: a personal sandbox is the
safe place to force a failure on purpose.
