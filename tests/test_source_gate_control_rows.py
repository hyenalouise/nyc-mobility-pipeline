"""The source gate's rows in 01-control.data_quality_results (#148).

As a job task the gate appends one row per check to the table every SQL gate
writes to. Nothing here needs Spark: these tests hold the row shape, which
is where a mismatch with the table would otherwise first show up as a failed
INSERT on Databricks.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ingestion import source_gate  # noqa: E402

CONTROL_DDL = REPO_ROOT / "etl" / "01_control" / "00_create_control_tables.sql"

RESULTS = [
    source_gate.create_result("row_count_not_empty", "VOLUME", "BLOCK", 0, 1, 0.0, "rows: 3"),
    source_gate.create_result("trip_distance_non_negative", "RANGE", "BLOCK", 1, 3, 0.0, "negative"),
    source_gate.create_result("fare_amount_non_negative", "RANGE", "INFO", 1, 3, None, "negative fares"),
]


def rows(code_revision="abc123"):
    return source_gate.control_rows(
        source="green_taxi",
        inputs=["/Volumes/a.parquet", "/Volumes/b.parquet"],
        results=RESULTS,
        run_id="run-1",
        code_revision=code_revision,
    )


def as_dicts(code_revision="abc123"):
    return [dict(zip(source_gate.CONTROL_COLUMNS, row)) for row in rows(code_revision)]


def table_columns():
    """Column names of data_quality_results, in table order, from its DDL."""
    ddl = CONTROL_DDL.read_text(encoding="utf-8")
    body = re.search(r"data_quality_results \((.*?)\n\)", ddl, re.DOTALL).group(1)
    return re.findall(r"^\s+(\w+)\s+(?:STRING|TIMESTAMP|BIGINT|DOUBLE)", body, re.MULTILINE)


def test_the_rows_match_the_table_columns():
    columns = table_columns()
    assert "executed_at" in columns, "the DDL parse found no executed_at; check the regex"
    assert [c for c in columns if c != "executed_at"] == list(source_gate.CONTROL_COLUMNS)


def test_one_row_per_check_under_the_source_layer():
    records = as_dicts()
    assert [r["check_name"] for r in records] == [r["check_name"] for r in RESULTS]
    assert {(r["run_id"], r["layer"], r["dataset"]) for r in records} == {("run-1", "source", "green_taxi")}


def test_block_is_recorded_as_fail_like_the_sql_gates():
    severities = {r["check_name"]: (r["severity"], r["status"]) for r in as_dicts()}
    assert severities["row_count_not_empty"] == ("FAIL", "PASS")
    assert severities["trip_distance_non_negative"] == ("FAIL", "FAIL")
    assert severities["fare_amount_non_negative"] == ("INFO", "INFO")


def test_every_severity_the_gate_emits_has_a_mapping():
    emitted = set(re.findall(r'severity="(\w+)"', Path(source_gate.__file__).read_text(encoding="utf-8")))
    assert emitted, "found no severities in source_gate.py; check the pattern"
    assert emitted <= set(source_gate.CONTROL_SEVERITY)


def test_the_revision_falls_back_to_the_same_sentinel_as_the_sql_gates():
    assert {r["code_revision"] for r in as_dicts("abc123")} == {"abc123"}
    assert {r["code_revision"] for r in as_dicts("")} == {"UNSET"}
    assert {r["code_revision"] for r in as_dicts(None)} == {"UNSET"}


def test_lineage_points_at_the_inputs_not_at_a_batch():
    record = as_dicts()[0]
    assert record["batch_id"] is None and record["source_version_id"] is None
    assert record["evidence_location"] == "/Volumes/a.parquet, /Volumes/b.parquet"


def test_an_info_check_keeps_its_null_threshold():
    fare = next(r for r in as_dicts() if r["check_name"] == "fare_amount_non_negative")
    assert fare["threshold_pct"] is None
    assert isinstance(fare["fail_pct"], float)
