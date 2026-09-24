"""D29: which Green Taxi checks block, in the source gate and the Bronze gate.

Silver keeps negative distances, reversed trips, zero-length trips and
implausible passenger counts, and flags them (D15). D28 stopped the source
gate blocking on negative fares for that reason, and #153 asked the same
question of three more checks. The answers, pinned here:

- trip_distance_non_negative stays BLOCK. Unlike a negative fare, which can
  be a refund, a negative distance has no legitimate meaning, so it points to
  a broken delivery. 0 rows in March to May 2026.
- dropoff_after_pickup counted dropoff at OR before pickup. 99 of its 100
  rows were zero-length trips, and April was 7 rows from blocking. It is
  split: dropoff_before_pickup (Silver's own condition) stays WARN at 0.1%,
  and zero_length_trip is INFO. Both gates change the same way, or the same
  risk just moves to the Bronze gate.
- passenger_count_gt_8 stays WARN at 0.1%. The worst month was 0.0156%.
"""
import json
import re
import sys
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ingestion import source_gate  # noqa: E402

BRONZE_GATE = REPO_ROOT / "etl" / "02_bronze" / "90_validate_green_taxi.sql"

# check_name -> (check_type, severity, threshold_pct), as decided in D28 and D29.
DECIDED = {
    "trip_distance_non_negative": ("RANGE", "BLOCK", 0.0),
    "fare_amount_non_negative": ("RANGE", "INFO", None),
    "dropoff_before_pickup": ("CONSISTENCY", "WARN", 0.1),
    "zero_length_trip": ("CONSISTENCY", "INFO", None),
    "passenger_count_gt_8": ("RANGE", "WARN", 0.1),
}

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


def write_delivery(path, rows=1000, zero_length=0, reversed_=0):
    """A clean month of distinct trips, where the first `zero_length` rows end
    at the instant they start and the next `reversed_` rows end before it."""
    dropoff = (
        f"CASE WHEN i < {zero_length} THEN pickup "
        f"WHEN i < {zero_length + reversed_} THEN pickup - INTERVAL 5 MINUTE "
        "ELSE pickup + INTERVAL 12 MINUTE END"
    )
    connection = duckdb.connect()
    connection.execute(f"""
        COPY (
            SELECT
                2::INTEGER AS VendorID, pickup AS lpep_pickup_datetime,
                {dropoff} AS lpep_dropoff_datetime, 'N' AS store_and_fwd_flag,
                1::BIGINT AS RatecodeID, 74::INTEGER AS PULocationID, 42::INTEGER AS DOLocationID,
                1::BIGINT AS passenger_count, 3.2::DOUBLE AS trip_distance, 14.5::DOUBLE AS fare_amount,
                0.5::DOUBLE AS extra, 0.5::DOUBLE AS mta_tax, 2.0::DOUBLE AS tip_amount,
                0.0::DOUBLE AS tolls_amount, NULL::DOUBLE AS ehail_fee, 1.0::DOUBLE AS improvement_surcharge,
                18.5::DOUBLE AS total_amount, 1::BIGINT AS payment_type, 1::BIGINT AS trip_type,
                0.0::DOUBLE AS congestion_surcharge, 0.0::DOUBLE AS cbd_congestion_fee
            FROM (SELECT i, TIMESTAMP '2026-03-01 00:00:00' + i * INTERVAL 1 MINUTE AS pickup
                  FROM range({rows}) t(i))
        ) TO '{path}' (FORMAT PARQUET)
    """)
    connection.close()


@pytest.fixture
def gate_run(tmp_path, monkeypatch):
    def run(**delivery):
        contract = tmp_path / "source_contract.json"
        contract.write_text(json.dumps({"green_taxi": {
            "required_columns": [name for name, _ in COLUMNS],
            "row_count_floor": 1,
            "reporting_window": {"start": "2026-03-01", "end": "2026-05-31"},
        }}))
        parquet = tmp_path / "green_tripdata_2026-03.parquet"
        write_delivery(parquet, **delivery)
        evidence = tmp_path / "evidence.json"
        monkeypatch.setattr(source_gate, "CONTRACT_PATH", contract)
        monkeypatch.setattr(sys, "argv", [
            "source_gate.py", "--input", str(parquet), "--evidence", str(evidence),
        ])
        exit_code = source_gate.main()
        results = {r["check_name"]: r for r in json.loads(evidence.read_text())["results"]}
        return exit_code, results
    return run


def test_each_decided_check_has_its_decided_metadata(gate_run):
    exit_code, results = gate_run()
    assert exit_code == source_gate.EXIT_ACCEPTED
    for name, (check_type, severity, threshold) in DECIDED.items():
        assert name in results, f"the gate no longer runs {name}"
        got = (
            results[name]["check_type"],
            results[name]["severity"],
            results[name]["threshold_pct"],
        )
        expected = (check_type, severity, threshold)
        assert got == expected, f"{name}: expected {expected}, got {got}"
    assert "dropoff_after_pickup" not in results, "the old at-or-before check is back"


def test_zero_length_trips_are_counted_but_do_not_block(gate_run):
    """2% zero-length trips: well past the old 0.1% threshold, which counted
    them as dropoff at or before pickup and would have blocked."""
    exit_code, results = gate_run(zero_length=20)
    assert exit_code == source_gate.EXIT_ACCEPTED
    assert results["zero_length_trip"]["status"] == "INFO"
    assert results["zero_length_trip"]["fail_count"] == 20
    assert results["dropoff_before_pickup"]["status"] == "PASS"


def test_reversed_trips_still_block(gate_run):
    """2% of trips ending before they start is a broken delivery, e.g. swapped
    timestamp columns, and must still stop the load."""
    exit_code, results = gate_run(reversed_=20)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert results["dropoff_before_pickup"]["status"] == "FAIL"
    assert results["dropoff_before_pickup"]["fail_count"] == 20
    assert results["zero_length_trip"]["fail_count"] == 0


def bronze_check(name):
    """The UNION ALL branch of the Bronze gate that produces check `name`."""
    text = BRONZE_GATE.read_text(encoding="utf-8")
    match = re.search(rf"SELECT '{name}',(.*?)FROM `ftw-week-08`", text, re.S)
    return match.group(1) if match else None


def test_the_bronze_gate_makes_the_same_split():
    """The Bronze gate had the same at-or-before rule. Changing only the source
    gate would leave the same risk one step later in the same run."""
    assert bronze_check("dropoff_after_pickup") is None, "the Bronze gate still has the at-or-before check"
    reversed_check = bronze_check("dropoff_before_pickup")
    assert reversed_check and "'CONSISTENCY', 'WARN', 0.1" in reversed_check
    assert "lpep_dropoff_datetime < lpep_pickup_datetime" in reversed_check
    zero_check = bronze_check("zero_length_trip")
    assert zero_check and "'CONSISTENCY', 'INFO', NULL" in zero_check
    assert "lpep_dropoff_datetime = lpep_pickup_datetime" in zero_check
    distance_check = bronze_check("trip_distance_non_negative")
    assert distance_check and "'FAIL', 0.0" in distance_check
