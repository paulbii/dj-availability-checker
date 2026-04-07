#!/usr/bin/env python3
"""
Cancel Booking Script
=====================
Reverses a booking: clears the DJ's cell in the availability matrix,
deletes the calendar event, optionally removes the backup DJ, and
opens the Google Form pre-filled with "Canceled" status.

Usage:
  python3 cancel_booking.py booking.json
  python3 cancel_booking.py booking.json --dry-run
  python3 cancel_booking.py booking.json --test

Input: Same JSON format as gig_booking_manager.py (from gig database).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta
from urllib.parse import quote

from dj_core import (
    COLUMN_MAPS,
    get_dj_initials,
    get_dj_short_name,
    get_default_cell_value,
    is_paid_backup,
    init_google_sheets_from_file,
    get_full_inquiries_for_date,
)

from gig_booking_manager import (
    CALENDAR_NAME,
    BOOKING_LOG_FORM_URL,
    FORM_FIELDS,
    SheetsClient,
    DEFAULT_CREDENTIALS_PATH,
    parse_booking_data,
    show_warning_dialog,
    get_backup_title,
    extract_client_first_names,
)


# ── Calendar deletion ────────────────────────────────────────────────────────

def delete_booking_calendar_event(date_obj, initials_bracket):
    """
    Delete the booking calendar event for a DJ on a given date.
    Matches events by date and DJ initials bracket (e.g., [PB]).
    Skips events containing 'BACKUP DJ' or 'Hold to DJ'.
    Returns the count of deleted events.
    """
    date_str = date_obj.strftime("%B %d, %Y")  # "March 28, 2026"

    script = f'''
    tell application "Calendar"
        tell calendar "{CALENDAR_NAME}"
            set matchingEvents to (every event whose start date >= date "{date_str} 12:00:00 AM" and start date < date "{date_str} 11:59:59 PM" and summary contains "{initials_bracket}")
            set deletedCount to 0
            repeat with anEvent in matchingEvents
                set eventTitle to summary of anEvent
                if eventTitle does not contain "BACKUP DJ" and eventTitle does not contain "Hold to DJ" then
                    delete anEvent
                    set deletedCount to deletedCount + 1
                end if
            end repeat
            return deletedCount
        end tell
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30,
        )
        count = result.stdout.strip()
        return int(count) if count.isdigit() else 0
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"  WARNING: Could not delete calendar event: {e}")
        return 0


def delete_backup_calendar_event(date_obj, backup_dj):
    """Delete the backup DJ's all-day calendar event on a given date."""
    date_str = date_obj.strftime("%B %d, %Y")
    backup_initials = f"[{get_dj_initials(backup_dj)}]"

    script = f'''
    tell application "Calendar"
        tell calendar "{CALENDAR_NAME}"
            set backupEvents to (every event whose start date >= date "{date_str} 12:00:00 AM" and start date < date "{date_str} 11:59:59 PM" and summary contains "BACKUP DJ" and summary contains "{backup_initials}")
            set deletedCount to count of backupEvents
            repeat with anEvent in backupEvents
                delete anEvent
            end repeat
            return deletedCount
        end tell
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30,
        )
        count = result.stdout.strip()
        return int(count) if count.isdigit() else 0
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"  WARNING: Could not delete backup calendar event: {e}")
        return 0


# ── Backup DJ detection ──────────────────────────────────────────────────────

def find_backup_dj(sheets, row_num, year, date_obj):
    """
    Scan the row for any DJ with BACKUP in their cell.
    Returns the DJ name or None.
    """
    row_data = sheets.get_row_data(row_num, year)
    dj_names = ["Henry", "Woody", "Paul", "Stefano", "Felipe", "Stephanie"]

    for dj in dj_names:
        val = row_data.get(dj, "")
        if val:
            statuses = [s.strip().lower() for s in val.split(",")]
            if "backup" in statuses:
                return dj
    return None


# ── Google Form ──────────────────────────────────────────────────────────────

def open_cancel_form(booking):
    """Open Google Form pre-filled with cancellation info."""
    event_date = booking["date"].strftime("%-m-%-d-%y")
    decision_date = datetime.now().strftime("%-m-%-d-%y")
    venue = booking["venue_name"]

    params = (
        f"?usp=pp_url"
        f"&{FORM_FIELDS['event_date']}={quote(event_date)}"
        f"&{FORM_FIELDS['decision_date']}={quote(decision_date)}"
        f"&{FORM_FIELDS['venue']}={quote(venue)}"
        f"&{FORM_FIELDS['status']}={quote('Canceled')}"
    )
    url = BOOKING_LOG_FORM_URL + params
    webbrowser.open(url)
    return url


# ── Ask user about backup removal ────────────────────────────────────────────

def ask_remove_backup(date_display, backup_dj):
    """
    Show AppleScript dialog asking if backup should be removed.
    Returns True if user wants to remove, False to keep.
    """
    paid = "paid" if is_paid_backup(backup_dj) else "unpaid"
    msg = (
        f"{date_display}\\n\\n"
        f"Backup DJ assigned: {backup_dj} ({paid})\\n\\n"
        f"Remove backup assignment?"
    )

    script = f'''
    display dialog "{msg}" with title "Cancel Booking — Backup" buttons {{"Keep Backup", "Remove Backup"}} default button "Remove Backup"
    return button returned of result
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60,
        )
        return result.stdout.strip() == "Remove Backup"
    except Exception:
        return False


# ── Main cancellation flow ───────────────────────────────────────────────────

class BookingCanceller:
    """Orchestrates the cancellation flow."""

    def __init__(self, credentials_path=None, dry_run=False, test_mode=False):
        self.dry_run = dry_run
        self.test_mode = test_mode
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.actions = []

        self.sheets = SheetsClient(self.credentials_path)

    def log(self, action):
        self.actions.append(action)

    def run(self, json_path):
        """Main cancellation flow."""
        print(f"\n{'=' * 60}")
        print(f"  BOOKING CANCELLATION")
        print(f"{'=' * 60}")

        if self.dry_run:
            print("  MODE: DRY RUN (no writes)")
        elif self.test_mode:
            print("  MODE: TEST")
        print()

        # ── Parse booking data ──
        print("  [1/6] Parsing booking data...")
        booking = parse_booking_data(json_path)
        date_obj = booking["date"]
        year = booking["year"]
        dj_name = booking["dj_short_name"]
        initials_bracket = booking["dj_initials_bracket"]
        date_display = booking["date_display"]
        venue = booking["venue_name"]
        client = booking["client_display"]

        print(f"  Date: {date_display}")
        print(f"  DJ: {dj_name} {initials_bracket}")
        print(f"  Client: {client}")
        print(f"  Venue: {venue}")
        print()

        # ── Connect to Sheets ──
        print("  [2/6] Connecting to availability matrix...")
        self.sheets.init()
        print("  Connected.")
        print()

        # ── Validate: confirm DJ is BOOKED ──
        print("  [3/6] Validating booking in matrix...")
        row_num = self.sheets.find_date_row(date_obj, year)
        if not row_num:
            msg = f"Could not find {date_display} in the {year} sheet."
            print(f"  ERROR: {msg}")
            if not self.dry_run:
                show_warning_dialog(f"Cancel Booking Error:\n\n{msg}")
            return False

        col_map = COLUMN_MAPS.get(year, COLUMN_MAPS[2026])
        if dj_name not in col_map:
            msg = f"{dj_name} is not in the column map for {year}."
            print(f"  ERROR: {msg}")
            return False

        col_num = col_map[dj_name]
        row_data = self.sheets.get_row_data(row_num, year)
        current_val = (row_data.get(dj_name, "") or "").strip()
        current_lower = current_val.lower()

        if "booked" not in current_lower and "reserved" not in current_lower and "wedfaire" not in current_lower:
            msg = (
                f"{dj_name}'s cell on {date_display} shows \"{current_val}\" "
                f"(expected BOOKED, RESERVED, or WEDFAIRE)."
            )
            print(f"  WARNING: {msg}")
            if not self.dry_run:
                show_warning_dialog(f"Cancel Booking Warning:\n\n{msg}\n\nProceeding anyway.")

        print(f"  Current value: \"{current_val}\"")

        # Check for backup DJ
        backup_dj = find_backup_dj(self.sheets, row_num, year, date_obj)
        if backup_dj:
            print(f"  Backup DJ found: {backup_dj}")
        print()

        # ── Clear DJ cell in matrix ──
        print("  [4/6] Updating availability matrix...")
        default_val = get_default_cell_value(dj_name, date_obj)
        display_val = f'"{default_val}"' if default_val else "(blank)"

        if self.dry_run:
            print(f"  [DRY RUN] Would set {dj_name} to {display_val} on {date_display}")
            self.log(f"Matrix: would restore {dj_name} to {display_val}")
        else:
            self.sheets.write_cell(row_num, col_num, default_val, year)
            print(f"  ✓ {dj_name} → {display_val}")
            self.log(f"Matrix: restored {dj_name} to {display_val}")

        # Handle backup DJ
        remove_backup = False
        if backup_dj:
            if self.dry_run:
                print(f"  [DRY RUN] Would ask about removing backup: {backup_dj}")
                self.log(f"Backup: would ask about {backup_dj}")
            else:
                remove_backup = ask_remove_backup(date_display, backup_dj)

                if remove_backup:
                    backup_col = col_map.get(backup_dj)
                    if backup_col:
                        backup_default = get_default_cell_value(backup_dj, date_obj)
                        backup_display = f'"{backup_default}"' if backup_default else "(blank)"
                        self.sheets.write_cell(row_num, backup_col, backup_default, year)
                        print(f"  ✓ {backup_dj} → {backup_display} (backup removed)")
                        self.log(f"Matrix: restored {backup_dj} to {backup_display}")
                else:
                    print(f"  Keeping backup: {backup_dj}")
                    self.log(f"Backup: kept {backup_dj}")

        print()

        # ── Delete calendar events ──
        print("  [5/6] Cleaning up calendar...")

        if self.dry_run:
            print(f"  [DRY RUN] Would delete {initials_bracket} event on {date_display}")
            self.log(f"Calendar: would delete {initials_bracket} event")
            if backup_dj:
                print(f"  [DRY RUN] Would consider deleting backup event for {backup_dj}")
        else:
            deleted = delete_booking_calendar_event(date_obj, initials_bracket)
            if deleted:
                print(f"  ✓ Deleted {deleted} calendar event(s) for {initials_bracket}")
                self.log(f"Calendar: deleted {deleted} event(s) for {initials_bracket}")
            else:
                print(f"  ⚠️  No calendar events found for {initials_bracket} on {date_display}")
                self.log(f"Calendar: no events found for {initials_bracket}")

            if remove_backup and backup_dj:
                backup_deleted = delete_backup_calendar_event(date_obj, backup_dj)
                if backup_deleted:
                    print(f"  ✓ Deleted backup event for {backup_dj}")
                    self.log(f"Calendar: deleted backup event for {backup_dj}")
                else:
                    print(f"  ⚠️  No backup calendar event found for {backup_dj}")

        print()

        # ── Clean up nurture emails ──
        print("  [6/6] Cleaning up nurture emails...")
        self._cancel_nurture_emails(booking, date_display)
        print()

        # ── Open Google Form ──
        print("  Opening booking log form (Canceled)...")
        if self.dry_run:
            event_date = booking["date"].strftime("%-m-%-d-%y")
            print(f"  [DRY RUN] Would open form: date={event_date}, venue={venue}, status=Canceled")
            self.log("Form: would open with Canceled status")
        else:
            url = open_cancel_form(booking)
            self.log("Form: opened with Canceled status")
            print("  ✓ Form opened in browser")

        # ── Summary ──
        print()
        print(f"{'=' * 60}")
        print(f"  CANCELLATION SUMMARY")
        print(f"{'=' * 60}")
        for action in self.actions:
            print(f"  • {action}")
        print()

        # ── Check for turned-away inquiries ──
        self._check_turned_away(date_obj, year)

        return True

    def _cancel_nurture_emails(self, booking, date_display):
        """Mark any pending nurture emails for this booking as skipped."""
        try:
            from nurture_config import (
                init_nurture_sheet, col_index, NURTURE_SPREADSHEET_ID
            )

            if not NURTURE_SPREADSHEET_ID:
                print("  ℹ️  Nurture Tracker not configured. Skipping.")
                return

            worksheet = init_nurture_sheet(self.credentials_path)
            all_rows = worksheet.get_all_values()

            if len(all_rows) <= 1:
                print("  ℹ️  No nurture rows to clean up.")
                return

            event_date_str = booking["date"].strftime('%m/%d/%Y')
            venue = booking["venue_name"]
            status_col = col_index("Status")
            event_date_col = col_index("Event Date")
            venue_col = col_index("Venue")
            notes_col = col_index("Notes")

            skipped_count = 0
            today_str = datetime.now().strftime('%m/%d/%Y')

            for i, row in enumerate(all_rows[1:], start=2):  # 1-indexed + header
                row_event = row[event_date_col - 1].strip()
                row_venue = row[venue_col - 1].strip()
                row_status = row[status_col - 1].strip().lower()

                if (row_event == event_date_str and
                        row_venue == venue and
                        row_status == 'pending'):
                    if self.dry_run:
                        print(f"  [DRY RUN] Would skip row {i}: email #{row[col_index('Email #') - 1]}")
                    else:
                        worksheet.update_cell(i, status_col, 'skipped')
                        worksheet.update_cell(i, notes_col,
                                              f"Booking cancelled {today_str}")
                    skipped_count += 1

            if skipped_count > 0:
                action = "would skip" if self.dry_run else "skipped"
                print(f"  ✓ {skipped_count} nurture email(s) {action}")
                self.log(f"Nurture: {action} {skipped_count} pending email(s)")
            else:
                print("  ℹ️  No pending nurture emails found for this booking.")

        except ImportError:
            print("  ℹ️  Nurture system not installed. Skipping.")
        except Exception as e:
            print(f"  ⚠️  Could not clean up nurture emails: {e}")
            self.log(f"Nurture: cleanup failed ({e})")

    def _check_turned_away(self, date_obj, year):
        """Check for inquiries turned away (Full) on this date within 60 days."""
        date_str = date_obj.strftime("%-m/%-d/%Y")
        try:
            results = get_full_inquiries_for_date(date_str, self.sheets.gc, year)
        except Exception:
            return

        if not results:
            return

        # Filter to inquiries where decision date was within the last 60 days
        cutoff = datetime.now() - timedelta(days=60)
        recent = []
        for r in results:
            decision_str = r.get('decision_date', '')
            if not decision_str or decision_str == '—':
                continue
            parsed = None
            for fmt in ("%m/%d/%Y", "%m/%d/%y"):
                try:
                    parsed = datetime.strptime(decision_str, fmt)
                    break
                except ValueError:
                    continue
            if parsed and parsed >= cutoff:
                recent.append(r)

        if not recent:
            return

        print(f"{'=' * 60}")
        print(f"  TURNED-AWAY INQUIRIES FOR THIS DATE")
        print(f"{'=' * 60}")
        for r in recent:
            tier = r.get('tier', 3)
            if tier == 1:
                label = "REACH OUT"
            elif tier == 2:
                label = "MAYBE"
            else:
                label = "STALE"
            venue = r.get('venue', '(no venue)')
            age = r.get('inquiry_age_label', '')
            inquiry_date = r.get('inquiry_date', '')
            age_part = f" -- inquired {age}" if age else ""
            date_part = f" ({inquiry_date})" if inquiry_date and inquiry_date != '—' else ""
            print(f"  {'●' if tier == 1 else '○'} {label}: {venue}{age_part}{date_part}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Cancel a DJ booking: clear matrix, delete calendar event, log to form",
        epilog="Example: python3 cancel_booking.py booking.json",
    )
    parser.add_argument(
        "json_file",
        help="Path to booking JSON file (same format as gig_booking_manager)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without writing to sheets or calendar",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode",
    )
    parser.add_argument(
        "--credentials",
        help="Path to Google service account credentials JSON",
        default=DEFAULT_CREDENTIALS_PATH,
    )

    args = parser.parse_args()

    if not os.path.exists(args.json_file):
        print(f"ERROR: File not found: {args.json_file}")
        sys.exit(1)

    canceller = BookingCanceller(
        credentials_path=args.credentials,
        dry_run=args.dry_run,
        test_mode=args.test,
    )

    try:
        success = canceller.run(args.json_file)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n  Cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        if not args.dry_run:
            show_warning_dialog(f"Cancel Booking Error:\n\n{str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
