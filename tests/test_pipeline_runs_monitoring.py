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


def test_no_stuck_runs_excludes_its_own_run():
    """The check must exclude the current run's own row explicitly, so a
    run in progress cannot flag itself as stuck regardless of where this
    check falls relative to the UPDATE that finalizes the run's status."""
    text = strip_sql_comments(CONTROL_GATE.read_text(encoding="utf-8"))
    check_pos = text.find("'no_stuck_runs'")
    assert check_pos != -1, "no_stuck_runs check not found"
    window = text[check_pos:check_pos + 800]
    assert "run_id <> dq_run_id" in window, (
        "no_stuck_runs does not exclude its own run_id -- it could flag "
        "itself while still in progress"
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