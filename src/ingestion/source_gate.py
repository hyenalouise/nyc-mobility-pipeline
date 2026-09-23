import argparse
import json
import sys
from pathlib import Path

import duckdb


CONTRACT_PATH = Path("config/source_contract.json")
DEFAULT_EVIDENCE_PATH = Path(
    "evidence/proof/source-validation/results.json"
)


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


def create_source_view(connection, inputs):
    input_list = sql_list(inputs)

    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW green_taxi_source AS
        SELECT *
        FROM read_parquet(
            {input_list},
            union_by_name = true,
            filename = true
        )
        """
    )


def get_columns(connection):
    rows = connection.execute(
        """
        DESCRIBE
        SELECT *
        FROM green_taxi_source
        """
    ).fetchall()

    return [row[0] for row in rows]


def run_checks(connection, contract):
    results = []

    total_rows = scalar(
        connection,
        """
        SELECT COUNT(*)
        FROM green_taxi_source
        """,
    )

    columns = get_columns(connection)

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
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
    negative_fare_amount = scalar(
        connection,
        """
        SELECT COUNT(*)
        FROM green_taxi_source
        WHERE fare_amount < 0
        """,
    )

    results.append(
        create_result(
            check_name="fare_amount_non_negative",
            check_type="RANGE",
            severity="WARN",
            fail_count=negative_fare_amount,
            total_count=total_rows,
            threshold_pct=0.1,
            details=(
                "Negative fare amounts are flagged. "
                "A maximum failure rate of 0.1% is tolerated."
            ),
        )
    )

    # 8. Drop-off after pickup
    invalid_trip_order = scalar(
        connection,
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
        FROM green_taxi_source
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
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
        """
        SELECT COUNT(*)
        FROM green_taxi_source
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
        """
        SELECT COALESCE(
            SUM(duplicate_count - 1),
            0
        )
        FROM (
            SELECT
                COUNT(*) AS duplicate_count
            FROM green_taxi_source
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


def print_results(results):
    print(
        "\nDUCKDB PRE-INGESTION GATE: green_taxi"
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
        "source": "green_taxi",
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
            "Validate Green Taxi source files locally "
            "with DuckDB before Bronze ingestion."
        )
    )

    parser.add_argument(
        "--input",
        nargs="+",
        required=True,
        help=(
            "One or more local parquet paths or glob patterns."
        ),
    )

    parser.add_argument(
        "--evidence",
        default=str(DEFAULT_EVIDENCE_PATH),
        help="Path for generated JSON evidence.",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    contract_registry = load_json(
        CONTRACT_PATH
    )

    if "green_taxi" not in contract_registry:
        print(
            "MISSING_CONTRACT: green_taxi is not "
            "declared in config/source_contract.json"
        )
        return 2

    inputs = args.input

    if not inputs:
        print(
            "MISSING_INPUT: No Green Taxi inputs "
            "were provided."
        )
        return 2

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
            return 2

    connection = duckdb.connect()

    try:
        create_source_view(
            connection,
            inputs,
        )
    except Exception as error:
        print("MISSING_OR_UNREADABLE_INPUT")
        print(str(error))
        connection.close()
        return 3

    results = run_checks(
        connection,
        contract_registry["green_taxi"],
    )

    print_results(results)

    blocking_failures = [
        result
        for result in results
        if result["status"] == "FAIL"
    ]

    if blocking_failures:
        gate_result = "BLOCKED"
        exit_code = 1
    else:
        gate_result = "ACCEPTED"
        exit_code = 0

    print(f"\nGate result: {gate_result}")
    print(f"Exit code: {exit_code}")

    evidence_path = Path(args.evidence)

    write_evidence(
        path=evidence_path,
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