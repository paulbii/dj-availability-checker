#!/usr/bin/env python3
"""
Unit tests for calendar_read.py (CalDAV reads of the BIG FUN master calendars).

Run with:
  python3 -m unittest test_calendar_read -v

Replaces icalBuddy, which returns "No calendars" on macOS 27.2 even with Full
Access (2026-10-04) and failed silently in every caller. The rule under test:
a failed read RAISES. It never comes back as an empty list.
"""

import unittest
from datetime import date, datetime, timezone

import calendar_read
from calendar_read import (CalendarReadError, CalendarNotConfigured, CalEvent, fetch_events,
                           fetch_day_events, fetch_events_by_day, event_local_date)


class FakeEvent:
    def __init__(self, summary, dtstart, uid=None, dtend=None):
        from icalendar import Event
        self.icalendar_component = Event()
        self.icalendar_component.add("summary", summary)
        self.icalendar_component.add("dtstart", dtstart)
        if dtend:
            self.icalendar_component.add("dtend", dtend)
        if uid:
            self.icalendar_component.add("uid", uid)


class FakeCalendar:
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error
        self.searches = []

    def search(self, start, end, event, expand):
        self.searches.append((start, end, event, expand))
        if self.error:
            raise self.error
        return self.events


def connect_to(calendars):
    """Build a fake connect() returning {name: FakeCalendar}."""
    return lambda names: {n: calendars[n] for n in names}


class TestEventLocalDate(unittest.TestCase):

    def test_all_day_date_used_as_is(self):
        self.assertEqual(event_local_date(date(2026, 9, 5)), date(2026, 9, 5))

    def test_timed_utc_converted_to_pacific(self):
        # 10 PM PDT on 11/21 is 05:00 UTC on 11/22; the event is on 11/21.
        dt = datetime(2026, 11, 22, 5, 0, tzinfo=timezone.utc)
        self.assertEqual(event_local_date(dt), date(2026, 11, 21))

    def test_floating_datetime_treated_as_local(self):
        self.assertEqual(event_local_date(datetime(2026, 9, 24, 15, 30)), date(2026, 9, 24))


class TestFetchEvents(unittest.TestCase):

    def test_returns_date_and_summary_pairs_sorted(self):
        gigs = FakeCalendar([
            FakeEvent("[PB, WM] CASA of San Mateo County Fundraiser",
                      datetime(2026, 9, 24, 22, 30, tzinfo=timezone.utc)),
            FakeEvent("[WM] BACKUP DJ", date(2026, 9, 24)),
            FakeEvent("[HK] Starry Foundation SF", date(2026, 9, 23)),
        ])
        result = fetch_events(["Gigs"], date(2026, 1, 1), date(2026, 12, 31),
                              connect=connect_to({"Gigs": gigs}))
        self.assertEqual(result, [
            (date(2026, 9, 23), "[HK] Starry Foundation SF"),
            (date(2026, 9, 24), "[PB, WM] CASA of San Mateo County Fundraiser"),
            (date(2026, 9, 24), "[WM] BACKUP DJ"),
        ])

    def test_merges_multiple_calendars(self):
        cals = {
            "Gigs": FakeCalendar([FakeEvent("[PB] Nicole and Tommy", date(2026, 6, 6))]),
            "Wedding Faires": FakeCalendar([FakeEvent("[PB] Bridal Faire", date(2026, 1, 11))]),
        }
        result = fetch_events(["Gigs", "Wedding Faires"], date(2026, 1, 1), date(2026, 12, 31),
                              connect=connect_to(cals))
        self.assertEqual([s for _, s in result], ["[PB] Bridal Faire", "[PB] Nicole and Tommy"])

    def test_search_covers_whole_end_day_and_expands_recurrences(self):
        gigs = FakeCalendar([])
        fetch_events(["Gigs"], date(2026, 9, 24), date(2026, 9, 24),
                     connect=connect_to({"Gigs": gigs}))
        start, end, event, expand = gigs.searches[0]
        self.assertEqual(start.date(), date(2026, 9, 24))
        self.assertEqual(end.date(), date(2026, 9, 25))
        self.assertTrue(event)
        self.assertTrue(expand)

    def test_empty_calendar_is_empty_list_not_error(self):
        result = fetch_events(["Gigs"], date(2026, 1, 1), date(2026, 12, 31),
                              connect=connect_to({"Gigs": FakeCalendar([])}))
        self.assertEqual(result, [])

    def test_search_failure_raises(self):
        gigs = FakeCalendar(error=ConnectionError("server down"))
        with self.assertRaises(CalendarReadError):
            fetch_events(["Gigs"], date(2026, 1, 1), date(2026, 12, 31),
                         connect=connect_to({"Gigs": gigs}))

    def test_connect_failure_raises(self):
        def broken_connect(names):
            raise RuntimeError("No CalDAV credentials")
        with self.assertRaises(CalendarReadError):
            fetch_events(["Gigs"], date(2026, 1, 1), date(2026, 12, 31), connect=broken_connect)

    def test_unknown_calendar_name_raises(self):
        with self.assertRaises(CalendarReadError):
            fetch_events(["Gigz"], date(2026, 1, 1), date(2026, 12, 31))

    def test_known_calendars_have_urls(self):
        for name in ("Gigs", "Wedding Faires", "Unavailable"):
            self.assertIn(name, calendar_read.CALENDAR_URLS)


PT = calendar_read.TIMEZONE


class TestFetchEventsByDay(unittest.TestCase):
    """Paul's own calendars, for the availability checker: every event that
    covers a day, with its calendar and times."""

    def fetch(self, cals, start, end):
        return fetch_events_by_day(list(cals), start, end, connect=connect_to(cals))

    def test_timed_event_carries_calendar_and_local_times(self):
        cals = {"Paul": FakeCalendar([FakeEvent(
            "[PB] Babysit",
            datetime(2026, 11, 19, 23, 0, tzinfo=timezone.utc),      # 3:00 PM PST
            dtend=datetime(2026, 11, 20, 1, 30, tzinfo=timezone.utc))])}  # 5:30 PM PST
        result = self.fetch(cals, date(2026, 11, 19), date(2026, 11, 19))
        self.assertEqual(result, {date(2026, 11, 19): [CalEvent(
            "Paul", "[PB] Babysit", False,
            datetime(2026, 11, 19, 15, 0, tzinfo=PT), datetime(2026, 11, 19, 17, 30, tzinfo=PT))]})

    def test_all_day_event_end_is_exclusive(self):
        # An all-day event on 11/20 is stored as 11/20 to 11/21.
        cals = {"BIG FUN": FakeCalendar([FakeEvent("[PB] OUT", date(2026, 11, 20),
                                                   dtend=date(2026, 11, 21))])}
        result = self.fetch(cals, date(2026, 11, 19), date(2026, 11, 22))
        self.assertEqual(list(result), [date(2026, 11, 20)])
        self.assertTrue(result[date(2026, 11, 20)][0].all_day)

    def test_multi_day_event_is_on_every_day_it_covers(self):
        cals = {"Paul": FakeCalendar([FakeEvent("Trip", date(2026, 11, 20),
                                                dtend=date(2026, 11, 23))])}
        result = self.fetch(cals, date(2026, 11, 19), date(2026, 11, 30))
        self.assertEqual(sorted(result), [date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 22)])

    def test_event_started_before_the_range_still_shows(self):
        cals = {"Paul": FakeCalendar([FakeEvent("Trip", date(2026, 11, 18),
                                                dtend=date(2026, 11, 23))])}
        result = self.fetch(cals, date(2026, 11, 20), date(2026, 11, 20))
        self.assertEqual(list(result), [date(2026, 11, 20)])

    def test_timed_event_ending_at_midnight_is_not_on_the_next_day(self):
        cals = {"Paul": FakeCalendar([FakeEvent(
            "Late", datetime(2026, 11, 20, 20, 0, tzinfo=PT),
            dtend=datetime(2026, 11, 21, 0, 0, tzinfo=PT))])}
        result = self.fetch(cals, date(2026, 11, 20), date(2026, 11, 21))
        self.assertEqual(list(result), [date(2026, 11, 20)])

    def test_no_end_is_a_single_day(self):
        cals = {"Paul": FakeCalendar([FakeEvent("Note", date(2026, 11, 20))])}
        result = self.fetch(cals, date(2026, 11, 19), date(2026, 11, 22))
        self.assertEqual(list(result), [date(2026, 11, 20)])

    def test_all_day_first_then_by_start_time(self):
        cals = {
            "Paul": FakeCalendar([
                FakeEvent("Babysit", datetime(2026, 11, 20, 15, 0, tzinfo=PT),
                          dtend=datetime(2026, 11, 20, 17, 30, tzinfo=PT)),
                FakeEvent("Lunch", datetime(2026, 11, 20, 11, 30, tzinfo=PT),
                          dtend=datetime(2026, 11, 20, 12, 30, tzinfo=PT))]),
            "BIG FUN": FakeCalendar([FakeEvent("[PB] OUT", date(2026, 11, 20),
                                               dtend=date(2026, 11, 21))]),
        }
        result = self.fetch(cals, date(2026, 11, 20), date(2026, 11, 20))
        self.assertEqual([e.summary for e in result[date(2026, 11, 20)]],
                         ["[PB] OUT", "Lunch", "Babysit"])

    def test_nothing_on_the_calendars_is_an_empty_dict(self):
        result = self.fetch({"Paul": FakeCalendar([])}, date(2026, 11, 20), date(2026, 11, 20))
        self.assertEqual(result, {})

    def test_search_failure_raises(self):
        cals = {"Paul": FakeCalendar(error=ConnectionError("server down"))}
        with self.assertRaises(CalendarReadError) as ctx:
            self.fetch(cals, date(2026, 11, 20), date(2026, 11, 20))
        self.assertNotIsInstance(ctx.exception, CalendarNotConfigured)

    def test_missing_credentials_raise_not_configured(self):
        # A machine with no Keychain entry (Henry's) is not a failed read.
        def no_credentials(names):
            raise CalendarNotConfigured("No CalDAV credentials")
        with self.assertRaises(CalendarNotConfigured):
            fetch_events_by_day(["Paul"], date(2026, 11, 20), date(2026, 11, 20),
                                connect=no_credentials)

    def test_missing_library_raises_not_configured(self):
        def no_library(names):
            raise ImportError("No module named 'caldav'")
        with self.assertRaises(CalendarNotConfigured):
            fetch_events_by_day(["Paul"], date(2026, 11, 20), date(2026, 11, 20),
                                connect=no_library)

    def test_pauls_calendars_have_urls(self):
        for name in ("Paul", "BIG FUN"):
            self.assertIn(name, calendar_read.CALENDAR_URLS)


if __name__ == "__main__":
    unittest.main()


class TestFetchDayEvents(unittest.TestCase):
    """(uid, summary) for the events that START on one day of one calendar.

    The uid is the iCalendar UID, which is also what Calendar.app's
    `event id` resolves, so a caller can find over CalDAV and edit by id."""

    def test_returns_uid_and_summary_sorted_by_summary(self):
        gigs = FakeCalendar([
            FakeEvent("[UP] Jenna and Tyler",
                      datetime(2027, 5, 1, 0, 0, tzinfo=timezone.utc), uid="u-jenna"),  # 5 PM PDT 4/30
            FakeEvent("[HK] BACKUP DJ", date(2027, 4, 30), uid="u-backup"),
        ])
        self.assertEqual(
            fetch_day_events("Gigs", date(2027, 4, 30), connect=connect_to({"Gigs": gigs})),
            [("u-backup", "[HK] BACKUP DJ"), ("u-jenna", "[UP] Jenna and Tyler")])

    def test_event_from_the_day_before_running_past_midnight_is_excluded(self):
        gigs = FakeCalendar([
            FakeEvent("[PB] Late Night", datetime(2027, 4, 29, 22, 0, tzinfo=calendar_read.TIMEZONE), uid="u-late"),
        ])
        self.assertEqual(
            fetch_day_events("Gigs", date(2027, 4, 30), connect=connect_to({"Gigs": gigs})), [])

    def test_searches_exactly_that_day_with_expansion(self):
        gigs = FakeCalendar([])
        fetch_day_events("Gigs", date(2027, 4, 30), connect=connect_to({"Gigs": gigs}))
        (start, end, event, expand), = gigs.searches
        self.assertEqual(start, datetime(2027, 4, 30, 0, 0, tzinfo=calendar_read.TIMEZONE))
        self.assertEqual(end, datetime(2027, 5, 1, 0, 0, tzinfo=calendar_read.TIMEZONE))
        self.assertTrue(event)
        self.assertTrue(expand)

    def test_search_failure_raises_never_empty(self):
        gigs = FakeCalendar(error=ConnectionError("server down"))
        with self.assertRaises(CalendarReadError):
            fetch_day_events("Gigs", date(2027, 4, 30), connect=connect_to({"Gigs": gigs}))

    def test_unknown_calendar_raises(self):
        with self.assertRaises(CalendarReadError):
            fetch_day_events("Nope", date(2027, 4, 30), connect=connect_to({}))
