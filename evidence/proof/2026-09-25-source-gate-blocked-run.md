# Proof: a bad delivery refused before Bronze

Issues #158, #148 · captured 2026-09-25

## What was demonstrated

A Green Taxi delivery with 5 negative trip distances was put through the deployed job. The source gate refused it, the Green Taxi loader and everything after it were skipped, and Taxi Zones and Weather still loaded and passed their gates. Bronze, `ingestion_batches` and the landing folder were unchanged afterwards. A normal run with the default inputs then succeeded on all 32 tasks with the same counts.

This is the controlled run #148 asked for and #151 merged without.

## How the bad delivery was staged

The job never read a bad file from the landing folder. #158 made each gate's input a job parameter (`green_taxi_input`, `taxi_zones_input`) whose default is the landing path its loader reads. For this test only the Green Taxi gate was pointed at a separate test folder. The loaders always read the landing folder, so the test files could not be loaded even if the gate had passed.

Test folder: `/Volumes/ftw-week-08/00-source/group_a_source/_test/green_taxi_blocked/`

| File | Change | SHA-256 |
|---|---|---|
| `green_tripdata_2026-03.parquet` | none, byte-identical copy | `60c8bdfc0aa7826a2d6d2a6cca0f0e0dcb2d8aa7336212a45382794bb55b9cc0` |
| `green_tripdata_2026-04.parquet` | 5 rows (positions 3, 4, 9, 12, 14, all 1–5 mile trips) set to `trip_distance = -1`; row count still 44,238 | `b44aea6dedf221d3de7182d46a9115e8dabb622aa1b0eadb83d2530ff9b9e6e8` |
| `green_tripdata_2026-05.parquet` | none, byte-identical copy | `15ff57840a1103d49298ad244492730ca4236b4de0d2758a689ded08bc332752` |

`trip_distance_non_negative` was chosen because it is a BLOCK check that passes on the real data (0 failures) and stays BLOCK under D29. Before uploading, the gate was run locally with DuckDB 1.1.3, the version the job pins: the real files were ACCEPTED, the test copies were BLOCKED, and the only check whose result changed was `trip_distance_non_negative` (0 → 5 failures). Every other check gave the same result on both.

## Run identity

| | |
|---|---|
| Job | `[dev ina_magno] NYC Mobility Pipeline` (id `224133189973974`) |
| Target | `dev` (development mode, schedule paused) |
| Commit | `14297bafbaf86739fb43aab541d03ad05e93cb71` (branch `proof/issue-158-live-blocked-gate-run`) |
| Blocked run | `1057607894632804`, started 12:34 AM with `green_taxi_input` overridden to the test folder |
| Repair of it | repair id `97876694020375`, 12:42 AM |
| Rerun with defaults | `896268451335384`, 12:49–12:55 AM, 5m 53s |
| Earlier attempt, cancelled | `196037847989948`, see "A run that hung" below |

Times are local (UTC+8), as the job UI shows them. `executed_at` values from SQL are UTC, so 16:35 UTC is 12:35 AM local.

## Before and after

    SELECT 'bronze_green_taxi_raw' AS t, COUNT(*) AS n FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
    UNION ALL SELECT 'ingestion_batches', COUNT(*) FROM `ftw-week-08`.`01-control`.ingestion_batches
    UNION ALL SELECT 'dq_source_rows', COUNT(*) FROM `ftw-week-08`.`01-control`.data_quality_results WHERE layer = 'source';

| | Before | After all runs |
|---|---:|---:|
| `bronze_green_taxi_raw` | 133,367 | 133,367 |
| `ingestion_batches` | 8 | 8 |
| `dq_source_rows` | 121 | 201 |

**[Screenshot: before and after query results]**

`green_taxi_raw` has 0 rows whose `source_file` is in `_test`. The three landing files kept their original sizes and modification dates (14 and 19 Sept). The 80 new source rows are one set per gate attempt, broken down below.

## The blocked run

**[Screenshot: timeline of run 1057607894632804, with job parameters showing the override]**

| Tasks | Result |
|---|---|
| `05_source_gate_green_taxi` | FAILED, twice (see the retry below) |
| `10_load_green_taxi` and the 19 tasks after it, including `nyc_mobility_analytics` | UPSTREAM_FAILED, never started |
| `05_source_gate_taxi_zones`, `30_load_taxi_zones`, the Taxi Zones Bronze and Silver gates, `30_clean_taxi_zones` | SUCCESS |
| `20_load_open_meteo`, the Weather Bronze and Silver gates, `20_clean_weather_hourly` | SUCCESS |
| `00_create_control_tables`, `dq_dashboard` (`run_if: ALL_DONE`) | SUCCESS |

11 succeeded, 1 failed, 20 skipped: each source is gated on its own, so a refused Green Taxi delivery stopped Green Taxi and nothing else (D17). Integration and everything after it need all three sources, so they were skipped too.

The gate's output:

    FAIL  trip_distance_non_negative       failures=5        fail_pct=0.0037%
    ...
    Gate result: BLOCKED
    Exit code: 1
    Recorded 16 rows in `ftw-week-08`.`01-control`.data_quality_results

**[Screenshot: 05_source_gate_green_taxi, Original attempt, output and parameters]**

The task's resolved parameters show `--input /Volumes/ftw-week-08/00-source/group_a_source/_test/green_taxi_blocked/*.parquet`, so the job parameter reached the gate. The rows were recorded before the task exited, so the refusal is in `data_quality_results` and not only in the task log.

### Databricks retried the gate on its own

The job sets no retries, but the failed gate ran a second time about a minute later. The task page shows it as "Retry: 1st", launched "By retry scheduler". The retry read the same files and refused them the same way: same check, same 5 rows, exit 1, and its own 16 rows with its own `run_id`.

**[Screenshot: 05_source_gate_green_taxi, Retry 1st, launched by retry scheduler]**

So retrying identical bad input fails identically, which is correct. It also costs a minute and a second set of FAIL rows for a verdict that can't change, so gate tasks should probably not be retried (follow-up below).

## Every gate attempt in the source layer

    SELECT run_id, dataset, COUNT(*) AS checks, COUNT_IF(status = 'FAIL') AS fails, MIN(executed_at) AS executed_at
    FROM `ftw-week-08`.`01-control`.data_quality_results
    WHERE layer = 'source' AND code_revision LIKE '14297ba%'
    GROUP BY ALL ORDER BY executed_at, dataset;

| run_id | dataset | checks | fails | executed_at (UTC) | Attempt |
|---|---|---:|---:|---|---|
| `a2845db5…` | taxi_zones | 8 | 0 | 16:35:47 | blocked run |
| `23a978c2…` | green_taxi | 16 | 1 | 16:35:47 | blocked run, original |
| `3f1abf6d…` | green_taxi | 16 | 1 | 16:36:20 | blocked run, automatic retry |
| `8f98fab0…` | green_taxi | 16 | 0 | 16:42:54 | repair |
| `1a22cf3e…` | taxi_zones | 8 | 0 | 16:50:25 | rerun with defaults |
| `1bfaf823…` | green_taxi | 16 | 0 | 16:50:28 | rerun with defaults |

**[Screenshot: gate attempts query result]**

16 + 16 + 16 + 16 + 8 + 8 = 80 rows, which is the 121 → 201 above. The cancelled run wrote none. Only the two attempts that read the test folder have a FAIL.

## The repair did not keep the override

The plan in #158 expected a repair with nothing changed to fail the same way. It succeeded instead: the repaired gate was ACCEPTED, the loader ran, and all 21 repaired tasks succeeded.

**[Screenshot: 05_source_gate_green_taxi, Repair 1, ACCEPTED with the landing path]**

The repair was started from the CLI, `databricks jobs repair-run 1057607894632804 --rerun-all-failed-tasks`, with no parameters. The run still records the override, but the repaired gate's resolved `--input` was the landing default, `/Volumes/ftw-week-08/00-source/group_a_source/green_taxi/*.parquet`. The gate checked the real files, which pass, and the loader then read the same landing files, found them already loaded, and added nothing. Bronze stayed 133,367 and `ingestion_batches` stayed 8.

That is safe, because the gate and the loader read the same files. It does mean **a repair is not a retry of a test run** unless the override is passed again. The Repair dialog in the UI shows `green_taxi_input` with a remove button where the defaults have an edit button, which suggests the UI carries the override into the repair; the value is cut off in the screenshot, so that part is not confirmed.

**[Screenshot: Repair job run dialog, Parameters]**

The general point, for #121: a repair re-runs the failed tasks and succeeds only if what made them fail has changed. A temporary platform failure can simply be repaired. A BLOCK on bad data fails again on every repair until the data is fixed; here it passed only because the input changed.

## The rerun with defaults

Run `896268451335384`, no overrides: **32 of 32 tasks succeeded**. Both gates were ACCEPTED on the landing files, the loaders added nothing, and every Bronze, Silver, Integration, Gold and Analytics gate passed. The counts are those in "Before and after".

**[Screenshot: timeline of run 896268451335384, all green, default job parameters]**

## A run that hung

The first blocked run, `196037847989948`, gave the right verdicts within a minute (Green Taxi BLOCKED on the same check, Taxi Zones ACCEPTED) but then both gates hung while writing their rows to `data_quality_results`. They wrote nothing, and after 24 minutes the run was cancelled. Weather had already loaded and passed its gates in that run.

**[Screenshot: timeline of run 196037847989948, both gates at 24m, cancelled]**

It was not caused by the override: the Taxi Zones gate hung the same way on its default input, and the same code wrote its rows in about a minute in the runs before and after. It did not happen again in this session. The job has no timeout, so nothing would have stopped it on its own.

## Follow-ups

- **Retries on the gate tasks.** Set `max_retries: 0` on the two source-gate tasks, so a BLOCK verdict is recorded once. Separate issue.
- **A timeout on the gate tasks.** A few minutes would have failed the hung run instead of leaving it running. Separate issue.
- **Repair and overrides.** Noted in `docs/job_setup.md`: to repeat a test, start a new run with the override.
- **The shell quoting** for `--params` is fixed in `966adec`. Unquoted, zsh expands the `*` and stops with `no matches found` before the job starts, which is what happened on the first try.

## What this proves

- A bad delivery is refused by the deployed job before Bronze, and the refusal is recorded in `data_quality_results` under layer `source`.
- The refused source's loader and everything after it are skipped, while the other sources still load and pass their gates.
- Nothing from the refused delivery reached any table, and nothing was duplicated by the repair or the rerun.
- The gate reads the input the job gives it, and the default is what the loader reads.

## What it does not prove

- **`prod` was not used.** Only the `dev` job.
- **Taxi Zones was not refused live.** Only Green Taxi was. The Taxi Zones gate's BLOCK is covered by the tests and the committed `taxi_zones_broken_results.json`, not by a job run.
- **The bad files were never in the landing folder.** A real bad delivery would land there, and every run and repair would fail until it was replaced. That is the case the automatic retry shows, not the repair.

## Cleanup

The test folder stays until #121 is done, in case it is needed for the retry and rerun walkthrough. It cannot be loaded: the loaders only read the landing folder, and the tests fail if a gate's default input stops matching its loader. It will be deleted once Haze confirms.
