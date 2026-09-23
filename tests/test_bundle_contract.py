"""databricks.yml is only the source of truth for the job if it is deployable.

It carried `resources:` alone until issue #117 — which reads like a bundle but
`databricks bundle validate` rejects before it reaches the job definition, so
changing the job by changing this file was never actually possible.

These tests hold the shape in place, and guard the three per-workspace
identifiers that were frozen into a file meant to be portable. Since #132 they
also hold the schedule, which has two easy ways to go quietly wrong.
"""
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = REPO_ROOT / "databricks.yml"
JOB_NAME = "NYC_Mobility_Pipeline"


def bundle():
    return yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))


def job():
    return bundle()["resources"]["jobs"][JOB_NAME]


def schedule():
    return job().get("schedule") or {}


def strip_yaml_comments(text):
    """Drop '#' comments. databricks.yml is YAML, not SQL."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def quartz_problem(expression):
    """Why `expression` is not a usable Quartz cron, or None if it is."""
    fields = expression.split()
    if len(fields) not in (6, 7):
        return f"{len(fields)} fields; Quartz needs 6 or 7, seconds first (crontab has 5)"
    day_of_month, day_of_week = fields[3], fields[5]
    if (day_of_month == "?") == (day_of_week == "?"):
        return "exactly one of day-of-month and day-of-week must be '?'"
    return None


# --- deployability -------------------------------------------------------

def test_the_bundle_is_deployable():
    document = bundle()
    assert document.get("bundle", {}).get("name"), (
        "databricks.yml declares no bundle name, so it is a job definition rather "
        "than a bundle and cannot be deployed."
    )
    assert document.get("targets"), "databricks.yml declares no targets to deploy to."


def test_exactly_one_target_is_the_default():
    defaults = [name for name, spec in bundle()["targets"].items() if (spec or {}).get("default")]
    assert len(defaults) == 1, f"expected one default target, found {defaults}"


def test_the_default_target_is_not_production():
    """An accidental bare `databricks bundle deploy` must not land on prod."""
    targets = bundle()["targets"]
    default = next(n for n, s in targets.items() if (s or {}).get("default"))
    assert targets[default].get("mode") != "production", (
        f"target {default!r} is both the default and production mode."
    )


# --- the identifiers that were frozen into the file ----------------------

def test_the_warehouse_is_declared_once():
    """A warehouse id is per workspace. It was written out 30 times, so the
    first deploy to a workspace whose warehouse differed needed 30 edits."""
    # [^\S\n] is "whitespace but not a newline": the declaration line in
    # `variables:` is `warehouse_id:` with nothing after it, and a pattern
    # crossing the newline would match the next key as if it were a value.
    literals = re.findall(
        r"warehouse_id:[^\S\n]*(?!\$\{)(\S+)", strip_yaml_comments(BUNDLE_PATH.read_text(encoding="utf-8"))
    )
    assert not literals, (
        f"warehouse_id is hardcoded in {len(literals)} place(s): {sorted(set(literals))}. "
        "Reference ${var.warehouse_id} so it is declared once."
    )


def test_the_warehouse_variable_exists():
    assert "warehouse_id" in bundle().get("variables", {}), (
        "tasks reference ${var.warehouse_id} but no such bundle variable is declared."
    )


def test_every_target_declares_its_workspace_host():
    """Deploying must not depend on which workspace the operator is logged in to."""
    missing = [
        name for name, spec in bundle()["targets"].items()
        if not (spec or {}).get("workspace", {}).get("host")
    ]
    assert not missing, (
        f"target(s) {missing} declare no workspace host, so a deploy lands wherever "
        "the operator is authenticated."
    )


def test_no_credentials_are_committed():
    """A host is an address. A token is not, and must never appear here."""
    leaked = re.findall(
        r"(?i)(token|password|secret|client_secret)\s*:\s*\S+",
        strip_yaml_comments(BUNDLE_PATH.read_text(encoding="utf-8")),
    )
    assert not leaked, f"credential-looking entries in databricks.yml: {leaked}"


# --- what runs must be what is recorded ----------------------------------

def test_the_source_is_pinned_to_a_commit():
    """A branch resolves at run time; ${bundle.git.commit} resolves at deploy
    time. Mixing them lets the job run one commit while recording another."""
    source = job()["git_source"]
    assert "git_branch" not in source and "git_tag" not in source, (
        "git_source is pinned to a moving ref. The job would run whatever that ref "
        "points at when it starts, not the commit that was deployed."
    )
    assert source["git_commit"] == "${bundle.git.commit}"


# --- the schedule (#132) -------------------------------------------------

def test_the_job_runs_on_a_schedule():
    """Before #132 every run was started by hand, so "how does it run
    tomorrow" had no answer and freshness had no interval to measure against."""
    assert schedule().get("quartz_cron_expression"), "the job has no schedule."


def test_the_schedule_is_quartz_not_crontab():
    """Databricks reads Quartz: seconds first, and '?' in one of the two day
    fields. A crontab line such as "0 6 * * 1" is not a Quartz expression."""
    expression = schedule()["quartz_cron_expression"]
    problem = quartz_problem(expression)
    assert problem is None, f"{expression!r}: {problem}"


def test_the_schedule_is_in_new_york_time():
    """The reporting timezone. 06:00 in any other zone is a different hour."""
    assert schedule().get("timezone_id") == "America/New_York"


def test_the_target_decides_whether_the_schedule_is_paused():
    """Development mode pauses schedules, so a dev deploy never fires on a
    timer. A pause_status on the job overrides that for every target: checked
    with `databricks bundle validate --target dev`, where an explicit UNPAUSED
    came out UNPAUSED."""
    assert "pause_status" not in schedule(), (
        "the schedule sets its own pause_status, which overrides development "
        "mode's pause: every dev sandbox would run on this timer."
    )
    for name, spec in bundle()["targets"].items():
        spec = spec or {}
        if spec.get("mode") == "development":
            assert (spec.get("presets") or {}).get("trigger_pause_status") != "UNPAUSED", (
                f"target {name!r} is development mode but unpauses its triggers."
            )


def test_the_quartz_rule_would_catch_its_regressions():
    assert quartz_problem("0 0 6 ? * MON") is None
    assert quartz_problem("0 6 * * 1") is not None      # crontab: five fields
    assert quartz_problem("0 0 6 * * MON") is not None  # both day fields set
    assert quartz_problem("0 0 6 ? * ?") is not None    # neither day field set


def test_the_rules_would_catch_their_regressions():
    pattern = r"warehouse_id:[^\S\n]*(?!\$\{)(\S+)"
    assert re.findall(pattern, "        warehouse_id: abc123\n") == ["abc123"]
    assert re.findall(pattern, "        warehouse_id: ${var.warehouse_id}\n") == []
    # The variable's own declaration is a key with no value on the line.
    assert re.findall(pattern, "  warehouse_id:\n    default: abc123\n") == []
