#!/usr/bin/env python3
"""
Read events from the BIG FUN master calendars over CalDAV.

Replaces icalBuddy, which on macOS 27.2 returns "No calendars" even with
Terminal at Full Access (2026-10-04) and failed silently in every caller.
CalDAV needs no macOS Calendar permission, so this works from any terminal,
Claude Code included.

A failed read RAISES CalendarReadError. It never returns an empty list, so a
caller can't mistake "couldn't read the calendar" for "nothing on the calendar."
"""

import datetime
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/Los_Angeles")
CALDAV_SERVICE = "bigfun-caldav"

# Direct URLs: these calendars live in the shared BIG FUN calendar home, not in
# the logged-in principal's own calendar list, so they can't be found by name.
_HOME = "https://caldav.love2tap.com/calendars/__uids__/65B490A6-6667-48BC-B9E4-1A638DAA787E/"
CALENDAR_URLS = {
    "Gigs": _HOME + "1187934A-6A2E-43A3-8355-74382DC82F47/",
    "Wedding Faires": _HOME + "67B6FC2C-1D53-4E52-8BE5-B76D5F967DB0/",
    "Unavailable": _HOME + "E7F24781-3EAF-44E2-8264-B5CC03D48A81/",
}


class CalendarReadError(Exception):
    """The calendar could not be read. Never means 'no events'."""


def _connect(names):
    """Return {name: caldav.Calendar} for the named calendars."""
    import caldav
    import keyring

    url = keyring.get_password(CALDAV_SERVICE, "url")
    username = keyring.get_password(CALDAV_SERVICE, "username")
    password = keyring.get_password(CALDAV_SERVICE, "password")
    if not all([url, username, password]):
        raise RuntimeError("No CalDAV credentials found in Keychain (bigfun-caldav). Run setup_caldav.py first.")

    client = caldav.DAVClient(url=url, username=username, password=password)
    return {name: caldav.Calendar(client=client, url=CALENDAR_URLS[name]) for name in names}


def event_local_date(dt):
    """Calendar date of an event start, in Pacific time.

    All-day events carry a date and are used as is. Timed events are converted
    to Pacific first, so 10 PM on 11/21 stored as 05:00 UTC on 11/22 is 11/21.
    A floating (naive) datetime is already local.
    """
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            return dt.date()
        return dt.astimezone(TIMEZONE).date()
    return dt


def fetch_events(calendar_names, start_date, end_date, connect=_connect):
    """Events overlapping start_date..end_date (inclusive) on the named calendars.

    Returns a list of (local start date, summary), sorted by date then summary.
    Recurring events are expanded. Multi-day events are dated by their start,
    the same way the icalBuddy parse dated them.

    Raises CalendarReadError if any calendar can't be read.
    """
    unknown = [n for n in calendar_names if n not in CALENDAR_URLS]
    if unknown:
        raise CalendarReadError(f"Unknown calendar(s): {', '.join(unknown)}")

    start = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=TIMEZONE)
    end = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min, tzinfo=TIMEZONE)

    try:
        calendars = connect(calendar_names)
        events = []
        for name in calendar_names:
            for event in calendars[name].search(start=start, end=end, event=True, expand=True):
                vevent = event.icalendar_component
                summary = str(vevent.get("summary", ""))
                events.append((event_local_date(vevent.get("dtstart").dt), summary))
    except Exception as e:
        raise CalendarReadError(f"{type(e).__name__}: {e}") from e

    return sorted(events)
