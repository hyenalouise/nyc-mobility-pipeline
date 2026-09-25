# Operations runbook

This runbook covers verification and recovery for the Databricks Asset Bundle
defined in `databricks.yml`. It does not authorize a deployment or production
run; the operator still needs the appropriate approval and workspace access.

## Before a deployment

1. Confirm the intended branch and commit are reviewed.
2. Run the local test suite and `git diff --check`.
3. Validate the bundle for the exact target and Databricks CLI profile.
4. Review the resolved job name, workspace path, schedule, notifications,
   source paths, warehouse ID, and code revision.
5. Confirm the target is `dev` before testing a new change.
6. Confirm no unrelated local changes will be included.

The deployment workflow and commands live in [workflow.md](workflow.md). The
task inventory and dependencies live in [job setup](job-setup.md).

## Before a run

Record:

- environment and job ID;
- deployed Git revision;
- source paths or approved input overrides;
- expected source periods or source versions;
- whether this is a normal run, controlled test, repair, or backfill;
- operator and reviewer when production is involved.

For a source-gate test override, verify that the gate input and loader input
differ intentionally. Exit code 4 prevents the loader from publishing landing
data that the gate did not inspect.

## Success criteria

A run is accepted only when:

- every required task succeeded;
- no blocking source, Bronze, Silver, Integration, Gold, or Analytics check
  failed;
- source-to-Bronze and downstream row counts reconcile;
- quarantined rows have an explicit, mutually exclusive reason;
- Gold keys and required foreign keys satisfy their contracts;
- Analytics validation passed before the business dashboard refreshed;
- the run and quality rows record the intended code revision;
- the relevant evidence is captured without committing raw data or large logs.

Job success alone is not enough. The data-quality result must also be green.

## Useful control queries

Latest recorded gate state:

```sql
SELECT
  layer,
  dataset,
  status,
  checks_run,
  fail_count,
  warn_count,
  executed_at,
  run_id,
  code_revision
FROM `ftw-week-08`.`01-control`.gate_status
ORDER BY layer, dataset;
```

Failed or warned checks for a run:

```sql
SELECT
  layer,
  dataset,
  check_name,
  severity,
  status,
  fail_count,
  total_count,
  fail_pct,
  owner,
  details
FROM `ftw-week-08`.`01-control`.data_quality_results
WHERE run_id = '<run-id>'
  AND status IN ('FAIL', 'WARN')
ORDER BY layer, dataset, check_name;
```

Batch history for a source object:

```sql
SELECT
  batch_id,
  source_system,
  source_object,
  source_period,
  content_sha256,
  status,
  started_at,
  completed_at,
  error_message,
  supersedes_batch_id,
  row_count
FROM `ftw-week-08`.`01-control`.ingestion_batches
WHERE source_system = '<source-system>'
ORDER BY discovered_at, batch_id;
```

## Failure response

Use the same sequence every time:

1. **Detect** — identify the failed task, gate, check, and run.
2. **Contain** — confirm dependent trusted tasks were skipped.
3. **Diagnose** — distinguish bad input, code, configuration, permissions,
   unavailable compute, or a transient external failure.
4. **Assess impact** — identify the last validated published data.
5. **Fix through review** — never edit Gold rows or mark a failed gate successful.
6. **Retry, repair, or rerun** — use the smallest safe action that preserves
   audit history.
7. **Verify** — repeat reconciliation and downstream checks.
8. **Record evidence** — add a new run-specific proof summary when required.

## Recovery choices

| Situation | Preferred response |
|---|---|
| Temporary platform or network failure | Repair or rerun after availability returns |
| Source gate blocks the delivered files | Replace or correct the delivery; a repair against unchanged bad input should fail again |
| Schema contract changes | Update the contract and implementation through review, then rerun |
| Transformation defect | Fix and deploy a reviewed commit, then rerun affected data |
| Interrupted incremental load | Inspect batch state and partial writes before repair |
| Duplicate-success or reconciliation failure | Stop publication and repair idempotency before rerunning |
| Historical correction | Use an explicitly reviewed backfill or revised-source procedure |

Do not delete failed batch or quality rows. They are part of the operational
history.

## Source-gate exit codes

| Exit code | Meaning | Operator action |
|---:|---|---|
| 0 | Accepted input matches the loader input | Continue with the configured job graph |
| 1 | One or more blocking checks failed | Investigate or replace the source delivery |
| 2 | Gate execution or input error | Correct the command, path, environment, or dependency |
| 3 | Declared input was unavailable or unreadable | Correct the input path, permissions, file, or glob |
| 4 | Test input differs from loader input | Expected for isolated demonstrations; loader remains blocked |

The implementation in `src/ingestion/source_gate.py` is authoritative for exact
exit behavior.

## Monitoring

Review both kinds of signals:

- **Pipeline signals:** task status, failures, skipped tasks, duration,
  concurrency, retries, and stuck runs.
- **Data signals:** gate status, freshness, reconciliation, nulls, duplicate
  disposition, key integrity, and measure coverage.

Current source-gate tasks have no configured timeout. Evidence records three
development attempts that remained pending during serverless Spark write-back;
treat a similar pending task as an operational incident rather than proof that
the input passed or failed.

## Evidence checklist

Record only compact reviewed facts:

- job and run ID;
- code revision;
- source versions or paths;
- start/end time and final state;
- accepted, quarantined, and rejected counts;
- important reconciled measures;
- failed or warned checks and their owners;
- what remains unverified.

Store run evidence under `evidence/pipeline-runs/`. Never overwrite an earlier
run summary.
