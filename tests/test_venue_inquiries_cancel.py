#!/usr/bin/env python3
"""
get_venue_inquiries_for_date (dj_core) must read a booking and its later
cancellation as one cancelled event, whatever the Decision Dates say.

Bug being fixed: the function kept, per venue, the row with the latest
Decision Date. The 06-17-27 Nestldown cancel (2026-11-03) only showed as
Canceled because its Decision Date happened to be later than the booking's;
a blank or earlier Decision Date on the cancel row showed the date as Booked.
"""

import unittest
from unittest.mock import patch, MagicMock

import dj_core


def _row(ts, event_date, venue, resolution, decision=""):
    return {"Timestamp": ts, "Event Date": event_date, "Venue (if known)": venue,
            "Resolution": resolution, "Decision Date": decision}


def _fake_spreadsheet(rows):
    sheet = MagicMock()
    sheet.get_all_records.return_value = rows
    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = sheet
    return spreadsheet


class TestVenueInquiriesCancellation(unittest.TestCase):
    def _call(self, rows, date_str="Thu 6/17", year=2027):
        with patch.object(dj_core, "open_spreadsheet_with_retry",
                          return_value=_fake_spreadsheet(rows)):
            return dj_core.get_venue_inquiries_for_date(date_str, client=None, year=year)

    def test_booked_then_canceled_shows_canceled_even_with_blank_decision_date(self):
        rows = [_row("2/20/2026 9:01:48", "6/17/2027", "Nestldown", "Booked", "2/20/2026"),
                _row("11/3/2026 9:41:13", "6/17/2027", "Nestldown", "Canceled", "")]
        result = self._call(rows)
        self.assertEqual(result["booked"], [])
        self.assertEqual(result["not_booked"], ["Nestldown (Canceled)"])

    def test_booked_then_canceled_with_earlier_decision_date_still_canceled(self):
        rows = [_row("2/20/2026 9:01:48", "6/17/2027", "Nestldown", "Booked", "2/20/2026"),
                _row("11/3/2026 9:41:13", "6/17/2027", "Nestldown", "Canceled", "1/1/2026")]
        result = self._call(rows)
        self.assertEqual(result["booked"], [])
        self.assertEqual(result["not_booked"], ["Nestldown (Canceled)"])

    def test_rebooked_after_a_cancel_shows_booked(self):
        rows = [_row("2/20/2026 9:01:48", "6/17/2027", "Nestldown", "Booked", "2/20/2026"),
                _row("11/3/2026 9:41:13", "6/17/2027", "Nestldown", "Canceled", "11/3/2026"),
                _row("12/1/2026 9:00:00", "6/17/2027", "Nestldown", "Booked", "12/1/2026")]
        result = self._call(rows)
        self.assertEqual(result["booked"], ["Nestldown"])
        self.assertEqual(result["not_booked"], [])

    def test_two_live_bookings_at_one_venue_list_it_once(self):
        rows = [_row("1/1/2026 10:00:00", "6/17/2027", "Allied Arts Guild", "Booked", "1/1/2026"),
                _row("1/2/2026 10:00:00", "6/17/2027", "Allied Arts Guild", "Booked", "1/2/2026")]
        result = self._call(rows)
        self.assertEqual(result["booked"], ["Allied Arts Guild"])

    def test_other_dates_do_not_pair_with_this_one(self):
        rows = [_row("2/20/2026 9:01:48", "6/17/2027", "Nestldown", "Booked", "2/20/2026"),
                _row("11/3/2026 9:41:13", "6/18/2027", "Nestldown", "Canceled", "11/3/2026")]
        result = self._call(rows)
        self.assertEqual(result["booked"], ["Nestldown"])


if __name__ == "__main__":
    unittest.main()
