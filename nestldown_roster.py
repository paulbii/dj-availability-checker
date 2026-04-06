#!/usr/bin/env python3
"""
Nestldown DJ Roster Page Generator

Reads Nestldown events from the Gigs calendar via CalDAV, generates a styled
HTML roster page, and uploads it via FTP to bigfundj.com/CLIENTS/nestldown/.
"""

import datetime
import re
from zoneinfo import ZoneInfo

import caldav
import keyring

from dj_core import DJ_INITIALS, DJ_EMAILS, DJ_PHONES, DJ_FULL_NAMES

TIMEZONE = ZoneInfo("America/Los_Angeles")
CALDAV_SERVICE = "bigfun-caldav"
VENUE_FILTER = "nestldown"
# Direct URL to the Gigs calendar (proven pattern from test_caldav_write.py)
GIGS_CALENDAR_URL = "https://caldav.love2tap.com/calendars/__uids__/65B490A6-6667-48BC-B9E4-1A638DAA787E/1187934A-6A2E-43A3-8355-74382DC82F47/"

# Reverse lookup: initials -> first name (for email/phone lookup)
# Exclude "Unknown" which maps to "UP" -- that's the unassigned fallback, not a real DJ
INITIALS_TO_NAME = {v: k for k, v in DJ_INITIALS.items() if k != "Unknown"}

# Non-booking event patterns to exclude
EXCLUDE_PATTERNS = ["backup dj", "hold to dj", "dad-duty"]


def is_booking_event(summary):
    """Return True if this calendar event is an actual booking (not backup, hold, etc.)."""
    summary_lower = summary.lower()
    return not any(pattern in summary_lower for pattern in EXCLUDE_PATTERNS)


def parse_event_summary(summary):
    """Parse a calendar event summary into roster data.

    Input format: '[XX] CoupleName' or '[XX] CoupleName (planner)'
    Returns dict with: couple, dj_name, email, phone
    Returns None if summary doesn't match expected format.
    """
    match = re.match(r"^\[([A-Z]{2})\]\s+(.+)$", summary)
    if not match:
        return None

    initials = match.group(1)
    couple = match.group(2).strip()

    # Strip (planner) suffix
    couple = re.sub(r"\s*\(planner\)\s*$", "", couple, flags=re.IGNORECASE)

    # Look up DJ by initials
    if initials in DJ_FULL_NAMES:
        first_name = INITIALS_TO_NAME.get(initials)
        return {
            "couple": couple,
            "dj_name": DJ_FULL_NAMES[initials],
            "email": DJ_EMAILS.get(first_name, "info@bigfundj.com"),
            "phone": DJ_PHONES.get(first_name, "1-800-924-4386"),
        }
    else:
        # Unknown initials = unassigned
        return {
            "couple": couple,
            "dj_name": "Unassigned",
            "email": "info@bigfundj.com",
            "phone": "1-800-924-4386",
        }


def fetch_nestldown_events():
    """Fetch all Nestldown events from the Gigs calendar for current year + next year.

    Returns list of dicts: {date, couple, dj_name, email, phone}
    Sorted chronologically.
    """
    url = keyring.get_password(CALDAV_SERVICE, "url")
    username = keyring.get_password(CALDAV_SERVICE, "username")
    password = keyring.get_password(CALDAV_SERVICE, "password")
    if not all([url, username, password]):
        raise RuntimeError("No CalDAV credentials found. Run setup_caldav.py first.")

    client = caldav.DAVClient(url=url, username=username, password=password)
    gigs_cal = caldav.Calendar(client=client, url=GIGS_CALENDAR_URL)

    # Query date range: Jan 1 current year through Dec 31 next year
    now = datetime.datetime.now(TIMEZONE)
    start = datetime.datetime(now.year, 1, 1, tzinfo=TIMEZONE)
    end = datetime.datetime(now.year + 2, 1, 1, tzinfo=TIMEZONE)

    events = gigs_cal.search(start=start, end=end, event=True, expand=True)

    roster = []
    skipped = 0

    for event in events:
        vevent = event.icalendar_component
        summary = str(vevent.get("summary", ""))
        location = str(vevent.get("location", ""))

        # Filter: Nestldown events only
        if VENUE_FILTER not in location.lower():
            continue

        # Filter: bookings only (exclude backups, holds, etc.)
        if not is_booking_event(summary):
            continue

        # Parse the summary
        parsed = parse_event_summary(summary)
        if parsed is None:
            skipped += 1
            print(f"  WARNING: Skipping malformed event: {summary}")
            continue

        # Extract date
        dtstart = vevent.get("dtstart")
        if dtstart is None:
            skipped += 1
            continue

        dt = dtstart.dt
        if isinstance(dt, datetime.datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TIMEZONE)
            else:
                dt = dt.astimezone(TIMEZONE)
            event_date = dt.date()
        elif isinstance(dt, datetime.date):
            event_date = dt
        else:
            skipped += 1
            continue

        parsed["date"] = event_date
        roster.append(parsed)

    if skipped:
        print(f"  Skipped {skipped} malformed or unparseable events")

    # Sort chronologically
    roster.sort(key=lambda e: e["date"])
    return roster
