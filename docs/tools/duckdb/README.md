# DuckDB documentation

DuckDB has a narrow role in this project: validate source deliveries close to
their files and provide an independent reconciliation path without replacing
the Databricks lakehouse.

| Document | Purpose |
|---|---|
| [source-gate.md](source-gate.md) | Inputs, outputs, exit codes, and runtime behavior of the pre-Bronze gate |
| [validation-checks.md](validation-checks.md) | Source-specific checks, severities, thresholds, and ownership |
| [evidence.md](evidence.md) | How local and committed DuckDB evidence is generated and interpreted |

The executable implementation is `src/ingestion/source_gate.py`; the approved
contract is `config/source_contract.json`; the configured production tasks are
in `databricks.yml`.

DuckDB does not replace Spark SQL, Delta tables, Unity Catalog governance,
Databricks scheduling, or workspace-specific integration testing.
