# Evidence

This folder contains compact, reviewed records of pipeline behavior. Evidence is
append-only: add a new run-specific file rather than replacing an earlier result.

## Folder guide

| Location | Contents |
|---|---|
| [`pipeline-runs/`](pipeline-runs/) | Human-readable records of end-to-end, incremental, rerun, failure, recovery, deployment, and reconciliation checks |
| [`source-validation/`](source-validation/) | Machine-readable JSON results emitted by the DuckDB source gate |

Use the README inside each folder for its file index and interpretation guidance.

## What belongs here

- run and job IDs;
- code and configuration revisions;
- source versions, request windows, or input paths;
- row-count and measure reconciliation;
- accepted and quarantined counts;
- gate outcomes and recovery behavior;
- explicit limitations and anything still unverified.

## What does not belong here

- raw source datasets;
- complete table exports;
- large query results or logs;
- credentials or workspace configuration;
- screenshots containing sensitive information;
- local databases or processing state.

Large evidence belongs in the approved external storage location. The committed
summary should identify where it can be found without exposing secrets.
