"""Deterministically corrupt a real taxi_zone_lookup.csv for gate testing.

The original broken_zones.csv was a small handmade file, not committed, and
it failed row_count_floor too -- meaning nobody else could reproduce the
"broken file refused" evidence against the actual 265-row snapshot.

This script takes a real, clean taxi_zone_lookup.csv and injects exactly
three known defects, each targeting one specific check in
run_taxi_zones_checks(), so the resulting evidence is reproducible and each
failure can be traced to the check it exercises:

  1. Row 2's LocationID is duplicated onto row 3   -> location_id_unique
  2. Row 4's Borough is blanked                     -> borough_not_null
  3. Row 5's LocationID is replaced with "abc"      -> location_id_valid_integer

Usage:
    python -m src.ingestion.make_broken_zones taxi_zone_lookup.csv broken_zones.csv
"""
import csv
import sys


def make_broken(input_path, output_path):
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    if len(rows) < 5:
        raise SystemExit(
            f"{input_path} has only {len(rows)} data rows; need at least 5 "
            "to inject the three defects this script targets."
        )

    location_id_index = header.index("LocationID")
    borough_index = header.index("Borough")

    # Defect 1: duplicate row 2's LocationID onto row 3.
    rows[2][location_id_index] = rows[1][location_id_index]

    # Defect 2: blank row 4's Borough.
    rows[3][borough_index] = ""

    # Defect 3: replace row 5's LocationID with a non-numeric value.
    rows[4][location_id_index] = "abc"

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"Wrote {output_path}: {len(rows)} rows, 3 defects injected.")
    print(f"  duplicate LocationID at row 3 (matches row 2: {rows[1][location_id_index]})")
    print(f"  blank Borough at row 4 ({rows[3][0]})")
    print(f"  non-numeric LocationID at row 5 ({rows[4][0]})")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: python {sys.argv[0]} <clean_csv> <output_csv>")
    make_broken(sys.argv[1], sys.argv[2])