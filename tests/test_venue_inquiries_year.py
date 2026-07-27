#!/usr/bin/env python3
"""
Tests for year filtering in get_venue_inquiries_for_date (dj_core).

Bug being fixed: the function matched inquiries on month + day only, ignoring
the year. On a year-specific availability view (check_2027.py), that surfaced
inquiries from any year sharing the same MM/DD, so a 2026 "Full" showed up on
a wide-open 2027 date and read as a contradiction.
"""

import unittest
from unittest.mock import patch, MagicMock

import dj_core


# Real 10/23 inquiry history (venue rows only; a no-venue row is included to
# confirm it stays filtered out).
FIXTURE_ROWS = [
    {'Event Date': '10/23/2023', 'Venue (if known)': 'Nestldown',
     'Resolution': 'Cold', 'Decision Date': ''},
    {'Event Date': '10/23/2025', 'Venue (if known)': 'Rengstorff',
     'Resolution': "Didn't Book", 'Decision Date': ''},
    {'Event Date': '10/23/2026', 'Venue (if known)': 'Villa Montalvo',
     'Resolution': 'Full', 'Decision Date': '11/22/2026'},
    {'Event Date': '10/23/2026', 'Venue (if known)': '',
     'Resolution': "Didn't Book", 'Decision Date': '2/9/2026'},
]


def _fake_spreadsheet(rows):
    sheet = MagicMock()
    sheet.get_all_records.return_value = rows
    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = sheet
    return spreadsheet


class TestVenueInquiriesYearFilter(unittest.TestCase):
    def _call(self, date_str, year):
        with patch.object(dj_core, 'open_spreadsheet_with_retry',
                          return_value=_fake_spreadsheet(FIXTURE_ROWS)):
            return dj_core.get_venue_inquiries_for_date(date_str, client=None, year=year)

    def test_2027_has_no_inquiries(self):
        # No inquiry exists for 10/23/2027; nothing should surface.
        result = self._call('Sat 10/23', 2027)
        self.assertEqual(result['booked'], [])
        self.assertEqual(result['not_booked'], [])

    def test_2026_returns_only_that_years_row(self):
        result = self._call('Fri 10/23', 2026)
        self.assertEqual(result['not_booked'], ['Villa Montalvo (Full)'])

    def test_2023_returns_only_that_years_row(self):
        result = self._call('Mon 10/23', 2023)
        self.assertEqual(result['not_booked'], ['Nestldown (Cold)'])

    def test_year_none_preserves_month_day_only_behavior(self):
        # Backward compatible: no year given still matches on MM/DD across years.
        result = self._call('10/23', None)
        self.assertEqual(
            result['not_booked'],
            ['Nestldown (Cold)', 'Rengstorff (Didn\'t Book)', 'Villa Montalvo (Full)'],
        )


if __name__ == '__main__':
    unittest.main()
