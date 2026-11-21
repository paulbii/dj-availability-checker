#!/usr/bin/env python3
"""
Paul's own calendars in the availability checker (Paul, 2026-11-20).

The checker lists what is on his "Paul" and "BIG FUN" calendars for a date.
The events are information, not blockers: he may be able to move them, so
they never change a status or a spot count. A failed read says so; it never
looks like an empty day. A machine with no CalDAV setup shows nothing.
"""

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dj_core
from calendar_read import CalEvent, CalendarReadError, CalendarNotConfigured, TIMEZONE as PT

D = date(2026, 11, 20)
OUT = CalEvent("BIG FUN", "[PB] OUT", True, D, D)
BABYSIT = CalEvent("Paul", "[PB] Babysit", False,
                   datetime(2026, 11, 20, 15, 0, tzinfo=PT), datetime(2026, 11, 20, 17, 30, tzinfo=PT))
NO_MEETINGS = CalEvent("BIG FUN", "[PB] No Meetings", False,
                       datetime(2026, 11, 20, 11, 30, tzinfo=PT), datetime(2026, 11, 20, 21, 0, tzinfo=PT))


def fetch_returning(by_day):
    calls = []

    def fetch(names, start, end):
        calls.append((names, start, end))
        return by_day
    fetch.calls = calls
    return fetch


def fetch_raising(error):
    def fetch(names, start, end):
        raise error
    return fetch


class TestPersonalCalendarLines(unittest.TestCase):
    """The block under Paul's line on a single-date check."""

    def lines(self, by_day, dj="Paul", value="", day=D):
        return dj_core.personal_calendar_lines(dj, day, value, fetch=fetch_returning(by_day))

    def test_lists_each_event_with_calendar_time_and_title(self):
        lines = self.lines({D: [NO_MEETINGS, BABYSIT]})
        self.assertEqual(lines, [
            ("   On Paul's calendars:", "dim"),
            ("     BIG FUN   11:30 AM - 9:00 PM   [PB] No Meetings", "dim"),
            ("     Paul      3:00 PM - 5:30 PM    [PB] Babysit", "dim"),
        ])

    def test_all_day_event_says_all_day(self):
        lines = self.lines({D: [OUT]}, value="OUT")
        self.assertEqual(lines[1], ("     BIG FUN   all day   [PB] OUT", "dim"))

    def test_multi_day_all_day_event_shows_its_dates(self):
        trip = CalEvent("BIG FUN", "Trip", True, date(2026, 11, 19), date(2026, 11, 22))
        lines = self.lines({D: [trip]})
        self.assertEqual(lines[1], ("     BIG FUN   all day (11/19 - 11/22)   Trip", "dim"))

    def test_timed_event_across_midnight_shows_its_dates(self):
        late = CalEvent("Paul", "Party", False,
                        datetime(2026, 11, 20, 20, 0, tzinfo=PT), datetime(2026, 11, 21, 1, 0, tzinfo=PT))
        lines = self.lines({D: [late]})
        self.assertEqual(lines[1], ("     Paul   11/20 8:00 PM - 11/21 1:00 AM   Party", "dim"))

    def test_nothing_on_the_calendars_adds_nothing(self):
        self.assertEqual(self.lines({}), [])

    def test_asks_for_pauls_two_calendars_for_that_one_day(self):
        fetch = fetch_returning({})
        dj_core.personal_calendar_lines("Paul", D, "", fetch=fetch)
        self.assertEqual(fetch.calls, [(["Paul", "BIG FUN"], D, D)])

    def test_accepts_the_checkers_datetime(self):
        fetch = fetch_returning({D: [BABYSIT]})
        lines = dj_core.personal_calendar_lines("Paul", datetime(2026, 11, 20), "", fetch=fetch)
        self.assertEqual(fetch.calls[0][1:], (D, D))
        self.assertEqual(len(lines), 2)

    def test_other_djs_are_never_looked_up(self):
        fetch = fetch_returning({D: [BABYSIT]})
        self.assertEqual(dj_core.personal_calendar_lines("Henry", D, "", fetch=fetch), [])
        self.assertEqual(fetch.calls, [])

    def test_failed_read_says_so(self):
        lines = dj_core.personal_calendar_lines(
            "Paul", D, "", fetch=fetch_raising(CalendarReadError("ConnectionError: server down")))
        self.assertEqual(lines, [
            ("   Could not read Paul's calendars (ConnectionError: server down)", "warn")])

    def test_machine_without_caldav_shows_nothing(self):
        lines = dj_core.personal_calendar_lines(
            "Paul", D, "", fetch=fetch_raising(CalendarNotConfigured("no credentials")))
        self.assertEqual(lines, [])


class TestAllDayRemindersLeftOut(unittest.TestCase):
    """All-day items on the "Paul" calendar are reminders ("Pay Chase"), so
    they are left out. A real all-day absence goes on "BIG FUN" (Paul,
    2026-11-21)."""

    REMINDER = CalEvent("Paul", "Pay Chase", True, D, D)

    def test_all_day_on_the_paul_calendar_is_not_listed(self):
        lines = dj_core.personal_calendar_lines(
            "Paul", D, "", fetch=fetch_returning({D: [self.REMINDER, BABYSIT]}))
        self.assertEqual([text for text, _ in lines],
                         ["   On Paul's calendars:", "     Paul   3:00 PM - 5:30 PM   [PB] Babysit"])

    def test_a_day_with_only_a_reminder_shows_nothing(self):
        lines = dj_core.personal_calendar_lines(
            "Paul", D, "", fetch=fetch_returning({D: [self.REMINDER]}))
        self.assertEqual(lines, [])

    def test_all_day_on_big_fun_is_still_listed(self):
        lines = dj_core.personal_calendar_lines("Paul", D, "OUT", fetch=fetch_returning({D: [OUT]}))
        self.assertEqual(len(lines), 2)

    def test_timed_event_on_the_paul_calendar_is_still_listed(self):
        lines = dj_core.personal_calendar_lines("Paul", D, "", fetch=fetch_returning({D: [BABYSIT]}))
        self.assertEqual(len(lines), 2)

    def test_range_notes_leave_a_reminder_only_day_out(self):
        notes, _ = dj_core.personal_calendar_notes(
            D, date(2026, 11, 22),
            fetch=fetch_returning({D: [self.REMINDER, BABYSIT], date(2026, 11, 22): [self.REMINDER]}))
        self.assertEqual(notes, {"Paul": {D: "Paul: [PB] Babysit (3:00 PM - 5:30 PM)"}})


class TestOutMismatch(unittest.TestCase):
    """An all-day OUT on the calendar should also be OUT on the Matrix."""

    WARNING = ("   ⚠️  \"[PB] OUT\" is on the BIG FUN calendar but the Matrix does not show OUT", "warn")

    def lines(self, events, value):
        return dj_core.personal_calendar_lines("Paul", D, value, fetch=fetch_returning({D: events}))

    def test_warns_when_matrix_is_blank(self):
        self.assertEqual(self.lines([OUT], "")[-1], self.WARNING)

    def test_warns_when_matrix_is_booked(self):
        self.assertEqual(self.lines([OUT], "BOOKED")[-1], self.WARNING)

    def test_no_warning_when_matrix_is_out(self):
        self.assertNotIn(self.WARNING, self.lines([OUT], "OUT"))

    def test_no_warning_when_matrix_out_is_bold(self):
        self.assertNotIn(self.WARNING, self.lines([OUT], "OUT (BOLD)"))

    def test_timed_event_is_not_an_out(self):
        timed = CalEvent("BIG FUN", "[PB] OUT", False,
                         datetime(2026, 11, 20, 9, 0, tzinfo=PT), datetime(2026, 11, 20, 12, 0, tzinfo=PT))
        self.assertEqual(len(self.lines([timed], "")), 2)

    def test_lowercase_out_in_a_title_is_not_an_out(self):
        dinner = CalEvent("BIG FUN", "Dinner out with Alisa", True, D, D)
        self.assertEqual(len(self.lines([dinner], "")), 2)

    def test_out_inside_another_word_is_not_an_out(self):
        self.assertEqual(len(self.lines([CalEvent("BIG FUN", "ROUTE planning", True, D, D)], "")), 2)


class TestPersonalCalendarNotes(unittest.TestCase):
    """One read for a whole range: {dj: {day: text}} plus an error line."""

    def test_one_line_of_text_per_day(self):
        notes, error = dj_core.personal_calendar_notes(
            date(2026, 11, 19), date(2026, 11, 21), fetch=fetch_returning({D: [OUT, BABYSIT]}))
        self.assertEqual(notes, {"Paul": {
            D: "BIG FUN: [PB] OUT (all day); Paul: [PB] Babysit (3:00 PM - 5:30 PM)"}})
        self.assertEqual(error, "")

    def test_reads_the_whole_range_once(self):
        fetch = fetch_returning({})
        dj_core.personal_calendar_notes(date(2026, 5, 1), date(2026, 5, 31), fetch=fetch)
        self.assertEqual(fetch.calls, [(["Paul", "BIG FUN"], date(2026, 5, 1), date(2026, 5, 31))])

    def test_accepts_datetimes(self):
        fetch = fetch_returning({})
        dj_core.personal_calendar_notes(datetime(2026, 5, 1), datetime(2026, 5, 31), fetch=fetch)
        self.assertEqual(fetch.calls[0][1:], (date(2026, 5, 1), date(2026, 5, 31)))

    def test_failed_read_returns_the_error_line(self):
        notes, error = dj_core.personal_calendar_notes(
            D, D, fetch=fetch_raising(CalendarReadError("ConnectionError: server down")))
        self.assertEqual(notes, {})
        self.assertEqual(error, "Could not read Paul's calendars (ConnectionError: server down)")

    def test_machine_without_caldav_is_silent(self):
        notes, error = dj_core.personal_calendar_notes(
            D, D, fetch=fetch_raising(CalendarNotConfigured("no credentials")))
        self.assertEqual((notes, error), ({}, ""))

    def test_personal_note_looks_up_one_dj_and_day(self):
        notes = {"Paul": {D: "Paul: Lunch (11:30 AM - 12:30 PM)"}}
        self.assertEqual(dj_core.personal_note(notes, "Paul", datetime(2026, 11, 20)),
                         "Paul: Lunch (11:30 AM - 12:30 PM)")
        self.assertEqual(dj_core.personal_note(notes, "Paul", date(2026, 11, 21)), "")
        self.assertEqual(dj_core.personal_note(notes, "Henry", D), "")


class TestMarkPersonalConflicts(unittest.TestCase):
    """Open-spots range: a star on a DJ who has something on that day."""

    NOTES = {"Paul": {D: "Paul: [PB] Babysit (3:00 PM - 5:30 PM)"}}

    def test_stars_the_dj_on_that_day(self):
        self.assertEqual(dj_core.mark_personal_conflicts(["Henry", "Paul"], D, self.NOTES),
                         ["Henry", "Paul*"])

    def test_no_star_on_a_clear_day(self):
        self.assertEqual(dj_core.mark_personal_conflicts(["Henry", "Paul"], date(2026, 11, 21), self.NOTES),
                         ["Henry", "Paul"])

    def test_accepts_the_checkers_datetime(self):
        self.assertEqual(dj_core.mark_personal_conflicts(["Paul"], datetime(2026, 11, 20), self.NOTES),
                         ["Paul*"])

    def test_other_labels_are_left_alone(self):
        self.assertEqual(dj_core.mark_personal_conflicts(["Stefano [MAYBE]"], D, self.NOTES),
                         ["Stefano [MAYBE]"])

    def test_footnote_explains_the_star(self):
        self.assertIn("*", dj_core.PERSONAL_MARK_FOOTNOTE)


if __name__ == "__main__":
    unittest.main()
