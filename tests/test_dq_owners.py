"""Every data-quality check names its owner (#126).

#161 replaced the 'TODO' owner in every gate, but a check added by a PR that
merged just before it (#146's no_stuck_runs) kept the placeholder. Nothing
failed, because nothing checked. These tests hold every gate, SQL and
source, to a named owner, so the next new check can't ship with a
placeholder.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ingestion import source_gate  # noqa: E402

SQL_GATES = sorted((REPO_ROOT / "etl").glob("*/90_validate_*.sql"))
PLACEHOLDERS = {"", "TODO", "TBD", "UNKNOWN"}


def placeholder_owner_lines(text):
    """Line numbers where a gate writes 'TODO' as a value, ignoring comments."""
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if re.search(r"'TODO'", line.split("--", 1)[0])
    ]


def test_every_sql_gate_is_found():
    assert len(SQL_GATES) >= 10, f"expected the ten gate files, found {len(SQL_GATES)}"


def test_no_sql_gate_writes_a_placeholder_owner():
    found = {
        str(path.relative_to(REPO_ROOT)): lines
        for path in SQL_GATES
        if (lines := placeholder_owner_lines(path.read_text(encoding="utf-8")))
    }
    assert not found, f"these gates still write a 'TODO' owner: {found}"


def test_the_rule_would_catch_the_leftover():
    leftover = "    code_revision,\n    'TODO',\n    NULL,\n"
    commented = "    'Ina Magno',  -- was 'TODO' before #126\n"
    assert placeholder_owner_lines(leftover) == [2]
    assert placeholder_owner_lines(commented) == []


def test_the_source_gate_names_an_owner():
    result = source_gate.create_result("row_count_not_empty", "VOLUME", "BLOCK", 0, 1, 0.0, "rows: 1")
    rows = source_gate.control_rows(
        source="green_taxi",
        inputs=["/Volumes/a.parquet"],
        results=[result],
        run_id="run-1",
        code_revision="abc123",
    )
    owners = {dict(zip(source_gate.CONTROL_COLUMNS, row))["owner"] for row in rows}
    assert owners and not owners & PLACEHOLDERS, f"the source gate records owner {owners}"
