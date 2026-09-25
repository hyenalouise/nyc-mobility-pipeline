# Source-validation result files

These compact JSON files are machine-readable evidence emitted by the DuckDB
source gate.

| File | Scenario |
|---|---|
| `results.json` | Accepted Green Taxi delivery |
| `taxi_zones_results.json` | Accepted Taxi Zones delivery |
| `taxi_zones_broken_results.json` | Controlled failing Taxi Zones delivery |

Interpret a result together with its recorded source path, execution time, code
revision, contract, and related Markdown run record in
[`../pipeline-runs/`](../pipeline-runs/). A JSON result is evidence for
that run; it is not a permanent statement about later source deliveries.
