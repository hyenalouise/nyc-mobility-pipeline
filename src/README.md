# Python source

Reusable Python that is executed or intentionally retained by the project lives
under `src/`.

Current contents:

- `ingestion/source_gate.py` — active DuckDB pre-Bronze validation for Green
  Taxi, Taxi Zones, and Weather;
- `ingestion/batch_tracking.py` — retained batch-tracking helper, not invoked by
  the configured Databricks job;
- `ingestion/schema_drift_check.py` — retained schema helper, not invoked by the
  configured Databricks job.

Relational production transformations remain in `etl/`. Do not introduce a
second Python implementation of the complete pipeline under `src/`.
