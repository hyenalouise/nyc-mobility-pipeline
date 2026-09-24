# Proof: a bad delivery refused before Bronze

Issues #158, #148 · captured 2026-09-25

## What was demonstrated

A Green Taxi delivery with 5 negative trip distances was put through the deployed job. The source gate refused it, the Green Taxi loader and everything after it were skipped, and Taxi Zones and Weather still loaded and passed their gates. Bronze, `ingestion_batches` and the landing folder were unchanged afterwards. A normal run with the default inputs then succeeded on all 32 tasks with the same counts.

This is the controlled run #148 asked for and #151 merged without.

## How the bad delivery was staged

The job never read a bad file from the landing folder. #158 made each gate's input a job parameter (`green_taxi_input`, `taxi_zones_input`) whose default is the landing path its loader reads. For this test only the Green Taxi gate was pointed at a separate test folder. The loaders always read the landing folder, so the test files could not be loaded. If the gate had passed, though, its loader would have loaded the landing folder, which this run did not check. Review found that gap, and it is now closed: see "An override run can no longer load" below.

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

<img width="1059" height="828" alt="image" src="https://github.com/user-attachments/assets/aae0fce5-94d2-4bed-b5a3-4056987d954b" />

`green_taxi_raw` has 0 rows whose `source_file` is in `_test`. The three landing files kept their original sizes and modification dates (14 and 19 Sept). The 80 new source rows are one set per gate attempt, broken down below.

## The blocked run
<img width="1514" height="1026" alt="image" src="https://github.com/user-attachments/assets/d4c64c8d-de77-4bc2-86da-58d29bfb4be6" />

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

<img width="1520" height="1003" alt="image" src="https://github.com/user-attachments/assets/00854868-20df-41de-85de-ba616b618471" />

The task's resolved parameters show `--input /Volumes/ftw-week-08/00-source/group_a_source/_test/green_taxi_blocked/*.parquet`, so the job parameter reached the gate. The rows were recorded before the task exited, so the refusal is in `data_quality_results` and not only in the task log.

### Databricks retried the gate on its own

The job sets no retries, but the failed gate ran a second time about a minute later. The task page shows it as "Retry: 1st", launched "By retry scheduler". The retry read the same files and refused them the same way: same check, same 5 rows, exit 1, and its own 16 rows with its own `run_id`.

<img width="1517" height="1001" alt="image" src="https://github.com/user-attachments/assets/ae80ad9d-1ffa-44cb-99cf-d1a4c5e8399e" />

So retrying identical bad input fails identically, which is correct. **This retry is the evidence for #158's "the repair fails the same way" step**, not the repair below: it is the one attempt that re-ran on the same bad input. It also costs a minute and a second set of FAIL rows for a verdict that can't change, so gate tasks should probably not be retried (follow-up below).

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

<img width="1059" height="425" alt="image" src="https://github.com/user-attachments/assets/a50b62b5-ef5c-44f6-ae1c-4c558dbc25db" />

16 + 16 + 16 + 16 + 8 + 8 = 80 rows, which is the 121 → 201 above. The cancelled run wrote none. Only the two attempts that read the test folder have a FAIL.

## The repair did not keep the override

The plan in #158 expected a repair with nothing changed to fail the same way. It succeeded instead: the repaired gate was ACCEPTED, the loader ran, and all 21 repaired tasks succeeded.

<img width="1512" height="1004" alt="image" src="https://github.com/user-attachments/assets/ab79f40f-755b-4aaa-8208-dbebbea63b60" />

The repair was started from the CLI, `databricks jobs repair-run 1057607894632804 --rerun-all-failed-tasks`, with no parameters. The run still records the override, but the repaired gate's resolved `--input` was the landing default, `/Volumes/ftw-week-08/00-source/group_a_source/green_taxi/*.parquet`. The gate checked the real files, which pass, and the loader then read the same landing files, found them already loaded, and added nothing. Bronze stayed 133,367 and `ingestion_batches` stayed 8.

That is safe, because the gate and the loader read the same files. It does mean **a repair is not a retry of a test run** unless the override is passed again. The Repair dialog in the UI shows `green_taxi_input` with a remove button where the defaults have an edit button, which suggests the UI carries the override into the repair; the value is cut off in the screenshot, so that part is not confirmed.

<img width="1357" height="574" alt="image" src="https://github.com/user-attachments/assets/0096f466-8328-4818-9549-0e5acdd1cb64" />

The general point, for #121: a repair re-runs the failed tasks and succeeds only if what made them fail has changed. A temporary platform failure can simply be repaired. A BLOCK on bad data fails again on every repair until the data is fixed; here it passed only because the input changed.

## The rerun with defaults

Run `896268451335384`, no overrides: **32 of 32 tasks succeeded**. Both gates were ACCEPTED on the landing files, the loaders added nothing, and every Bronze, Silver, Integration, Gold and Analytics gate passed. The counts are those in "Before and after".

<img width="1512" height="959" alt="image" src="https://github.com/user-attachments/assets/a6d3ef5b-829a-49e6-bb06-4faa9670848d" />

## A run that hung

The first blocked run, `196037847989948`, gave the right verdicts within a minute (Green Taxi BLOCKED on the same check, Taxi Zones ACCEPTED) but then both gates hung while writing their rows to `data_quality_results`. They wrote nothing, and after 24 minutes the run was cancelled. Weather had already loaded and passed its gates in that run.

<img width="1515" height="932" alt="image" src="https://github.com/user-attachments/assets/b1b4579c-dd11-4563-9b85-ebb1c565fcbe" />

It was not caused by the override: the Taxi Zones gate hung the same way on its default input, and the same code wrote its rows in about a minute in the runs before and after. It did not happen again in this session. The job has no timeout, so nothing would have stopped it on its own.

## Against the #158 test plan

| Expected in #158 | Result | Evidence |
|---|---|---|
| The gate FAILS with `trip_distance_non_negative` in layer `source` | ✅ | The blocked run, both attempts |
| The loader and everything after it are skipped; Zones and Weather load | ✅ | 20 skipped, 11 succeeded |
| Bronze stays 133,367, no new `ingestion_batches` row, Silver and Gold unchanged | ✅ | "Before and after" |
| Retrying the same bad input fails the same way | ✅ | The **automatic retry** (attempt 2), same check and same 5 rows |
| A repair with nothing changed fails the same way | ❌ as planned, ✅ in substance | The CLI repair dropped the override and checked the landing files. That is **operational evidence about repairs**, not proof of this step; the automatic retry covers it |
| A rerun with the defaults succeeds with no duplicates | ✅ | 32/32, same counts |

## An override run can no longer load

Bri's review of #159 pointed out what this run did not test: an override points only the gate at the test folder, and the loader still reads the landing folder. Had the test input **passed**, the loader would have loaded landing files this run never checked. The docs warned against that, but nothing stopped it.

#159 now stops it. Each gate is also given the exact path its loader reads (`--load-input`). When its `--input` differs, the gate still runs and records every check, then fails its task with exit 4 (`EXIT_TEST_INPUT`) even if the verdict is ACCEPTED. The loader and everything after it are skipped, as in this blocked run. Normal and scheduled runs, where the two paths are the same, are unchanged.

Tests cover both sides: a test input that passes exits 4 and is still recorded, a blocked one keeps exit 1, the real input still exits 0, and the job test fails if any gate's `--load-input` or default input is not exactly its loader's path.

### Live check of the fix

Deployed commit `294f24818052bb6fc7d6dcd18193538a0e3a2621` to the same `dev` job (33 tasks now, with the weather gate from #152) and ran it twice.

**Run A, `1087187638708963`: a test input that passes.** `green_taxi_input` was overridden with one real landing file, `green_tripdata_2026-03.parquet`, while the loader reads the whole folder. Nothing was staged or uploaded.

| Task | Result |
|---|---|
| `05_source_gate_green_taxi` | ACCEPTED, then `Test input: this run checked [...green_tripdata_2026-03.parquet], but the loader reads .../green_taxi/*.parquet. Nothing will be loaded.`, exit 4, 17 rows recorded. Retried once by Databricks, same result |
| `10_load_green_taxi` and the 19 tasks after it | UPSTREAM_FAILED, never started |
| Zones and Weather: gates, loads, Bronze and Silver gates, cleans; plus control setup and `dq_dashboard` | 12 succeeded |

**Run A timeline, with the green_taxi_input override in Job parameters**
<img width="1422" height="1142" alt="image" src="https://github.com/user-attachments/assets/7fd5c364-a04e-4f1f-80c1-f5cc552a57e4" />


**Run A, 05_source_gate_green_taxi, Original attempt: Test input line, exit 4, --input and --load-input**
<img width="1428" height="1139" alt="image" src="https://github.com/user-attachments/assets/ac692b93-c9d0-4bfe-9f23-60eddea94b22" />


**Run A, 05_source_gate_green_taxi, Retry 1st: same result**
<img width="1411" height="1136" alt="image" src="https://github.com/user-attachments/assets/9faabeb5-f63b-48e7-8cee-113484fba801" />


This is the case the first run could not show: the checks passed, and the loader still did not run.

**Run B, `1034205573179763`: a normal run, no overrides.** 33 of 33 tasks succeeded. All three gates were ACCEPTED with exit 0 and no test-input line. It is also the first live run of the weather gate from #152: 15 checks, all PASS.

**Run B timeline, all green, default job parameters**
<img width="1436" height="1141" alt="image" src="https://github.com/user-attachments/assets/9ffd21e6-81e7-413b-a010-a1e1d04a8c11" />


**Run B, 05_source_gate_weather output**
<img width="1446" height="1133" alt="image" src="https://github.com/user-attachments/assets/01a341d8-25a3-48f7-8ed2-55ad995aa937" />


**Counts**, same query as "Before and after":

| | Before Run A | After Run B |
|---|---:|---:|
| `bronze_green_taxi_raw` | 133,367 | 133,367 |
| `ingestion_batches` | 8 | 8 |
| `dq_source_rows` | 361 | 458 |

Silver `green_taxi_clean` and Gold `fact_taxi_trip` stayed 133,353. The 97 new source rows are one set per gate attempt on this commit, all with 0 FAILs: Run A recorded 15 + 17 + 8 + 17 (the retry), Run B 15 + 8 + 17.
<img width="820" height="815" alt="image" src="https://github.com/user-attachments/assets/41a366be-e02f-4214-9849-451a402abc08" />
<img width="834" height="468" alt="image" src="https://github.com/user-attachments/assets/697b91a1-bd9a-4761-a864-432919e34298" />


### Two attempts that hung first

Runs `768975900287724` (03:53) and `716231120415734` (04:05) printed the same verdicts, including the test-input line and exit 4, but all three gates then hung before recording, like `196037847989948` earlier. Both were cancelled after about 10 minutes; they wrote nothing and loaded nothing.

The task's driver log explains it. The gate's Python ran on serverless compute, but the Spark service it records through never came up:

    BAD_REQUEST: The cluster is in unexpected state Pending, while waiting for the cluster to become available. This is expected for new sessions. Please try again. [state=PENDING]

That line repeats every few seconds until the cancel, the task shows no queries, and the query history is empty. It is a Databricks capacity problem for the Spark part of a serverless Python task, not the gate or its input: Zones and Weather hung the same way on their default inputs. The SQL warehouse, which runs every other task, was unaffected.

## Follow-ups

- **Retries on the gate tasks.** Set `max_retries: 0` on the source-gate tasks, so a BLOCK verdict is recorded once. Separate issue.
- **A timeout on the gate tasks.** Three runs hung on the Spark service staying Pending (see "Two attempts that hung first"). A timeout would fail them in minutes instead of leaving them running. Separate issue.
- **Recording without Spark.** The gate only needs Spark to write its rows. Writing them through the SQL warehouse instead would remove the dependency that hung. Separate issue.
- **Repair and overrides.** Noted in `docs/job_setup.md`: to repeat a test, start a new run with the override.
- **The shell quoting** for `--params` is fixed in `966adec`. Unquoted, zsh expands the `*` and stops with `no matches found` before the job starts, which is what happened on the first try.

## What this proves

- A bad delivery is refused by the deployed job before Bronze, and the refusal is recorded in `data_quality_results` under layer `source`.
- The refused source's loader and everything after it are skipped, while the other sources still load and pass their gates.
- Nothing from the refused delivery reached any table, and nothing was duplicated by the repair or the rerun.
- The gate reads the input the job gives it. In a normal run that input is exactly what the loader reads, which the tests pin.
- In the first run, an override checked something other than what the loader reads, which was safe only because the gate blocked. Since #159, a gate on an override input can't let its loader run at all: Run A shows a passing test input stopping the loader, and Run B shows normal runs unchanged.

## What it does not prove

- **`prod` was not used.** Only the `dev` job.
- **Taxi Zones was not refused live.** Only Green Taxi was. The Taxi Zones gate's BLOCK is covered by the tests and the committed `taxi_zones_broken_results.json`, not by a job run.
- **The bad files were never in the landing folder.** A real bad delivery would land there, and every run and repair would fail until it was replaced. That is the case the automatic retry shows, not the repair.

## Cleanup

The test folder stays until #121 is done, in case it is needed for the retry and rerun walkthrough. It cannot be loaded: the loaders only read the landing folder, and the tests fail if a gate's default input stops matching its loader. It will be deleted once Haze confirms.
