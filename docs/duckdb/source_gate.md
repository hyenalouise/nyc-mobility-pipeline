# DuckDB Pre-Ingestion Source Gate

Purpose:
Validate the Green Taxi and Taxi Zones source files before Bronze ingestion. It runs locally, in CI against generated samples, and as a task in the Databricks job before each source's Bronze loader.

Flow:

Source Files
    ↓
DuckDB Source Gate
    ↓
ACCEPTED / BLOCKED
    ↓
Bronze Ingestion

Exit Codes

`src/ingestion/source_gate.py` treats these as a supported interface — CI
(`.github/workflows/ci.yml`) and any orchestrating job branch on the exact
value, not just zero-vs-nonzero. The named constants live at the top of
that file; keep this table in sync with them.

| Code | Constant | Meaning |
|---|---|---|
| 0 | `EXIT_ACCEPTED` | No blocking check failed. |
| 1 | `EXIT_BLOCKED` | At least one check has status FAIL: a BLOCK check with any failing row, or a WARN check above its threshold. INFO checks never cause it. |
| 2 | `EXIT_INVALID_CONFIGURATION` | The gate never ran a check — `MISSING_CONTRACT` (no contract declared for the `--source`), `MISSING_INPUT` (no `--input` supplied), or `NETWORK_INPUT_NOT_ALLOWED` (an `--input` pointed at a network location instead of a local file). |
| 3 | `EXIT_INPUT_UNAVAILABLE` | The declared input could not be read (missing file, unreadable file, or a glob that matched nothing).
| 4 | `EXIT_TEST_INPUT` | No blocking check failed, but `--input` is not the `--load-input` the loader reads, so this was a test run. The task fails so the loader can't load files this run didn't check (#159). A test input that is BLOCKED exits 1 as usual. |

## In the Databricks job (#148)

The job runs the gate once per contracted source, right after control setup and before that source's Bronze loader:

```
--source green_taxi --input {{job.parameters.green_taxi_input}} --load-input /Volumes/ftw-week-08/00-source/group_a_source/green_taxi/*.parquet --evidence /tmp/source_gate_green_taxi.json --record-control --code-revision {{job.parameters.code_revision}}
```

- Exit 1 (BLOCKED) fails the task, and the loader that depends on it is skipped.
- `--input` comes from a job parameter that defaults to the landing path, and `--load-input` is the path the loader reads. They only differ in a test run, which then exits 4 even if the test input passes, so the loader is skipped either way (#159).
- `--evidence` points at `/tmp` because the JSON is only a by-product in the job. The record is the rows in `data_quality_results`.
- The contract and default evidence paths resolve from the repository root, not the working directory, so the script works from the job's Git checkout.

## Results in 01-control

With `--record-control`, the gate appends one row per check to `ftw-week-08`.`01-control`.`data_quality_results`, so its verdict appears in `gate_status` and on the DQ dashboard next to the SQL gates. It records before it exits, so a BLOCKED delivery is on record too. Without the flag (local and CI runs) nothing is recorded, since there is no Spark session.

| Column | Value |
|---|---|
| `layer` | `source` |
| `dataset` | the `--source`, e.g. `green_taxi` |
| `severity` | the gate's severity, except `BLOCK`, which is recorded as `FAIL` to match `dq_status()` and the SQL gates |
| `status` | `PASS`, `WARN`, `FAIL` or `INFO`, as the gate computed it |
| `code_revision` | `--code-revision`, or `UNSET` when empty (D25) |
| `batch_id`, `source_version_id` | `NULL`: the gate runs before Bronze creates a batch or version |
| `evidence_location` | the input paths the gate read |
| `owner` | `TODO`, like the SQL gates, until #126 |
