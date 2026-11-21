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
from collections import namedtuple
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

# Paul's own calendars, in his own calendar home on the same server. The
# availability checker lists what is on them (Paul, 2026-11-20). "BIG FUN" is
# the events calendar; the task list of the same name is a different URL.
_PAUL_HOME = "https://caldav.love2tap.com/calendars/__uids__/7E95F965-A066-4943-8E35-FAD23D5C3FDE/"
CALENDAR_URLS.update({
    "Paul": _PAUL_HOME + "3B845CA3-41DA-4CF6-9B32-104FF351ED29/",
    "BIG FUN": _PAUL_HOME + "6BC7EFDA-3A3D-4277-A179-43146D3A1623/",
})


class CalendarReadError(Exception):
    """The calendar could not be read. Never means 'no events'."""


class CalendarNotConfigured(CalendarReadError):
    """This machine has no CalDAV credentials, so there is nothing to read
    from. Different from a read that was tried and failed."""


# One event on one calendar. For a timed event start and end are Pacific
# datetimes; for an all-day event they are dates and end is the last day.
CalEvent = namedtuple("CalEvent", "calendar summary all_day start end")


def _connect(names):
    """Return {name: caldav.Calendar} for the named calendars."""
    import caldav
    import keyring

    url = keyring.get_password(CALDAV_SERVICE, "url")
    username = keyring.get_password(CALDAV_SERVICE, "username")
    password = keyring.get_password(CALDAV_SERVICE, "password")
    if not all([url, username, password]):
        raise CalendarNotConfigured("No CalDAV credentials found in Keychain (bigfun-caldav). Run setup_caldav.py first.")

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


def _local(dt):
    """A timed event's start or end as a Pacific datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TIMEZONE)
    return dt.astimezone(TIMEZONE)


def _to_cal_event(calendar_name, vevent):
    """(CalEvent, first day, last day) for one VEVENT."""
    summary = str(vevent.get("summary", ""))
    start = vevent.get("dtstart").dt
    end = vevent.get("dtend").dt if vevent.get("dtend") else None

    if not isinstance(start, datetime.datetime):
        # All-day: DTEND is the day after the last day.
        last = end - datetime.timedelta(days=1) if end and end > start else start
        return CalEvent(calendar_name, summary, True, start, last), start, last

    start = _local(start)
    end = _local(end) if end else start
    # An event ending at midnight is not on the day that starts then.
    last = max(start, end - datetime.timedelta(microseconds=1)).date()
    return CalEvent(calendar_name, summary, False, start, end), start.date(), last


def fetch_events_by_day(calendar_names, start_date, end_date, connect=_connect):
    """{day: [CalEvent, ...]} for every day in start_date..end_date (inclusive)
    that has something on the named calendars. A multi-day event is listed on
    each day it covers. All-day events come first, then timed ones by start.
    Days with nothing are left out. Recurring events are expanded.

    Raises CalendarNotConfigured when this machine has no CalDAV credentials,
    and CalendarReadError for anything else, a missing library included.
    """
    unknown = [n for n in calendar_names if n not in CALENDAR_URLS]
    if unknown:
        raise CalendarReadError(f"Unknown calendar(s): {', '.join(unknown)}")

    start = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=TIMEZONE)
    end = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min, tzinfo=TIMEZONE)

    by_day = {}
    try:
        calendars = connect(calendar_names)
        for name in calendar_names:
            for event in calendars[name].search(start=start, end=end, event=True, expand=True):
                cal_event, first, last = _to_cal_event(name, event.icalendar_component)
                day = max(first, start_date)
                while day <= min(last, end_date):
                    by_day.setdefault(day, []).append(cal_event)
                    day += datetime.timedelta(days=1)
    except CalendarNotConfigured:
        raise
    except Exception as e:
        raise CalendarReadError(f"{type(e).__name__}: {e}") from e

    for events in by_day.values():
        events.sort(key=lambda e: (0, e.summary) if e.all_day else (1, e.start, e.summary))
    return by_day


def fetch_day_events(calendar_name, day, connect=_connect):
    """(uid, summary) for every event that STARTS on `day` on one calendar.

    The uid is the iCalendar UID, which is also what Calendar.app's `event id`
    resolves, so a caller can find an event here in under a second and then
    edit or delete it in Calendar.app by id instead of a whole-calendar scan.
    An event from the day before that runs past midnight is that day's event
    and is left out. Sorted by summary.

    Raises CalendarReadError if the calendar can't be read.
    """
    if calendar_name not in CALENDAR_URLS:
        raise CalendarReadError(f"Unknown calendar: {calendar_name}")

    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=TIMEZONE)
    end = start + datetime.timedelta(days=1)
    try:
        calendar = connect([calendar_name])[calendar_name]
        found = []
        for event in calendar.search(start=start, end=end, event=True, expand=True):
            vevent = event.icalendar_component
            if event_local_date(vevent.get("dtstart").dt) != day:
                continue
            found.append((str(vevent.get("uid", "")), str(vevent.get("summary", ""))))
    except Exception as e:
        raise CalendarReadError(f"{type(e).__name__}: {e}") from e

    return sorted(found, key=lambda pair: pair[1])
