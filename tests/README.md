# Tests

Run the complete local suite from the repository root:

```bash
python3 -m pytest tests
```

## Test groups

| Area | Main files | What they protect |
|---|---|---|
| Repository and documentation policy | `test_repo_policy.py`, `test_notebook_source_format.py`, `test_documentation_structure.py` | Parseability, naming, paths, SQL references, notebook placement, README coverage, and local documentation links |
| Bundle contract | `test_bundle_contract.py`, `test_job_setup_doc.py` | Task dependencies, source-gate wiring, dashboards, parameters, dependency pins, and job-document parity |
| Traceability and monitoring | `test_code_revision_traceability.py`, `test_pipeline_runs_monitoring.py` | Code-revision lineage and run-health controls |
| Green Taxi policy | `test_green_taxi_deduplication_policy.py`, `test_source_gate_severities.py` | Duplicate disposition and severity behavior |
| Source-gate control flow | `test_source_gate_control_flow.py`, `test_source_gate_control_rows.py` | Exit behavior, blocking, test-input safety, and DQ recording |
| Source-specific gates | `test_taxi_zones_gate.py`, `test_weather_gate.py` | Taxi Zones and Weather contracts and edge cases |
| SQL safety | `test_sql_subquery_shapes.py` | SQL shapes known to require explicit safeguards |

## What local tests do not prove

The local suite does not connect to Databricks. It cannot prove:

- live workspace permissions;
- SQL warehouse or serverless capacity;
- Delta transaction behavior under concurrency;
- current deployed task configuration;
- dashboard rendering;
- external source availability.

Those claims require bundle validation, read-only workspace inspection, or a
reviewed run with evidence, depending on the claim.

## Adding a test

- Name the contract it protects.
- Prefer small generated fixtures over committed raw data.
- Keep source-specific expectations separate when the sources mean different
  things.
- Test both the accepted path and the blocking or failure path.
- Update this index when a new test category is introduced.
