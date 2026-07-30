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
    normalize_event_type,
    show_warning_dialog,
    show_notification,
    get_backup_title,
    extract_client_first_names,
    is_setup_booking,
    setup_helper_short,
    setup_event_bracket,
    primary_event_title,
)


# ── Calendar deletion ────────────────────────────────────────────────────────
#
# The whose-clause scan is inherently slow (Calendar.app walks the entire Gigs
# calendar), so the timeout is generous. 30s was not enough: on 2026-07-29 the
# delete timed out and was misreported as "no events found."
CALENDAR_TIMEOUT = 180


def _run_calendar_delete(script):
    """
    Run a deletion AppleScript that speaks the result protocol:
        DELETED:<n>          — n events deleted
        NONE                 — nothing matched at all
        FOUND:<t1>||<t2>...  — candidates found, none deleted

    Returns (status, payload):
        ("deleted", n) | ("not_found", 0) | ("ambiguous", [titles]) | ("error", msg)
    A timeout or osascript failure is ALWAYS ("error", ...) — never "not_found".
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=CALENDAR_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return ("error", f"Calendar query timed out after {CALENDAR_TIMEOUT}s")
    except Exception as e:
        return ("error", str(e))

    if result.returncode != 0:
        return ("error", result.stderr.strip() or f"osascript exit {result.returncode}")

    out = result.stdout.strip()
    if out.startswith("DELETED:"):
        count = out[len("DELETED:"):]
        if count.isdigit():
            return ("deleted", int(count))
        return ("error", f"unparseable count in {out!r}")
    if out == "NONE":
        return ("not_found", 0)
    if out.startswith("FOUND:"):
        titles = [t for t in out[len("FOUND:"):].split("||") if t]
        return ("ambiguous", titles)
    return ("error", f"unexpected osascript output: {out!r}")


def acceptable_event_titles(booking):
    """
    Every title the booking's calendar event may legitimately carry.

    Always the title gig_booking_manager would create today. When the client
    reads "A and B", also the "B and A" variant: the 10/16/2026 cancellation
    showed FileMaker's name order can differ from the order at booking time
    ("Jaylin and Julie" vs the event's "Julie and Jaylin"). Names with more
    than one "and" are left alone — permuting them would guess.
    """
    titles = [primary_event_title(booking)]

    parts = booking["client_display"].split(" and ")
    if len(parts) == 2:
        swapped = dict(booking)
        swapped["client_display"] = f"{parts[1]} and {parts[0]}"
        titles.append(primary_event_title(swapped))

    return titles


def delete_booking_calendar_event(date_obj, initials_bracket, expected_titles):
    """
    Delete the booking calendar event for a DJ on a given date.

    Deletes only events whose title EXACTLY matches one of expected_titles
    (from acceptable_event_titles). Events that merely share the initials
    bracket — a second booking for the same DJ that day — are reported back,
    never deleted. BACKUP DJ / Hold to DJ events are excluded from that
    report; they are never deletion candidates here.

    Returns (status, payload) per _run_calendar_delete.
    """
    date_str = date_obj.strftime("%B %d, %Y")  # "March 28, 2026"
    escaped = [t.replace("\\", "\\\\").replace('"', '\\"') for t in expected_titles]
    titles_list = "{" + ", ".join(f'"{t}"' for t in escaped) + "}"

    script = f'''
    tell application "Calendar"
        tell calendar "{CALENDAR_NAME}"
            set okTitles to {titles_list}
            set matchingEvents to (every event whose start date >= date "{date_str} 12:00:00 AM" and start date < date "{date_str} 11:59:59 PM" and summary contains "{initials_bracket}")
            set exactEvents to {{}}
            set otherTitles to {{}}
            repeat with anEvent in matchingEvents
                set eventTitle to summary of anEvent
                if okTitles contains eventTitle then
                    set end of exactEvents to anEvent
                else if eventTitle does not contain "BACKUP DJ" and eventTitle does not contain "Hold to DJ" then
                    set end of otherTitles to eventTitle
                end if
            end repeat
            if (count of exactEvents) > 0 then
                repeat with anEvent in exactEvents
                    delete anEvent
                end repeat
                return "DELETED:" & (count of exactEvents)
            else if (count of otherTitles) > 0 then
                set AppleScript's text item delimiters to "||"
                set joined to otherTitles as text
                set AppleScript's text item delimiters to ""
                return "FOUND:" & joined
            else
                return "NONE"
            end if
        end tell
    end tell
    '''
    return _run_calendar_delete(script)


def delete_backup_calendar_event(date_obj, backup_dj):
    """
    Delete the backup DJ's all-day calendar event on a given date.

    Backup titles are formulaic ('BACKUP DJ' + initials), so the contains
    match stays; only the timeout and error reporting changed.
    Returns (status, payload) per _run_calendar_delete.
    """
    date_str = date_obj.strftime("%B %d, %Y")
    backup_initials = f"[{get_dj_initials(backup_dj)}]"

    script = f'''
    tell application "Calendar"
        tell calendar "{CALENDAR_NAME}"
            set backupEvents to (every event whose start date >= date "{date_str} 12:00:00 AM" and start date < date "{date_str} 11:59:59 PM" and summary contains "BACKUP DJ" and summary contains "{backup_initials}")
            if (count of backupEvents) > 0 then
                set deletedCount to count of backupEvents
                repeat with anEvent in backupEvents
                    delete anEvent
                end repeat
                return "DELETED:" & deletedCount
            else
                return "NONE"
            end if
        end tell
    end tell
    '''
    return _run_calendar_delete(script)


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
    event_type = normalize_event_type(booking.get("event_type", ""))

    params = (
        f"?usp=pp_url"
        f"&{FORM_FIELDS['event_date']}={quote(event_date)}"
        f"&{FORM_FIELDS['decision_date']}={quote(decision_date)}"
        f"&{FORM_FIELDS['venue']}={quote(venue)}"
        f"&{FORM_FIELDS['status']}={quote('Canceled')}"
        f"&{FORM_FIELDS['event_type']}={quote(event_type)}"
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

    # Long timeout: this decides a matrix write. If it still expires, say the
    # answer was defaulted rather than chosen.
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=1800,
        )
        return result.stdout.strip() == "Remove Backup"
    except subprocess.TimeoutExpired:
        print("  WARNING: Backup dialog expired unanswered — keeping backup by default.")
        return False
    except Exception:
        return False


# ── Turned-away inquiries dialog ─────────────────────────────────────────────

def show_turned_away_dialog(date_display, inquiries, older_count=0, error=None):
    """
    Show the turned-away inquiries for a freed-up date.

    Always shows, even with nothing to report, so that "no one was turned
    away" is visibly different from "the lookup broke." Read-only, so it
    runs in dry-run too.
    """
    lines = [date_display, ""]

    if error:
        lines.append("Could not check the inquiry tracker:")
        lines.append(f"    {error}")
        lines.append("")
        lines.append("Check the tracker by hand before assuming no one")
        lines.append("was turned away on this date.")
    elif inquiries:
        for r in inquiries:
            tier = r.get("tier", 3)
            label = {1: "REACH OUT", 2: "MAYBE"}.get(tier, "STALE")
            bullet = "●" if tier == 1 else "○"
            venue = r.get("venue") or "(no venue)"
            lines.append(f"{bullet} {label}: {venue}")

            age = r.get("inquiry_age_label", "")
            inquiry_date = r.get("inquiry_date", "")
            detail = ""
            if age:
                detail = f"inquired {age}"
            if inquiry_date and inquiry_date != "—":
                detail = f"{detail} ({inquiry_date})" if detail else inquiry_date
            if detail:
                lines.append(f"    {detail}")
            lines.append("")
        if older_count:
            lines.append(f"({older_count} more, turned away over 60 days ago,")
            lines.append("not shown)")
    else:
        lines.append("No one was turned away on this date.")
        if older_count:
            lines.append("")
            lines.append(f"({older_count} turned away over 60 days ago,")
            lines.append("not shown)")

    msg = "\\n".join(lines).rstrip("\\n").replace('"', '\\"')

    # System Events owns the dialog so it comes to the front rather than
    # opening behind whatever window has focus.
    script = f'''
    tell application "System Events"
        activate
        display dialog "{msg}" with title "Turned-Away Inquiries" buttons {{"OK"}} default button "OK"
    end tell
    '''

    # Generous timeout: this dialog is the only place these inquiries surface
    # during a Stream Deck run, so it needs to survive stepping away from the
    # desk. If it does expire, the same list is still in the run log.
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=1800,
        )
    except subprocess.TimeoutExpired:
        print("  WARNING: Turned-away dialog expired unacknowledged (see list above).")
    except Exception as e:
        print(f"  WARNING: Could not show turned-away dialog: {e}")


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
        is_setup = is_setup_booking(booking)
        # For a 2-person setup the calendar title is [DJ1/DJ2]; match that exact
        # bracket so the event actually gets deleted (a plain [DJ1] won't match).
        initials_bracket = setup_event_bracket(booking)
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

        if ("booked" not in current_lower and "reserved" not in current_lower
                and "wedfaire" not in current_lower and "setup" not in current_lower):
            msg = (
                f"{dj_name}'s cell on {date_display} shows \"{current_val}\" "
                f"(expected BOOKED, RESERVED, WEDFAIRE, or SETUP)."
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

        # On a 2-person setup, also clear the helper's SETUP cell.
        if is_setup:
            helper = setup_helper_short(booking)
            if helper and helper in col_map and helper != dj_name:
                helper_current = (row_data.get(helper, "") or "").strip()
                if "setup" in helper_current.lower():
                    helper_col = col_map[helper]
                    helper_default = get_default_cell_value(helper, date_obj)
                    helper_display = f'"{helper_default}"' if helper_default else "(blank)"
                    if self.dry_run:
                        print(f"  [DRY RUN] Would set helper {helper} to {helper_display}")
                        self.log(f"Matrix: would restore helper {helper} to {helper_display}")
                    else:
                        self.sheets.write_cell(row_num, helper_col, helper_default, year)
                        print(f"  ✓ {helper} → {helper_display} (setup helper)")
                        self.log(f"Matrix: restored helper {helper} to {helper_display}")
                else:
                    print(f"  ℹ️  Helper {helper} cell is \"{helper_current}\" (not SETUP) — left as is")

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
        expected_titles = acceptable_event_titles(booking)
        expected_title = expected_titles[0]
        calendar_failed = False

        if self.dry_run:
            shown = " or ".join(f'"{t}"' for t in expected_titles)
            print(f"  [DRY RUN] Would delete event titled {shown} on {date_display}")
            self.log(f"Calendar: would delete \"{expected_title}\"")
            if backup_dj:
                print(f"  [DRY RUN] Would consider deleting backup event for {backup_dj}")
        else:
            status, payload = delete_booking_calendar_event(
                date_obj, initials_bracket, expected_titles)

            if status == "deleted":
                print(f"  ✓ Deleted {payload} calendar event(s): \"{expected_title}\"")
                self.log(f"Calendar: deleted {payload} event(s) \"{expected_title}\"")
            elif status == "not_found":
                print(f"  ⚠️  No {initials_bracket} events on {date_display} — nothing deleted")
                self.log(f"Calendar: no {initials_bracket} events found (nothing deleted)")
            elif status == "ambiguous":
                calendar_failed = True
                titles = "\n".join(f"  • {t}" for t in payload)
                msg = (
                    f"No event titled \"{expected_title}\" on {date_display}.\n\n"
                    f"Found instead:\n{titles}\n\n"
                    f"NOTHING was deleted. If one of these is this booking "
                    f"(renamed?), delete it in Calendar by hand."
                )
                print(f"  ⚠️  CALENDAR NOT UPDATED — exact title not found; "
                      f"{len(payload)} other {initials_bracket} event(s) left alone")
                self.log(f"⚠️ CALENDAR NOT UPDATED: \"{expected_title}\" not found; "
                         f"left alone: {', '.join(payload)}")
                show_warning_dialog(f"Cancel Booking — Calendar:\n\n{msg}")
            else:  # error
                calendar_failed = True
                print(f"  ⚠️  CALENDAR NOT UPDATED — {payload}")
                self.log(f"⚠️ CALENDAR NOT UPDATED ({payload}) — "
                         f"delete \"{expected_title}\" on {date_display} by hand")
                show_warning_dialog(
                    f"Cancel Booking — Calendar:\n\n"
                    f"Could not delete the calendar event:\n{payload}\n\n"
                    f"The matrix was already updated. Delete "
                    f"\"{expected_title}\" on {date_display} in Calendar by hand, "
                    f"then run the crosscheck."
                )

            if remove_backup and backup_dj:
                b_status, b_payload = delete_backup_calendar_event(date_obj, backup_dj)
                if b_status == "deleted":
                    print(f"  ✓ Deleted backup event for {backup_dj}")
                    self.log(f"Calendar: deleted backup event for {backup_dj}")
                elif b_status == "not_found":
                    print(f"  ⚠️  No backup calendar event found for {backup_dj}")
                    self.log(f"Calendar: no backup event found for {backup_dj}")
                else:
                    calendar_failed = True
                    print(f"  ⚠️  BACKUP EVENT NOT DELETED — {b_payload}")
                    self.log(f"⚠️ BACKUP EVENT NOT DELETED ({b_payload}) — "
                             f"remove {backup_dj}'s backup event on {date_display} by hand")
                    show_warning_dialog(
                        f"Cancel Booking — Calendar:\n\n"
                        f"Backup matrix cell was cleared, but {backup_dj}'s backup "
                        f"calendar event on {date_display} could not be deleted:\n"
                        f"{b_payload}\n\nRemove it in Calendar by hand."
                    )

        print()

        # ── Clean up nurture emails ──
        print("  [6/6] Cleaning up nurture emails...")
        self._cancel_nurture_emails(booking, date_display)
        print()

        # ── Check for turned-away inquiries ──
        # Before the form, so the browser tab is the last thing on screen
        # instead of a dialog fighting Safari for focus.
        self._check_turned_away(date_obj, year)

        # ── Open Google Form ──
        # A setup was never an inquiry/booking in the tracker (gig_booking_manager
        # skips the form for setups), so don't log a bogus "Canceled" row for one.
        if is_setup:
            print("  Skipping booking log form (setup — not an inquiry/booking)")
            self.log("Form: skipped (setup)")
        else:
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

        # ── Notify (production only) ──
        if not self.dry_run:
            title = "⚠️ Cancel Booking — CHECK CALENDAR" if calendar_failed else "Cancel Booking"
            show_notification(title, "\n".join(self.actions))

        return not calendar_failed

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
        """
        Check for inquiries turned away (Full) on this date within 60 days.

        The dialog always shows, including when there is nothing to report.
        A silent result is indistinguishable from a failure, which defeats
        the point of surfacing this at all.
        """
        date_str = date_obj.strftime("%-m/%-d/%Y")
        date_display = date_obj.strftime("%a %-m/%-d/%Y")

        try:
            results = get_full_inquiries_for_date(date_str, self.sheets.gc, year)
        except Exception as e:
            print(f"  WARNING: Turned-away lookup failed: {e}")
            self.log(f"Turned-away: lookup failed ({e})")
            show_turned_away_dialog(date_display, [], error=str(e))
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

        print(f"{'=' * 60}")
        print(f"  TURNED-AWAY INQUIRIES FOR THIS DATE")
        print(f"{'=' * 60}")
        if recent:
            for r in recent:
                tier = r.get('tier', 3)
                if tier == 1:
                    label = "REACH OUT"
                elif tier == 2:
                    label = "MAYBE"
                else:
                    label = "STALE"
                venue = r.get('venue') or '(no venue)'
                age = r.get('inquiry_age_label', '')
                inquiry_date = r.get('inquiry_date', '')
                age_part = f" -- inquired {age}" if age else ""
                date_part = f" ({inquiry_date})" if inquiry_date and inquiry_date != '—' else ""
                print(f"  {'●' if tier == 1 else '○'} {label}: {venue}{age_part}{date_part}")
            self.log(f"Turned-away: {len(recent)} inquiry(ies) found")
        else:
            older = len(results) - len(recent)
            extra = f" ({older} older than 60 days)" if older else ""
            print(f"  None within 60 days{extra}.")
            self.log("Turned-away: none")
        print()

        # Stream Deck runs this headless with stdout going to a log file, so the
        # printout above is invisible in normal use. Surface it as a dialog.
        show_turned_away_dialog(date_display, recent, older_count=len(results) - len(recent))


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
