# DuckDB Pre-Ingestion Source Gate

Purpose:
Validate Green Taxi source files locally before Bronze ingestion.

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