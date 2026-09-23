"""D26: pipeline_runs gained previous_attempt_run_id, and a stuck-run check.

Two ways this regresses silently:

1. `pipeline_runs` is written with a positional `INSERT ... SELECT`, not a
   named column list. Add a column to the DDL and forget to add a matching
   value to the INSERT, and every row after that shifts one column to the
   left -- `status` lands in `completed_at`, `previous_attempt_run_id` lands
   in `status`, and nothing errors, because every column here is STRING or
   TIMESTAMP and Delta does not reject a wrongly-shifted write.
2. `CREATE TABLE IF NOT EXISTS` is a no-op on a table that already exists
   (the same gotcha documented for Gold). On an already-deployed dev table,
   the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` line is what actually lands
   the column -- delete it and the DDL file still looks complete.

These tests hold both in place, plus the presence of the no_stuck_runs check
added alongside them.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_TABLES = REPO_ROOT / "etl/01_control/00_create_control_tables.sql"
CONTROL_GATE = REPO_ROOT / "etl/01_control/90_validate_control.sql"


def strip_sql_comments(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _split_top_level(body):
    entries, current, depth, in_string = [], [], 0, False
    for char in body:
        if in_string:
            in_string = char != "'"
        elif char == "'":
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            entries.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        entries.append(tail)
    return [e for e in entries if e]


def pipeline_runs_ddl_columns():
    """Column names from pipeline_runs' CREATE TABLE, in declared order."""
    text = strip_sql_comments(CONTROL_TABLES.read_text(encoding="utf-8"))
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS `ftw-week-08`\.`01-control`\.pipeline_runs\s*\((.*?)\)\s*\nUSING DELTA",
        text, re.DOTALL,
    )
    assert match, "could not find pipeline_runs' CREATE TABLE block in 00_create_control_tables.sql"
    return [entry.split()[0] for entry in _split_top_level(match.group(1))]


def pipeline_runs_insert_values():
    """The SELECT values of the pipeline_runs INSERT, in order."""
    text = strip_sql_comments(CONTROL_GATE.read_text(encoding="utf-8"))
    match = re.search(
        r"INSERT INTO `ftw-week-08`\.`01-control`\.pipeline_runs\s*\nSELECT\s+([^;]+);",
        text,
    )
    assert match, "could not find the pipeline_runs INSERT in 90_validate_control.sql"
    return _split_top_level(match.group(1))


def test_pipeline_runs_ddl_has_previous_attempt_run_id():
    assert "previous_attempt_run_id" in pipeline_runs_ddl_columns(), (
        "pipeline_runs' CREATE TABLE no longer declares previous_attempt_run_id."
    )


def test_the_column_is_also_landed_by_a_migration():
    """CREATE TABLE IF NOT EXISTS does nothing on a table that already
    exists. Without this ALTER TABLE, an already-deployed dev table never
    gets the column even though the DDL file looks complete."""
    text = strip_sql_comments(CONTROL_TABLES.read_text(encoding="utf-8"))
    assert re.search(
        r"ALTER TABLE `ftw-week-08`\.`01-control`\.pipeline_runs\s*\n"
        r"ADD COLUMN IF NOT EXISTS previous_attempt_run_id",
        text,
    ), "no ALTER TABLE ... ADD COLUMN IF NOT EXISTS previous_attempt_run_id found"


def test_the_insert_supplies_one_value_per_column():
    """The INSERT is positional. A column added to the DDL without a
    matching value here does not error -- it silently shifts every value
    after it one column to the left."""
    columns = pipeline_runs_ddl_columns()
    values = pipeline_runs_insert_values()
    assert len(values) == len(columns), (
        f"pipeline_runs has {len(columns)} columns {columns} but the INSERT "
        f"supplies {len(values)} values {values}. A positional mismatch here "
        "silently shifts every value into the wrong column."
    )


def test_the_insert_leaves_previous_attempt_run_id_null_for_now():
    """D26 Option A: population is deferred, so today's INSERT should
    write NULL for this column, not a real value. If this starts failing
    because a real value is now supplied, that's Option B landing -- update
    this test (and D26) rather than treating it as a regression."""
    columns = pipeline_runs_ddl_columns()
    values = pipeline_runs_insert_values()
    index = columns.index("previous_attempt_run_id")
    assert values[index] == "NULL", (
        f"expected NULL for previous_attempt_run_id (D26, Option A), found {values[index]!r}"
    )


def test_no_stuck_runs_check_exists_and_targets_pipeline_runs():
    """Mirrors no_stuck_batches (check 4), but for pipeline_runs itself."""
    text = strip_sql_comments(CONTROL_GATE.read_text(encoding="utf-8"))
    match = re.search(r"INSERT INTO `ftw-week-08`\.`01-control`\.data_quality_results\s*\nSELECT([^;]+);", text)
    statements = re.findall(
        r"INSERT INTO `ftw-week-08`\.`01-control`\.data_quality_results\s*\nSELECT([^;]+);", text
    )
    stuck_run_statements = [s for s in statements if "'no_stuck_runs'" in s]
    assert stuck_run_statements, "no INSERT containing the 'no_stuck_runs' check_name was found"
    assert "'pipeline_runs'" in stuck_run_statements[0], (
        "the no_stuck_runs check does not record dataset = 'pipeline_runs'"
    )


def test_no_stuck_runs_runs_after_the_run_is_finalized():
    """Placed after the UPDATE that finalizes this run's own status, so a
    run can't flag itself as stuck just for being young."""
    text = strip_sql_comments(CONTROL_GATE.read_text(encoding="utf-8"))
    update_pos = text.find("UPDATE `ftw-week-08`.`01-control`.pipeline_runs")
    check_pos = text.find("'no_stuck_runs'")
    assert update_pos != -1 and check_pos != -1, "expected both the UPDATE and the no_stuck_runs check to be present"
    assert update_pos < check_pos, (
        "no_stuck_runs check appears before the pipeline_runs UPDATE -- it would "
        "see this run still as STARTED and could flag itself"
    )