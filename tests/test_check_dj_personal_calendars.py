#!/usr/bin/env python3
"""The terminal checker shows Paul's own calendar events (Paul, 2026-11-20):
under his line on a single date, beside each available date when the range
query is for him, and as a star in the open-spots range."""

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_dj

D = datetime(2026, 11, 20)
NOTES = {"Paul": {date(2026, 11, 20): "Paul: [PB] Babysit (3:00 PM - 5:30 PM)"}}


def date_info(day, label, available):
    return {
        "date": label, "date_obj": day,
        "selected_data": {"Date": label, "Henry": "", "Paul": "", "Stefano": "OUT"},
        "bold_status": {},
        "availability": {"available_spots": len(available), "available_booking": available},
    }


BULK = [date_info(D, "Fri 11/20", ["Henry", "Paul"]),
        date_info(datetime(2026, 11, 21), "Sat 11/21", ["Henry", "Paul"])]


class Base(unittest.TestCase):

    def setUp(self):
        self._fore, self._style, self._back = check_dj.Fore, check_dj.Style, check_dj.Back
        check_dj.Fore = check_dj._Fore(False)
        check_dj.Style = check_dj._Style(False)
        check_dj.Back = check_dj._Back(False)
        p = mock.patch.object(check_dj, "get_bulk_availability_data", return_value=BULK)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        check_dj.Fore, check_dj.Style, check_dj.Back = self._fore, self._style, self._back

    def notes(self, notes=NOTES, error=""):
        p = mock.patch.object(check_dj, "personal_calendar_notes", return_value=(notes, error))
        self.addCleanup(p.stop)
        return p.start()


class TestSingleDate(Base):

    def run_check(self, lines):
        data = {
            "date_obj": D,
            "selected_data": {"Date": "Fri 11/20", "Henry": "", "Paul": "OUT"},
            "availability": {"booked_count": 0, "available_spots": 1, "available_booking": ["Henry"]},
        }
        with mock.patch.object(check_dj, "get_date_availability_data", return_value=data), \
             mock.patch.object(check_dj, "get_venue_inquiries_for_date", return_value=None), \
             mock.patch.object(check_dj, "get_venue_cautions", return_value=[]), \
             mock.patch.object(check_dj, "get_cache_info", return_value=None), \
             mock.patch.object(check_dj, "get_nearby_bookings_for_dj", return_value=[]), \
             mock.patch.object(check_dj, "personal_calendar_lines",
                               side_effect=lambda dj, d, v: lines if dj == "Paul" else []) as helper:
            out = check_dj.check_availability("2026", "11-20", None, None, None, None)
        return out.split("\n"), helper

    def test_events_follow_pauls_line(self):
        out, _ = self.run_check([("   On Paul's calendars:", "dim"),
                                 ("     Paul   3:00 PM - 5:30 PM   [PB] Babysit", "dim")])
        i = next(n for n, line in enumerate(out) if line.startswith("Paul:"))
        self.assertEqual(out[i + 1:i + 3], ["   On Paul's calendars:",
                                            "     Paul   3:00 PM - 5:30 PM   [PB] Babysit"])

    def test_helper_gets_the_date_and_the_matrix_value(self):
        _, helper = self.run_check([])
        self.assertIn(mock.call("Paul", D, "OUT"), helper.call_args_list)


class TestDJRange(Base):

    def test_available_date_carries_that_days_events(self):
        self.notes()
        out = check_dj.query_dj_availability("2026", "Paul", "11-20", "11-21", None, None, None)
        self.assertIn("  Fri 11/20   Paul: [PB] Babysit (3:00 PM - 5:30 PM)", out.split("\n"))
        self.assertIn("  Sat 11/21", out.split("\n"))

    def test_another_djs_dates_are_plain(self):
        self.notes()
        out = check_dj.query_dj_availability("2026", "Henry", "11-20", "11-21", None, None, None)
        self.assertIn("  Sat 11/21", out.split("\n"))
        self.assertNotIn("Babysit", out)

    def test_failed_read_is_reported(self):
        self.notes({}, "Could not read Paul's calendars (server down)")
        out = check_dj.query_dj_availability("2026", "Paul", "11-20", "11-21", None, None, None)
        self.assertIn("Could not read Paul's calendars (server down)", out)

    def test_failed_read_is_not_reported_for_another_dj(self):
        self.notes({}, "Could not read Paul's calendars (server down)")
        out = check_dj.query_dj_availability("2026", "Henry", "11-20", "11-21", None, None, None)
        self.assertNotIn("Could not read", out)


class TestOpenSpotsRange(Base):

    def test_star_on_the_day_with_something_on(self):
        self.notes()
        out = check_dj.query_date_range("2026", "11-20", "11-21", None, None, None, None).split("\n")
        self.assertIn("Fri 11/20: 2 spot(s) available (Henry, Paul*)", out)
        self.assertIn("Sat 11/21: 2 spot(s) available (Henry, Paul)", out)
        self.assertIn(check_dj.PERSONAL_MARK_FOOTNOTE, out)

    def test_no_footnote_when_nothing_is_starred(self):
        self.notes({})
        out = check_dj.query_date_range("2026", "11-20", "11-21", None, None, None, None)
        self.assertNotIn(check_dj.PERSONAL_MARK_FOOTNOTE, out)

    def test_reads_the_calendars_once_for_the_range(self):
        helper = self.notes()
        check_dj.query_date_range("2026", "11-20", "11-21", None, None, None, None)
        self.assertEqual(helper.call_count, 1)

    def test_failed_read_is_reported(self):
        self.notes({}, "Could not read Paul's calendars (server down)")
        out = check_dj.query_date_range("2026", "11-20", "11-21", None, None, None, None)
        self.assertIn("Could not read Paul's calendars (server down)", out)


if __name__ == "__main__":
    unittest.main()
