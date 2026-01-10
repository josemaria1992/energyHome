#!/usr/bin/env python3
"""
Sample Data Import Script for EnergyHome Forecast

This script imports sample data from a CSV file into the energyhome.sqlite database.
This is useful for testing and development without waiting for real data collection.

CSV Format:
    ts_local_bin_start,total_w,l1_w,l2_w,l3_w,grid_l1_w,grid_l2_w,grid_l3_w,inverter_w

Example CSV row:
    2026-01-10T14:00:00,3500.0,1200.0,1150.0,1150.0,100.0,50.0,50.0,3400.0

Usage:
    python import_sample_csv.py /data/energyhome.sqlite sample_data.csv

After import:
    1. POST /api/ilc/update  (to recalculate ILC curves)
    2. POST /api/recompute   (to regenerate forecast)
    3. Open /ui              (to view results)
"""

import csv
import sqlite3
import sys
from pathlib import Path


def import_csv_to_db(db_path: str, csv_path: str) -> None:
    """Import CSV data into the binned table."""

    if not Path(csv_path).exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    if not Path(db_path).exists():
        print(f"Error: Database file not found: {db_path}")
        print("Make sure the add-on has run at least once to create the database.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Verify table exists and has correct schema
    cursor.execute("PRAGMA table_info(binned)")
    columns = [row[1] for row in cursor.fetchall()]
    required_columns = ["ts_local_bin_start", "total_w", "l1_w", "l2_w", "l3_w",
                       "grid_l1_w", "grid_l2_w", "grid_l3_w", "inverter_w"]

    for col in required_columns:
        if col not in columns:
            print(f"Error: Database schema missing column: {col}")
            print("Please ensure the add-on is updated to the latest version.")
            conn.close()
            sys.exit(1)

    # Read and import CSV
    rows_imported = 0
    rows_skipped = 0

    with open(csv_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)

        # Validate CSV headers
        expected_headers = required_columns
        if not all(h in reader.fieldnames for h in expected_headers):
            print(f"Error: CSV must have headers: {', '.join(expected_headers)}")
            print(f"Found headers: {', '.join(reader.fieldnames)}")
            conn.close()
            sys.exit(1)

        for row in reader:
            try:
                # Convert empty strings to None
                def parse_float(value: str) -> float | None:
                    if value.strip() == '' or value.strip().lower() == 'null':
                        return None
                    return float(value)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO binned
                    (ts_local_bin_start, total_w, l1_w, l2_w, l3_w, grid_l1_w, grid_l2_w, grid_l3_w, inverter_w)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row['ts_local_bin_start'],
                        parse_float(row['total_w']),
                        parse_float(row['l1_w']),
                        parse_float(row['l2_w']),
                        parse_float(row['l3_w']),
                        parse_float(row['grid_l1_w']),
                        parse_float(row['grid_l2_w']),
                        parse_float(row['grid_l3_w']),
                        parse_float(row['inverter_w']),
                    )
                )
                rows_imported += 1
            except Exception as e:
                print(f"Warning: Skipping row due to error: {e}")
                print(f"  Row data: {row}")
                rows_skipped += 1

    conn.commit()
    conn.close()

    print(f"\n✅ Import completed!")
    print(f"   Rows imported: {rows_imported}")
    print(f"   Rows skipped: {rows_skipped}")
    print(f"\nNext steps:")
    print(f"   1. POST /api/ilc/update  (recalculate ILC curves)")
    print(f"   2. POST /api/recompute   (regenerate forecast)")
    print(f"   3. Open /ui              (view results)")


def generate_sample_csv(output_path: str) -> None:
    """Generate a sample CSV file with synthetic data."""
    from datetime import datetime, timedelta

    print(f"Generating sample CSV at: {output_path}")

    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            'ts_local_bin_start', 'total_w', 'l1_w', 'l2_w', 'l3_w',
            'grid_l1_w', 'grid_l2_w', 'grid_l3_w', 'inverter_w'
        ])

        # Generate 7 days of 15-minute samples (672 rows)
        start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)

        for i in range(672):
            ts = start_time + timedelta(minutes=15 * i)
            hour = ts.hour

            # Simulate realistic daily pattern
            base_load = 500 + 2500 * (0.5 + 0.5 * (1 - abs(hour - 12) / 12))  # Peak at noon

            total_w = base_load
            l1_w = total_w * 0.35
            l2_w = total_w * 0.33
            l3_w = total_w * 0.32

            # Grid power (small compared to load, representing net import/export)
            grid_l1_w = l1_w * 0.1
            grid_l2_w = l2_w * 0.08
            grid_l3_w = l3_w * 0.09

            # Inverter load (slightly less than total due to losses)
            inverter_w = total_w * 0.95

            writer.writerow([
                ts.strftime('%Y-%m-%dT%H:%M:%S'),
                f'{total_w:.1f}',
                f'{l1_w:.1f}',
                f'{l2_w:.1f}',
                f'{l3_w:.1f}',
                f'{grid_l1_w:.1f}',
                f'{grid_l2_w:.1f}',
                f'{grid_l3_w:.1f}',
                f'{inverter_w:.1f}',
            ])

    print(f"✅ Sample CSV generated with 672 rows (7 days of 15-min data)")
    print(f"   Use: python import_sample_csv.py <db_path> {output_path}")


def main():
    if len(sys.argv) == 1:
        print(__doc__)
        sys.exit(0)

    if len(sys.argv) == 2 and sys.argv[1] == '--generate-sample':
        generate_sample_csv('sample_data.csv')
        sys.exit(0)

    if len(sys.argv) != 3:
        print("Usage:")
        print(f"  {sys.argv[0]} <db_path> <csv_path>")
        print(f"  {sys.argv[0]} --generate-sample")
        print(f"\nExample:")
        print(f"  {sys.argv[0]} /data/energyhome.sqlite sample_data.csv")
        sys.exit(1)

    db_path = sys.argv[1]
    csv_path = sys.argv[2]

    print(f"Importing CSV data...")
    print(f"  Database: {db_path}")
    print(f"  CSV file: {csv_path}")
    print()

    import_csv_to_db(db_path, csv_path)


if __name__ == '__main__':
    main()
