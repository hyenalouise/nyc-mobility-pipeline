import argparse
import json
import sys
from pathlib import Path

import duckdb


CONTRACT_PATH = Path("config/source_contract.json")

# Green Taxi keeps its original, already-committed filename (results.json,
# referenced by docs/duckdb/evidence.md) so this fix stays backward
# compatible. Any other source falls back to a per-source filename instead
# of sharing that path -- which is what let a taxi_zones run silently
# overwrite Green Taxi's committed evidence before this fix.
DEFAULT_EVIDENCE_PATHS = {
    "green_taxi": Path("evidence/proof/source-validation/results.json"),
}


def default_evidence_path(source):
    return DEFAULT_EVIDENCE_PATHS.get(
        source,
        Path(f"evidence/proof/source-validation/{source}_results.json"),
    )

# Local view name each source is loaded into. Kept separate per source so a
# --source green_taxi run and a --source taxi_zones run can never silently
# read the wrong view if this module is ever extended to check more than
# one source in the same process.
VIEW_NAMES = {
    "green_taxi": "green_taxi_source",
    "taxi_zones": "taxi_zones_source",
}

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


# Keyed by --source. Each entry pairs the loader with the view it created,
# so main() does not need a chain of if/elif to pick the right reader.
SOURCE_LOADERS = {
    "green_taxi": create_green_taxi_view,
    "taxi_zones": create_taxi_zones_view,
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


# Keyed by --source. Both functions share the exact same signature and
# result shape, so main() can dispatch without a chain of if/elif.
CHECK_RUNNERS = {
    "green_taxi": run_green_taxi_checks,
    "taxi_zones": run_taxi_zones_checks,
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


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Validate a Green Taxi or Taxi Zones source locally "
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
            "--source (parquet for green_taxi, csv for taxi_zones)."
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

    connection.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
