#!/usr/bin/env python3
"""
Booking System Comparator
==========================
Cross-checks up to three booking systems to find discrepancies:

  1. Gig Database    — you provide a text file (raw or reformatted)
  2. Avail Matrix    — pulled LIVE from Google Sheets
  3. Master Calendar — pulled LIVE via icalBuddy (macOS)

Usage:
  python3 booking_comparator.py gig-db.txt --year 2026
  python3 booking_comparator.py gig-db.txt --year 2026 --no-calendar
  python3 booking_comparator.py gig-db.txt --year 2026 --output report.txt

The script:
  - Reads the gig database from your text file
  - Pulls the availability matrix directly from Google Sheets
  - Pulls the master calendar directly via icalBuddy
  - Compares all three and reports discrepancies
"""

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta

# Import shared DJ data and Google Sheets access from dj_core
from dj_core import (
    DJ_INITIALS,
    init_google_sheets_from_file,
    get_bulk_availability_data,
)


# =============================================================================
# GIG DATABASE PARSER (from text file)
# =============================================================================

def parse_gig_db(filepath, year):
    """
    Parse the gig database text file.
    Supports two formats:

    Raw format:
      >	10-22-26 Thu  P	3:00	10:00		--C-A--	Client	Venue

    Reformatted format:
      MM-DD-YY — DJ_CODE — Client Name — Venue (notes)

    Returns: dict of { "M/D": ["DJ1", "DJ2", ...] }
    """
    events = defaultdict(list)

    dj_map = {
        'H': 'Henry',
        'P': 'Paul',
        'S': 'Stefano',
        'W': 'Woody',
        'F': 'Felipe',
        'D': 'Stephanie',
        'SD': 'Stephanie',
        'FS': 'Felipe',
    }

    with open(filepath, 'r') as f:
        first_line = f.readline().strip()
        f.seek(0)

        is_raw_format = first_line.startswith('>')

        for line in f:
            line = line.strip()
            if not line:
                continue

            if is_raw_format:
                if not line.startswith('>'):
                    continue

                parts = line.split('\t')
                if len(parts) < 3:
                    continue

                # Date and DJ code are in parts[1], e.g. "10-22-26 Thu  P"
                date_dj = parts[1].strip()
                tokens = date_dj.split()
                if len(tokens) < 1:
                    continue

                date_str = tokens[0]  # "10-22-26"
                # DJ code might be in tokens[2] or parts[2]
                dj_code = tokens[2] if len(tokens) > 2 else parts[2].strip()

                try:
                    month, day, yr = date_str.split('-')
                    # Filter to requested year
                    full_year = int(yr) + 2000 if int(yr) < 100 else int(yr)
                    if str(full_year) != str(year):
                        continue
                    date_key = f"{int(month)}/{int(day)}"
                except (ValueError, IndexError):
                    continue

            else:
                # Reformatted: 01-03-26 — H — Client — Venue
                parts = [p.strip() for p in line.split('—')]
                if len(parts) < 2:
                    continue

                date_str = parts[0].strip()
                dj_code = parts[1].strip()

                try:
                    month, day, yr = date_str.split('-')
                    full_year = int(yr) + 2000 if int(yr) < 100 else int(yr)
                    if str(full_year) != str(year):
                        continue
                    date_key = f"{int(month)}/{int(day)}"
                except (ValueError, IndexError):
                    continue

            # Map DJ code to name
            if dj_code.startswith('U'):
                dj_name = 'TBA'
            else:
                dj_name = dj_map.get(dj_code, dj_code)

            events[date_key].append(dj_name)

    # Sort DJs for each date
    for date_key in events:
        events[date_key] = sorted(events[date_key])

    return events


# =============================================================================
# AVAILABILITY MATRIX (live from Google Sheets)
# =============================================================================

def fetch_availability_matrix(year):
    """
    Pull availability matrix directly from Google Sheets.
    Returns: (bookings, backups) where each is dict of { "M/D": ["DJ1", "DJ2", ...] }
    """
    events = defaultdict(list)
    backups = defaultdict(list)

    # Find credentials file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    creds_file = os.path.join(script_dir, 'your-credentials.json')
    if not os.path.exists(creds_file):
        print(f"Error: Credentials file not found: {creds_file}")
        sys.exit(1)

    print(f"  Connecting to Google Sheets...")
    os.chdir(script_dir)  # So dj_core finds the credentials
    service, spreadsheet, spreadsheet_id, client = init_google_sheets_from_file(creds_file)

    print(f"  Fetching {year} availability matrix...")
    all_dates = get_bulk_availability_data(str(year), service, spreadsheet, spreadsheet_id)

    for date_info in all_dates:
        date_obj = date_info['date_obj']
        date_key = f"{date_obj.month}/{date_obj.day}"

        # Collect booked DJs, skip RESERVED (held but not actually booked)
        booked = []
        for dj in date_info.get('booked_djs', []):
            if '(RESERVED)' in dj:
                continue
            booked.append(dj)

        # Add TBA entries
        tba_count = date_info.get('availability', {}).get('tba_bookings', 0)
        for _ in range(tba_count):
            booked.append('TBA')

        if booked:
            events[date_key] = sorted(booked)

        # Collect backup DJs
        for dj in date_info.get('backup_assigned', []):
            backups[date_key].append(dj)
        if backups[date_key]:
            backups[date_key] = sorted(backups[date_key])

    booking_count = sum(len(v) for v in events.values())
    backup_count = sum(len(v) for v in backups.values())
    print(f"  Found {booking_count} bookings on {len(events)} dates, {backup_count} backups on {len(backups)} dates")
    return events, backups


# =============================================================================
# MASTER CALENDAR (live via icalBuddy)
# =============================================================================

def fetch_master_calendar(year):
    """
    Pull master calendar events directly via icalBuddy.
    Queries the entire year of events.
    Returns: (bookings, backups) where each is dict of { "M/D": ["DJ1", "DJ2", ...] }
    """
    events = defaultdict(list)
    backups = defaultdict(list)

    # Check if icalBuddy is available
    ical_buddy = "/opt/homebrew/bin/icalBuddy"
    if not os.path.exists(ical_buddy):
        print("  WARNING: icalBuddy not installed (brew install ical-buddy)")
        print("  Skipping calendar comparison.")
        return None, None

    # Build reverse map: initials bracket → DJ name
    # DJ_INITIALS: {"Henry": "HK", "Woody": "WM", ...}
    initials_to_name = {}
    for name, initials in DJ_INITIALS.items():
        if name != "Unknown":
            initials_to_name[f"[{initials}]"] = name

    # Also handle unassigned: [U], [UP], etc.
    # We'll catch anything with [U followed by optional letters]

    # Query the entire year at once (Jan 1 to Dec 31)
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    print(f"  Querying calendar for {year}...")
    try:
        result = subprocess.run(
            [ical_buddy, "-ic", "Gigs",
             "-eep", "notes,url,location,attendees",
             "-b", "", "-nc", "-nrd",
             "-df", "%m/%d",
             "-iep", "title,datetime",
             f"eventsFrom:{start_date}", f"to:{end_date}"],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode != 0:
            print(f"  WARNING: icalBuddy returned error: {result.stderr}")
            return None

        # icalBuddy output format (title and datetime on separate lines):
        #   [PB] Christina and David
        #       01/03 at 1:00 PM - 10:00 PM
        #   [HK] Kristy's 50th Birthday Party
        #       01/03 at 3:00 PM - 10:00 PM
        # All-day events have just the date:
        #   [SB] PAID BACKUP DJ
        #       01/03

        pending_djs = None  # DJ(s) from title line, waiting for date line
        pending_is_backup = False
        pending_is_hold = False  # "Hold to DJ" = RESERVED, skip like matrix

        for line in result.stdout.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue

            # Check if this is a title line with a DJ bracket code
            # Handles single [PB], dual [WM/HK], and other formats
            bracket_match = re.search(r'\[([A-Za-z]{1,3}(?:/[A-Za-z]{1,3})*)\]', stripped)
            if bracket_match and not stripped[0].isdigit():
                is_backup = 'BACKUP' in stripped.upper()
                is_hold = 'HOLD TO DJ' in stripped.upper()

                # Title line — may contain multiple DJs separated by /
                raw_codes = bracket_match.group(1)  # "PB" or "WM/HK"
                dj_codes = raw_codes.split('/')

                # Resolve each DJ code to a name
                pending_djs = []
                for code in dj_codes:
                    bracket_key = f"[{code}]"
                    if bracket_key in initials_to_name:
                        pending_djs.append(initials_to_name[bracket_key])
                    elif code.startswith('U'):
                        pending_djs.append('TBA')
                    else:
                        pending_djs.append(f"?{code}")

                pending_is_backup = is_backup
                pending_is_hold = is_hold
                continue

            # Check if this is a date/time line (follows a title line)
            if pending_djs:
                date_match = re.search(r'(\d{1,2}/\d{1,2})', stripped)
                if date_match and not pending_is_hold:
                    raw_date = date_match.group(1)
                    parts = raw_date.split('/')
                    date_key = f"{int(parts[0])}/{int(parts[1])}"
                    for dj in pending_djs:
                        if pending_is_backup:
                            backups[date_key].append(dj)
                        else:
                            events[date_key].append(dj)
                pending_djs = None
                pending_is_backup = False
                pending_is_hold = False

        # Sort DJs for each date
        for date_key in events:
            events[date_key] = sorted(events[date_key])
        for date_key in backups:
            backups[date_key] = sorted(backups[date_key])

        booking_count = sum(len(v) for v in events.values())
        backup_count = sum(len(v) for v in backups.values())
        print(f"  Found {booking_count} events on {len(events)} dates, {backup_count} backups on {len(backups)} dates")
        return events, backups

    except FileNotFoundError:
        print("  WARNING: icalBuddy not found")
        return None, None
    except subprocess.TimeoutExpired:
        print("  WARNING: Calendar query timed out")
        return None, None


# =============================================================================
# COMPARISON ENGINE
# =============================================================================

def compare_systems(gig_db, avail_matrix, master_cal=None,
                    matrix_backups=None, cal_backups=None, output=None):
    """
    Compare all systems and generate discrepancy report.

    Args:
        gig_db: dict { "M/D": ["DJ1", ...] } — from text file
        avail_matrix: dict { "M/D": ["DJ1", ...] } — bookings from Sheets
        master_cal: dict { "M/D": ["DJ1", ...] } or None — bookings from calendar
        matrix_backups: dict { "M/D": ["DJ1", ...] } or None — backups from Sheets
        cal_backups: dict { "M/D": ["DJ1", ...] } or None — backups from calendar
        output: file object or None (prints to stdout)
    """
    out = output or sys.stdout

    def write(text=""):
        print(text, file=out)

    has_calendar = master_cal is not None

    write("=" * 70)
    write("BOOKING SYSTEM COMPARISON REPORT")
    write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    write("=" * 70)
    write()

    # Statistics
    write("STATISTICS")
    write("-" * 70)
    gig_count = sum(len(djs) for djs in gig_db.values())
    matrix_count = sum(len(djs) for djs in avail_matrix.values())
    write(f"  Gig Database:        {gig_count} bookings on {len(gig_db)} dates")
    write(f"  Availability Matrix: {matrix_count} bookings on {len(avail_matrix)} dates")
    if has_calendar:
        cal_count = sum(len(djs) for djs in master_cal.values())
        write(f"  Master Calendar:     {cal_count} events on {len(master_cal)} dates")
    write()

    # All unique dates, sorted chronologically
    all_date_keys = set(gig_db.keys()) | set(avail_matrix.keys())
    if has_calendar:
        all_date_keys |= set(master_cal.keys())

    def date_sort_key(d):
        parts = d.split('/')
        return (int(parts[0]), int(parts[1]))

    all_dates = sorted(all_date_keys, key=date_sort_key)

    # Find discrepancies
    issues = []
    for date_key in all_dates:
        gig_djs = sorted(set(gig_db.get(date_key, [])))
        matrix_djs = sorted(set(avail_matrix.get(date_key, [])))
        cal_djs = sorted(set(master_cal.get(date_key, []))) if has_calendar else None

        if has_calendar:
            all_match = (gig_djs == matrix_djs == cal_djs)
        else:
            all_match = (gig_djs == matrix_djs)

        if not all_match:
            issue = {
                'date': date_key,
                'gig_db': gig_djs,
                'avail_matrix': matrix_djs,
            }
            if has_calendar:
                issue['master_cal'] = cal_djs
            issues.append(issue)

    # Status
    if not issues:
        write("STATUS: ALL SYSTEMS IN SYNC")
        write("=" * 70)
        return

    write(f"STATUS: {len(issues)} DISCREPANCY(IES) FOUND")
    write("=" * 70)
    write()

    # Categorize issues
    missing_from_matrix = []
    missing_from_gig_db = []
    missing_from_calendar = []
    dj_mismatches = []

    for issue in issues:
        gig_set = set(issue['gig_db'])
        matrix_set = set(issue['avail_matrix'])
        cal_set = set(issue.get('master_cal', [])) if has_calendar else set()

        # Determine what kind of discrepancy
        in_gig_not_matrix = gig_set - matrix_set
        in_matrix_not_gig = matrix_set - gig_set

        if in_gig_not_matrix and not in_matrix_not_gig and not issue['avail_matrix']:
            missing_from_matrix.append(issue)
        elif in_matrix_not_gig and not in_gig_not_matrix and not issue['gig_db']:
            missing_from_gig_db.append(issue)
        else:
            dj_mismatches.append(issue)

        if has_calendar:
            in_gig_not_cal = gig_set - cal_set
            if in_gig_not_cal and not cal_set:
                missing_from_calendar.append(issue)

    # Report: Missing from Matrix
    if missing_from_matrix:
        write(f"MISSING FROM AVAILABILITY MATRIX ({len(missing_from_matrix)} dates)")
        write("-" * 70)
        write("These are in the Gig Database but not marked BOOKED in the matrix:")
        write()
        for issue in missing_from_matrix:
            write(f"  {issue['date']:>8}  Gig DB: {', '.join(issue['gig_db'])}")
        write()

    # Report: Missing from Gig DB
    if missing_from_gig_db:
        write(f"MISSING FROM GIG DATABASE ({len(missing_from_gig_db)} dates)")
        write("-" * 70)
        write("These are in the Availability Matrix but not in the Gig Database:")
        write()
        for issue in missing_from_gig_db:
            write(f"  {issue['date']:>8}  Matrix: {', '.join(issue['avail_matrix'])}")
        write()

    # Report: Missing from Calendar
    if has_calendar and missing_from_calendar:
        already_reported = set(i['date'] for i in dj_mismatches)
        cal_only = [i for i in missing_from_calendar if i['date'] not in already_reported]
        if cal_only:
            write(f"MISSING FROM MASTER CALENDAR ({len(cal_only)} dates)")
            write("-" * 70)
            write("These are in the Gig Database but not on the calendar:")
            write()
            for issue in cal_only:
                write(f"  {issue['date']:>8}  Gig DB: {', '.join(issue['gig_db'])}")
            write()

    # Report: DJ Mismatches (the investigation items)
    if dj_mismatches:
        write(f"DJ ASSIGNMENT MISMATCHES ({len(dj_mismatches)} dates)")
        write("-" * 70)
        write("These dates have different DJs across systems:")
        write()
        for issue in dj_mismatches:
            write(f"  {issue['date']:>8}")
            write(f"           Gig DB:  {', '.join(issue['gig_db']) if issue['gig_db'] else '[MISSING]'}")
            write(f"           Matrix:  {', '.join(issue['avail_matrix']) if issue['avail_matrix'] else '[MISSING]'}")
            if has_calendar and 'master_cal' in issue:
                write(f"           Cal:     {', '.join(issue['master_cal']) if issue['master_cal'] else '[MISSING]'}")
            write()

    # =====================================================================
    # BACKUP DJ COMPARISON (Matrix vs Calendar only)
    # =====================================================================
    backup_issues = []
    if matrix_backups is not None and cal_backups is not None:
        all_backup_dates = set(matrix_backups.keys()) | set(cal_backups.keys())
        for date_key in sorted(all_backup_dates, key=date_sort_key):
            m_backups = sorted(set(matrix_backups.get(date_key, [])))
            c_backups = sorted(set(cal_backups.get(date_key, [])))
            if m_backups != c_backups:
                backup_issues.append({
                    'date': date_key,
                    'matrix': m_backups,
                    'calendar': c_backups,
                })

        if backup_issues:
            write(f"BACKUP DJ MISMATCHES ({len(backup_issues)} dates)")
            write("-" * 70)
            write("Backup assignments differ between Matrix and Calendar:")
            write()
            for issue in backup_issues:
                write(f"  {issue['date']:>8}")
                write(f"           Matrix:  {', '.join(issue['matrix']) if issue['matrix'] else '[NONE]'}")
                write(f"           Cal:     {', '.join(issue['calendar']) if issue['calendar'] else '[NONE]'}")
                write()
        else:
            write("BACKUP DJs: Matrix and Calendar are in sync")
            write()

    write("=" * 70)
    total_issues = len(issues) + len(backup_issues)
    write(f"SUMMARY: {len(issues)} booking discrepancy(ies), {len(backup_issues)} backup discrepancy(ies)")
    systems = "Gig DB + Matrix"
    if has_calendar:
        systems += " + Calendar"
    write(f"Systems compared: {systems}")
    write("=" * 70)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Compare DJ booking systems for discrepancies",
        epilog="Example: python3 booking_comparator.py gig-db.txt --year 2026",
    )
    parser.add_argument("gig_db_file", help="Path to gig database text file")
    parser.add_argument("--year", required=True, help="Year to compare (e.g., 2026)")
    parser.add_argument("--no-calendar", action="store_true",
                        help="Skip master calendar comparison")
    parser.add_argument("--output", "-o", help="Save report to file (default: print to console)")

    args = parser.parse_args()

    if not os.path.exists(args.gig_db_file):
        print(f"Error: File not found: {args.gig_db_file}")
        sys.exit(1)

    print(f"\nBOOKING COMPARATOR — {args.year}")
    print("=" * 50)

    # 1. Parse gig database from file
    print(f"\n[1/3] Reading gig database from {args.gig_db_file}...")
    gig_db = parse_gig_db(args.gig_db_file, args.year)
    gig_count = sum(len(v) for v in gig_db.values())
    print(f"  Found {gig_count} bookings on {len(gig_db)} dates")

    # 2. Fetch availability matrix from Google Sheets
    print(f"\n[2/3] Fetching availability matrix from Google Sheets...")
    avail_matrix, matrix_backups = fetch_availability_matrix(args.year)

    # 3. Fetch master calendar via icalBuddy
    master_cal = None
    cal_backups = None
    if not args.no_calendar:
        print(f"\n[3/3] Fetching master calendar via icalBuddy...")
        master_cal, cal_backups = fetch_master_calendar(args.year)
    else:
        print(f"\n[3/3] Skipping master calendar (--no-calendar)")

    # 4. Compare and report
    print(f"\nComparing systems...\n")

    # Auto-generate output filename: MM-DD-YYYY - Systems crosscheck.txt
    if not args.output:
        today = datetime.now().strftime("%m-%d-%Y")
        args.output = f"{today} - Systems crosscheck.txt"

    # Always print to console AND save to file
    compare_systems(gig_db, avail_matrix, master_cal,
                    matrix_backups, cal_backups)

    with open(args.output, 'w') as f:
        compare_systems(gig_db, avail_matrix, master_cal,
                        matrix_backups, cal_backups, output=f)
    print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
