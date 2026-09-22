"""Guard against a SQL shape that only fails on a first run.

`IN ((SELECT ...))` wraps the subquery in an extra pair of parentheses, which
makes it a *scalar* subquery expression rather than a subquery list. It
succeeds while the inner query returns zero or one row, and fails with
SCALAR_SUBQUERY_TOO_MANY_ROWS (SQLSTATE 21000) the moment it returns two.

That is why it survived so long. The Bronze loaders only reach the statement
for files they consider new, and every run had been incremental -- one month at
a time, or nothing new at all. A first run into an empty schema makes all three
Green Taxi files new in one run, and the loader fails on its first statement.

A bug that hides on every rerun and only appears on a first run is the worst
kind for a pipeline other people are supposed to be able to stand up.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_FILES = sorted(REPO_ROOT.glob("etl/*/*.sql"))

# IN, an opening paren, then ANOTHER opening paren wrapping a SELECT.
DOUBLE_WRAPPED = re.compile(r"\bIN\s*\(\s*\(\s*SELECT\b", re.IGNORECASE)

# Removing the inner parentheses by deleting the projection as well leaves
# `IN ( FROM t)`. Databricks reads `FROM t` as shorthand for `SELECT * FROM t`,
# so it parses -- and then fails, because an IN subquery must return exactly
# one column while these views have several. A different error for the same
# statement, which is why the shape is worth naming.
BARE_FROM_SUBQUERY = re.compile(r"\bIN\s*\(\s*FROM\b", re.IGNORECASE)


def strip_sql_comments(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def offending_lines(path, pattern):
    return [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(
            strip_sql_comments(path.read_text(encoding="utf-8")).splitlines(), 1
        )
        if pattern.search(line)
    ]


def test_the_sql_files_were_found():
    """Guards the glob: an empty list would make the checks below vacuous."""
    assert len(SQL_FILES) > 20


def test_the_rules_catch_their_regressions():
    broken = "  AND content_sha256 IN ((SELECT content_sha256 FROM green_taxi_new_files));"
    bare = "  AND content_sha256 IN ( FROM green_taxi_new_files);"
    fixed = "  AND content_sha256 IN (SELECT content_sha256 FROM green_taxi_new_files);"

    assert DOUBLE_WRAPPED.search(broken)
    assert not DOUBLE_WRAPPED.search(fixed)
    assert BARE_FROM_SUBQUERY.search(bare)
    assert not BARE_FROM_SUBQUERY.search(fixed)
    # A comment describing the mistake must not trip either rule.
    assert not DOUBLE_WRAPPED.search(strip_sql_comments("-- never write IN ((SELECT x))\n"))


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_no_subquery_is_wrapped_as_a_scalar(path):
    offenders = offending_lines(path, DOUBLE_WRAPPED)
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: 'IN ((SELECT ...))' is a scalar subquery and "
        "raises SCALAR_SUBQUERY_TOO_MANY_ROWS as soon as it matches more than one row. "
        "Use 'IN (SELECT ...)':\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_in_subqueries_name_their_column(path):
    offenders = offending_lines(path, BARE_FROM_SUBQUERY)
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: an IN subquery must project exactly one column. "
        "'IN ( FROM t)' is shorthand for 'SELECT * FROM t' and returns every column:\n"
        + "\n".join(offenders)
    )
