#!/usr/bin/env python3
"""
Tests for parse_dj_codes in booking_comparator.

Bug being fixed: the calendar title parser only accepted slash-joined DJ
brackets ([WM/HK]). A comma-joined bracket ([PB, WM]) did not match, so the
whole event was skipped and the comparator reported the DJs as missing from
the calendar (9/24/2026 CASA fundraiser, misdiagnosed for six weeks).
"""

import unittest
from datetime import date

import booking_comparator


class TestParseDjCodes(unittest.TestCase):

    def test_single_code(self):
        self.assertEqual(booking_comparator.parse_dj_codes("[PB] Nicole and Tommy"), ["PB"])

    def test_slash_joined(self):
        self.assertEqual(booking_comparator.parse_dj_codes("[WM/HK] Memorial Service"), ["WM", "HK"])

    def test_comma_space_joined(self):
        self.assertEqual(booking_comparator.parse_dj_codes("[PB, WM] CASA Fundraiser"), ["PB", "WM"])

    def test_comma_no_space_joined(self):
        self.assertEqual(booking_comparator.parse_dj_codes("[PB,WM] CASA Fundraiser"), ["PB", "WM"])

    def test_three_codes_mixed_separators(self):
        self.assertEqual(booking_comparator.parse_dj_codes("[PB/WM, HK] Big one"), ["PB", "WM", "HK"])

    def test_unassigned_code(self):
        self.assertEqual(booking_comparator.parse_dj_codes("[UP] Alumis Holiday"), ["UP"])

    def test_no_bracket_returns_none(self):
        self.assertIsNone(booking_comparator.parse_dj_codes("Nicole and Tommy"))

    def test_date_line_returns_none(self):
        # A bare date/time string never carries a bracket; make sure nothing false-matches
        self.assertIsNone(booking_comparator.parse_dj_codes("09/24 at 3:30 PM - 9:30 PM"))

    def test_long_token_not_a_dj_bracket(self):
        self.assertIsNone(booking_comparator.parse_dj_codes("[SETUP] Something"))


class TestParseCalendarEvents(unittest.TestCase):
    """Calendar events (date, summary) -> bookings and backups keyed "M/D".

    Same rules the icalBuddy text parser applied; only the input shape changed.
    """

    NAMES = {"[PB]": "Paul", "[WM]": "Woody", "[HK]": "Henry", "[SB]": "Stefano"}

    def parse(self, events):
        return booking_comparator.parse_calendar_events(events, self.NAMES)

    def test_single_dj_booking(self):
        bookings, backups = self.parse([(date(2026, 6, 6), "[PB] Nicole and Tommy")])
        self.assertEqual(bookings, {"6/6": ["Paul"]})
        self.assertEqual(backups, {})

    def test_joint_bookings_both_formats_sorted(self):
        bookings, _ = self.parse([
            (date(2026, 9, 24), "[PB, WM] CASA of San Mateo County Fundraiser"),
            (date(2026, 11, 16), "[WM/HK] Memorial Service"),
        ])
        self.assertEqual(bookings, {"9/24": ["Paul", "Woody"], "11/16": ["Henry", "Woody"]})

    def test_backup_entries_go_to_backups(self):
        bookings, backups = self.parse([
            (date(2026, 9, 24), "[WM] BACKUP DJ"),
            (date(2026, 9, 5), "[SB] PAID BACKUP DJ"),
        ])
        self.assertEqual(bookings, {})
        self.assertEqual(backups, {"9/24": ["Woody"], "9/5": ["Stefano"]})

    def test_hold_to_dj_skipped(self):
        bookings, backups = self.parse([(date(2026, 3, 1), "[PB] Hold to DJ Smith wedding")])
        self.assertEqual((bookings, backups), ({}, {}))

    def test_unassigned_code_is_tba(self):
        bookings, _ = self.parse([(date(2027, 5, 15), "[UP] Alumis Holiday")])
        self.assertEqual(bookings, {"5/15": ["TBA"]})

    def test_unknown_code_flagged(self):
        _, backups = self.parse([(date(2026, 9, 5), "[AD] PAID BACKUP DJ")])
        self.assertEqual(backups, {"9/5": ["?AD"]})

    def test_no_bracket_ignored(self):
        self.assertEqual(self.parse([(date(2026, 7, 4), "Van 6 service")]), ({}, {}))

    def test_event_starting_in_prior_year_ignored(self):
        """A 12/31 event overlapping Jan 1 must not be keyed "12/31" in this year."""
        bookings, _ = booking_comparator.parse_calendar_events(
            [(date(2025, 12, 31), "[PB] New Year's Eve")], self.NAMES, year=2026)
        self.assertEqual(bookings, {})

    def test_two_events_same_date_accumulate(self):
        bookings, _ = self.parse([
            (date(2026, 6, 6), "[PB] Nicole and Tommy"),
            (date(2026, 6, 6), "[HK] Smith Wedding"),
        ])
        self.assertEqual(bookings, {"6/6": ["Henry", "Paul"]})


class TestFetchMasterCalendarFailure(unittest.TestCase):

    def test_read_failure_returns_none_pair(self):
        """A failed read must drop to the 2-of-3 report, never an empty calendar."""
        from unittest import mock
        from calendar_read import CalendarReadError
        with mock.patch.object(booking_comparator.calendar_read, "fetch_events",
                               side_effect=CalendarReadError("server down")):
            self.assertEqual(booking_comparator.fetch_master_calendar(2026), (None, None))

    def test_year_from_command_line_string(self):
        """argparse passes --year as a string; it must query that whole year."""
        from unittest import mock
        with mock.patch.object(booking_comparator.calendar_read, "fetch_events",
                               return_value=[(date(2026, 9, 24), "[PB] Nicole and Tommy")]) as fetch:
            bookings, _ = booking_comparator.fetch_master_calendar("2026")
        self.assertEqual(fetch.call_args[0][1:], (date(2026, 1, 1), date(2026, 12, 31)))
        self.assertEqual(bookings, {"9/24": ["Paul"]})


if __name__ == '__main__':
    unittest.main()
