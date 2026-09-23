"""Taxi Zones gate against generated data, so no real CSV is committed."""
import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ingestion import source_gate  # noqa: E402

HEADER = ["LocationID", "Borough", "Zone", "service_zone"]


def clean_rows():
    return [[str(i), "Queens", f"Zone {i}", "Boro Zone"] for i in range(1, 266)]


def run_gate(tmp_path, monkeypatch, rows):
    contract = tmp_path / "source_contract.json"
    contract.write_text(json.dumps({"taxi_zones": {
        "required_columns": HEADER, "row_count_floor": 265}}))
    zones = tmp_path / "zones.csv"
    with zones.open("w", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows([HEADER] + rows)
    evidence = tmp_path / "evidence.json"
    monkeypatch.setattr(source_gate, "CONTRACT_PATH", contract)
    monkeypatch.setattr(sys, "argv", ["source_gate.py", "--source", "taxi_zones",
                                      "--input", str(zones), "--evidence", str(evidence)])
    exit_code = source_gate.main()
    result = json.loads(evidence.read_text())
    return exit_code, [r["check_name"] for r in result["results"] if r["status"] == "FAIL"]


def test_a_clean_snapshot_is_accepted(tmp_path, monkeypatch):
    assert run_gate(tmp_path, monkeypatch, clean_rows()) == (source_gate.EXIT_ACCEPTED, [])


@pytest.mark.parametrize("column, value, expected_check", [
    (0, "2", "location_id_unique"),           # duplicates LocationID 2
    (1, "", "borough_not_null"),
    (0, "abc", "location_id_valid_integer"),
    (0, "266", "location_id_valid_integer"),
    (0, "12.5", "location_id_valid_integer"),
])
def test_each_defect_fails_only_its_own_check(tmp_path, monkeypatch, column, value, expected_check):
    rows = clean_rows()
    rows[10][column] = value
    assert run_gate(tmp_path, monkeypatch, rows) == (source_gate.EXIT_BLOCKED, [expected_check])