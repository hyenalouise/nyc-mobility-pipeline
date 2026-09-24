"""Weather gate against generated data, so no real API response is committed.

Weather is a request-window source (#125): a response covers the dates it
was requested for. Completeness is checked two ways --
hourly_series_has_no_gaps looks for holes inside the response's own
first-to-last hour, and hourly_series_covers_requested_window checks the
count and the first and last hour against the contract's requested_window.
The fixtures here request a single day, 2026-03-01, so a clean response is
24 hours.

The last three tests pin the gate to the Bronze and Silver weather SQL, so
the pre-Bronze gate can never quietly become looser than the gates after it.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ingestion import source_gate  # noqa: E402

REQUIRED_COLUMNS = ["latitude", "longitude", "elevation", "hourly"]
REQUIRED_HOURLY_FIELDS = ["time", "temperature_2m", "precipitation", "weather_code"]
REQUESTED_DAY = "2026-03-01"
HOURLY_KEYS = ("time", "temperature_2m", "precipitation", "weather_code")

BRONZE_GATE = REPO_ROOT / "etl/02_bronze/90_validate_open_meteo_weather.sql"
SILVER_GATE = REPO_ROOT / "etl/03_silver/90_validate_weather_hourly.sql"
BRONZE_LOADER = REPO_ROOT / "etl/02_bronze/20_load_open_meteo.sql"
GATE_SOURCE = REPO_ROOT / "src/ingestion/source_gate.py"


def clean_response(hours=24):
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
            "time": [f"{REQUESTED_DAY}T{hour:02d}:00" for hour in range(hours)],
            "temperature_2m": [5.0 + hour * 0.1 for hour in range(hours)],
            "precipitation": [0.0 for _ in range(hours)],
            "weather_code": [1 for _ in range(hours)],
        },
    }


def run_gate(tmp_path, monkeypatch, response):
    """Returns (exit code, names of FAIL checks, all results)."""
    contract = tmp_path / "source_contract.json"
    contract.write_text(json.dumps({"weather": {
        "required_columns": REQUIRED_COLUMNS,
        "required_hourly_fields": REQUIRED_HOURLY_FIELDS,
        "requested_window": {"start": REQUESTED_DAY, "end": REQUESTED_DAY},
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
    results = json.loads(evidence.read_text())["results"]
    failing = [r["check_name"] for r in results if r["status"] == "FAIL"]
    return exit_code, failing, results


def result(results, check_name):
    return next(r for r in results if r["check_name"] == check_name)


def drop_hour(response, index):
    for key in HOURLY_KEYS:
        del response["hourly"][key][index]


# --- accept -------------------------------------------------------------

def test_a_clean_response_is_accepted(tmp_path, monkeypatch):
    exit_code, failing, results = run_gate(tmp_path, monkeypatch, clean_response())
    assert (exit_code, failing) == (source_gate.EXIT_ACCEPTED, [])
    assert len(results) == 15


# --- completeness -------------------------------------------------------

def test_a_missing_hour_in_the_middle_fails_the_gap_check(tmp_path, monkeypatch):
    response = clean_response()
    drop_hour(response, 12)
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert set(failing) == {"hourly_series_has_no_gaps", "hourly_series_covers_requested_window"}


def test_a_response_cut_short_at_the_end_is_refused(tmp_path, monkeypatch):
    # The gap check cannot see this: the response's own span shrinks with
    # it (21 hours, 21 rows). Only the requested window can. Bronze's
    # hourly_volume would refuse this file, so the gate must too.
    response = clean_response()
    for _ in range(3):
        drop_hour(response, -1)
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["hourly_series_covers_requested_window"]


def test_a_response_starting_late_is_refused(tmp_path, monkeypatch):
    response = clean_response()
    drop_hour(response, 0)
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["hourly_series_covers_requested_window"]


def test_a_duplicated_hour_fails_the_duplicate_check(tmp_path, monkeypatch):
    # An extra copy of hour 0 keeps every hour present, so the duplicate is
    # the only defect -- and it pushes the count above both the span and the
    # requested window.
    response = clean_response()
    for key in HOURLY_KEYS:
        response["hourly"][key].append(response["hourly"][key][0])
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert set(failing) == {
        "no_duplicate_hourly_timestamps",
        "hourly_series_has_no_gaps",
        "hourly_series_covers_requested_window",
    }


def test_a_gap_backfilled_by_a_duplicate_is_still_caught(tmp_path, monkeypatch):
    # Overwriting hour 1 with a copy of hour 0 keeps the count at 24 and the
    # first and last hour right, so neither count-based check can see it --
    # only the duplicate check can. This is why both kinds of check exist.
    response = clean_response()
    response["hourly"]["time"][1] = response["hourly"]["time"][0]
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["no_duplicate_hourly_timestamps"]


# --- time ---------------------------------------------------------------

def test_an_unparseable_last_time_is_refused(tmp_path, monkeypatch):
    # Before hourly_time_valid, 'garbage' in the last hour was filtered out of
    # the gap check, observed and expected both dropped by one, and all
    # checks passed.
    response = clean_response()
    response["hourly"]["time"][-1] = "garbage"
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["hourly_time_valid"]


def test_a_null_time_is_refused(tmp_path, monkeypatch):
    response = clean_response()
    response["hourly"]["time"][5] = None
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["hourly_time_valid"]


# --- measures -----------------------------------------------------------

def test_a_null_temperature_fails_only_its_own_checks(tmp_path, monkeypatch):
    response = clean_response()
    response["hourly"]["temperature_2m"][1] = None
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert set(failing) == {"temperature_2m_not_null", "temperature_plausible_range"}


def test_an_out_of_range_temperature_fails_only_the_range_check(tmp_path, monkeypatch):
    response = clean_response()
    response["hourly"]["temperature_2m"][1] = 999.0
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["temperature_plausible_range"]


def test_negative_precipitation_fails_only_its_own_check(tmp_path, monkeypatch):
    response = clean_response()
    response["hourly"]["precipitation"][1] = -0.5
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["precipitation_non_negative"]


def test_a_single_unknown_weather_code_blocks(tmp_path, monkeypatch):
    # weather_code_known_domain blocks at 0%, matching Bronze's
    # weather_code_domain and Silver's weather_code_valid_wmo.
    response = clean_response()
    response["hourly"]["weather_code"][1] = 12345
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["weather_code_known_domain"]


def test_a_non_integer_weather_code_blocks(tmp_path, monkeypatch):
    # TRY_CAST(1.4 AS INTEGER) rounds to 1, which used to let this through.
    response = clean_response()
    response["hourly"]["weather_code"][1] = 1.4
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["weather_code_known_domain"]


# --- shape --------------------------------------------------------------

def test_a_missing_required_field_is_reported_and_stops_row_level_checks(tmp_path, monkeypatch):
    response = clean_response()
    del response["elevation"]
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["required_columns"]


def test_only_the_missing_hourly_field_is_reported(tmp_path, monkeypatch):
    # Used to report failures=4 whichever field was missing.
    response = clean_response()
    del response["hourly"]["precipitation"]
    exit_code, failing, results = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["required_hourly_fields"]
    check = result(results, "required_hourly_fields")
    assert check["fail_count"] == 1
    assert "precipitation" in check["details"]
    assert "time" not in check["details"].split(":", 1)[1]


def test_a_non_array_hourly_field_is_a_type_failure_not_a_missing_field(tmp_path, monkeypatch):
    response = clean_response()
    response["hourly"]["precipitation"] = 0.0
    exit_code, failing, results = run_gate(tmp_path, monkeypatch, response)
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["hourly_fields_are_arrays"]
    assert result(results, "required_hourly_fields")["status"] == "PASS"


def test_an_empty_hourly_series_is_rejected(tmp_path, monkeypatch):
    # hourly is present and its four fields all exist, they're just empty
    # arrays -- a distinct malformation from hourly being absent entirely.
    exit_code, failing, _ = run_gate(tmp_path, monkeypatch, clean_response(hours=0))
    assert exit_code == source_gate.EXIT_BLOCKED
    assert failing == ["hourly_series_not_empty"]


# --- pinned to the Bronze and Silver SQL --------------------------------

def codes(text, pattern):
    return set(map(int, re.findall(r"\d+", re.search(pattern, text, re.S).group(1))))


def test_wmo_codes_match_bronze_and_silver_gates():
    gate_codes = codes(GATE_SOURCE.read_text(encoding="utf-8"), r"known_weather_codes = \((.*?)\)")
    for sql in (BRONZE_GATE, SILVER_GATE):
        text = sql.read_text(encoding="utf-8")
        assert codes(text, r"weather_code NOT IN \((.*?)\)") == gate_codes, sql.name


def test_temperature_range_matches_bronze_gate():
    # Pinned to Bronze, the gate straight after this one. Silver's range is
    # wider (-90), so Bronze is the binding limit.
    bronze = re.search(
        r"temperature_2m < (-?\d+) OR temperature_2m > (-?\d+)",
        BRONZE_GATE.read_text(encoding="utf-8"),
    ).groups()
    gate = re.search(
        r"TRY_CAST\(temperature_2m AS DOUBLE\) < (-?\d+)\s+OR TRY_CAST\(temperature_2m AS DOUBLE\) > (-?\d+)",
        GATE_SOURCE.read_text(encoding="utf-8"),
    ).groups()
    assert gate == bronze


def test_requested_window_matches_the_bronze_loader():
    # The window the gate checks must be the one 20_load_open_meteo.sql
    # records as requested, which is what Bronze's hourly_volume checks.
    loader = BRONZE_LOADER.read_text(encoding="utf-8")

    def requested(name):
        return re.search(rf"SET VARIABLE weather_requested_{name}_date = '([^']+)'", loader).group(1)

    window = json.loads((REPO_ROOT / "config/source_contract.json").read_text(encoding="utf-8"))["weather"]["requested_window"]
    assert window == {"start": requested("start"), "end": requested("end")}
