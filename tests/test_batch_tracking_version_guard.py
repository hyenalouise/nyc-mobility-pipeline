"""Unit tests for the source_version_id guard in src/ingestion/batch_tracking.py.

These run without Spark or a Databricks workspace: `resolve_source_version_id`
only needs an object exposing `.sql(query, args=...).collect()`, so the control
table is faked here. The guard exists because D14 says a person confirms a
genuine content change before the version suffix moves, while the code used to
default to `_v1` unconditionally.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.batch_tracking import resolve_source_version_id  # noqa: E402

TABLE = "`ftw-week-08`.`01-control`.ingestion_batches"
SYSTEM = "green_taxi"
PERIOD = "2026-04"
ORIGINAL = "a" * 64
REVISED = "b" * 64


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def collect(self):
        return self._rows


class FakeSpark:
    """Returns canned rows, or raises, in place of a real control table."""

    def __init__(self, rows=None, error=None):
        self._rows = rows or []
        self._error = error
        self.calls = []

    def sql(self, query, args=None):
        self.calls.append((query, args))
        if self._error is not None:
            raise self._error
        return FakeResult(self._rows)


def row(digest, version):
    return {"content_sha256": digest, "source_version_id": version}


def test_first_batch_for_period_defaults_to_v1():
    spark = FakeSpark()
    assert (
        resolve_source_version_id(spark, TABLE, SYSTEM, PERIOD, ORIGINAL)
        == "green_taxi_2026-04_v1"
    )


def test_missing_control_table_is_treated_as_no_history():
    spark = FakeSpark(error=Exception("[TABLE_OR_VIEW_NOT_FOUND] table not found"))
    assert (
        resolve_source_version_id(spark, TABLE, SYSTEM, PERIOD, ORIGINAL)
        == "green_taxi_2026-04_v1"
    )


def test_unrelated_failure_is_not_swallowed():
    spark = FakeSpark(error=Exception("PERMISSION_DENIED"))
    with pytest.raises(Exception, match="PERMISSION_DENIED"):
        resolve_source_version_id(spark, TABLE, SYSTEM, PERIOD, ORIGINAL)


def test_identical_content_rediscovered_keeps_v1():
    spark = FakeSpark([row(ORIGINAL, "green_taxi_2026-04_v1")])
    assert (
        resolve_source_version_id(spark, TABLE, SYSTEM, PERIOD, ORIGINAL)
        == "green_taxi_2026-04_v1"
    )


def test_revised_content_without_explicit_label_is_refused():
    spark = FakeSpark([row(ORIGINAL, "green_taxi_2026-04_v1")])
    with pytest.raises(ValueError) as excinfo:
        resolve_source_version_id(spark, TABLE, SYSTEM, PERIOD, REVISED)
    message = str(excinfo.value)
    assert "green_taxi_2026-04_v1" in message
    assert REVISED in message
    assert "D04" in message


def test_revised_content_with_explicit_label_is_allowed():
    spark = FakeSpark([row(ORIGINAL, "green_taxi_2026-04_v1")])
    assert (
        resolve_source_version_id(
            spark, TABLE, SYSTEM, PERIOD, REVISED,
            source_version_label="green_taxi_2026-04_v2",
        )
        == "green_taxi_2026-04_v2"
    )


def test_reusing_a_label_against_different_content_is_refused():
    spark = FakeSpark([row(ORIGINAL, "green_taxi_2026-04_v1")])
    with pytest.raises(ValueError, match="already recorded"):
        resolve_source_version_id(
            spark, TABLE, SYSTEM, PERIOD, REVISED,
            source_version_label="green_taxi_2026-04_v1",
        )
