#!/usr/bin/env python3
"""
Backup DJ Assigner
===================
Scans the availability matrix for future dates that have bookings but
no backup DJ assigned, then lets you assign backups interactively.

Usage:
  python3 backup_assigner.py --year 2026
  python3 backup_assigner.py --year 2026 --dry-run
  python3 backup_assigner.py --year 2027

The script:
  - Fetches all availability data in bulk (2 API calls)
  - Filters to future dates with bookings but no backup
  - For each date, shows a dialog to select a backup DJ
  - Writes BACKUP to the matrix and creates an all-day calendar event
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime

# Import shared DJ data from dj_core
from dj_core import (
    SPREADSHEET_ID,
    BACKUP_ELIGIBLE_DJS,
    COLUMN_MAPS,
    get_dj_initials,
    is_paid_backup,
    init_google_sheets_from_file,
    get_bulk_availability_data,
)

# Gig database JSON endpoint (same as booking_comparator)
GIG_DB_JSON_URL = "https://database.bigfundj.com/bigfunadmin/listviewjson.php"

# Map full DJ names from gig DB to short names used in our system
DJ_NAME_MAP = {
    "Henry Newmann": "Henry",
    "Woody Ducharme": "Woody",
    "Paul Burchfield": "Paul",
    "Stefano Pace": "Stefano",
    "Felipe da Silva": "Felipe",
    "Stephanie de Jesus": "Stephanie",
}

# Import booking manager functions (reuse existing logic)
from gig_booking_manager import (
    can_backup,
    calculate_spots_remaining,
    check_existing_backup,
    show_backup_dialog,
    show_warning_dialog,
    create_allday_backup_event,
    check_calendar_conflicts,
    get_backup_title,
    SheetsClient,
    DEFAULT_CREDENTIALS_PATH,
)


class BackupAssigner:
    """Scans for unbackup'd dates and assigns backups interactively."""

    def __init__(self, year, credentials_path=None, dry_run=False, test_mode=False):
        self.year = year
        self.dry_run = dry_run
        self.test_mode = test_mode
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.sheets = SheetsClient(self.credentials_path)
        self.actions = []
        self.stats = {
            "reviewed": 0,
            "assigned": 0,
            "skipped": 0,
            "conflicts": 0,
        }

    def log(self, action):
        """Log an action for the summary."""
        self.actions.append(action)

    def fetch_booking_details(self):
        """
        Fetch venue/client info from gig database JSON endpoint.
        Returns dict: { "M/D": [{"dj": "Henry", "venue": "Kohl Mansion", "client": "Smith"}, ...] }
        """
        url = f"{GIG_DB_JSON_URL}?year={self.year}"
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'BigFunDJ-BackupAssigner/1.0',
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            print(f"  WARNING: Could not fetch booking details: {e}")
            return {}

        bookings = {}
        for record in data:
            date_str = record.get('event_date', '')
            dj_full = record.get('assigned_dj', '')
            venue = record.get('venue_name', '')
            client = record.get('client_name', '')
            status = record.get('status', '').lower()

            if not date_str or status in ('canceled', 'cancelled'):
                continue

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                date_key = f"{date_obj.month}/{date_obj.day}"
            except ValueError:
                continue

            if dj_full.lower() in ('unassigned', 'unknown', ''):
                dj_name = 'TBA'
            else:
                dj_name = DJ_NAME_MAP.get(dj_full, dj_full)

            if date_key not in bookings:
                bookings[date_key] = []
            bookings[date_key].append({
                'dj': dj_name,
                'venue': venue,
                'client': client,
            })

        return bookings

    def init(self):
        """Initialize Google Sheets connections and fetch booking details."""
        print("  Connecting to Google Sheets...")
        self.sheets.init()

        # Also init dj_core's connection for bulk reads
        script_dir = os.path.dirname(os.path.abspath(__file__))
        creds_file = os.path.join(script_dir, "your-credentials.json")
        os.chdir(script_dir)
        self.service, self.spreadsheet, self.spreadsheet_id, self.client = \
            init_google_sheets_from_file(creds_file)
        print("  Connected.")

        # Fetch booking details (DJ + venue) from gig database
        print("  Fetching booking details from gig database...")
        self.booking_details = self.fetch_booking_details()
        if self.booking_details:
            print(f"  Found booking details for {len(self.booking_details)} dates.")
        else:
            print("  No booking details available (venue info won't be shown).")

    def fetch_candidate_dates(self):
        """Fetch future dates with bookings but no backup assigned."""
        print(f"  Fetching {self.year} availability data...")
        all_data = get_bulk_availability_data(
            str(self.year), self.service, self.spreadsheet, self.spreadsheet_id
        )
        if not all_data:
            return []

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        candidates = []
        for d in all_data:
            date_obj = d["date_obj"]
            if date_obj <= today:
                continue
            if not d.get("booked_djs"):
                continue
            if d.get("backup_assigned"):
                continue
            candidates.append(d)

        return candidates

    def process_date(self, date_info, index, total):
        """Process one date: show dialog, optionally write backup."""
        date_obj = date_info["date_obj"]
        date_display = date_info["date"]
        selected_data = date_info["selected_data"]
        bold_status = date_info.get("bold_status", {})
        booked_djs = date_info.get("booked_djs", [])

        self.stats["reviewed"] += 1

        # Print date header with booking details (DJ + venue)
        # Parse "Sat 3/28" to get "3/28" for gig DB lookup
        date_key = date_display.split()[-1] if " " in date_display else date_display
        gig_bookings = self.booking_details.get(date_key, [])

        print(f"[{index}/{total}] {date_display}")
        if gig_bookings:
            for b in gig_bookings:
                venue_str = f" @ {b['venue']}" if b['venue'] else ""
                client_str = f" ({b['client']})" if b['client'] else ""
                print(f"  Booked: {b['dj']}{venue_str}{client_str}")
        else:
            # Fallback to just DJ names from the matrix
            booked_list = ", ".join(booked_djs)
            print(f"  Booked: {booked_list}")

        # Build row_data dict (strip "(BOLD)" suffix from values)
        row_data = {}
        for dj_name, value in selected_data.items():
            if dj_name == "Date":
                continue
            row_data[dj_name] = value.replace(" (BOLD)", "") if value else ""

        # Calculate spots remaining
        spots = calculate_spots_remaining(row_data, self.year, date_obj)

        # Build backup candidates
        candidates = []
        eligible_djs = BACKUP_ELIGIBLE_DJS.get(self.year, BACKUP_ELIGIBLE_DJS[2026])

        for dj_name in eligible_djs:
            # Skip DJs who are already booked on this date
            if dj_name in booked_djs:
                continue

            col_map = COLUMN_MAPS.get(self.year, COLUMN_MAPS[2026])
            if dj_name not in col_map:
                continue

            cell_val = row_data.get(dj_name, "")
            is_bold = bold_status.get(dj_name, False)

            eligible, note = can_backup(dj_name, cell_val, is_bold, date_obj, self.year)
            if eligible:
                candidates.append((dj_name, note))
                paid = "paid" if is_paid_backup(dj_name) else "unpaid"
                note_str = f" — {note}" if note else ""
                print(f"  ✓ {dj_name} ({paid}){note_str}")

        if not candidates:
            print("  No DJs available for backup")
            self.stats["skipped"] += 1
            return

        # Build booking context string for the dialog
        booking_context = None
        if gig_bookings:
            context_parts = []
            for b in gig_bookings:
                part = b['dj']
                if b['venue']:
                    part += f" @ {b['venue']}"
                context_parts.append(part)
            booking_context = "\\n".join(context_parts)

        # Show backup dialog
        if self.dry_run:
            print(f"  [DRY RUN] Would show backup dialog")
            print(f"  Candidates: {[c[0] for c in candidates]}")
            self.stats["skipped"] += 1
            return

        backup_dj = show_backup_dialog(date_display, spots, candidates, None, booking_context)

        if backup_dj == "STOP":
            print("  Stopped by user.")
            return "STOP"

        if not backup_dj:
            print("  Skipped")
            self.stats["skipped"] += 1
            return

        print(f"  Selected: {backup_dj}")

        # Check calendar conflicts
        initials_bracket = f"[{get_dj_initials(backup_dj)}]"
        conflicts = check_calendar_conflicts(date_obj, initials_bracket)

        if conflicts:
            conflict_list = "\n".join(conflicts)
            msg = (
                f"Calendar conflict for {initials_bracket} "
                f"on {date_display}:\n\n{conflict_list}\n\n"
                f"Backup NOT assigned."
            )
            print(f"  ⚠️  Calendar conflict: {conflict_list}")
            show_warning_dialog(msg)
            self.stats["conflicts"] += 1
            self.stats["skipped"] += 1
            return

        # Find row number for writing
        row_num = self.sheets.find_date_row(date_obj, self.year)
        if not row_num:
            print(f"  ERROR: Could not find row for {date_display}")
            self.stats["skipped"] += 1
            return

        # Write BACKUP to matrix
        col_map = COLUMN_MAPS.get(self.year, COLUMN_MAPS[2026])
        col_num = col_map[backup_dj]
        current_val = (row_data.get(backup_dj, "") or "").strip()
        replace_values = {"", "OUT", "OK", "DAD", "STANFORD", "LAST", "OK TO BACKUP", "BACKUP"}

        if current_val.upper() in replace_values:
            new_val = "BACKUP"
        else:
            new_val = f"{current_val}, BACKUP"

        self.sheets.write_cell(row_num, col_num, new_val, self.year)
        self.log(f"{date_display}: {backup_dj} → {new_val}")
        print(f"  ✓ Matrix: {backup_dj} → '{new_val}'")

        # Create calendar event
        backup_title = create_allday_backup_event(date_obj, backup_dj, self.test_mode)
        self.log(f"{date_display}: created '{backup_title}'")
        print(f"  ✓ Calendar: {backup_title}")

        self.stats["assigned"] += 1

    def run(self):
        """Main execution flow."""
        print(f"\n{'=' * 60}")
        print(f"  BACKUP DJ ASSIGNER — {self.year}")
        print(f"{'=' * 60}")

        if self.dry_run:
            print("  MODE: DRY RUN (no writes)")
        elif self.test_mode:
            print("  MODE: TEST (invites → paul@)")
        print()

        # Initialize
        self.init()
        print()

        # Fetch candidate dates
        candidates = self.fetch_candidate_dates()

        if not candidates:
            print("  No future dates found with bookings but no backup.")
            print("  All set!")
            return True

        print(f"  Found {len(candidates)} date(s) needing backup assignment")
        print()

        # Process each date
        for i, date_info in enumerate(candidates, 1):
            result = self.process_date(date_info, i, len(candidates))
            print()
            if result == "STOP":
                print("  Stopped early by user.")
                break

        # Summary
        print(f"{'=' * 60}")
        print(f"  SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Dates reviewed:     {self.stats['reviewed']}")
        print(f"  Backups assigned:   {self.stats['assigned']}")
        print(f"  Calendar conflicts: {self.stats['conflicts']}")
        print(f"  Dates skipped:      {self.stats['skipped']}")

        if self.actions:
            print()
            for action in self.actions:
                print(f"  • {action}")
        print()

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Assign backup DJs to dates with bookings but no backup",
        epilog="Example: python3 backup_assigner.py --year 2026",
    )
    parser.add_argument(
        "--year", required=True, type=int,
        help="Year to process (e.g., 2026, 2027)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without writing to sheets or calendar",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode: calendar invites go to paul@bigfundj.com",
    )
    parser.add_argument(
        "--credentials",
        help="Path to Google service account credentials JSON",
        default=DEFAULT_CREDENTIALS_PATH,
    )

    args = parser.parse_args()

    assigner = BackupAssigner(
        year=args.year,
        credentials_path=args.credentials,
        dry_run=args.dry_run,
        test_mode=args.test,
    )

    try:
        success = assigner.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n  Cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        if not args.dry_run:
            show_warning_dialog(f"Backup Assigner Error:\n\n{str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
