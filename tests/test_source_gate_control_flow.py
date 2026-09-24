"""Regression test for a real control-flow defect in source_gate.py's main().

`inputs = args.input`, `network_prefixes`, and the "no inputs" check used to
be indented inside the dead branch of the `green_taxi not in
contract_registry` guard, after its own `return`. Since the shipped contract
does declare `green_taxi`, that branch never ran on a normal invocation, so
`inputs` was never assigned and `for input_path in inputs:` raised
`NameError` unconditionally -- the gate could not accept a single delivery.

This calls `main()` directly, not a reimplementation of its logic, against a
throwaway contract and a tiny local Parquet file, and checks it reaches a
real gate verdict instead of crashing before ever getting there.
"""
import json
import sys
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ingestion import source_gate  # noqa: E402

# The full column set source_gate.py's checks reference. A sample built from
# only a contract's required_columns is not enough -- WARN-severity checks
# (passenger_count, payment_type, RatecodeID, ...) reference columns the
# contract never marks required, and DuckDB raises a BinderException the
# moment one of those checks runs. See ci.yml's sample-builder step, which
# validates its column set against the contract rather than generating it
# purely from required_columns for the same reason.
COLUMNS = [
    ("VendorID", "INTEGER"), ("lpep_pickup_datetime", "TIMESTAMP"),
    ("lpep_dropoff_datetime", "TIMESTAMP"), ("store_and_fwd_flag", "VARCHAR"),
    ("RatecodeID", "BIGINT"), ("PULocationID", "INTEGER"), ("DOLocationID", "INTEGER"),
    ("passenger_count", "BIGINT"), ("trip_distance", "DOUBLE"), ("fare_amount", "DOUBLE"),
    ("extra", "DOUBLE"), ("mta_tax", "DOUBLE"), ("tip_amount", "DOUBLE"),
    ("tolls_amount", "DOUBLE"), ("ehail_fee", "DOUBLE"), ("improvement_surcharge", "DOUBLE"),
    ("total_amount", "DOUBLE"), ("payment_type", "BIGINT"), ("trip_type", "BIGINT"),
    ("congestion_surcharge", "DOUBLE"), ("cbd_congestion_fee", "DOUBLE"),
]

CLEAN_ROW = [
    2, "2026-03-15 09:00:00", "2026-03-15 09:20:00", "N", 1, 74, 42, 1,
    3.2, 14.5, 0.5, 0.5, 2.0, 0.0, None, 1.0, 18.5, 1, 1, 0.0, 0.0,
]


def _write_contract(path):
    path.write_text(json.dumps({
        "green_taxi": {
            "required_columns": [name for name, _ in COLUMNS],
            "required_fields": ["lpep_pickup_datetime", "lpep_dropoff_datetime"],
            "row_count_floor": 1,
            "reporting_window": {"start": "2026-03-01", "end": "2026-05-31"},
        }
    }))


def _write_parquet(path, row):
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE t (%s)" % ", ".join('"%s" %s' % column for column in COLUMNS)
    )
    marks = ", ".join("?" * len(COLUMNS))
    connection.execute(f"INSERT INTO t VALUES ({marks})", row)
    connection.execute(f"COPY t TO '{path}' (FORMAT PARQUET)")
    connection.close()


@pytest.fixture
def gate_run(tmp_path, monkeypatch):
    """Runs main() against a throwaway contract + Parquet file, returns exit code."""

    def run(row):
        contract_path = tmp_path / "source_contract.json"
        _write_contract(contract_path)

        parquet_path = tmp_path / "sample.parquet"
        _write_parquet(parquet_path, row)

        evidence_path = tmp_path / "evidence.json"

        monkeypatch.setattr(source_gate, "CONTRACT_PATH", contract_path)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "source_gate.py",
                "--input", str(parquet_path),
                "--evidence", str(evidence_path),
            ],
        )

        exit_code = source_gate.main()
        evidence = json.loads(evidence_path.read_text())
        return exit_code, evidence

    return run


def test_a_normal_run_reaches_the_gate_instead_of_raising_nameerror(gate_run):
    exit_code, evidence = gate_run(CLEAN_ROW)

    assert exit_code == source_gate.EXIT_ACCEPTED
    assert evidence["gate_result"] == "ACCEPTED"
    assert evidence["check_count"] > 0


def test_a_blocking_failure_still_reaches_a_blocked_verdict(gate_run):
    bad_row = list(CLEAN_ROW)
    trip_distance_index = [name for name, _ in COLUMNS].index("trip_distance")
    bad_row[trip_distance_index] = -1.0

    exit_code, evidence = gate_run(bad_row)

    assert exit_code == source_gate.EXIT_BLOCKED
    assert evidence["gate_result"] == "BLOCKED"
    failing = [r["check_name"] for r in evidence["results"] if r["status"] == "FAIL"]
    assert "trip_distance_non_negative" in failing


def test_a_negative_fare_is_reported_not_blocking(gate_run):
    # One row out of one is a 100% failure rate, so a threshold of any size
    # coming back would turn this into a FAIL (D28).
    row = list(CLEAN_ROW)
    fare_index = [name for name, _ in COLUMNS].index("fare_amount")
    row[fare_index] = -14.5

    exit_code, evidence = gate_run(row)

    assert exit_code == source_gate.EXIT_ACCEPTED
    assert evidence["gate_result"] == "ACCEPTED"
    fare = next(r for r in evidence["results"] if r["check_name"] == "fare_amount_non_negative")
    assert (fare["severity"], fare["status"], fare["fail_count"]) == ("INFO", "INFO", 1)


def test_the_gate_finds_its_contract_from_any_working_directory(tmp_path, monkeypatch):
    # A job task runs the script from a Git checkout, not necessarily from
    # the repository root (#148). The real contract must still be found.
    parquet_path = tmp_path / "sample.parquet"
    _write_parquet(parquet_path, CLEAN_ROW)
    evidence_path = tmp_path / "evidence.json"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["source_gate.py", "--input", str(parquet_path), "--evidence", str(evidence_path)],
    )

    assert source_gate.CONTRACT_PATH.is_absolute()
    assert source_gate.main() == source_gate.EXIT_ACCEPTED
    assert source_gate.default_evidence_path("green_taxi").is_absolute()


def _run_main(tmp_path, monkeypatch, row, extra_args):
    contract_path = tmp_path / "source_contract.json"
    _write_contract(contract_path)
    parquet_path = tmp_path / "sample.parquet"
    _write_parquet(parquet_path, row)

    recorded = []
    monkeypatch.setattr(source_gate, "CONTRACT_PATH", contract_path)
    monkeypatch.setattr(source_gate, "record_in_control", recorded.append)
    monkeypatch.setattr(
        sys,
        "argv",
        ["source_gate.py", "--input", str(parquet_path), "--evidence", str(tmp_path / "e.json"), *extra_args],
    )
    return source_gate.main(), recorded


def test_a_blocked_delivery_is_still_recorded_in_control(tmp_path, monkeypatch):
    # The job task must leave a record even when it fails the run (#148).
    bad_row = list(CLEAN_ROW)
    bad_row[[name for name, _ in COLUMNS].index("trip_distance")] = -1.0

    exit_code, recorded = _run_main(
        tmp_path, monkeypatch, bad_row, ["--record-control", "--code-revision", "abc123"]
    )

    assert exit_code == source_gate.EXIT_BLOCKED
    assert len(recorded) == 1
    records = [dict(zip(source_gate.CONTROL_COLUMNS, row)) for row in recorded[0]]
    assert {r["code_revision"] for r in records} == {"abc123"}
    assert any(r["check_name"] == "trip_distance_non_negative" and r["status"] == "FAIL" for r in records)


def test_nothing_is_recorded_without_the_flag(tmp_path, monkeypatch):
    # Local and CI runs have no Spark session and must not try to write.
    exit_code, recorded = _run_main(tmp_path, monkeypatch, CLEAN_ROW, [])

    assert exit_code == source_gate.EXIT_ACCEPTED
    assert recorded == []
