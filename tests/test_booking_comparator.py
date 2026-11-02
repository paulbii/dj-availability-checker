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


class TestCalendarInitialsMap(unittest.TestCase):
    """The bracket map the calendar leg uses is built from dj_core's DJ_INITIALS."""

    def test_djs_resolve(self):
        m = booking_comparator.calendar_initials_map()
        self.assertEqual(m["[PB]"], "Paul")
        self.assertNotIn("[UP]", m)

    def test_alan_do_is_a_known_backup(self):
        """Alan Do roadies and backs up in emergencies (Paul, 2026-11-02); [AD] is not a typo."""
        m = booking_comparator.calendar_initials_map()
        self.assertEqual(m["[AD]"], "Alan")
        from dj_core import DJ_FULL_NAMES
        self.assertEqual(DJ_FULL_NAMES["AD"], "Alan Do")


class TestBackupCompareSkipsPeopleWithoutMatrixColumn(unittest.TestCase):
    """A backup who has no Availability Matrix column (Alan) can never be marked
    BACKUP in the Matrix, so comparing his calendar entry against the Matrix
    would mismatch every run. Such entries are reported, not counted."""

    MATRIX_DJS = {"Henry", "Woody", "Paul", "Stefano", "Felipe"}

    def report(self, matrix_backups, cal_backups, matrix_columns, bookings=None):
        import io
        out = io.StringIO()
        b = bookings or {}
        booking_comparator.compare_systems(b, b, b, matrix_backups, cal_backups,
                                           output=out, matrix_columns=matrix_columns)
        return out.getvalue()

    def test_filter_survives_the_booking_loop(self):
        """Regression: compare_systems has a per-date local that shadowed the
        parameter, so with any bookings present every DJ was 'skipped'."""
        text = self.report({"9/5": ["Henry"]}, {"9/5": ["Alan", "Henry"]}, self.MATRIX_DJS,
                           bookings={"9/5": ["Paul"], "9/12": ["Woody"]})
        self.assertIn("0 backup discrepancy", text)
        self.assertIn("9/5  Alan", text)

    def test_calendar_only_alan_is_not_a_mismatch(self):
        text = self.report({}, {"9/5": ["Alan"]}, self.MATRIX_DJS)
        self.assertIn("0 backup discrepancy", text)
        self.assertIn("Alan", text)
        self.assertIn("no Matrix column", text)

    def test_without_matrix_djs_behaviour_is_unchanged(self):
        text = self.report({}, {"9/5": ["Alan"]}, None)
        self.assertIn("1 backup discrepancy", text)

    def test_real_dj_on_same_date_still_compared(self):
        text = self.report({}, {"9/5": ["Alan", "Henry"]}, self.MATRIX_DJS)
        self.assertIn("1 backup discrepancy", text)
        self.assertIn("Cal:     Henry", text)

    def test_backup_drift_reported_when_bookings_are_in_sync(self):
        """Regression: a clean booking week used to return before the backup
        section, so backup mismatches were never printed."""
        text = self.report({"9/5": ["Woody"]}, {}, self.MATRIX_DJS)
        self.assertIn("ALL SYSTEMS IN SYNC", text)
        self.assertIn("1 backup discrepancy", text)
        self.assertIn("Matrix:  Woody", text)

    def test_unknown_code_is_still_a_mismatch(self):
        """A typo'd bracket must keep surfacing; only known names are skipped."""
        text = self.report({}, {"9/5": ["?HKK"]}, self.MATRIX_DJS)
        self.assertIn("1 backup discrepancy", text)


ACCEPTED_TEXT = """\
# year  date  kind     state...                       reason
2026 3/7   backup  matrix=none         cal=Paul,Henry    past date, leave it (Paul 11-02)
2026 9/6   backup  matrix=Woody        cal=none          past date (Paul 11-02)

2027 2/27  booking gigdb=Henry matrix=none cal=none     penciled in (Paul 7-27)
"""


class TestParseAccepted(unittest.TestCase):
    """Hand-written accepted-items file: one line per known discrepancy that
    Paul has decided to leave alone. A line pins the exact state, so a date
    that changes shape is flagged again."""

    def test_lines_parse_with_reason(self):
        entries = booking_comparator.parse_accepted(ACCEPTED_TEXT)
        self.assertEqual(len(entries), 3)
        e = entries[0]
        self.assertEqual((e["year"], e["date"], e["kind"]), (2026, "3/7", "backup"))
        self.assertEqual(e["state"], {"matrix": [], "cal": ["Henry", "Paul"]})
        self.assertEqual(e["reason"], "past date, leave it (Paul 11-02)")

    def test_booking_line_carries_three_systems(self):
        e = booking_comparator.parse_accepted(ACCEPTED_TEXT)[2]
        self.assertEqual(e["kind"], "booking")
        self.assertEqual(e["state"], {"gigdb": ["Henry"], "matrix": [], "cal": []})

    def test_bad_line_names_its_number(self):
        with self.assertRaises(ValueError) as cm:
            booking_comparator.parse_accepted("2026 3/7 backup matrix=none cal=none ok\nnonsense line\n")
        self.assertIn("line 2", str(cm.exception))

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            booking_comparator.parse_accepted("2026 3/7 helper matrix=none cal=none x\n")


class TestAcceptedItemsInReport(unittest.TestCase):

    def report(self, gig_db, matrix, cal, matrix_backups, cal_backups, accepted):
        import io
        out = io.StringIO()
        booking_comparator.compare_systems(gig_db, matrix, cal, matrix_backups, cal_backups,
                                           output=out, accepted=accepted)
        return out.getvalue()

    def accepted(self):
        return [e for e in booking_comparator.parse_accepted(ACCEPTED_TEXT)]

    def test_accepted_backup_is_listed_not_counted(self):
        text = self.report({}, {}, {}, {}, {"3/7": ["Henry", "Paul"]}, self.accepted())
        self.assertIn("0 backup discrepancy", text)
        self.assertIn("ACCEPTED", text)
        self.assertIn("past date, leave it (Paul 11-02)", text)
        self.assertIn("1 accepted", text)

    def test_accepted_booking_is_listed_not_counted(self):
        text = self.report({"2/27": ["Henry"]}, {}, {}, {}, {}, self.accepted())
        self.assertIn("ALL SYSTEMS IN SYNC", text)
        self.assertIn("0 booking discrepancy", text)
        self.assertIn("penciled in (Paul 7-27)", text)

    def test_changed_state_is_flagged_again(self):
        """3/7 is accepted as Matrix none / Cal Henry+Paul. Matrix now says Woody."""
        text = self.report({}, {}, {}, {"3/7": ["Woody"]}, {"3/7": ["Henry", "Paul"]},
                           self.accepted())
        self.assertIn("1 backup discrepancy", text)
        self.assertIn("Matrix:  Woody", text)

    def test_stale_lines_are_reported(self):
        """Nothing wrong on 9/6 any more: say so, so the line gets removed."""
        text = self.report({}, {}, {}, {}, {"3/7": ["Henry", "Paul"]}, self.accepted())
        self.assertIn("no longer match", text)
        self.assertIn("9/6", text.split("no longer match", 1)[1])
        self.assertIn("2/27", text.split("no longer match", 1)[1])

    def test_no_accepted_file_changes_nothing(self):
        text = self.report({}, {}, {}, {}, {"3/7": ["Henry", "Paul"]}, None)
        self.assertIn("1 backup discrepancy", text)
        self.assertNotIn("ACCEPTED", text)


if __name__ == '__main__':
    unittest.main()
