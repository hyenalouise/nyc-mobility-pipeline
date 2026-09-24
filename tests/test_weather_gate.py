"""Weather gate against generated data, so no real API response is committed.

Weather has no reporting_window or row_count_floor in its contract, unlike
Green Taxi and Taxi Zones: it's a request-window source (#125), and a
landed response can legitimately cover any span. hourly_series_has_no_gaps
is the check that stands in for a floor here -- it compares the observed
row count against the hour-span implied by the response's own min/max
timestamp, so it catches a truncated or gappy response without needing a
hardcoded window.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ingestion import source_gate  # noqa: E402

REQUIRED_COLUMNS = ["latitude", "longitude", "elevation", "hourly"]
REQUIRED_HOURLY_FIELDS = ["time", "temperature_2m", "precipitation", "weather_code"]


def clean_response(hours=4):
    return {
        "latitude": 40.7,
        "longitude": -74.0,
        "generationtime_ms": 1.2,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "elevation": 32.0,
        "hourly_units": {
            "time": "iso8601", "temperature_2m": "°C",
            "precipitation": "mm", "weather_code": "wmo code",
        },
        "hourly": {
            "time": [f"2026-03-01T{hour:02d}:00" for hour in range(hours)],
            "temperature_2m": [5.0 + hour * 0.1 for hour in range(hours)],
            "precipitation": [0.0 for _ in range(hours)],
            "weather_code": [1 for _ in range(hours)],
        },
    }


def run_gate(tmp_path, monkeypatch, response):
    contract = tmp_path / "source_contract.json"
    contract.write_text(json.dumps({"weather": {
        "required_columns": REQUIRED_COLUMNS,
        "required_hourly_fields": REQUIRED_HOURLY_FIELDS,
    }}))

    weather_json = tmp_path / "weather.json"
    weather_json.write_text(json.dumps(response))

    evidence = tmp_path / "evidence.json"
    monkeypatch.setattr(source_gate, "CONTRACT_PATH", contract)
    monkeypatch.setattr(sys, "argv", [
        "source_gate.py", "--source", "weather",
        "--input", str(weather_json), "--evidence", str(evidence),
    ])
    exit_code = source_gate.main()
    result = json.loads(evidence.read_text())
    return exit_code, [r["check_name"] for r in result["results"] if r["status"] == "FAIL"]


def test_a_clean_response_is_accepted(tmp_path, monkeypatch):
    assert run_gate(tmp_path, monkeypatch, clean_response()) == (source_gate.EXIT_ACCEPTED, [])


def test_a_missing_hour_fails_the_gap_check(tmp_path, monkeypatch):
    response = clean_response(hours=4)
    del response["hourly"]["time"][2]
    del response["hourly"]["temperature_2m"][2]
    del response["hourly"]["precipitation"][2]
    del response["hourly"]["weather_code"][2]
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert "hourly_series_has_no_gaps" in failing


def test_a_duplicated_hour_fails_the_duplicate_check(tmp_path, monkeypatch):
    # Appending an extra copy of hour 0 (rather than overwriting hour 1)
    # keeps every original hour present, so the only defect is the
    # duplicate -- and it also pushes the row count above what the span
    # implies (5 rows for a 4-hour span), so hourly_series_has_no_gaps
    # catches it too. Overwriting instead of appending would make the
    # duplicate coincidentally backfill the hour it erased, which is a
    # real, narrower case where only the duplicate check can see it.
    response = clean_response(hours=4)
    for key in ("time", "temperature_2m", "precipitation", "weather_code"):
        response["hourly"][key].append(response["hourly"][key][0])
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert "no_duplicate_hourly_timestamps" in failing
    assert "hourly_series_has_no_gaps" in failing


def test_a_gap_backfilled_by_a_duplicate_is_still_caught(tmp_path, monkeypatch):
    # Overwriting hour 1 with a copy of hour 0 removes hour 1 and adds a
    # second hour 0: row count and hour-span both stay at 4, so
    # hourly_series_has_no_gaps genuinely cannot see a defect here -- only
    # the duplicate check can. This is exactly why both checks exist
    # rather than relying on the count-vs-span arithmetic alone.
    response = clean_response(hours=4)
    response["hourly"]["time"][1] = response["hourly"]["time"][0]
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["no_duplicate_hourly_timestamps"]


def test_a_null_temperature_fails_only_its_own_checks(tmp_path, monkeypatch):
    response = clean_response(hours=4)
    response["hourly"]["temperature_2m"][1] = None
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert set(failing) == {"temperature_2m_not_null", "temperature_plausible_range"}


def test_an_out_of_range_temperature_fails_only_the_range_check(tmp_path, monkeypatch):
    response = clean_response(hours=4)
    response["hourly"]["temperature_2m"][1] = 999.0
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["temperature_plausible_range"]


def test_negative_precipitation_fails_only_its_own_check(tmp_path, monkeypatch):
    response = clean_response(hours=4)
    response["hourly"]["precipitation"][1] = -0.5
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["precipitation_non_negative"]


def test_a_mostly_unknown_weather_code_fails_the_domain_check(tmp_path, monkeypatch):
    # weather_code_known_domain tolerates up to 0.1% unfamiliar codes
    # (matching Green Taxi's vendor_id_domain/payment_type_domain
    # convention) before it flips from WARN to FAIL, so a single bad code
    # out of many rows would not be enough to trip it here.
    response = clean_response(hours=4)
    response["hourly"]["weather_code"] = [12345, 12345, 12345, 12345]
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert "weather_code_known_domain" in failing


def test_a_missing_required_field_is_reported_and_stops_row_level_checks(tmp_path, monkeypatch):
    response = clean_response()
    del response["elevation"]
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["required_columns"]


def test_an_empty_hourly_series_is_rejected(tmp_path, monkeypatch):
    # hourly is present (required_columns passes) and its four fields all
    # exist (required_hourly_fields passes), they're just empty arrays --
    # a distinct malformation from hourly being absent entirely.
    response = clean_response(hours=0)
    exit_code, failing = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["hourly_series_not_empty"]
