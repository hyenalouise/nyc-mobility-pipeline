"""Every gate result must trace to the commit that produced it.

All ten gates used to stamp a hardcoded sentinel, so `data_quality_results`
and `pipeline_runs` recorded a constant as the code version. The lineage chain
reached the source file and the run, but not the logic — which is the link you
need when a number is wrong.

Gold made it worse by spelling its sentinel differently, so "no revision
recorded" had two values while `gate_status` aggregates with
MAX(code_revision).

These tests hold the fix in place. A new gate that forgets the parameter, or a
revert to a hardcoded value, fails here rather than six weeks later during an
incident.
"""
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
GATES = sorted(REPO_ROOT.glob("etl/*/90_validate_*.sql"))
JOB_NAME = "NYC_Mobility_Pipeline"

MARKER = ":code_revision"
# Verified on the workspace 2026-09-22: `SET VARIABLE x = :marker` binds when a
# value is supplied, so the session variable stays and only the assignment
# changes. What must not come back is a literal.
ASSIGNS_LITERAL = re.compile(r"SET\s+VARIABLE\s+\w*code_revision\s*=\s*'", re.IGNORECASE)


def strip_sql_comments(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def job():
    return yaml.safe_load((REPO_ROOT / "databricks.yml").read_text(encoding="utf-8"))[
        "resources"]["jobs"][JOB_NAME]


def test_the_gates_were_found():
    """Guards the glob: an empty list would make every test below vacuous."""
    assert len(GATES) == 10


@pytest.mark.parametrize("path", GATES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_a_gate_takes_its_revision_from_the_job_parameter(path):
    assert MARKER in strip_sql_comments(path.read_text(encoding="utf-8")), (
        f"{path.relative_to(REPO_ROOT)} does not read the {MARKER} parameter, so its "
        "results cannot be traced to a commit."
    )


@pytest.mark.parametrize("path", GATES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_a_gate_does_not_hardcode_its_revision(path):
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    assert not ASSIGNS_LITERAL.search(code), (
        f"{path.relative_to(REPO_ROOT)} assigns a literal revision. That is how a "
        "constant ended up on every historical result row."
    )


def test_the_sentinel_is_spelled_one_way():
    """gate_status aggregates with MAX(code_revision). Two spellings of
    'no revision recorded' -- Gold used 'not_provided' -- make that ambiguous."""
    sentinels = set()
    for path in GATES:
        sentinels.update(re.findall(r"'UNSET'|'not_provided'", path.read_text(encoding="utf-8")))
    assert sentinels <= {"'UNSET'"}, f"mixed sentinels across the gates: {sentinels}"


def test_the_job_supplies_the_parameter():
    """A job-level parameter reaches a sql_task without per-task wiring, so one
    entry covers all ten gates. Without it every gate fails at runtime with
    UNBOUND_SQL_PARAMETER."""
    names = {p["name"] for p in job().get("parameters", [])}
    assert "code_revision" in names, (
        "databricks.yml declares no job parameter 'code_revision'. Every gate reads "
        ":code_revision and would fail with UNBOUND_SQL_PARAMETER."
    )


def test_the_parameter_resolves_to_the_deployed_commit():
    """A constant here would make every run claim the same revision."""
    default = next(p for p in job()["parameters"] if p["name"] == "code_revision")["default"]
    assert default == "${bundle.git.commit}", f"expected the deploy-time commit, found {default!r}"


def test_the_recorded_revision_is_the_commit_that_runs():
    """The source commit and the recorded revision must come from one
    substitution, or the job can run one commit while recording another."""
    parameter = next(p for p in job()["parameters"] if p["name"] == "code_revision")["default"]
    assert parameter == job()["git_source"]["git_commit"]


# ---------------------------------------------------------------------------
# An INSERT column list holds identifiers. A mechanical edit that puts an
# expression there fails with PARSE_SYNTAX_ERROR, and Gold is the only gate
# with an explicit column list -- so it is the one file where a careless
# find-and-replace breaks something the other nine would not reveal.
# ---------------------------------------------------------------------------

INSERT_HEAD = re.compile(r"INSERT\s+(?:INTO|OVERWRITE)\s+[^\s(]+\s*\(", re.IGNORECASE)
FOLLOWS_COLUMN_LIST = re.compile(r"(SELECT|WITH|VALUES)\b", re.IGNORECASE)
IDENTIFIER = re.compile(r"^`?[A-Za-z_]\w*`?$")


def _scan_to_close(text, start):
    depth, index, in_string = 1, start, False
    while index < len(text):
        char = text[index]
        if in_string:
            in_string = char != "'"
        elif char == "'":
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


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


def insert_column_lists(sql):
    text = strip_sql_comments(sql)
    for match in INSERT_HEAD.finditer(text):
        close = _scan_to_close(text, match.end())
        if close is None:
            continue
        if not FOLLOWS_COLUMN_LIST.match(text[close + 1:].lstrip()):
            continue
        yield _split_top_level(text[match.end():close])


def test_the_column_list_rule_catches_its_regression():
    broken = ("INSERT INTO `c`.`s`.t (\n    run_id,\n"
              "    COALESCE(NULLIF(:code_revision, ''), 'UNSET'),\n    layer\n)\nSELECT 1, 2, 3;")
    fine = "INSERT INTO `c`.`s`.t (\n    run_id,\n    code_revision,\n    layer\n)\nSELECT 1, 2, 3;"
    assert any(not IDENTIFIER.match(e) for e in next(insert_column_lists(broken)))
    assert all(IDENTIFIER.match(e) for e in next(insert_column_lists(fine)))


@pytest.mark.parametrize(
    "path", sorted(REPO_ROOT.glob("etl/*/*.sql")), ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_insert_column_lists_hold_only_column_names(path):
    offenders = []
    for entries in insert_column_lists(path.read_text(encoding="utf-8")):
        offenders.extend(e for e in entries if not IDENTIFIER.match(e))
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: an INSERT column list must name columns, "
        f"not expressions: {offenders}"
    )
