# Pipeline-run evidence

Each file below records a specific claim at a specific code and data state. It
does not automatically describe the latest deployed production revision.

| Evidence | What it proves |
|---|---|
| [`2026-09-19-full-pipeline-run.md`](2026-09-19-full-pipeline-run.md) | One complete Control-to-Analytics run and end-to-end reconciliation |
| [`2026-09-19-incremental.md`](2026-09-19-incremental.md) | March, then April, then May load without rebuilding prior successful source content |
| [`2026-09-19-idempotency.md`](2026-09-19-idempotency.md) | Identical-input rerun preserves business content and measures |
| [`2026-09-19-failure-restart.md`](2026-09-19-failure-restart.md) | A failed gate blocks dependants and a repair succeeds safely |
| [`2026-09-23-bronze-duckdb-reconciliation.md`](2026-09-23-bronze-duckdb-reconciliation.md) | DuckDB, source files, and Bronze reconcile independently |
| [`2026-09-23-deployed-run-with-code-revision.md`](2026-09-23-deployed-run-with-code-revision.md) | A deployed run records the code revision used by its quality results |
| [`2026-09-25-recovery-demonstration.md`](2026-09-25-recovery-demonstration.md) | A controlled source-gate failure is corrected and followed by a successful recovery run |
| [`2026-09-25-source-gate-blocked-run.md`](2026-09-25-source-gate-blocked-run.md) | A pre-Bronze source gate blocks bad input, protects its loader, and exposes an operational timeout gap |

## Reading evidence correctly

- Use the run ID, code revision, source identity, and date written in the file.
- Do not combine counts from different runs unless the evidence explicitly does so.
- A historical check count may differ from current `main` when checks were added
  later; that is expected when the code revision is clear.
- Repository evidence proves the recorded run. Verify Databricks directly for
  current deployment and schedule state.
- The May incremental section records batch evidence but does not include a job
  run ID; do not invent one.

## Adding pipeline-run evidence

Use a date-prefixed filename and record:

1. claim being tested;
2. job and run ID;
3. code revision;
4. source identity;
5. procedure;
6. counts and reconciled measures;
7. final result;
8. limitations and remaining work.
