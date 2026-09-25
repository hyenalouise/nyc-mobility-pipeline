# Proof: a deployed run, traceable to the commit that produced it

Issues #111, #112, #114, #117 · captured 2026-09-23

## What was demonstrated

The pipeline was deployed from `main` as a Databricks Asset Bundle and run end to end. Every gate passed, and every result row carries the commit that
produced it, supplied by the deploy, not typed by anyone.

Before this, `data_quality_results.code_revision` recorded the string `'UNSET'` on every row. An output could be traced to its source file and its run, but not to the code that built it.

## Run identity

| | |
|---|---|
| Job | `[dev ina_magno] NYC Mobility Pipeline` (id `224133189973974`) |
| Run id | `358447361381763` |
| Workspace | `dbc-cd77c839-62eb` |
| Target | `dev` (development mode) |
| Commit | `bddd28316073aefd2d9dadf66f168ec85bac4d82` |
| Warehouse | `bd9af8d40007e504`, Serverless Starter, 2X-Small |
| Started | 2026-09-23 14:20:17 |
| Ended | 2026-09-23 14:25:48 |
| Duration | 331 seconds |
| Launched | Manually, from the bundle |

## How it was deployed

The job is defined by `databricks.yml` and deployed with the Databricks CLI. Nothing about it is configured by hand in the workspace: a UI edit does not reach the file, and the next deploy overwrites it.

### 1. Check out the commit to deploy

    git switch main
    git pull --ff-only

The working tree must be clean. `${bundle.git.commit}` resolves to `HEAD`, so deploying from a dirty tree pins a commit that does not describe what was deployed.

### 2. Deploy

    databricks bundle deploy --target dev --profile crystal-workspace

What that does, in order:

1. Reads `databricks.yml` and resolves the substitutions. `${bundle.git.commit}` becomes the real SHA — in both `git_source.git_commit` and the `code_revision` job parameter, so the two cannot disagree.
2. Resolves `${var.warehouse_id}` to the warehouse declared once in `variables`.
3. Uploads the bundle to `/Workspace/Users/<user>/.bundle/nyc-mobility-pipeline/dev/`.
4. Creates or updates the job. In `development` mode the job is named `[dev <user>] NYC Mobility Pipeline` and any schedule is paused, so a deploy cannot land on top of a job someone else is relying on.

`deploy` updates the job definition. It does not run anything.

### 3. Confirm what was deployed

    databricks jobs get 224133189973974 --profile crystal-workspace

Both of these must be the commit you intended:

    git_source.git_commit  = bddd28316073aefd2d9dadf66f168ec85bac4d82
    parameters[code_revision].default = bddd28316073aefd2d9dadf66f168ec85bac4d82

A job shows the commit it was last **deployed** from, not whatever is on the branch. Deploying is what moves it.

### 4. Run

    databricks bundle run NYC_Mobility_Pipeline --target dev --profile crystal-workspace

Tasks execute in the dependency order declared in `databricks.yml`: Control, then the three Bronze loads in parallel, each source's Bronze gate, Silver, Integration, the four Gold dimensions, the two Gold facts, and Analytics. A gate that fails raises, and everything downstream is skipped rather than run on unvalidated data.

## How the commit reaches a result row

    commit
      -> deploy resolves ${bundle.git.commit}
        -> job parameter code_revision
          -> each gate: SET VARIABLE code_revision = COALESCE(NULLIF(:code_revision, ''), 'UNSET')
            -> every row the gate writes to data_quality_results and pipeline_runs

The value is fixed at **deploy** time, not run time. Ten runs of one deployment all record the same commit, because they were the same code. Picking up new code requires a deploy — which is the point of a controlled deployment rather than a limitation of it.

A gate run by hand with no parameter records `'UNSET'`: an unknown revision stated honestly rather than a claim the run cannot support.

## Result

**28 of 30 tasks succeeded.** Every data task passed.

### Gates

    SELECT layer, dataset, status, code_revision, checks_run
    FROM `ftw-week-08`.`01-control`.gate_status
    ORDER BY layer, dataset;
<img width="1084" height="714" alt="image" src="https://github.com/user-attachments/assets/4ab4b168-ae43-4a04-b0d6-fbe98179d3ee" />

**15 gates, 231 checks, 0 failures, and one distinct `code_revision`:**
`bddd28316073aefd2d9dadf66f168ec85bac4d82`.

Three warnings in the Bronze Green Taxi gate are the documented tolerances, pickups outside the reporting window, dropoff not after pickup, and pickups whose month differs from the file's month. All below their thresholds, all measured every run.

### Row counts, layer by layer

    SELECT 'bronze  green_taxi_raw'    AS table_name, COUNT(*) AS rows FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
    UNION ALL
    SELECT 'silver  green_taxi_clean',            COUNT(*) FROM `ftw-week-08`.`03-silver`.green_taxi_clean
    UNION ALL
    SELECT 'silver  green_taxi_quarantine',       COUNT(*) FROM `ftw-week-08`.`03-silver`.green_taxi_quarantine
    UNION ALL
    SELECT 'gold    fact_taxi_trip',              COUNT(*) FROM `ftw-week-08`.`05-gold`.fact_taxi_trip;
<img width="1085" height="499" alt="image" src="https://github.com/user-attachments/assets/e28f1d75-7895-4ce9-98ce-1f0af2268493" />


**133,353 + 14 = 133,367.** Every Bronze row is accounted for in Silver, either in the clean table or the quarantine table. Nothing was silently dropped.

`SUM(fare_amount)` over Bronze is **2,248,450.30**, matching the independently measured source total.

### Why 14 rows are held back

    SELECT quarantine_reasons, COUNT(*) AS rows, COUNT(DISTINCT trip_hash) AS collision_groups
    FROM `ftw-week-08`.`03-silver`.green_taxi_quarantine
    GROUP BY quarantine_reasons;
<img width="1081" height="417" alt="image" src="https://github.com/user-attachments/assets/d01006a7-310b-496d-89df-1a295a1227e2" />

Seven collision groups, two rows each. That is the D10 policy working as designed: where two rows share a trip identity, **both** are held back rather than a winner being picked. Correctness over completeness, no survivorship rule is applied, because none has been confirmed by anyone with TLC billing knowledge.

Gold matches Silver exactly, so nothing was lost between them either.

### What failed, and why it is expected

<img width="1502" height="835" alt="image" src="https://github.com/user-attachments/assets/a1346069-fd13-494c-9dc3-e82201e1fcad" />


Both carry dashboard ids that exist only in the workspace the job was first built in — the same class of defect as the hardcoded warehouse id and Git URL, which #117 fixed for those two. Tracked in #122. Neither task touches data, and both are leaves that nothing depends on, so every table is correct despite the run being reported as failed.

## History in one query

    SELECT code_revision, COUNT(*) AS runs, MAX(started_at) AS last_seen
    FROM `ftw-week-08`.`01-control`.pipeline_runs
    GROUP BY code_revision ORDER BY MAX(started_at) DESC;

<img width="1085" height="477" alt="image" src="https://github.com/user-attachments/assets/e0f1c09e-d880-4b29-9d3b-c1fca64cc889" />


`UNSET` and a real commit appear minutes apart in the same table: the state before these changes and the state after, on the same pipeline.

The merge commit shows **two runs**. One was started from the Databricks UI and one from `databricks bundle run`, both against the same deployment. That is the behaviour to expect: `code_revision` identifies the deployed **version**, not an individual execution, so every run of one deployment shares it. `run_id` distinguishes the executions.

## What this proves

- A gate result can be traced to the commit that produced it, with nothing typed by hand.
- The commit that runs and the commit recorded are the same value, resolved once at deploy.
- All ten gates work with the parameter, not just the one tested in isolation.
- `databricks.yml` is now the source of truth for the job: the deployment came from the file, not from the workspace UI.

## What it does not prove

- **`prod` has never been deployed.** Only `dev`, which runs under a prefixed job name with schedules paused.
- **This run was incremental.** Bronze skipped content already loaded, so the first-run defect fixed in #111 was not exercised here. It was demonstrated separately against an empty schema.
- **Nothing is scheduled or alerted.** Every run so far was started by a human, and no failure reaches anyone who is not looking. Tracked in #131 and #132.
- **The two dashboards are not refreshed by the pipeline.** Tracked in #122.
