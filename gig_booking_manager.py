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

import json
import sys
import os
import subprocess
import argparse
from datetime import datetime, timedelta
import re
import calendar as cal_module

# Import shared business logic from dj_core (single source of truth)
from dj_core import (
    # Constants
    SPREADSHEET_ID,
    DJ_INITIALS,
    DJ_EMAILS,
    DJ_NAME_MAP,
    PAID_BACKUP_DJS,
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
    parse_tba_value,
    is_paid_backup,
    # Time calculations
    calculate_arrival_offset,
    convert_times_to_24h,
    calculate_event_times,
)


# =============================================================================
# CONFIGURATION (local to booking manager)
# =============================================================================

CALENDAR_NAME = "Gigs"

# Default credentials path — override with --credentials flag
DEFAULT_CREDENTIALS_PATH = os.path.join(
    os.path.expanduser("~"), "Documents", "projects",
    "dj-availability-checker", "your-credentials.json"
)

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
    client_full = raw.get("FMclient", "Unknown Client")
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
    }


def parse_clean_format(raw):
    """Parse clean test format booking data."""
    date_str = raw.get("event_date", "")
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    dj_full = raw.get("assigned_dj", "")
    dj_short = get_dj_short_name(dj_full)
    dj2 = raw.get("secondary_dj", "")

    if dj_short == "Unassigned":
        dj_initials = get_unassigned_initials(dj2)
    elif dj_short == "Unknown":
        dj_initials = "UP"
    else:
        dj_initials = get_dj_initials(dj_short)

    client_full = raw.get("client_name", "Unknown Client")
    client_display = extract_client_first_names(client_full)

    venue_raw = raw.get("venue_name", "")
    venue_name = re.sub(r"\s*\(.*?\)\s*", "", venue_raw).strip()

    start_time = raw.get("setup_time", "")
    end_time = raw.get("clear_time", "")
    sound_type = raw.get("sound_type", "Standard Speakers")
    has_ceremony = raw.get("has_ceremony_sound", False)
    has_planner = bool(raw.get("planner_name", ""))

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

    # Guard: reject unknown cell values
    if value and value.lower() not in KNOWN_CELL_VALUES:
        print(f'  ⚠️  Unknown matrix value for {dj_name}: "{value}" (in can_backup) — treating as unavailable')
        return False, None

    # Universal: already booked, already backup, or maxed → no
    if value in ("BOOKED", "BACKUP", "MAXED", "RESERVED"):
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
        if val == "BACKUP":
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
        self.writes = []  # Track writes for verification

    def init(self):
        pass

    def set_mock_row(self, year, row_num, data):
        """Set up mock row data for testing."""
        if year not in self.mock_data:
            self.mock_data[year] = {}
        self.mock_data[year][row_num] = data

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
# CALENDAR OPERATIONS (via AppleScript)
# =============================================================================

def check_calendar_conflicts(date_obj, initials_bracket):
    """
    Check if any events on the given date contain the DJ initials in the title.
    Uses icalBuddy for fast calendar queries (AppleScript is too slow with large calendars).
    Returns list of conflicting event titles, or empty list if clear.
    """
    date_str = date_obj.strftime("%Y-%m-%d")  # "2026-02-21"

    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/icalBuddy", "-ic", "Gigs,Unavailable",
             "-eep", "notes,url,location,attendees",
             "-b", "", "-nc",
             f"eventsFrom:{date_str}", f"to:{date_str}"],
            capture_output=True, text=True, timeout=10,
        )
        conflicts = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and initials_bracket in line:
                conflicts.append(line)
        return conflicts
    except FileNotFoundError:
        print("  WARNING: icalBuddy not installed (brew install ical-buddy)")
        return []
    except subprocess.TimeoutExpired:
        print("  WARNING: Calendar conflict check timed out")
        return []


def create_timed_calendar_event(booking, cal_start, cal_end, test_mode=False):
    """Create the primary timed calendar event via AppleScript."""
    # Build title: [INITIALS] ClientName (planner)
    title = f"{booking['dj_initials_bracket']} {booking['client_display']}"
    if booking["has_planner"]:
        title += " (planner)"

    # Build location
    location_parts = [booking["venue_name"]]
    if booking["venue_street"]:
        location_parts.append(booking["venue_street"])
    if booking["venue_city_state_zip"]:
        location_parts.append(booking["venue_city_state_zip"])
    location = ", ".join(location_parts)

    # Format times for AppleScript
    start_str = cal_start.strftime("%B %d, %Y %I:%M:%S %p")
    end_str = cal_end.strftime("%B %d, %Y %I:%M:%S %p")

    # Determine invitee
    dj_short = booking["dj_short_name"]
    if dj_short in DJ_EMAILS and dj_short not in ("Unassigned", "Unknown"):
        if test_mode:
            invitee_email = "paul@bigfundj.com"
        else:
            invitee_email = DJ_EMAILS[dj_short]
    else:
        invitee_email = None

    # Escape strings for AppleScript
    title_esc = title.replace('"', '\\"')
    location_esc = location.replace('"', '\\"')

    # Build AppleScript
    invitee_block = ""
    if invitee_email:
        invitee_block = f'''
            tell newEvent
                make new attendee at end of attendees with properties {{email:"{invitee_email}"}}
            end tell'''

    script = f'''
    tell application "Calendar"
        tell calendar "{CALENDAR_NAME}"
            set newEvent to make new event with properties {{summary:"{title_esc}", location:"{location_esc}", start date:date "{start_str}", end date:date "{end_str}"}}
            {invitee_block}
        end tell
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=45,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Calendar event creation failed: {result.stderr}")

    return title


def create_allday_backup_event(date_obj, dj_name, test_mode=False):
    """Create an all-day backup calendar event via AppleScript."""
    title = get_backup_title(dj_name)
    date_str = date_obj.strftime("%B %d, %Y")

    if test_mode:
        invitee_email = "paul@bigfundj.com"
    else:
        invitee_email = DJ_EMAILS.get(dj_name)

    title_esc = title.replace('"', '\\"')

    invitee_block = ""
    if invitee_email:
        invitee_block = f'''
            tell newEvent
                make new attendee at end of attendees with properties {{email:"{invitee_email}"}}
            end tell'''

    script = f'''
    tell application "Calendar"
        tell calendar "{CALENDAR_NAME}"
            set newEvent to make new event with properties {{summary:"{title_esc}", start date:date "{date_str} 12:00:00 AM", end date:date "{date_str} 11:59:00 PM", allday event:true}}
            {invitee_block}
        end tell
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=45,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Backup event creation failed: {result.stderr}")

    return title


# =============================================================================
# DIALOG OPERATIONS (via AppleScript)
# =============================================================================

def show_warning_dialog(message):
    """Show a warning dialog and halt. Returns when user clicks OK."""
    msg_esc = message.replace('"', '\\"')
    script = f'''
    display dialog "{msg_esc}" with title "⚠️ Booking Manager Warning" buttons {{"OK"}} default button "OK" with icon caution
    '''
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)


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


def show_backup_dialog(date_display, spots_remaining, candidates, existing_backup):
    """
    Show backup selection dialog.
    candidates: list of (dj_name, note_or_None) tuples.
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
    items_str = ", ".join(f'"{item}"' for item in items)
    prompt = f"{date_display} — {spots_remaining} spot(s) remaining\\nNo backup assigned\\n\\nSelect backup DJ:"
    prompt_esc = prompt.replace('"', '\\"')

    script = f'''
    set candidates to {{{items_str}}}
    set userChoice to choose from list candidates with prompt "{prompt_esc}" with title "Assign Backup" default items {{"Skip"}}
    if userChoice is false then
        return "SKIP"
    else
        return item 1 of userChoice
    end if
    '''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=120,
    )
    choice = result.stdout.strip()

    if not choice or choice == "SKIP" or choice == "Skip" or choice == "false":
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
# MAIN ORCHESTRATOR
# =============================================================================

class GigBookingManager:
    """Orchestrates the full booking management flow."""

    def __init__(self, credentials_path=None, dry_run=False, test_mode=False):
        self.dry_run = dry_run
        self.test_mode = test_mode
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.actions = []  # Track what happened for summary

        # Always use real SheetsClient for reads, even in dry-run
        # Dry-run flag prevents writes but allows reads
        self.sheets = SheetsClient(self.credentials_path)

    def log(self, action):
        """Log an action for the summary."""
        self.actions.append(action)
        print(f"  {action}")

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
        print(f"  Date: {booking['date_display']} ({booking['date'].strftime('%Y-%m-%d')})")
        print(f"  DJ: {booking['dj_short_name']} {booking['dj_initials_bracket']}")
        print(f"  Client: {booking['client_display']}")
        print(f"  Venue: {booking['venue_name']}")
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
            matrix_count = count_booked_events(cell_value)

            # Count existing bookings in calendar (always check, even in dry-run)
            cal_conflicts = check_calendar_conflicts(
                booking["date"], booking["dj_initials_bracket"]
            )
            calendar_count = len(cal_conflicts)

            print(f"  Matrix shows: {matrix_count} booking(s) for {dj_short}")
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

            if allow_multiple:
                # Increment existing BOOKED value
                new_value = increment_booked(current_value)
                if self.dry_run:
                    print(f"  [DRY RUN] Would write '{new_value}' to row {row_num}, col {col_num} in {year} sheet")
                else:
                    self.sheets.write_cell(row_num, col_num, new_value, year)
                self.log(f"Matrix: {dj_short} → '{new_value}'")
                row_data[dj_short] = new_value  # Update local copy
            else:
                # First booking - write BOOKED
                if self.dry_run:
                    print(f"  [DRY RUN] Would write 'BOOKED' to row {row_num}, col {col_num} in {year} sheet")
                else:
                    self.sheets.write_cell(row_num, col_num, "BOOKED", year)
                self.log(f"Matrix: {dj_short} → BOOKED")
                row_data[dj_short] = "BOOKED"  # Update local copy
        else:
            tba_col = col_map["TBA"]
            current_tba = row_data.get("TBA", "")
            new_tba = increment_tba(current_tba)
            if self.dry_run:
                print(f"  [DRY RUN] Would write '{new_tba}' to row {row_num}, col {tba_col} in {year} sheet")
            else:
                self.sheets.write_cell(row_num, tba_col, new_tba, year)
            self.log(f"Matrix: TBA → '{new_tba}'")
            row_data["TBA"] = new_tba  # Update local copy
        print()

        # -----------------------------------------------------------------
        # Backup dialog (skip for unassigned)
        # -----------------------------------------------------------------
        backup_dj = None

        if not booking["is_unassigned"]:
            print("— Phase 2: Backup assessment...")
            spots = calculate_spots_remaining(row_data, year, booking["date"])
            existing_backup = check_existing_backup(row_data)

            if existing_backup:
                print(f"  Backup already assigned: {existing_backup}")
            else:
                print(f"  No backup assigned")

            print(f"  Spots remaining: {spots}")

            # Get backup candidates
            candidates = []
            eligible_djs = BACKUP_ELIGIBLE_DJS.get(year, BACKUP_ELIGIBLE_DJS[2026])

            for dj in eligible_djs:
                if dj == dj_short:
                    continue  # Can't backup yourself
                if dj not in col_map:
                    continue

                cell_val = row_data.get(dj, "")
                # Check bold only for Woody OUT
                bold = False
                if dj == "Woody" and (cell_val or "").strip().upper() == "OUT":
                    if not self.dry_run:
                        bold = self.sheets.is_cell_bold(year, row_num, col_map[dj])
                    else:
                        print(f"  [DRY RUN] Would check bold for Woody — assuming plain")

                eligible, note = can_backup(dj, cell_val, bold, booking["date"], year)
                if eligible:
                    candidates.append((dj, note))
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

            if backup_dj:
                print(f"  Selected backup: {backup_dj}")

                # Validate backup calendar conflict
                backup_initials_bracket = f"[{get_dj_initials(backup_dj)}]"
                print(f"  Checking calendar for {backup_initials_bracket}...")

                # Check backup calendar conflicts (always check, even in dry-run)
                backup_cal_conflicts = check_calendar_conflicts(
                    booking["date"], backup_initials_bracket
                )

                if backup_cal_conflicts:
                    conflict_list = "\n".join(backup_cal_conflicts)
                    msg = (
                        f"Calendar conflict for {backup_initials_bracket} "
                        f"on {booking['date_display']}:\n\n{conflict_list}\n\n"
                        f"Backup NOT assigned. Primary booking is intact."
                    )
                    print(f"  ⚠️  Backup calendar conflict: {conflict_list}")
                    self.log(f"Backup skipped: calendar conflict for {backup_dj}")
                    if not self.dry_run:
                        show_warning_dialog(msg)
                    backup_dj = None
                else:
                    # Write backup to matrix
                    backup_col = col_map[backup_dj]
                    if self.dry_run:
                        print(f"  [DRY RUN] Would write 'BACKUP' to row {row_num}, col {backup_col} in {year} sheet")
                    else:
                        self.sheets.write_cell(row_num, backup_col, "BACKUP", year)
                    self.log(f"Matrix: {backup_dj} → BACKUP")
                    print(f"  ✓ {backup_dj} → BACKUP written to matrix")
            elif not existing_backup and not self.dry_run:
                self.log("Backup: skipped")
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
                title = f"{booking['dj_initials_bracket']} {booking['client_display']}"
                if booking["has_planner"]:
                    title += " (planner)"
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

        # Backup event
        if backup_dj:
            if self.dry_run:
                backup_title = get_backup_title(backup_dj)
                print(f"  [DRY RUN] Would create: {backup_title}")
                self.log(f"Calendar: would create '{backup_title}'")
            else:
                backup_title = create_allday_backup_event(
                    booking["date"], backup_dj, self.test_mode
                )
                self.log(f"Calendar: created '{backup_title}'")
                print(f"  ✓ Created: {backup_title}")

        print()

        # =================================================================
        # Summary
        # =================================================================
        print("=" * 60)
        print("  SUMMARY")
        print("=" * 60)
        for action in self.actions:
            print(f"  • {action}")
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

    args = parser.parse_args()

    if not os.path.exists(args.json_path):
        print(f"Error: File not found: {args.json_path}")
        sys.exit(1)

    manager = GigBookingManager(
        credentials_path=args.credentials,
        dry_run=args.dry_run,
        test_mode=args.test,
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
