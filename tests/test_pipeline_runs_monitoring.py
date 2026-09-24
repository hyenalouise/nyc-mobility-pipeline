"""Regression tests for the no_stuck_runs check in the Control gate.

A pipeline run that crashes or hangs mid-execution leaves a row permanently
in STARTED. Without a check, that row sits in pipeline_runs unnoticed and
gives no signal that anything went wrong. These tests lock in the presence
and placement of the check that catches it.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_GATE = REPO_ROOT / "etl/01_control/90_validate_control.sql"


def strip_sql_comments(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def test_no_stuck_runs_check_exists_and_targets_pipeline_runs():
    text = strip_sql_comments(CONTROL_GATE.read_text(encoding="utf-8"))
    statements = re.findall(
        r"INSERT INTO `ftw-week-08`\.`01-control`\.data_quality_results\s*\nSELECT([^;]+);", text
    )
    stuck_run_statements = [s for s in statements if "'no_stuck_runs'" in s]
    assert stuck_run_statements, "no INSERT containing the 'no_stuck_runs' check_name was found"
    assert "'pipeline_runs'" in stuck_run_statements[0], (
        "the no_stuck_runs check does not record dataset = 'pipeline_runs'"
    )


def test_no_stuck_runs_runs_after_the_run_is_finalized():
    """The check must run after the UPDATE that finalizes this run's own
    status, so a run in progress cannot flag itself as stuck."""
    text = strip_sql_comments(CONTROL_GATE.read_text(encoding="utf-8"))
    update_pos = text.find("UPDATE `ftw-week-08`.`01-control`.pipeline_runs")
    check_pos = text.find("'no_stuck_runs'")
    assert update_pos != -1 and check_pos != -1, "expected both the UPDATE and the no_stuck_runs check to be present"
    assert update_pos < check_pos, (
        "no_stuck_runs check appears before the pipeline_runs UPDATE -- it would "
        "see this run still as STARTED and could flag itself"
    )


def test_no_stuck_runs_uses_the_existing_stuck_threshold():
    """Reuses stuck_after_hours rather than introducing a second threshold
    that could drift from the one no_stuck_batches already uses."""
    text = strip_sql_comments(CONTROL_GATE.read_text(encoding="utf-8"))
    check_pos = text.find("'no_stuck_runs'")
    assert check_pos != -1, "no_stuck_runs check not found"
    window = text[check_pos:check_pos + 800]
    assert "stuck_after_hours" in window, (
        "no_stuck_runs does not reference stuck_after_hours; it may be using a hardcoded threshold"
    )