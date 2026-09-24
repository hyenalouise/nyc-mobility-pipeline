import argparse
import inspect
import json
import sys
import uuid
from pathlib import Path

import duckdb


# Resolved from this file, not from the working directory. As a job task the
# script runs from a Git checkout whose working directory is not guaranteed
# to be the repository root, so a relative path could miss the contract.
#
# Databricks runs a job's Python file with exec(compile(source, path,
# "exec")), which defines no __file__ (run 329476320889065 failed on it).
# The compiled code still carries the path it was compiled from.
REPO_ROOT = Path(inspect.currentframe().f_code.co_filename).resolve().parents[2]

CONTRACT_PATH = REPO_ROOT / "config" / "source_contract.json"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "proof" / "source-validation"

# Green Taxi keeps its original, already-committed filename (results.json,
# referenced by docs/duckdb/evidence.md) so this fix stays backward
# compatible. Any other source falls back to a per-source filename instead
# of sharing that path -- which is what let a taxi_zones run silently
# overwrite Green Taxi's committed evidence before this fix.
DEFAULT_EVIDENCE_PATHS = {
    "green_taxi": EVIDENCE_DIR / "results.json",
}


def default_evidence_path(source):
    return DEFAULT_EVIDENCE_PATHS.get(
        source,
        EVIDENCE_DIR / f"{source}_results.json",
    )

# Local view name each source is loaded into. Kept separate per source so a
# --source green_taxi run and a --source taxi_zones run can never silently
# read the wrong view if this module is ever extended to check more than
# one source in the same process.
VIEW_NAMES = {
    "green_taxi": "green_taxi_source",
    "taxi_zones": "taxi_zones_source",
    "weather": "weather_source",
}

# Weather's hourly data arrives as four parallel arrays (hourly.time,
# .temperature_2m, .precipitation, .weather_code), not rows. Rather than
# writing array-indexing SQL for every row-level check, create_weather_view
# also builds this second view -- one row per hour, via UNNEST -- so every
# row-level check below is the same plain SQL as Green Taxi's, and
# get_columns()/create_result() stay unaware weather is array-shaped at all.
# Not registered in VIEW_NAMES: it's an internal detail of the weather
# loader, not a --source choice of its own.
WEATHER_HOURLY_VIEW = "weather_hourly_source"

# Exit codes are a supported interface: CI (.github/workflows/ci.yml) and
# any orchestrating job branch on these values, not just on zero-vs-nonzero.
# Keep this table and docs/duckdb/source_gate.md in sync with each other.
EXIT_ACCEPTED = 0
EXIT_BLOCKED = 1
EXIT_INVALID_CONFIGURATION = 2
EXIT_INPUT_UNAVAILABLE = 3


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def sql_list(values):
    escaped = [
        "'" + value.replace("'", "''") + "'"
        for value in values
    ]

    return "[" + ", ".join(escaped) + "]"


def calculate_status(
    severity,
    fail_count,
    total_count,
    threshold_pct,
):
    if severity == "INFO":
        return "INFO"

    if fail_count == 0:
        return "PASS"

    fail_pct = (
        0.0
        if total_count == 0
        else fail_count * 100.0 / total_count
    )

    if severity == "BLOCK":
        return "FAIL"

    if severity == "WARN" and fail_pct > threshold_pct:
        return "FAIL"

    return "WARN"


def create_result(
    check_name,
    check_type,
    severity,
    fail_count,
    total_count,
    threshold_pct,
    details,
):
    fail_count = int(fail_count or 0)
    total_count = int(total_count or 0)

    fail_pct = (
        0.0
        if total_count == 0
        else fail_count * 100.0 / total_count
    )

    status = calculate_status(
        severity,
        fail_count,
        total_count,
        threshold_pct,
    )

    return {
        "check_name": check_name,
        "check_type": check_type,
        "severity": severity,
        "status": status,
        "fail_count": fail_count,
        "total_count": total_count,
        "fail_pct": round(fail_pct, 4),
        "threshold_pct": threshold_pct,
        "details": details,
    }


def scalar(connection, query):
    return connection.execute(query).fetchone()[0]


def create_green_taxi_view(connection, inputs):
    """Green Taxi ships as parquet, one file per month, unioned by name."""
    input_list = sql_list(inputs)

    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW {VIEW_NAMES['green_taxi']} AS
        SELECT *
        FROM read_parquet(
            {input_list},
            union_by_name = true,
            filename = true
        )
        """
    )


def create_taxi_zones_view(connection, inputs):
    """Taxi Zones ships as a single CSV snapshot with a header row."""
    input_list = sql_list(inputs)

    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW {VIEW_NAMES['taxi_zones']} AS
        SELECT *
        FROM read_csv(
            {input_list},
            header = true,
            filename = true
        )
        """
    )


def create_weather_view(connection, inputs):
    """Weather ships as one landed JSON response per window, not a flat
    file. Unlike Green Taxi/Taxi Zones' `SELECT *` (which tolerates any
    column being absent, since it never names one), this source's checks
    need to reference specific fields -- but naming a field that is
    entirely absent from the JSON (not merely null: genuinely missing, so
    DuckDB's schema auto-detection never creates it) raises a Binder Error
    that would otherwise surface as an opaque "unreadable input" instead of
    a diagnosable required_columns failure.

    So this view stays a plain `SELECT *`: whatever top-level keys exist,
    including `hourly` as one nested struct column if present. Checking for
    latitude/longitude/elevation/hourly by name, and only then reaching
    into hourly's own fields, is run_weather_checks' job, not this
    function's -- that's what lets a genuinely missing field show up as a
    named, evidenced BLOCKED check instead of a crash.
    """
    input_list = sql_list(inputs)

    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW {VIEW_NAMES['weather']} AS
        SELECT *
        FROM read_json(
            {input_list},
            union_by_name = true
        )
        """
    )


# Keyed by --source. Each entry pairs the loader with the view it created,
# so main() does not need a chain of if/elif to pick the right reader.
SOURCE_LOADERS = {
    "green_taxi": create_green_taxi_view,
    "taxi_zones": create_taxi_zones_view,
    "weather": create_weather_view,
}


def get_columns(connection, view_name):
    rows = connection.execute(
        f"""
        DESCRIBE
        SELECT *
        FROM {view_name}
        """
    ).fetchall()

    return [row[0] for row in rows]


def run_green_taxi_checks(connection, contract):
    view = VIEW_NAMES["green_taxi"]
    results = []

    total_rows = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        """,
    )

    columns = get_columns(connection, view)

    required_columns = contract["required_columns"]

    missing_columns = [
        column
        for column in required_columns
        if column not in columns
    ]

    # 1. Source readable
    results.append(
        create_result(
            check_name="source_readable",
            check_type="AVAILABILITY",
            severity="BLOCK",
            fail_count=0,
            total_count=1,
            threshold_pct=0.0,
            details=(
                "DuckDB successfully opened all configured "
                "Green Taxi source files."
            ),
        )
    )

    # 2. Source is not empty
    results.append(
        create_result(
            check_name="row_count_not_empty",
            check_type="VOLUME",
            severity="BLOCK",
            fail_count=1 if total_rows == 0 else 0,
            total_count=1,
            threshold_pct=0.0,
            details=f"Observed source rows: {total_rows}.",
        )
    )

    # 3. Row-count floor
    row_count_floor = contract["row_count_floor"]

    results.append(
        create_result(
            check_name="row_count_floor",
            check_type="VOLUME",
            severity="BLOCK",
            fail_count=(
                1
                if total_rows < row_count_floor
                else 0
            ),
            total_count=1,
            threshold_pct=0.0,
            details=(
                f"Observed rows: {total_rows}; "
                f"required minimum: {row_count_floor}."
            ),
        )
    )

    # 4. Required source columns
    results.append(
        create_result(
            check_name="required_columns",
            check_type="SCHEMA",
            severity="BLOCK",
            fail_count=len(missing_columns),
            total_count=len(required_columns),
            threshold_pct=0.0,
            details=(
                "All required columns are present."
                if not missing_columns
                else f"Missing columns: {missing_columns}."
            ),
        )
    )

    # Stop safely if later checks cannot reference required columns.
    if missing_columns:
        return results

    # 5. Pickup timestamp not null
    pickup_nulls = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE lpep_pickup_datetime IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="pickup_timestamp_not_null",
            check_type="NOT_NULL",
            severity="BLOCK",
            fail_count=pickup_nulls,
            total_count=total_rows,
            threshold_pct=0.0,
            details="Pickup timestamp is required.",
        )
    )

    # 6. Drop-off timestamp not null
    dropoff_nulls = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE lpep_dropoff_datetime IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="dropoff_timestamp_not_null",
            check_type="NOT_NULL",
            severity="BLOCK",
            fail_count=dropoff_nulls,
            total_count=total_rows,
            threshold_pct=0.0,
            details="Drop-off timestamp is required.",
        )
    )

    # 7. Trip distance nonnegative
    negative_distance = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE trip_distance < 0
        """,
    )

    results.append(
        create_result(
            check_name="trip_distance_non_negative",
            check_type="RANGE",
            severity="BLOCK",
            fail_count=negative_distance,
            total_count=total_rows,
            threshold_pct=0.0,
            details="Trip distance must be zero or greater.",
        )
    )

    # 7b. Fare amount nonnegative -- INFO, never blocking (D28). Negative fares
    # are a known source trait that Silver retains and flags (D15), and the
    # Bronze SQL gate reports the same count as INFO. A threshold here would
    # refuse a delivery the rest of the pipeline accepts.
    negative_fare_amount = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE fare_amount < 0
        """,
    )

    results.append(
        create_result(
            check_name="fare_amount_non_negative",
            check_type="RANGE",
            severity="INFO",
            fail_count=negative_fare_amount,
            total_count=total_rows,
            threshold_pct=None,
            details=(
                "Negative fares are a known source trait: retained "
                "and flagged in Silver (D15). Counted, never blocking."
            ),
        )
    )

    # 8. Drop-off after pickup
    invalid_trip_order = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE lpep_pickup_datetime IS NOT NULL
          AND lpep_dropoff_datetime IS NOT NULL
          AND lpep_dropoff_datetime
              <= lpep_pickup_datetime
        """,
    )

    results.append(
        create_result(
            check_name="dropoff_after_pickup",
            check_type="CONSISTENCY",
            severity="WARN",
            fail_count=invalid_trip_order,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                "Drop-off should occur after pickup. "
                "A maximum failure rate of 0.1% is tolerated."
            ),
        )
    )

    # 9. Expected reporting-window coverage
    reporting_window = contract["reporting_window"]
    reporting_start = reporting_window["start"]
    reporting_end = reporting_window["end"]

    outside_window = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE lpep_pickup_datetime IS NOT NULL
          AND (
                lpep_pickup_datetime
                    < CAST('{reporting_start}' AS TIMESTAMP)
                OR
                lpep_pickup_datetime
                    >= CAST('{reporting_end}' AS DATE)
                       + INTERVAL 1 DAY
              )
        """,
    )

    results.append(
        create_result(
            check_name="expected_month_coverage",
            check_type="DATE_COVERAGE",
            severity="WARN",
            fail_count=outside_window,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                f"Expected reporting window: "
                f"{reporting_start} through "
                f"{reporting_end}, inclusive."
            ),
        )
    )

    # 10. Passenger count above 8
    high_passenger_count = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE passenger_count > 8
        """,
    )

    results.append(
        create_result(
            check_name="passenger_count_gt_8",
            check_type="RANGE",
            severity="WARN",
            fail_count=high_passenger_count,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                "Passenger counts above 8 are flagged. "
                "A maximum failure rate of 0.1% is tolerated."
            ),
        )
    )

    # 11. VendorID domain
    invalid_vendor = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE VendorID IS NOT NULL
          AND VendorID NOT IN (1, 2, 6)
        """,
    )

    results.append(
        create_result(
            check_name="vendor_id_domain",
            check_type="DOMAIN",
            severity="WARN",
            fail_count=invalid_vendor,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                "Expected VendorID values are 1, 2, and 6."
            ),
        )
    )

    # 12. Payment type domain
    invalid_payment_type = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE payment_type IS NOT NULL
          AND payment_type NOT IN (
              0, 1, 2, 3, 4, 5, 6
          )
        """,
    )

    results.append(
        create_result(
            check_name="payment_type_domain",
            check_type="DOMAIN",
            severity="WARN",
            fail_count=invalid_payment_type,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                "Expected payment_type values are 0 through 6."
            ),
        )
    )

    # 13. RatecodeID domain
    invalid_ratecode = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE RatecodeID IS NOT NULL
          AND RatecodeID NOT IN (
              1, 2, 3, 4, 5, 6, 99
          )
        """,
    )

    results.append(
        create_result(
            check_name="ratecode_id_domain",
            check_type="DOMAIN",
            severity="WARN",
            fail_count=invalid_ratecode,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                "Expected RatecodeID values are "
                "1 through 6 and 99."
            ),
        )
    )

    # 14. Pickup and drop-off LocationID ranges
    invalid_location_ids = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE (
                PULocationID IS NOT NULL
                AND (
                    PULocationID < 1
                    OR PULocationID > 265
                )
              )
           OR (
                DOLocationID IS NOT NULL
                AND (
                    DOLocationID < 1
                    OR DOLocationID > 265
                )
              )
        """,
    )

    results.append(
        create_result(
            check_name="location_id_range",
            check_type="RANGE",
            severity="WARN",
            fail_count=invalid_location_ids,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                "Pickup and drop-off LocationID values "
                "must be between 1 and 265."
            ),
        )
    )

    # 15. Full source-row duplicate occurrences
    #
    # Explicitly group by the business columns.
    # Do not include the generated filename column.
    duplicate_occurrences = scalar(
        connection,
        f"""
        SELECT COALESCE(
            SUM(duplicate_count - 1),
            0
        )
        FROM (
            SELECT
                COUNT(*) AS duplicate_count
            FROM {view}
            GROUP BY
                VendorID,
                lpep_pickup_datetime,
                lpep_dropoff_datetime,
                store_and_fwd_flag,
                RatecodeID,
                PULocationID,
                DOLocationID,
                passenger_count,
                trip_distance,
                fare_amount,
                extra,
                mta_tax,
                tip_amount,
                tolls_amount,
                ehail_fee,
                improvement_surcharge,
                total_amount,
                payment_type,
                trip_type,
                congestion_surcharge,
                cbd_congestion_fee
            HAVING COUNT(*) > 1
        )
        """,
    )

    results.append(
        create_result(
            check_name="full_source_row_duplicate",
            check_type="DUPLICATE",
            severity="WARN",
            fail_count=duplicate_occurrences,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                "Identical source rows are measured before "
                "the Silver duplicate policy is applied."
            ),
        )
    )

    return results


def run_taxi_zones_checks(connection, contract):
    """Taxi Zones is a small, static reference snapshot (265 rows, one row
    per LocationID). It has no reporting window and no per-trip business
    rules, so its check set is deliberately smaller than Green Taxi's --
    the shared framework (create_result/calculate_status) is reused as-is;
    only the measure queries below are source-specific, per #124's scope.
    """
    view = VIEW_NAMES["taxi_zones"]
    results = []

    total_rows = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        """,
    )

    columns = get_columns(connection, view)

    required_columns = contract["required_columns"]

    missing_columns = [
        column
        for column in required_columns
        if column not in columns
    ]

    # 1. Source readable
    results.append(
        create_result(
            check_name="source_readable",
            check_type="AVAILABILITY",
            severity="BLOCK",
            fail_count=0,
            total_count=1,
            threshold_pct=0.0,
            details=(
                "DuckDB successfully opened the configured "
                "Taxi Zones source file."
            ),
        )
    )

    # 2. Source is not empty
    results.append(
        create_result(
            check_name="row_count_not_empty",
            check_type="VOLUME",
            severity="BLOCK",
            fail_count=1 if total_rows == 0 else 0,
            total_count=1,
            threshold_pct=0.0,
            details=f"Observed source rows: {total_rows}.",
        )
    )

    # 3. Row-count floor. Taxi Zones is a complete snapshot, not an
    # incremental feed, so the floor is the full expected row count (265),
    # not a nominal "at least 1" like Green Taxi's monthly files.
    row_count_floor = contract["row_count_floor"]

    results.append(
        create_result(
            check_name="row_count_floor",
            check_type="VOLUME",
            severity="BLOCK",
            fail_count=(
                1
                if total_rows < row_count_floor
                else 0
            ),
            total_count=1,
            threshold_pct=0.0,
            details=(
                f"Observed rows: {total_rows}; "
                f"required minimum: {row_count_floor}."
            ),
        )
    )

    # 4. Required source columns
    results.append(
        create_result(
            check_name="required_columns",
            check_type="SCHEMA",
            severity="BLOCK",
            fail_count=len(missing_columns),
            total_count=len(required_columns),
            threshold_pct=0.0,
            details=(
                "All required columns are present."
                if not missing_columns
                else f"Missing columns: {missing_columns}."
            ),
        )
    )

    # Stop safely if later checks cannot reference required columns.
    if missing_columns:
        return results

    # 5. LocationID not null. LocationID is the business key; a null here
    # cannot be joined against anywhere downstream.
    location_id_nulls = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE LocationID IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="location_id_not_null",
            check_type="NOT_NULL",
            severity="BLOCK",
            fail_count=location_id_nulls,
            total_count=total_rows,
            threshold_pct=0.0,
            details="LocationID is required.",
        )
    )

    # 6. LocationID uniqueness. A reference table maps one zone per id;
    # a duplicate id makes any join against it ambiguous.
    duplicate_location_ids = scalar(
        connection,
        f"""
        SELECT COALESCE(
            SUM(duplicate_count - 1),
            0
        )
        FROM (
            SELECT
                LocationID,
                COUNT(*) AS duplicate_count
            FROM {view}
            GROUP BY LocationID
            HAVING COUNT(*) > 1
        )
        """,
    )

    results.append(
        create_result(
            check_name="location_id_unique",
            check_type="DUPLICATE",
            severity="BLOCK",
            fail_count=duplicate_location_ids,
            total_count=total_rows,
            threshold_pct=0.0,
            details="Every LocationID must appear exactly once.",
        )
    )

    # 7. LocationID is a valid integer in range. Not-null and uniqueness
    # alone let a non-numeric value like "abc" through, since DuckDB's CSV
    # sniffer widens the whole column to VARCHAR the moment one row is
    # non-numeric, and a string is still non-null and still unique.
    # TRY_CAST catches both a value that cannot be an integer at all and one
    # that parses but falls outside the real 1-265 LocationID range, mirroring
    # Green Taxi's location_id_range check.
    invalid_location_id = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE LocationID IS NOT NULL
          AND (
                TRY_CAST(LocationID AS INTEGER) IS NULL
                OR TRY_CAST(LocationID AS INTEGER) < 1
                OR TRY_CAST(LocationID AS INTEGER) > 265
                OR TRY_CAST(LocationID AS DOUBLE) <> TRY_CAST(LocationID AS INTEGER)
              )
        """,
    )

    results.append(
        create_result(
            check_name="location_id_valid_integer",
            check_type="RANGE",
            severity="BLOCK",
            fail_count=invalid_location_id,
            total_count=total_rows,
            threshold_pct=0.0,
            details=(
                "LocationID must be an integer between 1 and 265, "
                "since it is the key trips join against."
            ),
        )
    )

    # 7. Borough not null. Every zone must resolve to a named borough for
    # any downstream aggregation by borough to be meaningful.
    borough_nulls = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        WHERE Borough IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="borough_not_null",
            check_type="NOT_NULL",
            severity="BLOCK",
            fail_count=borough_nulls,
            total_count=total_rows,
            threshold_pct=0.0,
            details="Borough is required.",
        )
    )

    return results


def run_weather_checks(connection, contract):
    """Weather is a request-window source (#125): a response covers the
    dates it was requested for, and nothing in the file says what those
    were. So "is this response complete" is checked two ways:
    hourly_series_has_no_gaps catches a hole inside the response's own
    first-to-last hour, and hourly_series_covers_requested_window checks
    the count and the first and last hour against the contract's
    requested_window, which is pinned to the same dates
    20_load_open_meteo.sql requests. The second is what catches a file cut
    short at either end, which the first cannot see, and it matches
    Bronze's hourly_volume check (days x 24) so a response this gate accepts
    is not refused by Bronze in the same run.
    """
    view = VIEW_NAMES["weather"]
    hourly_view = WEATHER_HOURLY_VIEW
    results = []

    total_responses = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {view}
        """,
    )

    columns = get_columns(connection, view)

    required_columns = contract["required_columns"]

    missing_columns = [
        column
        for column in required_columns
        if column not in columns
    ]

    # 1. Source readable
    results.append(
        create_result(
            check_name="source_readable",
            check_type="AVAILABILITY",
            severity="BLOCK",
            fail_count=0,
            total_count=1,
            threshold_pct=0.0,
            details=(
                "DuckDB successfully opened the configured "
                "weather source file(s) as JSON."
            ),
        )
    )

    # 2. At least one response landed.
    results.append(
        create_result(
            check_name="row_count_not_empty",
            check_type="VOLUME",
            severity="BLOCK",
            fail_count=1 if total_responses == 0 else 0,
            total_count=1,
            threshold_pct=0.0,
            details=f"Observed responses: {total_responses}.",
        )
    )

    # 3. Required top-level fields present -- latitude, longitude,
    # elevation, and hourly as a whole. Checked against a plain `SELECT *`
    # (create_weather_view), which never errors on an absent key, so a
    # response missing one of these shows up here rather than as a crash.
    results.append(
        create_result(
            check_name="required_columns",
            check_type="SCHEMA",
            severity="BLOCK",
            fail_count=len(missing_columns),
            total_count=len(required_columns),
            threshold_pct=0.0,
            details=(
                "All required top-level fields are present."
                if not missing_columns
                else f"Missing top-level fields: {missing_columns}."
            ),
        )
    )

    # Stop safely if later checks cannot reference required fields.
    if missing_columns or total_responses == 0:
        return results

    # 4. hourly's own fields (time, temperature_2m, precipitation,
    # weather_code) present. hourly existing as a column (check 3) does not
    # guarantee its own sub-fields do, and dot-accessing a missing one
    # raises a Binder Error. So the keys hourly actually has are read first
    # (json_keys over every response) and compared by name, which reports
    # exactly which fields are missing. A key that is present but null
    # still counts as present here; its nulls are caught by the not-null
    # checks below.
    required_hourly_fields = contract["required_hourly_fields"]

    try:
        hourly_keys = {
            row[0]
            for row in connection.execute(
                f"""
                SELECT DISTINCT UNNEST(json_keys(to_json(hourly)))
                FROM {view}
                WHERE hourly IS NOT NULL
                """
            ).fetchall()
        }
    except duckdb.Error:
        # hourly is not an object at all (a string, a list), so it has no
        # keys: every required field is missing.
        hourly_keys = set()

    missing_hourly_fields = [
        field
        for field in required_hourly_fields
        if field not in hourly_keys
    ]

    results.append(
        create_result(
            check_name="required_hourly_fields",
            check_type="SCHEMA",
            severity="BLOCK",
            fail_count=len(missing_hourly_fields),
            total_count=len(required_hourly_fields),
            threshold_pct=0.0,
            details=(
                "hourly.time, .temperature_2m, .precipitation, and .weather_code are all present."
                if not missing_hourly_fields
                else f"hourly is missing required fields: {missing_hourly_fields}."
            ),
        )
    )

    if missing_hourly_fields:
        return results

    # 4b. Only reached when every field is present but the four cannot be
    # flattened into rows, for example a field that is a single value
    # rather than an array. Reported as its own check so a type problem is
    # never mistaken for a missing field. Absent from the evidence of a
    # response that flattens, like every check after an early return.
    try:
        connection.execute(
            f"""
            CREATE OR REPLACE TEMP VIEW {hourly_view} AS
            SELECT
                UNNEST(hourly.time::VARCHAR[]) AS time,
                UNNEST(hourly.temperature_2m)  AS temperature_2m,
                UNNEST(hourly.precipitation)   AS precipitation,
                UNNEST(hourly.weather_code)    AS weather_code
            FROM {view}
            """
        )
    except duckdb.Error as error:
        results.append(
            create_result(
                check_name="hourly_fields_are_arrays",
                check_type="SCHEMA",
                severity="BLOCK",
                fail_count=1,
                total_count=1,
                threshold_pct=0.0,
                details=(
                    "All required hourly fields are present, but they could "
                    f"not be read as parallel arrays: {error}"
                ),
            )
        )
        return results

    total_hours = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {hourly_view}
        """,
    )

    # 5. The hourly series itself is not empty. A response can have a
    # present-but-empty hourly block (all four arrays length 0) instead of
    # the 4xx error profiled for an invalid window (docs/source_profile.md)
    # -- this catches that shape distinctly from a response missing hourly
    # entirely (already caught by required_columns above).
    results.append(
        create_result(
            check_name="hourly_series_not_empty",
            check_type="VOLUME",
            severity="BLOCK",
            fail_count=1 if total_hours == 0 else 0,
            total_count=1,
            threshold_pct=0.0,
            details=f"Observed hourly rows: {total_hours}.",
        )
    )

    if total_hours == 0:
        return results

    # 6. hourly.time present and readable. The duplicate, gap and window
    # checks below all key off time, so a null or unparseable value has to
    # fail here: otherwise it silently drops out of those checks, and an
    # unreadable first or last hour shrinks the observed and expected
    # counts by one each, so they still match.
    invalid_times = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {hourly_view}
        WHERE time IS NULL
           OR TRY_CAST(time AS TIMESTAMP) IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="hourly_time_valid",
            check_type="NOT_NULL",
            severity="BLOCK",
            fail_count=invalid_times,
            total_count=total_hours,
            threshold_pct=0.0,
            details="hourly.time must be present and parse as a timestamp for every hour.",
        )
    )

    if invalid_times:
        return results

    # 7. temperature_2m not null
    temperature_nulls = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {hourly_view}
        WHERE temperature_2m IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="temperature_2m_not_null",
            check_type="NOT_NULL",
            severity="BLOCK",
            fail_count=temperature_nulls,
            total_count=total_hours,
            threshold_pct=0.0,
            details="hourly.temperature_2m is required for every hour.",
        )
    )

    # 8. precipitation not null
    precipitation_nulls = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {hourly_view}
        WHERE precipitation IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="precipitation_not_null",
            check_type="NOT_NULL",
            severity="BLOCK",
            fail_count=precipitation_nulls,
            total_count=total_hours,
            threshold_pct=0.0,
            details="hourly.precipitation is required for every hour.",
        )
    )

    # 9. weather_code not null
    weather_code_nulls = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {hourly_view}
        WHERE weather_code IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="weather_code_not_null",
            check_type="NOT_NULL",
            severity="BLOCK",
            fail_count=weather_code_nulls,
            total_count=total_hours,
            threshold_pct=0.0,
            details="hourly.weather_code is required for every hour.",
        )
    )

    # 10. No duplicate hourly timestamps. Directly targets the acceptance
    # criteria "replaying the same window produces no duplicates" at the
    # file-integrity level: this validator has no run history of its own
    # (it is stateless, like Green Taxi's and Taxi Zones' gates), so what
    # it can prove is that one landed response does not itself contain the
    # same hour twice -- cross-run duplicate suppression is Bronze's job,
    # via the business key documented in docs/ingestion.md.
    duplicate_hours = scalar(
        connection,
        f"""
        SELECT COALESCE(
            SUM(duplicate_count - 1),
            0
        )
        FROM (
            SELECT
                time,
                COUNT(*) AS duplicate_count
            FROM {hourly_view}
            GROUP BY time
            HAVING COUNT(*) > 1
        )
        """,
    )

    results.append(
        create_result(
            check_name="no_duplicate_hourly_timestamps",
            check_type="DUPLICATE",
            severity="BLOCK",
            fail_count=duplicate_hours,
            total_count=total_hours,
            threshold_pct=0.0,
            details="Every hourly.time value must appear at most once per response.",
        )
    )

    # 11. No gaps inside the series. Compares the observed row count to the
    # hour-span between the response's own first and last hour, so a
    # skipped hour in the middle, or duplicated hours inflating the count,
    # show up as a mismatch. It cannot see a response cut short at either
    # end -- the span shrinks with it -- which is check 12's job.
    gap_check = connection.execute(
        f"""
        SELECT
            COUNT(*) AS observed_hours,
            DATE_DIFF(
                'hour',
                MIN(CAST(time AS TIMESTAMP)),
                MAX(CAST(time AS TIMESTAMP))
            ) + 1 AS expected_hours
        FROM {hourly_view}
        """
    ).fetchone()

    observed_hours, expected_hours = gap_check
    coverage_gap = (
        0
        if observed_hours == expected_hours
        else 1
    )

    results.append(
        create_result(
            check_name="hourly_series_has_no_gaps",
            check_type="COMPLETENESS",
            severity="BLOCK",
            fail_count=coverage_gap,
            total_count=1,
            threshold_pct=0.0,
            details=(
                f"Observed {observed_hours} hourly rows; the response's own "
                f"min/max timestamp span implies {expected_hours}."
            ),
        )
    )

    # 12. The series covers the requested window. The same rule as
    # Bronze's hourly_volume (requested days x 24), plus the first and last
    # hour, so a response missing its first or last day is refused here
    # instead of being accepted and then blocked at Bronze. Together with
    # check 10 (no duplicates), a matching count and matching ends mean
    # every requested hour is present exactly once.
    requested_start = contract["requested_window"]["start"]
    requested_end = contract["requested_window"]["end"]

    window_check = connection.execute(
        f"""
        SELECT
            COUNT(*) AS observed_hours,
            DATE_DIFF(
                'day',
                CAST('{requested_start}' AS DATE),
                CAST('{requested_end}' AS DATE)
            ) * 24 + 24 AS requested_hours,
            MIN(CAST(time AS TIMESTAMP)) AS first_hour,
            MAX(CAST(time AS TIMESTAMP)) AS last_hour,
            CAST('{requested_start}' AS TIMESTAMP) AS expected_first,
            CAST('{requested_end}' AS TIMESTAMP) + INTERVAL 23 HOUR AS expected_last
        FROM {hourly_view}
        """
    ).fetchone()

    (
        window_observed,
        requested_hours,
        first_hour,
        last_hour,
        expected_first,
        expected_last,
    ) = window_check

    window_mismatch = (
        0
        if (
            window_observed == requested_hours
            and first_hour == expected_first
            and last_hour == expected_last
        )
        else 1
    )

    results.append(
        create_result(
            check_name="hourly_series_covers_requested_window",
            check_type="COMPLETENESS",
            severity="BLOCK",
            fail_count=window_mismatch,
            total_count=1,
            threshold_pct=0.0,
            details=(
                f"Requested {requested_start} through {requested_end}: "
                f"{requested_hours} hours from {expected_first} to "
                f"{expected_last}. Observed {window_observed} hours from "
                f"{first_hour} to {last_hour}."
            ),
        )
    )

    # 13. Temperature is within a physically plausible range. Mirrors the
    # anomaly query used to profile this source (docs/source_profile.md):
    # precipitation < 0 OR temperature_2m < -50 OR temperature_2m > 60.
    temperature_out_of_range = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {hourly_view}
        WHERE TRY_CAST(temperature_2m AS DOUBLE) < -50
           OR TRY_CAST(temperature_2m AS DOUBLE) > 60
           OR TRY_CAST(temperature_2m AS DOUBLE) IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="temperature_plausible_range",
            check_type="RANGE",
            severity="BLOCK",
            fail_count=temperature_out_of_range,
            total_count=total_hours,
            threshold_pct=0.0,
            details="temperature_2m must parse as a number between -50 and 60 (Celsius).",
        )
    )

    # 14. Precipitation is non-negative
    precipitation_negative = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {hourly_view}
        WHERE TRY_CAST(precipitation AS DOUBLE) < 0
           OR TRY_CAST(precipitation AS DOUBLE) IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="precipitation_non_negative",
            check_type="RANGE",
            severity="BLOCK",
            fail_count=precipitation_negative,
            total_count=total_hours,
            threshold_pct=0.0,
            details="precipitation must parse as a number and cannot be negative.",
        )
    )

    # 15. weather_code domain. BLOCK at 0%, matching Bronze's
    # weather_code_domain and Silver's weather_code_valid_wmo, which both
    # FAIL on any code outside this set and end in raise_error. The list is
    # the full WMO code table Open-Meteo documents (the same 28 codes Silver
    # maps to categories), not only the codes seen while profiling, so a
    # code outside it is genuinely outside WMO. Tolerating it here would
    # only move the block from this gate to Bronze -- later, after the file
    # has already landed -- which is the failure this gate exists to prevent.
    # Compared as DOUBLE, not INTEGER: TRY_CAST(1.4 AS INTEGER) rounds to 1,
    # which would let a non-integer code through. As a DOUBLE, 1.4 matches
    # nothing in the list, and 1.0 still matches 1.
    known_weather_codes = (
        0, 1, 2, 3, 45, 48,
        51, 53, 55, 56, 57,
        61, 63, 65, 66, 67,
        71, 73, 75, 77,
        80, 81, 82, 85, 86,
        95, 96, 99,
    )

    invalid_weather_code = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {hourly_view}
        WHERE TRY_CAST(weather_code AS DOUBLE) NOT IN {known_weather_codes}
           OR TRY_CAST(weather_code AS DOUBLE) IS NULL
        """,
    )

    results.append(
        create_result(
            check_name="weather_code_known_domain",
            check_type="DOMAIN",
            severity="BLOCK",
            fail_count=invalid_weather_code,
            total_count=total_hours,
            threshold_pct=0.0,
            details="weather_code should be one of the WMO codes Open-Meteo documents.",
        )
    )

    return results


# Keyed by --source. Both functions share the exact same signature and
# result shape, so main() can dispatch without a chain of if/elif.
CHECK_RUNNERS = {
    "green_taxi": run_green_taxi_checks,
    "taxi_zones": run_taxi_zones_checks,
    "weather": run_weather_checks,
}


def print_results(results, source):
    print(
        f"\nDUCKDB PRE-INGESTION GATE: {source}"
    )
    print("=" * 72)

    for result in results:
        print(
            f"{result['status']:<5} "
            f"{result['check_name']:<32} "
            f"failures={result['fail_count']:<8} "
            f"fail_pct={result['fail_pct']:.4f}%"
        )

    print("=" * 72)


def write_evidence(
    path,
    source,
    inputs,
    results,
    gate_result,
    exit_code,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    evidence = {
        "source": source,
        "inputs": inputs,
        "check_count": len(results),
        "gate_result": gate_result,
        "exit_code": exit_code,
        "results": results,
    }

    path.write_text(
        json.dumps(
            evidence,
            indent=2,
        ),
        encoding="utf-8",
    )


# --- Recording in 01-control (#148) -----------------------------------------
#
# As a job task the gate also writes one row per check to
# data_quality_results, the table every SQL gate writes to, so a
# pre-ingestion verdict appears in gate_status and on the DQ dashboard next
# to the Bronze and Silver gates. Locally and in CI nothing is recorded:
# there is no Spark session there, and the JSON evidence is the record.

DQ_TABLE = "`ftw-week-08`.`01-control`.data_quality_results"
CONTROL_LAYER = "source"
UNSET_REVISION = "UNSET"

# The gate calls its blocking severity BLOCK. data_quality_results and the
# dq_status() function in 01-control call the same thing FAIL.
CONTROL_SEVERITY = {
    "BLOCK": "FAIL",
    "WARN": "WARN",
    "INFO": "INFO",
}

# data_quality_results' columns in table order, without executed_at, which
# the INSERT sets with current_timestamp() the same way the SQL gates do.
CONTROL_COLUMNS = (
    "run_id",
    "layer",
    "dataset",
    "check_name",
    "check_type",
    "severity",
    "status",
    "fail_count",
    "total_count",
    "fail_pct",
    "threshold_pct",
    "batch_id",
    "source_version_id",
    "code_revision",
    "owner",
    "evidence_location",
    "details",
)


def control_rows(source, inputs, results, run_id, code_revision):
    """One data_quality_results row per check, in CONTROL_COLUMNS order.

    batch_id and source_version_id stay NULL: the gate runs before Bronze
    has created a batch or a version to point at. evidence_location records
    the input paths the gate read instead.
    """
    revision = code_revision or UNSET_REVISION
    evidence_location = ", ".join(inputs)

    return [
        (
            run_id,
            CONTROL_LAYER,
            source,
            result["check_name"],
            result["check_type"],
            CONTROL_SEVERITY[result["severity"]],
            result["status"],
            result["fail_count"],
            result["total_count"],
            float(result["fail_pct"]),
            (
                None
                if result["threshold_pct"] is None
                else float(result["threshold_pct"])
            ),
            None,
            None,
            revision,
            # The same placeholder the SQL gates write until #126 names
            # an owner per check.
            "TODO",
            evidence_location,
            result["details"],
        )
        for result in results
    ]


def record_in_control(rows):
    """Append rows to data_quality_results. Needs Databricks' Spark session."""
    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        DoubleType,
        LongType,
        StringType,
        StructField,
        StructType,
    )

    numeric_types = {
        "fail_count": LongType(),
        "total_count": LongType(),
        "fail_pct": DoubleType(),
        "threshold_pct": DoubleType(),
    }
    schema = StructType([
        StructField(column, numeric_types.get(column, StringType()), True)
        for column in CONTROL_COLUMNS
    ])

    spark = SparkSession.builder.getOrCreate()
    spark.createDataFrame(rows, schema).createOrReplaceTempView(
        "source_gate_results"
    )

    columns = ", ".join(CONTROL_COLUMNS)
    spark.sql(
        f"""
        INSERT INTO {DQ_TABLE} (executed_at, {columns})
        SELECT current_timestamp(), {columns}
        FROM source_gate_results
        """
    )


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Validate a Green Taxi, Taxi Zones, or Weather source locally "
            "with DuckDB before Bronze ingestion."
        )
    )

    parser.add_argument(
        "--source",
        default="green_taxi",
        choices=sorted(CHECK_RUNNERS.keys()),
        help="Which declared source contract to validate against.",
    )

    parser.add_argument(
        "--input",
        nargs="+",
        required=True,
        help=(
            "One or more local paths or glob patterns for the chosen "
            "--source (parquet for green_taxi, csv for taxi_zones, "
            "json for weather)."
        ),
    )

    parser.add_argument(
        "--evidence",
        default=None,
        help=(
            "Path for generated JSON evidence. Defaults to a path specific "
            "to --source, so different sources never share, and silently "
            "overwrite, one evidence file."
        ),
    )

    parser.add_argument(
        "--record-control",
        action="store_true",
        help=(
            "Also append one row per check to data_quality_results. "
            "For the Databricks job task; needs a Spark session."
        ),
    )

    parser.add_argument(
        "--code-revision",
        default="",
        help=(
            "Commit recorded on the control rows. The job passes its "
            "code_revision parameter; empty records 'UNSET' (D25)."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    contract_registry = load_json(
        CONTRACT_PATH
    )

    if args.source not in contract_registry:
        print(
            f"MISSING_CONTRACT: {args.source} is not "
            "declared in config/source_contract.json"
        )
        return EXIT_INVALID_CONFIGURATION

    inputs = args.input

    if not inputs:
        print(
            f"MISSING_INPUT: No {args.source} inputs "
            "were provided."
        )
        return EXIT_INVALID_CONFIGURATION

    network_prefixes = (
        "http://",
        "https://",
        "s3://",
        "r2://",
    )

    for input_path in inputs:
        if input_path.lower().startswith(network_prefixes):
            print(
                "NETWORK_INPUT_NOT_ALLOWED: "
                "Only local files may be validated."
            )
            return EXIT_INVALID_CONFIGURATION

    connection = duckdb.connect()

    load_view = SOURCE_LOADERS[args.source]

    try:
        load_view(
            connection,
            inputs,
        )
    except Exception as error:
        print("MISSING_OR_UNREADABLE_INPUT")
        print(str(error))
        connection.close()
        return EXIT_INPUT_UNAVAILABLE

    run_checks = CHECK_RUNNERS[args.source]

    results = run_checks(
        connection,
        contract_registry[args.source],
    )

    print_results(results, args.source)

    blocking_failures = [
        result
        for result in results
        if result["status"] == "FAIL"
    ]

    if blocking_failures:
        gate_result = "BLOCKED"
        exit_code = EXIT_BLOCKED
    else:
        gate_result = "ACCEPTED"
        exit_code = EXIT_ACCEPTED

    print(f"\nGate result: {gate_result}")
    print(f"Exit code: {exit_code}")

    evidence_path = (
        Path(args.evidence)
        if args.evidence
        else default_evidence_path(args.source)
    )

    write_evidence(
        path=evidence_path,
        source=args.source,
        inputs=inputs,
        results=results,
        gate_result=gate_result,
        exit_code=exit_code,
    )

    print(f"Evidence: {evidence_path}")

    # Recorded before returning, so a BLOCKED delivery is on record too.
    if args.record_control:
        rows = control_rows(
            source=args.source,
            inputs=inputs,
            results=results,
            run_id=str(uuid.uuid4()),
            code_revision=args.code_revision,
        )
        record_in_control(rows)
        print(f"Recorded {len(rows)} rows in {DQ_TABLE}")

    connection.close()

    return exit_code


if __name__ == "__main__":
    exit_code = main()

    # Exit only to signal a failure. Databricks runs a job's Python file
    # inside IPython, which reports even SystemExit(0) as a failed task (run
    # 159238056445742 failed two ACCEPTED gates that way). Returning normally
    # is success everywhere, and a non-zero code still fails the task and
    # sets the process exit status that CI checks.
    if exit_code != EXIT_ACCEPTED:
        sys.exit(exit_code)
