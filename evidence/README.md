# Evidence

This folder contains compact, reviewed proof of pipeline behavior. Evidence is
append-only: add a new run-specific file rather than replacing an earlier result.

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

See [proof/README.md](proof/README.md) for the current evidence index.
