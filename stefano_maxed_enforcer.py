"""
Stefano MAXED Enforcer

Scans Stefano's availability matrix column, identifies dates that should be
marked MAXED based on booking rules, and applies them with your approval.

Rules applied:
  1. Weekend buffer: If Stefano is booked any Fri/Sat/Sun, the Fri/Sat/Sun of
     the immediately preceding week AND immediately following week are MAXED
     (unless already booked).
  2. Monthly cap: If a calendar month already has 2+ bookings, all remaining
     Fri/Sat/Sun dates in that month are MAXED.

Overwrites cells that currently have OK or blank values.

Usage:
  python3 stefano_maxed_enforcer.py [--year 2026] [--dry-run]
"""

import argparse
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta

from dj_core import init_google_sheets_from_file, get_default_cell_value

# =============================================================================
# CONFIGURATION
# =============================================================================

STEFANO_COL_LETTER = "G"   # Column G in both 2026 and 2027
STEFANO_COL_INDEX  = 6     # 0-based index for reading rows
STEFANO_COL_NUM    = 7     # 1-based for gspread update_cell
STEFANO_EMAIL      = "stefano@bigfundj.com"

# Cell values that indicate Stefano is already committed — never overwrite these
SKIP_VALUES = {"BOOKED", "BACKUP", "RESERVED", "STANFORD"}


# =============================================================================
# DATE HELPERS
# =============================================================================

def parse_matrix_date(date_str, year):
    """Parse 'Sat 1/18' → date(2026, 1, 18). Returns None on failure."""
    try:
        parts = date_str.strip().split()
        if len(parts) != 2:
            return None
        m, d = parts[1].split("/")
        return date(int(year), int(m), int(d))
    except (ValueError, IndexError):
        return None


def is_fss(d):
    """True if date is Friday (4), Saturday (5), or Sunday (6)."""
    return d.weekday() >= 4


def adjacent_weekend_dates(booked_date):
    """
    Given a booked Fri/Sat/Sun, return the Fri/Sat/Sun dates of the
    immediately preceding week and immediately following week.

    Week boundaries: Monday–Sunday.
    """
    monday = booked_date - timedelta(days=booked_date.weekday())

    prior = [
        monday - timedelta(days=3),   # Prior Friday
        monday - timedelta(days=2),   # Prior Saturday
        monday - timedelta(days=1),   # Prior Sunday
    ]
    nxt = [
        monday + timedelta(days=11),  # Next Friday  (next Monday + 4)
        monday + timedelta(days=12),  # Next Saturday
        monday + timedelta(days=13),  # Next Sunday
    ]
    return prior, nxt


# =============================================================================
# SHEET READING
# =============================================================================

def read_stefano_column(spreadsheet, year):
    """
    Read the date column (A) and Stefano's column (G) for the given year tab.

    Returns list of (date_obj, row_number, cell_value) for every valid date row.
    Row numbers are 1-based (matching gspread update_cell expectations).
    """
    sheet = spreadsheet.worksheet(year)

    # Single bulk read: columns A through G, rows 2 onward
    rows_raw = sheet.get(f"A2:{STEFANO_COL_LETTER}400")

    result = []
    for i, row in enumerate(rows_raw):
        if not row or not row[0].strip():
            continue

        date_obj = parse_matrix_date(row[0], year)
        if not date_obj:
            continue

        # Stefano's cell may be absent if the row is short
        value = row[STEFANO_COL_INDEX].strip().upper() if len(row) > STEFANO_COL_INDEX else ""

        row_number = i + 2  # +1 for 1-based, +1 for skipped header row
        result.append((date_obj, row_number, value))

    return result


# =============================================================================
# RULE ENGINE
# =============================================================================

def calculate_sync(rows, year):
    """
    Recalculate which dates should be MAXED based on current bookings,
    then diff against the matrix to find additions and removals.

    Returns:
        additions:  {date: (row_number, current_value, [reasons])}
        removals:   {date: (row_number, current_value, [reasons])}
        booked_fss: list of confirmed booked Fri/Sat/Sun dates
    """
    date_map = {d: (row, val) for d, row, val in rows}

    # Only Fri/Sat/Sun bookings trigger rules
    booked_fss = [
        d for d, row, val in rows
        if val == "BOOKED" and is_fss(d)
    ]

    # Build the set of dates that SHOULD be MAXED, with reasons
    pending_reasons = defaultdict(set)  # date -> set of reason strings

    # -- Rule 1: Weekend buffer --
    for booked_date in booked_fss:
        prior, nxt = adjacent_weekend_dates(booked_date)
        label = booked_date.strftime("%b %-d")

        for adj in prior:
            if adj in date_map:
                pending_reasons[adj].add(f"prior weekend buffer ({label} booking)")

        for adj in nxt:
            if adj in date_map:
                pending_reasons[adj].add(f"next weekend buffer ({label} booking)")

    # -- Rule 2: Monthly cap --
    by_month = defaultdict(list)
    for d in booked_fss:
        by_month[d.month].append(d)

    for month, booked_dates in by_month.items():
        if len(booked_dates) >= 2:
            month_name = booked_dates[0].strftime("%B")
            reason = f"monthly cap ({month_name} has {len(booked_dates)} bookings)"
            for d, row, val in rows:
                if d.month == month and is_fss(d):
                    pending_reasons[d].add(reason)

    # Build should_be_maxed, excluding SKIP values
    should_be_maxed = set()
    for d in pending_reasons:
        if d in date_map:
            _, val = date_map[d]
            if val not in SKIP_VALUES:
                should_be_maxed.add(d)

    # -- Diff against current state --
    additions = {}
    removals = {}

    for d, row, val in rows:
        if not is_fss(d):
            continue

        if val in SKIP_VALUES:
            continue

        if d in should_be_maxed:
            # Should be MAXED
            if val not in ("MAXED", "OUT"):  # Already blocked -- no action needed
                # Currently blank or OK -- needs to be added
                additions[d] = (row, val, sorted(pending_reasons.get(d, set())))
            # If already MAXED or OUT, no action needed
        else:
            # Should NOT be MAXED
            if val == "MAXED":
                removals[d] = (row, val, ["no active booking requires this date to be blocked"])

    return additions, removals, sorted(booked_fss)


# =============================================================================
# CALENDAR
# =============================================================================

def create_calendar_event(event_date, dry_run=False):
    """Create an all-day [SB] MAXED OUT event on the Unavailable calendar via AppleScript."""
    if dry_run:
        print(f"      [DRY RUN] Calendar: [SB] MAXED OUT on {event_date.strftime('%b %-d, %Y')}")
        return True
    try:
        date_str = event_date.strftime("%B %d, %Y")
        script = f'''
        tell application "Calendar"
            tell calendar "Unavailable"
                set newEvent to make new event with properties {{summary:"[SB] MAXED OUT", start date:date "{date_str} 12:00:00 AM", end date:date "{date_str} 11:59:00 PM", allday event:true}}
                tell newEvent
                    make new attendee at end of attendees with properties {{email:"{STEFANO_EMAIL}"}}
                end tell
            end tell
        end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=45,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return True
    except Exception as e:
        print(f"      Calendar error: {e}")
        return False


def delete_calendar_event(event_date, dry_run=False):
    """Delete [SB] MAXED OUT event(s) from the Unavailable calendar via AppleScript."""
    if dry_run:
        print(f"      [DRY RUN] Calendar: delete [SB] MAXED OUT on {event_date.strftime('%b %-d, %Y')}")
        return True
    try:
        date_str = event_date.strftime("%B %d, %Y")
        script = f'''
        tell application "Calendar"
            tell calendar "Unavailable"
                set matchingEvents to (every event whose start date >= date "{date_str} 12:00:00 AM" and start date < date "{date_str} 11:59:59 PM" and summary contains "[SB]" and summary contains "MAXED")
                set deletedCount to 0
                repeat with anEvent in matchingEvents
                    delete anEvent
                    set deletedCount to deletedCount + 1
                end repeat
                return deletedCount
            end tell
        end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30,
        )
        count = result.stdout.strip()
        if count.isdigit() and int(count) > 0:
            return True
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        print(f"      Calendar: no matching event found to delete")
        return True
    except Exception as e:
        print(f"      Calendar warning: {e}")
        return True  # Don't fail -- matrix is source of truth


# =============================================================================
# SHEET WRITE
# =============================================================================

def write_maxed(spreadsheet, year, row_number, dry_run=False):
    """Write MAXED to Stefano's cell at the given row."""
    if dry_run:
        print(f"      [DRY RUN] Matrix: row {row_number} → MAXED")
        return True

    sheet = spreadsheet.worksheet(year)
    sheet.update_cell(row_number, STEFANO_COL_NUM, "MAXED")
    return True


def clear_maxed(spreadsheet, year, row_number, event_date, dry_run=False):
    """Restore Stefano's cell to its default value (reversing a MAXED entry)."""
    default_val = get_default_cell_value("Stefano", event_date)
    display_val = default_val if default_val else "(blank)"

    if dry_run:
        print(f"      [DRY RUN] Matrix: row {row_number} -> {display_val}")
        return True

    sheet = spreadsheet.worksheet(year)
    sheet.update_cell(row_number, STEFANO_COL_NUM, default_val)
    return True


# =============================================================================
# INTERACTIVE SELECTION
# =============================================================================

def display_and_select(suggestions):
    """
    Display suggestions grouped by rule category, prompt for selection.
    Returns list of (date, row_number, current_value) to apply.
    """
    if not suggestions:
        print("\n✅  No suggested MAXED dates — Stefano's column looks clean.")
        return []

    # Separate into buffer-only, cap-only, and both
    buffer_dates = {}
    cap_dates    = {}
    both_dates   = {}

    for d, (row, val, reasons) in suggestions.items():
        has_buffer = any("buffer" in r for r in reasons)
        has_cap    = any("cap"    in r for r in reasons)
        if has_buffer and has_cap:
            both_dates[d] = (row, val, reasons)
        elif has_buffer:
            buffer_dates[d] = (row, val, reasons)
        else:
            cap_dates[d] = (row, val, reasons)

    ordered = []

    def print_group(label, group):
        if not group:
            return
        print(f"\n── {label} {'─' * (52 - len(label))}")
        for d in sorted(group):
            row, val, reasons = group[d]
            idx = len(ordered) + 1
            current = f"  (currently: {val})" if val else ""
            print(f"  [{idx:2d}]  {d.strftime('%a %b %-d')}{current}")
            for r in reasons:
                print(f"         → {r}")
            ordered.append((d, row, val))

    print_group("Weekend Buffer",    buffer_dates)
    print_group("Monthly Cap",       cap_dates)
    print_group("Buffer + Cap",      both_dates)

    print(f"\n  {len(ordered)} dates suggested.")
    print("  Enter numbers to apply (e.g. 1,3,5), 'all', or press Enter to skip: ", end="")

    raw = input().strip().lower()

    if not raw or raw == "none":
        return []

    if raw == "all":
        return ordered

    try:
        indices  = [int(x.strip()) - 1 for x in raw.split(",")]
        selected = [ordered[i] for i in indices if 0 <= i < len(ordered)]
        return selected
    except ValueError:
        print("⚠️  Could not parse input. No changes made.")
        return []


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Stefano MAXED Enforcer")
    parser.add_argument("--year",    default="2026", choices=["2026", "2027"],
                        help="Which year tab to scan (default: 2026)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview suggestions without writing any changes")
    args = parser.parse_args()

    year    = args.year
    dry_run = args.dry_run

    print(f"\n🎧  Stefano MAXED Enforcer — {year}")
    if dry_run:
        print("    (DRY RUN — no changes will be made)\n")

    # Connect
    print("Connecting to Google Sheets...")
    try:
        service, spreadsheet, spreadsheet_id, client = init_google_sheets_from_file()
    except Exception as e:
        print(f"❌  Could not connect: {e}")
        sys.exit(1)

    # Read
    print(f"Reading Stefano's column ({STEFANO_COL_LETTER}) for {year}...")
    rows = read_stefano_column(spreadsheet, year)

    # Analyze
    additions, removals, booked_fss = calculate_sync(rows, year)

    already_maxed = sum(1 for _, _, v in rows if v in ("MAXED", "OUT"))

    print(f"\n  Booked dates (Fri/Sat/Sun): {len(booked_fss)}")
    if booked_fss:
        print(f"  {', '.join(d.strftime('%b %-d') for d in sorted(booked_fss))}")
    print(f"  Already MAXED/OUT: {already_maxed}")
    print(f"  New suggestions:   {len(additions)}")
    if removals:
        print(f"  Dates to unblock:  {len(removals)}")
    suggestions = additions

    # Select
    selected = display_and_select(suggestions)

    if not selected:
        print("\nNo changes made.")
        return

    # Apply
    print(f"\nApplying {len(selected)} change(s)...\n")
    ok_matrix  = 0
    ok_cal     = 0

    for d, row_number, current_val in selected:
        print(f"  {d.strftime('%a %b %-d, %Y')}:")

        if write_maxed(spreadsheet, year, row_number, dry_run):
            print(f"      ✓ Matrix updated")
            ok_matrix += 1

        if create_calendar_event(d, dry_run):
            print(f"      ✓ Calendar event created")
            ok_cal += 1

    tag = "[DRY RUN] " if dry_run else ""
    print(f"\n{tag}Done — {ok_matrix} matrix update(s), {ok_cal} calendar event(s).")


if __name__ == "__main__":
    main()
