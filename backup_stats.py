#!/usr/bin/env python3
"""
Backup DJ Stats
================
Shows how many times each DJ is assigned as BACKUP in the availability
matrix for a given year.

Usage:
  python3 backup_stats.py --year 2026
"""

import argparse
import os
import sys
from datetime import datetime

from dj_core import (
    BACKUP_ELIGIBLE_DJS,
    init_google_sheets_from_file,
    get_bulk_availability_data,
)


def main():
    parser = argparse.ArgumentParser(
        description="Show backup assignment counts per DJ for a given year",
    )
    parser.add_argument(
        "--year", required=True, type=int,
        help="Year to check (e.g., 2026)",
    )
    args = parser.parse_args()
    year = args.year

    # Init Google Sheets
    script_dir = os.path.dirname(os.path.abspath(__file__))
    creds_file = os.path.join(script_dir, "your-credentials.json")
    os.chdir(script_dir)

    print(f"\nBackup Stats — {year}")
    print("=" * 40)
    print("Connecting to Google Sheets...")

    service, spreadsheet, spreadsheet_id, client = init_google_sheets_from_file(creds_file)

    print("Fetching availability data...")
    all_data = get_bulk_availability_data(str(year), service, spreadsheet, spreadsheet_id)

    if not all_data:
        print("No data found.")
        sys.exit(1)

    # Count backups per DJ
    dj_names = ["Henry", "Woody", "Paul", "Stefano", "Felipe", "Stephanie"]
    backup_counts = {dj: 0 for dj in dj_names}
    backup_dates = {dj: [] for dj in dj_names}

    for d in all_data:
        selected_data = d["selected_data"]
        date_display = d["date"]

        for dj in dj_names:
            value = selected_data.get(dj, "")
            if not value:
                continue
            value_clean = value.replace(" (BOLD)", "")
            statuses = [s.strip().lower() for s in value_clean.split(",")]
            if "backup" in statuses:
                backup_counts[dj] += 1
                backup_dates[dj].append(date_display)

    # Display results sorted by count (descending)
    print()
    sorted_djs = sorted(backup_counts.items(), key=lambda x: x[1], reverse=True)
    total = 0
    for dj, count in sorted_djs:
        if count > 0:
            print(f"  {dj:<12} {count:>3} backup(s)")
            total += count
        else:
            print(f"  {dj:<12}   —")

    print(f"  {'':─<12}─{'':─>3}─{'':─<9}")
    print(f"  {'Total':<12} {total:>3}")
    print()

    # Show detail per DJ
    for dj, count in sorted_djs:
        if count > 0:
            dates_str = ", ".join(backup_dates[dj])
            print(f"  {dj}: {dates_str}")

    print()


if __name__ == "__main__":
    main()
