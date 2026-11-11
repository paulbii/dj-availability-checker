#!/usr/bin/env python3
"""
Gig Booking Manager
====================
Automates availability matrix updates and calendar event creation when a new
booking is entered in the FileMaker gig database.

Flow:
  Phase 1 (Validate):   Check matrix cell + check calendar for conflicts
  Phase 2 (Matrix):     Write BOOKED + backup dialog + write BACKUP
  Phase 3 (Calendar):   Create primary event + create backup event

Usage:
  # From AppleScript (production)
  python3 gig_booking_manager.py /tmp/gig_booking.json

  # Test mode (all writes simulated, printed to console)
  python3 gig_booking_manager.py /tmp/gig_booking.json --dry-run

  # Direct with clean-format JSON for testing
  python3 gig_booking_manager.py sample_bookings/normal_booking.json --dry-run
"""

import html
import json
import sys
import os
import subprocess
import argparse
import webbrowser
import imaplib
from datetime import datetime, timedelta
from urllib.parse import quote
import re
import calendar as cal_module
import calendar_read
from booking_comparator import parse_dj_codes

# Import shared business logic from dj_core (single source of truth)
from dj_core import (
    # Constants
    SPREADSHEET_ID,
    DJ_INITIALS,
    DJ_EMAILS,
    DJ_NAME_MAP,
    IMAP_KEYCHAIN_ACCOUNT,
    IMAP_KEYCHAIN_SERVICE,
    PAID_BACKUP_DJS,
    load_imap_credentials,
    UNPAID_BACKUP_DJS,
    COLUMN_MAPS,
    BACKUP_ELIGIBLE_DJS,
    KNOWN_CELL_VALUES,
    SCOPE as SCOPES,
    # Utility functions
    get_dj_short_name,
    get_dj_initials,
    get_unassigned_initials,
    is_weekend,
    date_to_sheet_format,
    extract_client_first_names,
    strip_preference_tag,
    parse_tba_value,
    is_paid_backup,
    # Time calculations
    calculate_arrival_offset,
    convert_times_to_24h,
    calculate_event_times,
    aag_couple_from_row,
    aag_reserved_dj,
    get_default_cell_value,
)


# =============================================================================
# CONFIGURATION (local to booking manager)
# =============================================================================

from calendar_app import CALENDAR_NAME, CalendarApp, CalendarAppError  # CALENDAR_NAME re-exported for the other buttons

# Google Form for booking log
BOOKING_LOG_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScNrxG2zvtJ-3BAh72xUkN_UinzRC66n1j3zACGqsC_62Do7w/viewform"
FORM_FIELDS = {
    "event_date": "entry.537274969",
    "decision_date": "entry.1777773709",
    "venue": "entry.2004165625",
    "status": "entry.918038989",
    "event_type": "entry.202193973",
}

# Event Type dropdown options on the inquiry-tracker form. FileMaker's Type
# field shares this vocabulary, except its empty default ("Unselected") and any
# value not in this set, which we normalize to "Unknown" so the prefill always
# matches a real dropdown option.
FORM_EVENT_TYPES = {
    "Wedding", "Anniversary", "Bar/Bat Mitzvah", "Birthday", "College",
    "Community", "Corporate", "High School", "Holiday", "Other", "Unknown",
}


def normalize_event_type(raw):
    """Map a FileMaker event type to a valid form dropdown value."""
    value = (raw or "").strip()
    return value if value in FORM_EVENT_TYPES else "Unknown"


def is_setup_booking(booking):
    """True when the booking is a setup/rehearsal day (Event Type = Setup).

    A setup is a resource commitment, not a sale: it gets SETUP in the matrix
    (not BOOKED), no backup, and a Setup-labeled calendar event.
    """
    return booking.get("event_type", "").strip().lower() == "setup"


def setup_matrix_value(current_value):
    """The matrix cell value when writing a setup commitment.

    Blank cell → 'SETUP'. A cell with an existing value keeps it and appends
    ', SETUP' (e.g. 'DAD' → 'DAD, SETUP'), parallel to how backups are written.
    Idempotent: never adds a second SETUP.
    """
    current = (current_value or "").strip()
    if not current:
        return "SETUP"
    parts = [p.strip() for p in current.split(",") if p.strip()]
    if any(p.upper() == "SETUP" for p in parts):
        return current
    return f"{current}, SETUP"


def setup_helper_short(booking):
    """The rostered co-DJ ("helper") in the DJ2 slot of a setup, or None.

    Only returns a name for setup events, and only when the DJ2 slot holds a
    rostered DJ. Roadies / unknown names return None (they aren't tracked in the
    matrix). Used to mark both people SETUP and to build the [DJ1/DJ2] title.
    """
    if not is_setup_booking(booking):
        return None
    short = get_dj_short_name(booking.get("dj2_full_name", ""))
    return short if short in DJ_EMAILS else None


def setup_event_bracket(booking):
    """Calendar title bracket for a booking: '[DJ1/DJ2]' for a 2-person setup,
    else the primary's '[DJ1]'. Shared by title-building and cancellation so the
    bracket that gets created is the same one that gets deleted."""
    helper = setup_helper_short(booking)
    if helper:
        return f"[{booking['dj_initials']}/{get_dj_initials(helper)}]"
    return booking["dj_initials_bracket"]


def primary_event_title(booking):
    """Build the primary calendar event title: '[XX] Client'.

    For a 2-person setup, both DJs go in the bracket ('[WM/PB] …') so the
    calendar cross-check sees both. Appends ' Setup' for setup events (unless the
    client name already says it) and a ' (planner)' suffix when a planner is
    involved. Single source of truth so the dry-run preview and the real
    calendar write can't diverge.
    """
    title = f"{setup_event_bracket(booking)} {booking['client_display']}"
    if is_setup_booking(booking) and "setup" not in booking["client_display"].lower():
        title += " Setup"
    if booking["has_planner"]:
        title += " (planner)"
    return title

# Default credentials path — override with --credentials flag
DEFAULT_CREDENTIALS_PATH = os.path.join(
    os.path.expanduser("~"), "Documents", "projects",
    "dj-availability-checker", "your-credentials.json"
)

# Booking email folders live under this top-level mailbox on the love2tap
# account (a sibling of INBOX on Fastmail): BIG FUN/<year>/<MM-DD-YY: names>.
EMAIL_FOLDER_ROOT = "BIG FUN"

# Formula templates for auto-creating new date rows
# Column letters map to formulas. {row} will be replaced with actual row number.
# Based on template from row 229 in 2026 sheet.
ROW_FORMULA_TEMPLATES = {
    "B": '=IF(T{row}<1,LEFT("(((((((",S{row})&"NO SPOTS"&LEFT(")))))))",S{row}),"")',
    "C": '=IF(T{row}=1,LEFT("(((((((",S{row})&"1 SPOT"&LEFT(")))))))",S{row}),"")',
    "E": '=if(or(weekday($A{row},2)>5),"OUT","")',
    "G": '=if(or(weekday($A{row},2)<6,weekday($A{row},2)=7),"OUT","")',
    "H": '=if(weekday($A{row},2)<6,"OUT","")',
}
# Columns D, F, I, J, K, L are left blank (data entry columns)


def increment_tba(current_value):
    """
    Increment TBA column value when adding an unassigned booking.
    '' → 'BOOKED', 'BOOKED' → 'BOOKED x 2', 'BOOKED x 2' → 'BOOKED x 3',
    'AAG' → 'BOOKED, AAG', 'BOOKED, AAG' → 'BOOKED x 2, AAG'
    """
    if not current_value or current_value.strip() == "":
        return "BOOKED"

    parts = [p.strip() for p in current_value.split(",")]
    aag_parts = [p for p in parts if p.upper() == "AAG"]
    booked_parts = [p for p in parts if p.upper() != "AAG"]

    if not booked_parts:
        # Only AAG, add BOOKED
        return "BOOKED, " + ", ".join(aag_parts)
    elif len(booked_parts) == 1:
        bp = booked_parts[0].upper()
        if bp == "BOOKED":
            new_booked = "BOOKED x 2"
        elif bp.startswith("BOOKED X "):
            try:
                n = int(bp.replace("BOOKED X ", ""))
                new_booked = f"BOOKED x {n + 1}"
            except ValueError:
                new_booked = "BOOKED x 2"
        else:
            new_booked = "BOOKED x 2"
    else:
        new_booked = booked_parts[0]  # Shouldn't happen

    if aag_parts:
        return new_booked + ", " + ", ".join(aag_parts)
    return new_booked


def count_booked_events(cell_value):
    """
    Count the number of BOOKED events in a matrix cell value.
    '' or 'OUT' → 0
    'BOOKED' → 1
    'BOOKED x 2' → 2
    'BOOKED x 3' → 3
    """
    if not cell_value or cell_value.strip() == "":
        return 0

    value_upper = cell_value.upper().strip()

    if value_upper == "BOOKED":
        return 1
    elif value_upper.startswith("BOOKED X "):
        try:
            n = int(value_upper.replace("BOOKED X ", ""))
            return n
        except ValueError:
            return 0
    else:
        return 0


def increment_booked(current_value):
    """
    Increment a DJ's BOOKED cell value when adding multiple bookings.
    '' → 'BOOKED', 'BOOKED' → 'BOOKED x 2', 'BOOKED x 2' → 'BOOKED x 3'
    """
    if not current_value or current_value.strip() == "":
        return "BOOKED"

    value_upper = current_value.upper().strip()

    if value_upper == "BOOKED":
        return "BOOKED x 2"
    elif value_upper.startswith("BOOKED X "):
        try:
            n = int(value_upper.replace("BOOKED X ", ""))
            return f"BOOKED x {n + 1}"
        except ValueError:
            return "BOOKED x 2"
    else:
        # Cell has some other value (OUT, BACKUP, etc.) - shouldn't happen
        return current_value


# =============================================================================
# BOOKING DATA PARSING
# =============================================================================

def parse_booking_data(json_path):
    """Load and normalize booking data from FM or clean JSON format."""
    with open(json_path, "r") as f:
        raw = json.load(f)

    # FileMaker exports can arrive with HTML entities baked in (e.g. "&" as
    # "&amp;"), which flow untouched into calendar event titles. Decode at the
    # boundary so downstream code sees plain text.
    raw = {k: html.unescape(v) if isinstance(v, str) else v for k, v in raw.items()}

    # Detect format by presence of FM-specific field
    if "FMclient" in raw:
        return parse_fm_format(raw)
    else:
        return parse_clean_format(raw)


def parse_fm_format(raw):
    """Parse FileMaker format booking data."""
    # Date
    date_str = raw.get("FMeventDate", "")
    date_obj = datetime.strptime(date_str, "%m/%d/%Y")

    # DJ assignment
    dj1 = raw.get("FMDJ1", "")
    dj2 = raw.get("FMDJ2", "")
    dj_short = get_dj_short_name(dj1)

    if dj_short == "Unassigned":
        dj_initials = get_unassigned_initials(dj2)
    elif dj_short == "Unknown":
        dj_initials = "UP"
    else:
        dj_initials = get_dj_initials(dj_short)

    # Client name
    client_full = strip_preference_tag(raw.get("FMclient", "Unknown Client"))
    client_display = extract_client_first_names(client_full)

    # Venue
    venue_raw = raw.get("FMvenue", "")
    venue_name = re.sub(r"\s*\(.*?\)\s*", "", venue_raw).strip()

    # Venue address
    address_raw = raw.get("FMvenueAddress", "")
    address_parts = address_raw.split("***")
    venue_street = address_parts[0].strip() if len(address_parts) > 0 else ""
    # Skip middle part (unused), city/state/zip is last
    venue_city_state_zip = address_parts[-1].strip() if len(address_parts) > 1 else ""

    # Times
    start_time = raw.get("FMstartTime", "")
    end_time = raw.get("FMendTime", "")

    # Sound and ceremony
    sound_type = raw.get("FMsound", "Standard Speakers")
    ceremony_sound = raw.get("FMcersound", "0")
    has_ceremony = ceremony_sound == "1"

    # Planner
    coordinator = raw.get("MailCoordinator", "")
    has_planner = bool(coordinator and coordinator.strip())

    # Client email addresses (for nurture system)
    email1 = raw.get("FMemail1", "").strip()
    email2 = raw.get("FMemail2", "").strip()

    # Event type
    event_type = raw.get("FMeventType", "").strip()

    return {
        "date": date_obj,
        "date_display": date_to_sheet_format(date_obj),
        "year": date_obj.year,
        "dj_full_name": dj1,
        "dj_short_name": dj_short,
        "dj_initials": dj_initials,
        "dj_initials_bracket": f"[{dj_initials}]",
        "dj2_full_name": dj2,
        "client_full": client_full,
        "client_display": client_display,
        "venue_name": venue_name,
        "venue_raw": venue_raw,
        "venue_street": venue_street,
        "venue_city_state_zip": venue_city_state_zip,
        "start_time": start_time,
        "end_time": end_time,
        "sound_type": sound_type,
        "has_ceremony": has_ceremony,
        "has_planner": has_planner,
        "is_unassigned": dj_short in ("Unassigned", "Unknown"),
        "email1": email1,
        "email2": email2,
        "event_type": event_type,
    }


def parse_clean_format(raw):
    """Parse clean test format booking data."""
    date_str = raw.get("event_date", "")
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    dj_full = raw.get("assigned_dj", "")
    dj_short = get_dj_short_name(dj_full)
    # Henry's feed names the DJ2 slot `assigned_roadie_or_dj2`; older/clean
    # payloads use `secondary_dj`. Accept either.
    dj2 = raw.get("assigned_roadie_or_dj2") or raw.get("secondary_dj", "")

    if dj_short == "Unassigned":
        dj_initials = get_unassigned_initials(dj2)
    elif dj_short == "Unknown":
        dj_initials = "UP"
    else:
        dj_initials = get_dj_initials(dj_short)

    client_full = strip_preference_tag(raw.get("client_name", "Unknown Client"))
    client_display = extract_client_first_names(client_full)

    venue_raw = raw.get("venue_name", "")
    venue_name = re.sub(r"\s*\(.*?\)\s*", "", venue_raw).strip()

    start_time = raw.get("setup_time", "")
    end_time = raw.get("clear_time", "")
    sound_type = raw.get("sound_type", "Standard Speakers")
    has_ceremony = raw.get("has_ceremony_sound", False)
    has_planner = bool(raw.get("planner_name", ""))

    # Client email addresses (for nurture system)
    email1 = raw.get("email1", "").strip()
    email2 = raw.get("email2", "").strip()

    # Event type
    event_type = raw.get("event_type", "").strip()

    return {
        "date": date_obj,
        "date_display": date_to_sheet_format(date_obj),
        "year": date_obj.year,
        "dj_full_name": dj_full,
        "dj_short_name": dj_short,
        "dj_initials": dj_initials,
        "dj_initials_bracket": f"[{dj_initials}]",
        "dj2_full_name": dj2,
        "client_full": client_full,
        "client_display": client_display,
        "venue_name": venue_name,
        "venue_raw": venue_raw,
        "venue_street": raw.get("venue_street", ""),
        "venue_city_state_zip": raw.get("venue_city_state_zip", ""),
        "start_time": start_time,
        "end_time": end_time,
        "sound_type": sound_type,
        "has_ceremony": has_ceremony,
        "has_planner": has_planner,
        "is_unassigned": dj_short in ("Unassigned", "Unknown"),
        "email1": email1,
        "email2": email2,
        "event_type": event_type,
    }


# =============================================================================
# DJ AVAILABILITY RULES
# =============================================================================

def can_backup(dj_name, cell_value, is_bold, date_obj, year):
    """
    Determine if a DJ can serve as backup based on cell value and rules.
    Returns (can_backup: bool, note: str or None).
    """
    value = (cell_value or "").strip().upper()
    weekend = is_weekend(date_obj)

    # Split compound values (e.g., "DAD, BACKUP") for checking
    statuses = [s.strip().lower() for s in value.split(",")]

    # Guard: reject unknown cell values
    for s in statuses:
        if s and s not in KNOWN_CELL_VALUES:
            print(f'  ⚠️  Unknown matrix value for {dj_name}: "{value}" (in can_backup) — treating as unavailable')
            return False, None

    # Universal: already booked, already backup, or maxed → no
    if any(s in ("booked", "backup", "maxed", "reserved", "wedfaire", "setup") for s in statuses):
        return False, None

    # STANFORD and LAST: DJ is available for booking and backup
    if value in ("STANFORD", "LAST"):
        return True, None

    if dj_name == "Henry":
        if value == "OUT":
            return False, None
        # Blank on any day = can backup
        return True, None

    elif dj_name == "Woody":
        if value == "OUT":
            if weekend and not is_bold:
                return True, None  # Plain OUT on weekend = can backup
            return False, None  # Bold OUT or weekday OUT = no
        # Blank = can backup
        return True, None

    elif dj_name == "Paul":
        if value == "OUT":
            return False, None
        return True, None

    elif dj_name == "Stefano":
        if value == "OUT":
            return False, None
        if value == "":
            return True, "check with Stefano"  # Blank = maybe
        return False, None

    elif dj_name == "Felipe":
        if year >= 2026:
            if value in ("", "OK", "DAD", "OK TO BACKUP"):
                return True, None
            return False, None  # OUT, MAXED = no
        else:
            # 2025: standard rules
            if value == "OUT":
                return False, None
            return True, None

    elif dj_name == "Stephanie":
        if year == 2026:
            return False, None  # Not in rotation for 2026
        elif year >= 2027:
            if value in ("OUT", "RESERVED"):
                return False, None
            if weekend and value == "":
                return True, None
            return False, None  # Weekday = no

    return False, None


def get_backup_title(dj_name):
    """Get the calendar event title for a backup assignment."""
    initials = get_dj_initials(dj_name)
    if is_paid_backup(dj_name):
        return f"[{initials}] PAID BACKUP DJ"
    return f"[{initials}] BACKUP DJ"


def calculate_spots_remaining(row_data, year, date_obj=None):
    """
    Calculate available booking spots for a date.
    Available Spots = (DJs available for booking) - (TBA bookings) - (AAG holds)
    """
    col_map = COLUMN_MAPS.get(year, COLUMN_MAPS[2026])
    available_djs = 0

    # Count DJs available for booking
    for dj in ["Henry", "Woody", "Paul"]:
        val = (row_data.get(dj, "") or "").strip().upper()
        if val == "":
            available_djs += 1

    # Stefano blank = MAYBE, doesn't count toward available spots
    stef_val = (row_data.get("Stefano", "") or "").strip().upper()
    # Don't count Stefano

    # Felipe (2026+): only "OK" counts as available for booking
    if year >= 2026:
        felipe_val = (row_data.get("Felipe", "") or "").strip().upper()
        if felipe_val == "OK":
            available_djs += 1
    else:
        felipe_val = (row_data.get("Felipe", "") or "").strip().upper()
        if felipe_val == "":
            available_djs += 1

    # Stephanie (2027+): blank on weekend = available, weekday = not available
    if year >= 2027 and "Stephanie" in row_data:
        steph_val = (row_data.get("Stephanie", "") or "").strip().upper()
        if steph_val == "" and date_obj and date_obj.weekday() >= 5:
            available_djs += 1

    # Subtract TBA bookings
    tba_val = row_data.get("TBA", "")
    tba_count = parse_tba_value(tba_val)
    available_djs -= tba_count

    # Subtract AAG holds
    if "AAG" in col_map and "AAG" in row_data:
        aag_val = (row_data.get("AAG", "") or "").strip().upper()
        if aag_val == "RESERVED":
            available_djs -= 1

    return max(0, available_djs)


def check_existing_backup(row_data):
    """Check if any DJ is already assigned as backup. Returns DJ name or None."""
    for dj in ["Henry", "Woody", "Paul", "Stefano", "Felipe", "Stephanie"]:
        val = (row_data.get(dj, "") or "").strip().upper()
        statuses = [s.strip() for s in val.split(",")]
        if "BACKUP" in statuses:
            return dj
    return None


# =============================================================================
# GOOGLE SHEETS OPERATIONS
# =============================================================================

class SheetsClient:
    """Handles all Google Sheets read/write operations."""

    def __init__(self, credentials_path):
        self.credentials_path = credentials_path
        self.gc = None
        self.service = None
        self.spreadsheet = None
        self._initialized = False

    def init(self):
        """Initialize Google Sheets connection."""
        import gspread
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_service_account_file(
            self.credentials_path, scopes=SCOPES
        )
        self.gc = gspread.authorize(creds)
        self.service = build("sheets", "v4", credentials=creds)
        self.spreadsheet = self.gc.open_by_key(SPREADSHEET_ID)
        self._initialized = True

    def get_sheet(self, year):
        """Get the worksheet for a specific year."""
        return self.spreadsheet.worksheet(str(year))

    def find_date_row(self, date_obj, year):
        """
        Find the row number for a date in the availability matrix.
        Dates are in 'Sat 2/21' format in column A.
        Returns row number (1-indexed) or None.
        """
        sheet = self.get_sheet(year)
        date_values = sheet.col_values(1)  # Column A
        target = date_to_sheet_format(date_obj)

        for i, val in enumerate(date_values):
            if val.strip() == target:
                return i + 1  # 1-indexed
        return None

    def get_row_data(self, row_num, year):
        """
        Read all DJ columns for a row. Returns dict like:
        {'Henry': 'BOOKED', 'Woody': '', 'Paul': 'OUT', ...}
        """
        sheet = self.get_sheet(year)
        col_map = COLUMN_MAPS.get(year, COLUMN_MAPS[2026])

        # Find the max column we need
        max_col = max(col_map.values())
        row_values = sheet.row_values(row_num)

        # Pad row_values if shorter than expected
        while len(row_values) < max_col:
            row_values.append("")

        data = {}
        for name, col_idx in col_map.items():
            if name == "Date":
                continue
            data[name] = row_values[col_idx - 1]  # Convert to 0-indexed

        return data

    def get_aag_couple(self, row_num, year):
        """The AAG couple names on a row ('' if none, or no such column that year)."""
        return aag_couple_from_row(self.get_sheet(year).row_values(row_num), year)

    def is_cell_bold(self, year, row_num, col_num):
        """
        Check if a cell has bold formatting.
        Uses Sheets API v4 with includeGridData for format data.
        row_num and col_num are 1-indexed.
        """
        sheet_name = str(year)
        # Convert to A1 notation for the range
        col_letter = chr(ord('A') + col_num - 1) if col_num <= 26 else 'A'
        cell_range = f"{sheet_name}!{col_letter}{row_num}"

        result = self.service.spreadsheets().get(
            spreadsheetId=SPREADSHEET_ID,
            ranges=[cell_range],
            includeGridData=True,
        ).execute()

        try:
            grid_data = result["sheets"][0]["data"][0]
            row_data = grid_data["rowData"][0]
            cell_data = row_data["values"][0]

            # Check textFormatRuns first (partially formatted cells)
            if "textFormatRuns" in cell_data:
                runs = cell_data["textFormatRuns"]
                if runs and "format" in runs[0]:
                    return runs[0]["format"].get("bold", False)

            # Check effectiveFormat
            eff_fmt = cell_data.get("effectiveFormat", {})
            text_fmt = eff_fmt.get("textFormat", {})
            return text_fmt.get("bold", False)

        except (KeyError, IndexError):
            return False

    def write_cell(self, row_num, col_num, value, year):
        """Write a value to a specific cell. row_num and col_num are 1-indexed."""
        sheet = self.get_sheet(year)
        sheet.update_cell(row_num, col_num, value)

    def create_date_row(self, date_obj, year):
        """
        Create a new row for a date in the availability matrix.
        Inserts row chronologically, adds date to column A, and applies formula templates.
        Returns the new row number (1-indexed).
        """
        sheet = self.get_sheet(year)
        date_values = sheet.col_values(1)  # Column A - all dates
        target_date = date_to_sheet_format(date_obj)

        # Find insertion point (first date that comes after our target date)
        # Assume dates are in ascending chronological order
        insert_row = len(date_values) + 1  # Default: append at end

        for i, existing_date_str in enumerate(date_values):
            if not existing_date_str.strip():
                continue
            try:
                # Parse existing date to compare
                # Format is like "Thu 12/31" - extract month/day
                parts = existing_date_str.split()
                if len(parts) >= 2:
                    month_day = parts[1]  # "12/31"
                    month, day = map(int, month_day.split('/'))
                    existing_date = datetime(year, month, day)

                    if existing_date > date_obj:
                        insert_row = i + 1  # Found first date after target
                        break
            except (ValueError, IndexError):
                continue

        # Insert blank row
        sheet.insert_row([], insert_row)

        # Write date to column A
        self.write_cell(insert_row, 1, target_date, year)

        # Apply formula templates to appropriate columns
        for col_letter, formula_template in ROW_FORMULA_TEMPLATES.items():
            col_num = ord(col_letter) - ord('A') + 1  # Convert letter to 1-indexed number
            formula = formula_template.format(row=insert_row)
            self.write_cell(insert_row, col_num, formula, year)

        return insert_row


class MockSheetsClient:
    """Mock client for dry-run testing. Prints actions instead of executing."""

    def __init__(self):
        self._initialized = True
        self.mock_data = {}  # {year: {row: {col_name: value}}}
        self.mock_bold = {}  # {(year, row, col): True/False}
        self.mock_aag_couple = {}  # {(year, row): "Kelly and Ryan"}
        self.writes = []  # Track writes for verification

    def init(self):
        pass

    def set_mock_row(self, year, row_num, data):
        """Set up mock row data for testing."""
        if year not in self.mock_data:
            self.mock_data[year] = {}
        self.mock_data[year][row_num] = data

    def set_mock_aag_couple(self, year, row_num, couple):
        self.mock_aag_couple[(year, row_num)] = couple

    def get_aag_couple(self, row_num, year):
        return self.mock_aag_couple.get((year, row_num), "")

    def set_mock_bold(self, year, row_num, col_num, is_bold):
        """Set up mock bold status."""
        self.mock_bold[(year, row_num, col_num)] = is_bold

    def find_date_row(self, date_obj, year):
        return 5  # Default test row

    def get_row_data(self, row_num, year):
        if year in self.mock_data and row_num in self.mock_data[year]:
            return self.mock_data[year][row_num]
        return {
            "Henry": "", "Woody": "", "Paul": "", "Stefano": "",
            "Felipe": "", "TBA": "", "Stephanie": "",
        }

    def is_cell_bold(self, year, row_num, col_num):
        return self.mock_bold.get((year, row_num, col_num), False)

    def write_cell(self, row_num, col_num, value, year):
        self.writes.append({
            "row": row_num, "col": col_num,
            "value": value, "year": year,
        })
        print(f"  [DRY RUN] Would write '{value}' to row {row_num}, col {col_num} in {year} sheet")


# =============================================================================
# CALENDAR OPERATIONS (reads via CalDAV, writes via AppleScript)
# =============================================================================

def check_calendar_conflicts(date_obj, initials_bracket):
    """
    Check if any events on the given date contain the DJ initials in the title.
    Reads the Gigs and Unavailable calendars over CalDAV (calendar_read.py).
    Returns list of conflicting event titles, or empty list if clear.

    Raises calendar_read.CalendarReadError if the calendar can't be read.
    Callers must treat that as "not checked", never as "clear".
    """
    day = date_obj.date() if isinstance(date_obj, datetime) else date_obj
    events = calendar_read.fetch_events(["Gigs", "Unavailable"], day, day)

    # Non-booking event keywords — these contain DJ initials but aren't real booking conflicts
    non_booking_keywords = ["DAD-DUTY", "BACKUP DJ", "HOLD"]

    # Match on the parsed bracket so joint events count for each DJ:
    # "[PB, WM] CASA" and "[WM/HK] Memorial" are both conflicts for [WM].
    # Only events that start on this day count; one running past midnight
    # from the day before is that day's booking.
    code = initials_bracket.strip("[]").upper()
    conflicts = []
    for event_day, title in events:
        if event_day != day:
            continue
        codes = parse_dj_codes(title) or []
        if code in (c.upper() for c in codes):
            # Skip non-booking events (DAD-DUTY, BACKUP DJ, etc.)
            title_upper = title.upper()
            if any(kw in title_upper for kw in non_booking_keywords):
                continue
            conflicts.append(title)
    return conflicts


def is_aag_venue(venue_name):
    """Allied Arts Guild / Cafe Wisteria."""
    v = (venue_name or "").lower()
    return "allied arts" in v or "wisteria" in v


def split_backup_hits(titles):
    """Split conflict-check hits into (already_backup, real_conflicts).

    check_calendar_conflicts skips "BACKUP DJ", but a hand-made "[WM] BACKUP"
    gets through. That means the backup is already on the calendar, not a clash.
    """
    already = [t for t in titles if "BACKUP" in t.upper()]
    return already, [t for t in titles if t not in already]


# =============================================================================
# THE BACKUP STEP (shared by Book Event, Assign DJ and Backup Assigner)
# =============================================================================

# Default availability markers a backup write replaces outright; anything else
# ('DAD-DUTY') is kept and BACKUP appended.
BACKUP_REPLACES = {"", "OUT", "OK", "DAD", "STANFORD", "LAST", "OK TO BACKUP", "BACKUP"}


def backup_cell_value(current_value):
    v = (current_value or "").strip()
    if v.upper() in BACKUP_REPLACES:
        return "BACKUP"
    return f"{v}, BACKUP"


def backup_candidates(row_data, exclude, year, date_obj, col_map, bold_lookup):
    """
    (dj, note) pairs for the backup dialog: the year's eligible DJs, minus the
    ones in `exclude` (booked that day), filtered through can_backup.
    bold_lookup(dj) answers the Woody plain-vs-bold OUT question and is only
    called for that case.
    """
    out = []
    for cand in BACKUP_ELIGIBLE_DJS.get(year, BACKUP_ELIGIBLE_DJS[2026]):
        if cand in exclude or cand not in col_map:
            continue
        cell = row_data.get(cand, "") or ""
        bold = False
        if cand == "Woody" and cell.strip().upper() == "OUT":
            bold = bool(bold_lookup(cand))
        ok, note = can_backup(cand, cell, bold, date_obj, year)
        if ok:
            out.append((cand, note))
    return out


def assign_backup(backup_dj, date_obj, date_display, sheets, row_num, col_map, row_data,
                  year, test_mode=False, log=print, warn=None,
                  conflicts=None, make_backup_event=None):
    """
    Calendar check, Matrix BACKUP, all-day calendar event, for one chosen backup.

    Returns (status, summary). status is one of:
      "assigned"             Matrix and calendar event written
      "already_on_calendar"  a [XX] BACKUP event was there; Matrix written, no new event
      "conflict"             the DJ has a booking that day; nothing written
      "check_failed"         calendar unreadable; nothing written (not checked != clear)
      "event_failed"         Matrix written, calendar event failed; make it by hand
    conflicts / make_backup_event default to the real functions, looked up at
    call time so tests can patch them on this module.
    """
    conflicts = conflicts or check_calendar_conflicts
    make_backup_event = make_backup_event or create_allday_backup_event
    bracket = f"[{get_dj_initials(backup_dj)}]"
    try:
        clash = conflicts(date_obj, bracket)
    except Exception as e:
        log(f"Backup: calendar check failed for {backup_dj}: {e}")
        if warn:
            warn(f"Calendar check failed for backup {bracket} on {date_display}:\n\n{e}\n\n"
                 "Backup NOT assigned (not checked, so not written). The booking itself is intact.")
        return "check_failed", "no backup (calendar check failed)"

    already, clash = split_backup_hits(clash)
    if clash:
        log(f"Backup: calendar conflict for {backup_dj}: {clash}")
        if warn:
            warn(f"Calendar conflict for backup {bracket} on {date_display}:\n\n"
                 + "\n".join(clash) + "\n\nBackup NOT assigned. The booking itself is intact.")
        return "conflict", "no backup (calendar conflict)"

    new_val = backup_cell_value(row_data.get(backup_dj, ""))
    sheets.write_cell(row_num, col_map[backup_dj], new_val, year)
    log(f"Matrix: {backup_dj} -> '{new_val}'")

    if already:
        log(f"Calendar: backup already on the calendar ({already[0]}), no new event")
        return "already_on_calendar", f"backup {backup_dj} (calendar event already there)"

    try:
        title = make_backup_event(date_obj, backup_dj, test_mode)
    except Exception as e:
        log(f"Backup: calendar event failed for {backup_dj}, create by hand: {e}")
        if warn:
            warn(f"Matrix shows {backup_dj} as BACKUP but the calendar event failed:\n\n{e}\n\n"
                 f"Create the all-day '{bracket} BACKUP DJ' event by hand, or the crosscheck will show the gap.")
        return "event_failed", f"backup {backup_dj} (matrix only, calendar by hand)"
    log(f"Calendar: created '{title}'")
    return "assigned", f"backup {backup_dj}"


def create_timed_calendar_event(booking, cal_start, cal_end, test_mode=False, app=None):
    """Create the primary timed calendar event. Returns the title. Raises RuntimeError on failure."""
    title = primary_event_title(booking)

    location_parts = [booking["venue_name"]]
    if booking["venue_street"]:
        location_parts.append(booking["venue_street"])
    if booking["venue_city_state_zip"]:
        location_parts.append(booking["venue_city_state_zip"])
    location = ", ".join(location_parts)

    dj_short = booking["dj_short_name"]
    if dj_short in DJ_EMAILS and dj_short not in ("Unassigned", "Unknown"):
        invitee_email = "paul@bigfundj.com" if test_mode else DJ_EMAILS[dj_short]
    else:
        invitee_email = None

    app = app or CalendarApp()
    try:
        app.create_event(title, cal_start, cal_end, location=location, invitee_email=invitee_email)
    except CalendarAppError as e:
        raise RuntimeError(f"Calendar event creation failed: {e}")
    return title


def create_allday_backup_event(date_obj, dj_name, test_mode=False, app=None):
    """Create the all-day backup event. Returns the title. Raises RuntimeError on failure."""
    title = get_backup_title(dj_name)
    invitee_email = "paul@bigfundj.com" if test_mode else DJ_EMAILS.get(dj_name)

    app = app or CalendarApp()
    try:
        app.create_event(title, date_obj, None, allday=True, invitee_email=invitee_email)
    except CalendarAppError as e:
        raise RuntimeError(f"Backup event creation failed: {e}")
    return title


def delete_hold_calendar_event(date_obj, initials_bracket, fetch_day=calendar_read.fetch_day_events, app=None):
    """
    Delete the 'Hold to DJ' calendar event for a DJ on a date.
    Called when converting a RESERVED status to BOOKED.

    The day's events are read over CalDAV and the hold deleted in Calendar.app
    by `event id` through CalendarApp (a whole-calendar `whose` scan took 30s+).
    Returns True if a hold was deleted, False if there was none to delete or the
    calendar could not be read. Raises CalendarAppError if Calendar.app failed:
    the caller must tell Paul, because the hold is still on the calendar.
    """
    try:
        listing = fetch_day(CALENDAR_NAME, date_obj.date())
    except calendar_read.CalendarReadError as e:
        print(f"  WARNING: Could not read the calendar to find the hold event: {e}")
        return False

    bracket = initials_bracket.lower()
    uids = [uid for uid, title in listing
            if "hold to dj" in title.lower() and bracket in title.lower()]
    if not uids:
        return False

    app = app or CalendarApp()
    return app.delete_events(uids) > 0


# =============================================================================
# DIALOG OPERATIONS (via AppleScript)
# =============================================================================

WARNING_DIALOG_TIMEOUT = 1800   # same as the backup dialogs: Paul may have stepped away


def show_warning_dialog(message):
    """
    Show a warning dialog and wait for OK. Never raises: an unanswered dialog
    is printed and the script carries on, so the steps after it still run.
    2026-11-03: a 60s timeout here raised and ended a cancellation before the
    backup event, the turned-away check and the booking log form.
    """
    msg_esc = message.replace('"', '\\"')
    script = f'''
    display dialog "{msg_esc}" with title "⚠️ Booking Manager Warning" buttons {{"OK"}} default button "OK" with icon caution
    '''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                       timeout=WARNING_DIALOG_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"  WARNING: Warning dialog expired unacknowledged: {message.splitlines()[0]}")


def show_multiple_booking_dialog(dj_name, date_display, existing_count, existing_events):
    """
    Ask user if they want to add another booking for a DJ who already has event(s).
    Returns True if user wants to proceed, False if they want to cancel.

    Args:
        dj_name: DJ short name (e.g., "Paul")
        date_display: Formatted date string (e.g., "06/15/2026")
        existing_count: Number of existing bookings (1, 2, etc.)
        existing_events: List of event title strings from calendar
    """
    # Build event summary
    event_count_text = f"{existing_count} event" if existing_count == 1 else f"{existing_count} events"

    if existing_count == 1 and existing_events:
        # Show details for single event
        event_info = existing_events[0]  # e.g., "[PB] Smith Wedding"
        message = (
            f"{dj_name} already has an event in the availability matrix and calendar "
            f"on {date_display}:\\n\\n{event_info}\\n\\n"
            f"Add this new booking anyway?"
        )
    elif existing_count == 2:
        # Just say "2 events"
        message = (
            f"{dj_name} already has 2 booked events in the availability matrix and calendar "
            f"on {date_display}.\\n\\n"
            f"Add this new booking anyway?"
        )
    else:
        # For 3+, say the number
        message = (
            f"{dj_name} already has {existing_count} booked events in the availability matrix and calendar "
            f"on {date_display}.\\n\\n"
            f"Add this new booking anyway?"
        )

    msg_esc = message.replace('"', '\\"')
    script = f'''
    set userChoice to button returned of (display dialog "{msg_esc}" with title "Multiple Bookings" buttons {{"Cancel", "Add Booking"}} default button "Add Booking" with icon caution)
    return userChoice
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=60,
    )

    choice = result.stdout.strip()
    return choice == "Add Booking"


def show_clear_aag_reservation_dialog(holder, aag_couple, client, date_display):
    """
    The date has a DJ RESERVED for an AAG couple, and this AAG booking went to
    someone else (or is unassigned). Ask whether to clear the reserved DJ.
    Returns True to clear. Keep is the default, so a stray Return changes nothing.
    """
    message = (
        f"{holder} is RESERVED on {date_display} for the AAG couple {aag_couple}.\\n\\n"
        f"This booking ({client}) is not going to {holder}.\\n\\n"
        f"If this is that couple, clear {holder}'s RESERVED?"
    )
    msg_esc = message.replace('"', '\\"')
    script = f'''
    set userChoice to button returned of (display dialog "{msg_esc}" with title "AAG Reservation" buttons {{"Clear {holder}", "Keep"}} default button "Keep" with icon caution)
    return userChoice
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=120)
    return result.stdout.strip() == f"Clear {holder}"


def show_backup_dialog(date_display, spots_remaining, candidates, existing_backup, booking_context=None):
    """
    Show backup selection dialog.
    candidates: list of (dj_name, note_or_None) tuples.
    booking_context: optional string with venue/DJ info for the date (shown in prompt).
    Returns selected DJ name, or None if skipped.
    """
    if existing_backup:
        info = f"{date_display} — {spots_remaining} spot(s) remaining\\nBackup assigned: {existing_backup}"
        script = f'''
        display dialog "{info}" with title "Backup Status" buttons {{"OK"}} default button "OK"
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
        return None

    if not candidates:
        info = f"{date_display} — {spots_remaining} spot(s) remaining\\nNo backup assigned\\nNo DJs available for backup."
        script = f'''
        display dialog "{info}" with title "Backup Status" buttons {{"OK"}} default button "OK"
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
        return None

    # Build list items
    items = []
    for dj_name, note in candidates:
        paid = "paid" if is_paid_backup(dj_name) else "unpaid"
        label = f"{dj_name} ({paid})"
        if note:
            label += f" — {note}"
        items.append(label)
    items.append("Skip")

    # AppleScript choose from list
    # Cancel button (built-in) = stop entire script
    # "Skip" list option = skip this date, continue to next
    items_str = ", ".join(f'"{item}"' for item in items)
    context_line = f"\\n{booking_context}\\n" if booking_context else ""
    prompt = f"{date_display} — {spots_remaining} spot(s) remaining{context_line}\\nNo backup assigned\\n\\nSelect backup DJ (Cancel = stop script):"
    prompt_esc = prompt.replace('"', '\\"')

    script = f'''
    set candidates to {{{items_str}}}
    set userChoice to choose from list candidates with prompt "{prompt_esc}" with title "Assign Backup" default items {{"Skip"}}
    if userChoice is false then
        return "CANCEL"
    else
        return item 1 of userChoice
    end if
    '''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=120,
    )
    choice = result.stdout.strip()

    if not choice or choice == "CANCEL" or choice == "false":
        return "STOP"

    if choice == "Skip":
        return None

    # Extract DJ name from the choice string (format: "Woody (unpaid)")
    for dj_name, _ in candidates:
        if choice.startswith(dj_name):
            return dj_name

    return None


def show_notification(title, message):
    """Show a macOS notification."""
    title_esc = title.replace('"', '\\"')
    msg_esc = message.replace('"', '\\"')
    script = f'display notification "{msg_esc}" with title "{title_esc}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)


# =============================================================================
# BOOKING LOG (Google Form pre-fill)
# =============================================================================

def open_booking_log_form(booking):
    """
    Open the Google Form for booking log with known fields pre-filled.
    Pre-fills: event date, decision date (today), venue, status (Booked),
    event type (from FileMaker). User completes the remaining fields manually.
    """
    event_date = booking["date"].strftime("%-m-%-d-%y")    # e.g., "10-24-26"
    decision_date = datetime.now().strftime("%-m-%-d-%y")   # today
    venue = booking["venue_name"]
    event_type = normalize_event_type(booking.get("event_type", ""))

    params = (
        f"?usp=pp_url"
        f"&{FORM_FIELDS['event_date']}={quote(event_date)}"
        f"&{FORM_FIELDS['decision_date']}={quote(decision_date)}"
        f"&{FORM_FIELDS['venue']}={quote(venue)}"
        f"&{FORM_FIELDS['status']}={quote('Booked')}"
        f"&{FORM_FIELDS['event_type']}={quote(event_type)}"
    )
    url = BOOKING_LOG_FORM_URL + params
    webbrowser.open(url)
    return url


# =============================================================================
# MUSIC LINK (Paul's weddings)
# =============================================================================

# dj-prep's launcher: logs to ~/Library/Logs/dj-prep/music.log and shows its own
# dialog on failure, so a failed music step explains itself.
DJ_PREP_RUNNER = "/Users/paulburchfield/Documents/projects/dj-prep/bin/dj-prep-run.sh"


def wants_music_link(booking):
    """Same gate as the nurture emails: Paul's couples, weddings (or blank type)."""
    event_type = booking.get("event_type", "").strip().lower()
    return booking["dj_short_name"] == "Paul" and event_type in ("", "wedding")


def make_music_link(fm_html_path, dry_run=False, test_mode=False, run=subprocess.run):
    """
    Run dj-prep's `music` on the FileMaker page Book Event just read, so the
    couple link is on the clipboard for the confirmation email. Same command as
    the Music link button, so names, folder and tokens come out identical.

    Never raises: the booking is already written by now, and a music failure
    only means pressing Music link by hand. Returns one summary line.
    """
    if not fm_html_path:
        return "Music: skipped (no page HTML); press Music link by hand"
    if dry_run:
        return "Music: would make the couple's music link"
    cmd = [DJ_PREP_RUNNER, "music", "--fm-html", fm_html_path]
    if test_mode:
        cmd.append("--stage-only")
    try:
        result = run(cmd, timeout=180)
    except Exception as e:
        return f"Music: FAILED ({e}); press Music link by hand"
    if result.returncode != 0:
        return "Music: FAILED (see the dj-prep dialog); press Music link by hand"
    if test_mode:
        return "Music: staged only (test mode), nothing uploaded"
    return "Music: couple link copied to clipboard"


# =============================================================================
# EMAIL FOLDER CREATION (Paul only)
# =============================================================================

def email_folder_name(booking):
    """'MM-DD-YY: first name and first name', plus ' (planner)' when there is one."""
    name = f"{booking['date'].strftime('%m-%d-%y')}: {booking['client_display']}"
    if booking.get("has_planner"):
        name += " (planner)"
    return name


_LIST_DELIM_RE = re.compile(r'^\((?:[^)]*)\)\s+"([^"]*)"\s')


def parse_list_delimiter(list_line):
    """
    Hierarchy delimiter from one IMAP LIST reply line, or None if it can't be
    read. Fastmail: (\\HasNoChildren) "/" INBOX (name unquoted). Bluehost:
    (\\HasNoChildren) "." "INBOX". A NIL delimiter (flat namespace) is None.
    """
    if not list_line:
        return None
    line = list_line.decode() if isinstance(list_line, bytes) else list_line
    m = _LIST_DELIM_RE.match(line)
    return m.group(1) or None if m else None


def folder_create_outcome(status, response):
    """
    'created', 'exists', or None from an IMAP CREATE reply. Fastmail answers
    NO "Mailbox already exists"; Bluehost used the [ALREADYEXISTS] code.
    """
    if status == "OK":
        return "created"
    text = response[0] if response else b""
    text = (text.decode(errors="replace") if isinstance(text, bytes) else (text or "")).upper()
    if "ALREADYEXISTS" in text or "ALREADY EXISTS" in text:
        return "exists"
    return None


def email_folder_path(year, folder_name, delimiter):
    """Server path for the folder, using the delimiter the server reports."""
    return f"{EMAIL_FOLDER_ROOT}{delimiter}{year}{delimiter}{folder_name}"


def create_email_folder(booking, dry_run=False):
    """
    Create the booking's email folder on Paul's love2tap mailbox (Fastmail).

    Path: BIG FUN/<year>/<MM-DD-YY: first name and first name (planner)>.
    Returns the folder name on success (or if it already existed), None when
    nothing was created; every failure is printed and swallowed, so callers
    must read the return value rather than assume.
    """
    folder_name = email_folder_name(booking)
    year = str(booking["year"])

    creds = load_imap_credentials()
    if creds is None:
        print(f"  ⚠️  No IMAP password in Keychain ({IMAP_KEYCHAIN_SERVICE} / {IMAP_KEYCHAIN_ACCOUNT})")
        print("  Skipping email folder creation.")
        return None

    if dry_run:
        print(f"  [DRY RUN] Would create email folder: {EMAIL_FOLDER_ROOT}/{year}/{folder_name}")
        return folder_name

    try:
        imap = imaplib.IMAP4_SSL(creds["host"], creds["port"])
        imap.login(creds["username"], creds["password"])

        # The server states its hierarchy delimiter in any LIST reply. Never
        # guess it: a wrong one creates a top-level folder with a literal
        # 'BIG FUN.2027.x' name instead of nesting (happened 2026-11-01).
        status, list_response = imap.list('""', 'INBOX')
        delimiter = parse_list_delimiter(list_response[0] if list_response else None)
        if not delimiter:
            print(f"  ⚠️  Could not read the server's folder delimiter from {list_response!r}")
            print("  Skipping email folder creation.")
            imap.logout()
            return None

        full_path = email_folder_path(year, folder_name, delimiter)

        # Create the folder
        status, response = imap.create(f'"{full_path}"')

        outcome = folder_create_outcome(status, response)
        if outcome == "created":
            # Subscribe so it shows up in mail clients
            imap.subscribe(f'"{full_path}"')
            print(f"  ✓ Created email folder: {full_path}")
        elif outcome == "exists":
            print(f"  ✓ Email folder already exists: {full_path}")
        else:
            print(f"  ⚠️  Folder creation returned: {status} {response}")
            imap.logout()
            return None

        imap.logout()
        return folder_name

    except imaplib.IMAP4.error as e:
        print(f"  ⚠️  IMAP error: {e}")
        print("  Skipping email folder creation.")
        return None
    except Exception as e:
        print(f"  ⚠️  Email folder error: {e}")
        print("  Skipping email folder creation.")
        return None


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

class GigBookingManager:
    """Orchestrates the full booking management flow."""

    def __init__(self, credentials_path=None, dry_run=False, test_mode=False, fm_html_path=None):
        self.dry_run = dry_run
        self.test_mode = test_mode
        self.fm_html_path = fm_html_path
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.actions = []  # Track what happened for summary

        # Dry-run reads the live sheet but skips writes. Test mode swaps in an
        # in-memory client so the suite never touches Google Sheets.
        if test_mode:
            self.sheets = MockSheetsClient()
        else:
            self.sheets = SheetsClient(self.credentials_path)

    def log(self, action):
        """Log an action for the summary."""
        self.actions.append(action)
        print(f"  {action}")

    def _schedule_nurture_emails(self, booking):
        """Schedule post-booking nurture emails for this couple."""
        try:
            from nurture_config import (
                calculate_send_dates, determine_sender, get_recipients,
                init_nurture_sheet, check_duplicate, col_index,
                NURTURE_SPREADSHEET_ID, SHORT_BOOKER_MONTHS
            )

            if not NURTURE_SPREADSHEET_ID:
                print("— Nurture emails: not configured (no spreadsheet ID). Skipping.")
                print()
                return

            event_type = booking.get("event_type", "").lower()
            if event_type and event_type != "wedding":
                print(f"— Nurture emails: skipping (event type: {booking.get('event_type', 'unknown')})")
                print()
                return

            # Soft launch: Paul's couples only
            if booking["dj_short_name"] != "Paul":
                print(f"— Nurture emails: skipping (DJ: {booking['dj_short_name']}, Paul only for now)")
                print()
                return

            print("— Scheduling nurture emails...")

            booking_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            event_date = booking["date"]
            lead_days = (event_date - booking_date).days

            if lead_days < SHORT_BOOKER_MONTHS * 30:
                print(f"  ℹ️  Under {SHORT_BOOKER_MONTHS} months out. No nurture emails.")
                print()
                return

            scheduled = calculate_send_dates(booking_date, event_date)
            if not scheduled:
                print("  ℹ️  No emails qualify for this timeline.")
                print()
                return

            # Build rows
            recipients = get_recipients(
                booking.get("email1", ""), booking.get("email2", "")
            )
            email_str = ", ".join(recipients) if recipients else ""
            sender = determine_sender(booking["dj_short_name"])
            event_date_str = event_date.strftime('%m/%d/%Y')
            booking_date_str = booking_date.strftime('%m/%d/%Y')

            rows = []
            for email in scheduled:
                rows.append([
                    booking["client_display"],
                    email_str,
                    booking["venue_name"],
                    event_date_str,
                    booking_date_str,
                    email["num"],
                    email["topic"],
                    email["send_date"].strftime('%m/%d/%Y'),
                    "pending",
                    "",
                    sender,
                    booking["dj_short_name"] if not booking["is_unassigned"] else "",
                    "",
                ])

            if self.dry_run:
                print(f"  [DRY RUN] Would schedule {len(rows)} nurture email(s):")
                for email in scheduled:
                    print(f"    #{email['num']}  {email['send_date'].strftime('%b %d')}  "
                          f"{email['topic']}")
                if not email_str:
                    print("  ⚠️  No email addresses in booking data.")
                self.log(f"Nurture: would schedule {len(rows)} email(s)")
                print()
                return

            # Write to sheet
            worksheet = init_nurture_sheet(self.credentials_path)

            if check_duplicate(worksheet, booking["client_display"], event_date_str):
                print(f"  ⚠️  Nurture rows already exist. Skipping.")
                self.log("Nurture: skipped (duplicate)")
                print()
                return

            worksheet.append_rows(rows, value_input_option='USER_ENTERED')
            print(f"  ✓ {len(rows)} nurture email(s) scheduled")
            if not email_str:
                print("  ⚠️  No email addresses. Update the sheet when available.")
            for email in scheduled:
                print(f"    #{email['num']}  {email['send_date'].strftime('%b %d')}  "
                      f"{email['topic']}")
            self.log(f"Nurture: scheduled {len(rows)} email(s)")
            print()

        except ImportError:
            print("— Nurture emails: system not installed. Skipping.")
            print()
        except Exception as e:
            print(f"  ⚠️  Could not schedule nurture emails: {e}")
            self.log(f"Nurture: failed ({e})")
            print()

    def run(self, json_path):
        """Execute the full booking management flow."""
        print("\n" + "=" * 60)
        print("  GIG BOOKING MANAGER")
        print("=" * 60)

        if self.dry_run:
            print("  MODE: DRY RUN (no writes)")
        elif self.test_mode:
            print("  MODE: TEST (invites → paul@)")
        print()

        # -----------------------------------------------------------------
        # Step 1: Parse booking data
        # -----------------------------------------------------------------
        print("— Parsing booking data...")
        booking = parse_booking_data(json_path)
        is_setup = is_setup_booking(booking)
        print(f"  Date: {booking['date_display']} ({booking['date'].strftime('%Y-%m-%d')})")
        print(f"  DJ: {booking['dj_short_name']} {booking['dj_initials_bracket']}")
        print(f"  Client: {booking['client_display']}")
        print(f"  Venue: {booking['venue_name']}")
        if is_setup:
            print(f"  Event type: Setup — matrix SETUP, no backup, Setup calendar label")
        print()

        year = booking["year"]
        col_map = COLUMN_MAPS.get(year)
        if not col_map:
            msg = f"No column mapping defined for year {year}."
            print(f"  ERROR: {msg}")
            if not self.dry_run:
                show_warning_dialog(msg)
            return False

        # -----------------------------------------------------------------
        # Step 2: Initialize Google Sheets
        # -----------------------------------------------------------------
        print("— Connecting to availability matrix...")
        self.sheets.init()
        print("  Connected.")
        print()

        # -----------------------------------------------------------------
        # Step 3: Find date row
        # -----------------------------------------------------------------
        print("— Finding date in matrix...")
        row_num = self.sheets.find_date_row(booking["date"], year)
        if row_num is None:
            # Date doesn't exist - create new row
            print(f"  Date {booking['date_display']} not found in {year} sheet")
            if self.dry_run:
                print(f"  [DRY RUN] Would create new row for {booking['date_display']}")
                # For dry-run, use a placeholder row number
                row_num = 999
            else:
                print(f"  Creating new row for {booking['date_display']}...")
                row_num = self.sheets.create_date_row(booking["date"], year)
                print(f"  ✓ Created new row at row {row_num}")
        else:
            print(f"  Found at row {row_num}.")
        print()

        # -----------------------------------------------------------------
        # Step 4: Read row data
        # -----------------------------------------------------------------
        print("— Reading matrix data...")
        # If dry-run and row doesn't exist (placeholder 999), skip the read
        if self.dry_run and row_num == 999:
            print("  [DRY RUN] Row doesn't exist yet - no data to read")
            row_data = {}
        else:
            row_data = self.sheets.get_row_data(row_num, year)
            for dj, val in row_data.items():
                if val:
                    print(f"  {dj}: {val}")
        print()

        # -----------------------------------------------------------------
        # Phase 1: VALIDATE MATRIX & CALENDAR
        # -----------------------------------------------------------------
        print("— Phase 1: Validating matrix and calendar...")
        dj_short = booking["dj_short_name"]
        allow_multiple = False  # Track if user approved multiple bookings

        if not booking["is_unassigned"]:
            if dj_short not in col_map:
                msg = f"{dj_short} does not have a column in the {year} matrix."
                print(f"  ERROR: {msg}")
                if not self.dry_run:
                    show_warning_dialog(msg)
                return False

            # Count existing bookings in matrix
            cell_value = row_data.get(dj_short, "")
            is_reserved = cell_value.strip().upper() == "RESERVED"
            matrix_count = count_booked_events(cell_value)

            # Count existing bookings in calendar (always check, even in dry-run)
            try:
                cal_conflicts = check_calendar_conflicts(
                    booking["date"], booking["dj_initials_bracket"]
                )
            except calendar_read.CalendarReadError as e:
                msg = (
                    f"Calendar check FAILED for {booking['date_display']}:\n\n{e}\n\n"
                    f"Could not read the Gigs/Unavailable calendars, so conflicts "
                    f"were NOT checked. The booking was NOT written. Verify the "
                    f"calendar manually, then run the booking again."
                )
                print(f"  ERROR: {msg}")
                self.log(f"HALTED: calendar check failed — {e}")
                if not self.dry_run:
                    show_warning_dialog(msg)
                return False
            calendar_count = len(cal_conflicts)

            print(f"  Matrix shows: {matrix_count} booking(s) for {dj_short}")
            if is_reserved:
                print(f"  Matrix cell is RESERVED — will convert to BOOKED")
            print(f"  Calendar shows: {calendar_count} event(s) for {booking['dj_initials_bracket']}")

            # Validate matrix and calendar agree
            if matrix_count != calendar_count:
                msg = (
                    f"Matrix/calendar mismatch for {dj_short} on {booking['date_display']}:\n\n"
                    f"Matrix cell: \"{cell_value}\" ({matrix_count} booking(s))\n"
                    f"Calendar: {calendar_count} event(s)\n\n"
                    f"These numbers must match. Please investigate and fix before proceeding."
                )
                print(f"  ⚠️  MISMATCH: Matrix={matrix_count}, Calendar={calendar_count}")
                self.log(f"HALTED: Matrix/calendar mismatch — {dj_short}")
                if not self.dry_run:
                    show_warning_dialog(msg)
                return False

            # If DJ already has bookings, ask for confirmation
            if matrix_count > 0:
                if self.dry_run:
                    print(f"  [DRY RUN] {dj_short} has {matrix_count} existing booking(s) — would show dialog")
                    allow_multiple = True
                else:
                    user_approved = show_multiple_booking_dialog(
                        dj_short, booking['date_display'], matrix_count, cal_conflicts
                    )
                    if user_approved:
                        print(f"  ✓ User approved adding booking #{matrix_count + 1}")
                        allow_multiple = True
                    else:
                        msg = f"User cancelled adding multiple booking for {dj_short}."
                        print(f"  ⚠️  CANCELLED: {msg}")
                        self.log(f"HALTED: {msg}")
                        return False
            elif is_reserved:
                print(f"  ✓ {dj_short} is RESERVED — converting to BOOKED")
            else:
                print(f"  ✓ {dj_short}'s cell is blank — OK to write")
        else:
            print(f"  Unassigned booking — will update TBA column")
        print()

        # =================================================================
        # Phase 2: MATRIX WRITES
        # =================================================================

        # -----------------------------------------------------------------
        # Write primary booking to matrix
        # -----------------------------------------------------------------
        print("— Phase 2: Writing to matrix...")
        if not booking["is_unassigned"]:
            col_num = col_map[dj_short]
            current_value = row_data.get(dj_short, "")

            if is_setup:
                # Setup day: write SETUP (a commitment, not a sale), never BOOKED.
                new_value = setup_matrix_value(current_value)
                if self.dry_run and not self.test_mode:
                    print(f"  [DRY RUN] Would write '{new_value}' to row {row_num}, col {col_num} in {year} sheet")
                else:
                    self.sheets.write_cell(row_num, col_num, new_value, year)
                self.log(f"Matrix: {dj_short} → '{new_value}' (setup)")
                row_data[dj_short] = new_value
            elif allow_multiple:
                # Increment existing BOOKED value
                new_value = increment_booked(current_value)
                if self.dry_run and not self.test_mode:
                    print(f"  [DRY RUN] Would write '{new_value}' to row {row_num}, col {col_num} in {year} sheet")
                else:
                    self.sheets.write_cell(row_num, col_num, new_value, year)
                self.log(f"Matrix: {dj_short} → '{new_value}'")
                row_data[dj_short] = new_value  # Update local copy
            else:
                # First booking - write BOOKED (overwrites RESERVED if present)
                if self.dry_run and not self.test_mode:
                    print(f"  [DRY RUN] Would write 'BOOKED' to row {row_num}, col {col_num} in {year} sheet")
                else:
                    self.sheets.write_cell(row_num, col_num, "BOOKED", year)
                if is_reserved:
                    self.log(f"Matrix: {dj_short} RESERVED → BOOKED")
                else:
                    self.log(f"Matrix: {dj_short} → BOOKED")
                row_data[dj_short] = "BOOKED"  # Update local copy

                # If converting from RESERVED, remove the Hold to DJ calendar event
                if is_reserved:
                    if self.dry_run:
                        print(f"  [DRY RUN] Would delete Hold to DJ event for {booking['dj_initials_bracket']}")
                    else:
                        try:
                            deleted = delete_hold_calendar_event(
                                booking["date"], booking["dj_initials_bracket"]
                            )
                        except CalendarAppError as e:
                            print(f"  ⚠️  HOLD EVENT NOT DELETED — {e}")
                            self.log(f"⚠️ HOLD EVENT NOT DELETED ({e}) — "
                                     f"delete the Hold to DJ event for {dj_short} by hand")
                            show_warning_dialog(
                                f"Booking Manager — Calendar:\n\n"
                                f"The Hold to DJ event for {dj_short} could not be deleted:\n{e}\n\n"
                                f"The booking continues. Delete the hold in Calendar by hand."
                            )
                        else:
                            if deleted:
                                self.log(f"Calendar: deleted Hold to DJ event for {dj_short}")
                                print(f"  ✓ Deleted Hold to DJ calendar event")
                            else:
                                print(f"  ℹ️  No Hold to DJ event found to delete")
        else:
            tba_col = col_map["TBA"]
            current_tba = row_data.get("TBA", "")
            new_tba = increment_tba(current_tba)
            if self.dry_run and not self.test_mode:
                print(f"  [DRY RUN] Would write '{new_tba}' to row {row_num}, col {tba_col} in {year} sheet")
            else:
                self.sheets.write_cell(row_num, tba_col, new_tba, year)
            self.log(f"Matrix: TBA → '{new_tba}'")
            row_data["TBA"] = new_tba  # Update local copy

        # Setup helper (DJ2): mark the rostered co-DJ SETUP too, so both people
        # read as committed and the [DJ1/DJ2] calendar title reconciles in the
        # cross-check. Roadies / non-rostered DJ2 names are skipped.
        setup_helper = setup_helper_short(booking)
        if setup_helper and setup_helper in col_map and setup_helper != dj_short:
            helper_col = col_map[setup_helper]
            helper_value = setup_matrix_value(row_data.get(setup_helper, ""))
            if self.dry_run and not self.test_mode:
                print(f"  [DRY RUN] Would write '{helper_value}' to row {row_num}, col {helper_col} in {year} sheet (setup helper)")
            else:
                self.sheets.write_cell(row_num, helper_col, helper_value, year)
            self.log(f"Matrix: {setup_helper} → '{helper_value}' (setup helper)")
            row_data[setup_helper] = helper_value

        # AAG reservation (Paul, 2026-11-11): RESERVED in a DJ's column + names in
        # the AAG couple column = that DJ holds an AAG couple not yet handed off.
        # Booked to that DJ, RESERVED became BOOKED above. Booked elsewhere (or
        # unassigned), ask whether this is that couple and the DJ should be cleared.
        if is_aag_venue(booking["venue_name"]) and not is_setup:
            aag_couple = self.sheets.get_aag_couple(row_num, year) if row_num != 999 else ""
            holder = aag_reserved_dj(row_data, aag_couple)
            if holder and holder != dj_short:
                print(f"  {holder} is RESERVED for AAG couple {aag_couple}")
                if self.dry_run:
                    print(f"  [DRY RUN] Would ask whether to clear {holder}'s RESERVED")
                elif show_clear_aag_reservation_dialog(holder, aag_couple, booking["client_display"],
                                                       booking["date_display"]):
                    cleared = get_default_cell_value(holder, booking["date"])
                    self.sheets.write_cell(row_num, col_map[holder], cleared, year)
                    row_data[holder] = cleared
                    self.log(f"Matrix: {holder} RESERVED (AAG {aag_couple}) → '{cleared}'")
                else:
                    self.log(f"Matrix: {holder} kept RESERVED (AAG {aag_couple})")
        print()

        # -----------------------------------------------------------------
        # Backup dialog (skip for unassigned)
        # -----------------------------------------------------------------
        backup_dj = None

        if not booking["is_unassigned"] and not is_setup:
            print("— Phase 2: Backup assessment...")
            spots = calculate_spots_remaining(row_data, year, booking["date"])
            existing_backup = check_existing_backup(row_data)

            if existing_backup:
                print(f"  Backup already assigned: {existing_backup}")
            else:
                print(f"  No backup assigned")

            print(f"  Spots remaining: {spots}")

            # Get backup candidates
            def bold_lookup(dj):
                if self.dry_run:
                    print(f"  [DRY RUN] Would check bold for {dj} — assuming plain")
                    return False
                return self.sheets.is_cell_bold(year, row_num, col_map[dj])

            candidates = backup_candidates(
                row_data, [dj_short], year, booking["date"], col_map, bold_lookup
            )
            for dj, note in candidates:
                paid = "paid" if is_paid_backup(dj) else "unpaid"
                note_str = f" — {note}" if note else ""
                print(f"  ✓ {dj} ({paid}){note_str}")

            print()

            # Show dialog
            if self.dry_run:
                print("  [DRY RUN] Would show backup dialog")
                print(f"  Candidates: {[c[0] for c in candidates]}")
                print(f"  Existing backup: {existing_backup}")
                # In dry run, don't select backup
            else:
                backup_dj = show_backup_dialog(
                    booking["date_display"], spots, candidates, existing_backup
                )

            if backup_dj == "STOP":
                # Cancel on the dialog: no backup, but the booking carries on.
                print("  Backup cancelled")
                self.log("Backup: cancelled")
            elif backup_dj:
                print(f"  Selected backup: {backup_dj}")

                def step_log(msg):
                    print(f"  {msg}")
                    self.log(msg)

                assign_backup(
                    backup_dj, booking["date"], booking["date_display"], self.sheets,
                    row_num, col_map, row_data, year, test_mode=self.test_mode,
                    log=step_log, warn=show_warning_dialog,
                )
            elif not existing_backup and not self.dry_run:
                self.log("Backup: skipped")
        elif is_setup:
            print("— Skipping backup (setup day — no backup needed)")
            self.log("Backup: skipped (setup)")
        else:
            print("— Skipping backup (unassigned booking)")
        print()

        # =================================================================
        # Phase 3: CALENDAR EVENTS
        # =================================================================
        print("— Phase 3: Creating calendar events...")

        # Primary event
        cal_start, cal_end = calculate_event_times(booking)
        if cal_start and cal_end:
            if self.dry_run:
                title = primary_event_title(booking)
                print(f"  [DRY RUN] Would create: {title}")
                print(f"  Start: {cal_start.strftime('%I:%M %p')}")
                print(f"  End: {cal_end.strftime('%I:%M %p')}")
                self.log(f"Calendar: would create '{title}'")
            else:
                title = create_timed_calendar_event(
                    booking, cal_start, cal_end, self.test_mode
                )
                self.log(f"Calendar: created '{title}'")
                print(f"  ✓ Created: {title}")
        else:
            print("  ⚠️  No times available — skipping primary calendar event")
            self.log("Calendar: skipped (no times)")


        print()

        # -----------------------------------------------------------------
        # Phase 4: Email folder (Paul only)
        # -----------------------------------------------------------------
        if booking["dj_short_name"] == "Paul":
            print("— Creating email folder...")
            folder_name = create_email_folder(booking, dry_run=self.dry_run)
            if folder_name:
                if self.dry_run:
                    self.log(f"Email: would create folder '{folder_name}'")
                else:
                    self.log(f"Email: created folder '{folder_name}'")
            print()

        # -----------------------------------------------------------------
        # Phase 4b: Music link (Paul's weddings) — last write step, so a
        # failure here never leaves the Matrix or calendar half-done.
        # -----------------------------------------------------------------
        if wants_music_link(booking):
            print("— Making the music link...")
            self.log(make_music_link(self.fm_html_path, self.dry_run, self.test_mode))
            print()

        # -----------------------------------------------------------------
        # Phase 5: Schedule nurture emails
        # -----------------------------------------------------------------
        if not self.test_mode:
            self._schedule_nurture_emails(booking)

        # =================================================================
        # Summary
        # =================================================================
        print("=" * 60)
        print("  SUMMARY")
        print("=" * 60)
        for action in self.actions:
            print(f"  • {action}")
        print()

        # Open pre-filled booking log form (safe in dry-run — nothing submits until user clicks).
        # Skip for setups: the inquiry tracker is for events we're booking, not setup days.
        if is_setup:
            print("— Skipping booking log form (setup day — not an inquiry/booking)")
            self.log("Booking log: skipped (setup)")
            print()
        elif not self.test_mode:
            print("— Opening booking log form...")
            open_booking_log_form(booking)
            self.log("Booking log: form opened in browser")
            print(f"  ✓ Pre-filled form opened — complete remaining fields")
            print()

        # Show notification (production only)
        if not self.dry_run:
            summary_lines = "\n".join(self.actions)
            show_notification("Booking Manager", summary_lines)

        return True


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Gig Booking Manager — automate matrix updates and calendar events"
    )
    parser.add_argument(
        "json_path",
        help="Path to booking data JSON file (FM or clean format)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate only, no writes to sheets or calendar"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode: calendar invites go to paul@bigfundj.com"
    )
    parser.add_argument(
        "--credentials",
        help="Path to Google service account credentials JSON",
        default=DEFAULT_CREDENTIALS_PATH,
    )
    parser.add_argument(
        "--fm-html",
        help="Saved FileMaker page HTML; passed to dj-prep to make the music link",
    )

    args = parser.parse_args()

    if not os.path.exists(args.json_path):
        print(f"Error: File not found: {args.json_path}")
        sys.exit(1)

    manager = GigBookingManager(
        credentials_path=args.credentials,
        dry_run=args.dry_run,
        test_mode=args.test,
        fm_html_path=args.fm_html,
    )

    try:
        success = manager.run(args.json_path)
        # Exit 0 even if success is False (handled conflicts already showed dialog)
        # Reserve non-zero exit for unexpected errors only
        sys.exit(0)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        if not args.dry_run:
            show_warning_dialog(f"Booking Manager Error:\n\n{str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
