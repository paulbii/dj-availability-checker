"""
Post-Booking Nurture Email System - Configuration & Shared Utilities

Central constants, scheduling math, and shared logic used by both
nurture_scheduler.py and nurture_sender.py.
"""

import os
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# ── Credentials ──────────────────────────────────────────────────────────────

DEFAULT_CREDENTIALS_PATH = os.path.join(
    os.path.expanduser("~"), "Documents", "projects",
    "dj-availability-checker", "your-credentials.json"
)

SMTP_CREDENTIALS_PATH = os.path.join(
    os.path.expanduser("~"), "Documents", "projects",
    "dj-availability-checker", "smtp_credentials.json"
)

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# ── Nurture Tracker Sheet ────────────────────────────────────────────────────

NURTURE_SPREADSHEET_ID = '1GysTt5Ep2PLtJ3A-LG3d3CnS0oi_pq--Hdjg4LEOg_E'
NURTURE_SHEET_NAME = 'Nurture Emails'

# Column order in the Nurture Tracker sheet (1-indexed for gspread)
NURTURE_COLUMNS = [
    "Couple Name",      # A (1)
    "Email",            # B (2)
    "Venue",            # C (3)
    "Event Date",       # D (4)
    "Booking Date",     # E (5)
    "Email #",          # F (6)
    "Email Topic",      # G (7)
    "Scheduled Send",   # H (8)
    "Status",           # I (9)
    "Sent Date",        # J (10)
    "Sender",           # K (11)
    "DJ Name",          # L (12)
    "Notes",            # M (13)
]

def col_index(name):
    """Get 1-indexed column number for a column name."""
    return NURTURE_COLUMNS.index(name) + 1

# ── Email Schedule ───────────────────────────────────────────────────────────

BATCH_DAY = 1  # Tuesday (Monday=0 in Python's weekday())

HARD_STOP_MONTHS = 2
SHORT_BOOKER_MONTHS = 2
LONG_LEAD_MONTHS = 12  # Lead times over this use wider booking-anchored spacing

EMAIL_SCHEDULE = [
    {
        "num": 1,
        "topic": "Flow, Pacing, and Timeline",
        "anchor": "booking",
        "offset_weeks": 2,
        "template": "nurture-01-timeline-flow.txt",
        "subject": "Your {{venue}} timeline",
    },
    {
        "num": 2,
        "topic": "Toast Logistics",
        "anchor": "booking",
        "offset_weeks": 4,
        "template": "nurture-02-toast-logistics.txt",
        "subject": "A few thoughts on toasts",
    },
    {
        "num": 3,
        "topic": "Other Moments Needing Music",
        "anchor": "booking",
        "offset_weeks": 6,
        "template": "nurture-03-moments-needing-music.txt",
        "subject": "Music for your {{venue}} wedding",
    },
    {
        "num": 4,
        "topic": "Dance Music Preferences",
        "anchor": "event",
        "offset_months": 5,
        "template": "nurture-04-dance-music.txt",
        "subject": "Sharing your dance music preferences",
    },
    {
        "num": 5,
        "topic": "Guest Request Policy",
        "anchor": "event",
        "offset_months": 4,
        "template": "nurture-05-guest-requests.txt",
        "subject": "Guest requests during dancing",
    },
    {
        "num": 6,
        "topic": "Custom Edits for Special Dances",
        "anchor": "event",
        "offset_months": 3.5,
        "template": "nurture-06-custom-edits.txt",
        "subject": "First dance and special dance edits",
    },
    {
        "num": 7,
        "topic": "Name Pronunciations",
        "anchor": "event",
        "offset_months": 3,
        "template": "nurture-07-names-introductions.txt",
        "subject": "Names and introductions",
    },
]

# ── Template Paths ───────────────────────────────────────────────────────────

TEMPLATES_DIR = os.path.join(
    os.path.expanduser("~"), "EA", "projects",
    "post-booking-nurture", "templates"
)

# ── Sender Addresses ────────────────────────────────────────────────────────

PAUL_SENDER = "paul@bigfundj.com"
INFO_SENDER = "info@bigfundj.com"

# ── Utility Functions ────────────────────────────────────────────────────────

def snap_to_tuesday(date_obj):
    """Snap a date to the nearest Tuesday.

    If equidistant (Saturday), snaps forward to the following Tuesday.
    """
    current_weekday = date_obj.weekday()  # Monday=0, Tuesday=1, ...
    days_since_tuesday = (current_weekday - BATCH_DAY) % 7
    days_until_tuesday = (BATCH_DAY - current_weekday) % 7

    if days_since_tuesday == 0:
        return date_obj  # Already Tuesday
    elif days_until_tuesday <= days_since_tuesday:
        return date_obj + timedelta(days=days_until_tuesday)
    else:
        return date_obj - timedelta(days=days_since_tuesday)


def determine_sender(dj_name):
    """Return the sender email address based on the assigned DJ.

    Paul's own couples and unassigned couples come from paul@.
    Other DJs' couples come from info@.
    """
    if not dj_name or dj_name.lower() in ("paul", "unassigned", "unknown", "tba", ""):
        return PAUL_SENDER
    return INFO_SENDER


def is_shared_email(email_str):
    """Check if an email address looks like a shared/wedding email.

    Patterns: contains 'and', '&', 'wedding', combined names with a year, etc.
    """
    local_part = email_str.split("@")[0].lower()

    # Contains "wedding"
    if "wedding" in local_part:
        return True

    # Contains "and" as a word or separator (mariaandjames, maria.and.james)
    if re.search(r'[._]?and[._]?', local_part):
        return True

    # Contains ampersand
    if "&" in local_part:
        return True

    # Contains "n" as a joiner between what look like two names (mariandjames style
    # is already caught above; check for mariandjames2027 pattern)

    # Contains a 4-digit year (2024-2029)
    if re.search(r'20(2[4-9]|3[0-2])', local_part):
        return True

    return False


def get_recipients(email1, email2=""):
    """Determine which email address(es) to send to.

    If one email looks shared/wedding, use only that one.
    If both are provided and neither is shared, use both.
    If only one is provided, use that one.
    """
    emails = [e.strip() for e in [email1, email2] if e and e.strip()]

    if not emails:
        return []

    if len(emails) == 1:
        return emails

    # Check if either is a shared email
    for email in emails:
        if is_shared_email(email):
            return [email]

    return emails


def calculate_send_dates(booking_date, event_date):
    """Calculate which nurture emails to send and when.

    Returns a list of dicts with email schedule info and computed send dates.
    Applies hybrid logic, overlap prevention, and hard stop rules.

    For lead times over LONG_LEAD_MONTHS, booking-anchored emails use wider
    spacing (4/8/12 weeks instead of 2/4/6) and a mid-gap check-in is added.
    """
    lead_days = (event_date - booking_date).days
    lead_months = lead_days / 30.44
    hard_stop_date = event_date - relativedelta(months=HARD_STOP_MONTHS)
    is_long_lead = lead_months > LONG_LEAD_MONTHS

    if lead_days < SHORT_BOOKER_MONTHS * 30:
        return []

    # Wider spacing for long lead times
    if is_long_lead:
        booking_week_multiplier = 2  # 2/4/6 becomes 4/8/12
    else:
        booking_week_multiplier = 1

    # First pass: compute all event-anchored dates to find the earliest
    event_anchored_dates = {}
    for email in EMAIL_SCHEDULE:
        if email["anchor"] == "event":
            offset = email["offset_months"]
            whole_months = int(offset)
            extra_weeks = int((offset - whole_months) * 4)
            raw_date = event_date - relativedelta(months=whole_months, weeks=extra_weeks)
            snapped = snap_to_tuesday(raw_date)
            event_anchored_dates[email["num"]] = snapped

    earliest_event_email = min(event_anchored_dates.values()) if event_anchored_dates else None

    # Second pass: build the full schedule
    scheduled = []
    last_booking_anchored_date = None

    for email in EMAIL_SCHEDULE:
        if email["anchor"] == "booking":
            weeks = email["offset_weeks"] * booking_week_multiplier
            raw_date = booking_date + timedelta(weeks=weeks)
            snapped = snap_to_tuesday(raw_date)

            # Overlap prevention: skip if this would land on or after the
            # earliest event-anchored email
            if earliest_event_email and snapped >= earliest_event_email:
                continue

            last_booking_anchored_date = snapped
        else:
            snapped = event_anchored_dates[email["num"]]

        # Hard stop: skip if send date is too close to the event
        if snapped >= hard_stop_date:
            continue

        # Skip if send date is in the past
        if snapped < booking_date:
            continue

        scheduled.append({
            **email,
            "send_date": snapped,
        })

    # For long lead times, add a mid-gap check-in between the last
    # booking-anchored email and the first event-anchored email
    if is_long_lead and last_booking_anchored_date and earliest_event_email:
        gap_days = (earliest_event_email - last_booking_anchored_date).days
        if gap_days > 120:  # Only if gap is more than 4 months
            midpoint = last_booking_anchored_date + timedelta(days=gap_days // 2)
            midpoint_snapped = snap_to_tuesday(midpoint)

            scheduled.append({
                "num": 0,
                "topic": "Check-in",
                "anchor": "midpoint",
                "template": "nurture-00-checkin.txt",
                "subject": "Checking in on your {{venue}} wedding",
                "send_date": midpoint_snapped,
            })

    # Sort by send date
    scheduled.sort(key=lambda x: x["send_date"])

    return scheduled


# ── Google Sheets Connection ─────────────────────────────────────────────────

def init_nurture_sheet(credentials_path=None):
    """Initialize connection to the Nurture Tracker Google Sheet.

    Returns the gspread worksheet object.
    """
    creds_path = credentials_path or DEFAULT_CREDENTIALS_PATH
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(NURTURE_SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(NURTURE_SHEET_NAME)
    return worksheet


def check_duplicate(worksheet, couple_name, event_date_str):
    """Check if nurture rows already exist for this couple + event date.

    Returns True if rows found (likely a duplicate run).
    """
    all_values = worksheet.get_all_values()
    for row in all_values[1:]:  # skip header
        if (row[col_index("Couple Name") - 1] == couple_name and
                row[col_index("Event Date") - 1] == event_date_str):
            return True
    return False
