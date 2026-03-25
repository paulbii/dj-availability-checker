#!/usr/bin/env python3
"""
Unit tests for stefano_maxed_enforcer.py

Run with:
  python3 -m pytest test_stefano_enforcer.py -v

Tests all sync logic (recalculation, diffing) without
requiring Google Sheets or Calendar access.
"""

import unittest
from datetime import date

from stefano_maxed_enforcer import (
    calculate_sync,
    is_fss,
    adjacent_weekend_dates,
    parse_matrix_date,
)


def make_rows(entries, year=2026):
    """
    Build fake row data from a compact format.

    entries: list of (month, day, value) tuples
    Returns: list of (date_obj, row_number, cell_value) matching
             read_stefano_column() output format.
    """
    rows = []
    for i, (m, d, val) in enumerate(entries):
        rows.append((date(year, m, d), i + 2, val))
    return rows


class TestIsFSS(unittest.TestCase):
    def test_friday(self):
        self.assertTrue(is_fss(date(2026, 8, 7)))   # Friday

    def test_saturday(self):
        self.assertTrue(is_fss(date(2026, 8, 8)))   # Saturday

    def test_sunday(self):
        self.assertTrue(is_fss(date(2026, 8, 9)))   # Sunday

    def test_weekday(self):
        self.assertFalse(is_fss(date(2026, 8, 10)))  # Monday


class TestAdjacentWeekendDates(unittest.TestCase):
    def test_saturday_booking(self):
        """Booking on Sat Aug 8 should buffer Fri/Sat/Sun of prior and next week."""
        prior, nxt = adjacent_weekend_dates(date(2026, 8, 8))
        self.assertEqual(prior, [date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2)])
        self.assertEqual(nxt, [date(2026, 8, 14), date(2026, 8, 15), date(2026, 8, 16)])

    def test_month_boundary(self):
        """Booking on Sat Aug 1 should produce prior dates in July."""
        prior, nxt = adjacent_weekend_dates(date(2026, 8, 1))
        self.assertEqual(prior[0], date(2026, 7, 24))  # Prior Friday


class TestCalculateSync(unittest.TestCase):

    def test_single_booking_adds_buffers(self):
        """One booking on Aug 8 should propose MAXED for adjacent weekends."""
        rows = make_rows([
            (8, 1, ""),       # Sat - should be added
            (8, 2, ""),       # Sun - should be added
            (8, 7, "OUT"),    # Fri - OUT, skip
            (8, 8, "BOOKED"), # Sat - the booking
            (8, 9, "OUT"),    # Sun - OUT, skip
            (8, 14, ""),      # Fri - should be added
            (8, 15, ""),      # Sat - should be added
            (8, 16, ""),      # Sun - should be added
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 1)
        self.assertIn(date(2026, 8, 1), additions)
        self.assertIn(date(2026, 8, 15), additions)
        self.assertEqual(len(removals), 0)

    def test_cancellation_removes_buffers(self):
        """
        Aug 8 was booked, adjacent dates were MAXED.
        After cancellation (Aug 8 now blank), those MAXED dates should be removals.
        """
        rows = make_rows([
            (8, 1, "MAXED"),  # Was buffered, should be removed
            (8, 2, "MAXED"),  # Was buffered, should be removed
            (8, 8, ""),       # Booking canceled
            (8, 14, ""),      # Fri
            (8, 15, "MAXED"), # Was buffered, should be removed
            (8, 16, "MAXED"), # Was buffered, should be removed
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 0)
        self.assertEqual(len(additions), 0)
        self.assertIn(date(2026, 8, 1), removals)
        self.assertIn(date(2026, 8, 15), removals)

    def test_cancellation_with_nearby_booking_keeps_shared_buffer(self):
        """
        Aug 8 canceled but Aug 22 still booked.
        Aug 15 should stay MAXED (buffer for Aug 22).
        Aug 1 should be removed (no longer needed).
        """
        rows = make_rows([
            (8, 1, "MAXED"),  # Should be removed
            (8, 2, "MAXED"),  # Should be removed
            (8, 8, ""),       # Canceled
            (8, 14, ""),      # Fri before Aug 15
            (8, 15, "MAXED"), # Should stay (buffer for Aug 22)
            (8, 16, "MAXED"), # Should stay (buffer for Aug 22)
            (8, 22, "BOOKED"),# Still booked
            (8, 28, ""),      # Fri after
            (8, 29, ""),      # Sat after - should be added
            (8, 30, ""),      # Sun after - should be added
        ])
        additions, removals, booked = calculate_sync(rows, "2026")

        # Aug 1, 2 should be removals (no booking needs them)
        self.assertIn(date(2026, 8, 1), removals)
        self.assertIn(date(2026, 8, 2), removals)

        # Aug 15, 16 should NOT be removals (Aug 22 needs them)
        self.assertNotIn(date(2026, 8, 15), removals)
        self.assertNotIn(date(2026, 8, 16), removals)

        # Aug 29, 30 should be additions (buffer after Aug 22)
        self.assertIn(date(2026, 8, 29), additions)
        self.assertIn(date(2026, 8, 30), additions)

    def test_monthly_cap_two_bookings(self):
        """Two bookings in a month should MAXED all remaining Fri/Sat/Sun."""
        rows = make_rows([
            (9, 4, ""),        # Fri - should be added (cap)
            (9, 5, ""),        # Sat - should be added (cap)
            (9, 6, ""),        # Sun - should be added (cap)
            (9, 12, "BOOKED"), # Sat - booking 1
            (9, 19, ""),       # Sat - should be added (buffer + cap)
            (9, 26, "BOOKED"), # Sat - booking 2
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 2)
        # All non-booked Fri/Sat/Sun should be additions
        self.assertIn(date(2026, 9, 4), additions)
        self.assertIn(date(2026, 9, 5), additions)
        self.assertIn(date(2026, 9, 19), additions)

    def test_monthly_cap_drops_below_two(self):
        """
        Month had 2 bookings (Sep 12 + Sep 26), all dates MAXED.
        Sep 26 canceled. Only buffer around Sep 12 should remain.
        """
        rows = make_rows([
            (9, 4, "MAXED"),   # Fri - was cap'd. Now buffer for Sep 12: keep
            (9, 5, "MAXED"),   # Sat - buffer for Sep 12: keep
            (9, 6, "MAXED"),   # Sun - buffer for Sep 12: keep
            (9, 12, "BOOKED"), # Sat - still booked
            (9, 18, "MAXED"),  # Fri - buffer for Sep 12: keep
            (9, 19, "MAXED"),  # Sat - buffer for Sep 12: keep
            (9, 20, "MAXED"),  # Sun - buffer for Sep 12: keep
            (9, 25, "MAXED"),  # Fri - no longer needed: remove
            (9, 26, ""),       # Sat - canceled
            (9, 27, "MAXED"),  # Sun - no longer needed: remove
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 1)

        # Buffer dates around Sep 12 should NOT be removals
        self.assertNotIn(date(2026, 9, 5), removals)
        self.assertNotIn(date(2026, 9, 19), removals)

        # Sep 25, 27 should be removals
        self.assertIn(date(2026, 9, 25), removals)
        self.assertIn(date(2026, 9, 27), removals)

    def test_skip_values_not_touched(self):
        """BOOKED/BACKUP/RESERVED dates in buffer zones are never proposed."""
        rows = make_rows([
            (8, 1, "BACKUP"),  # In buffer zone but BACKUP -- skip
            (8, 8, "BOOKED"),  # The booking
            (8, 15, "RESERVED"),  # In buffer zone but RESERVED -- skip
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertNotIn(date(2026, 8, 1), additions)
        self.assertNotIn(date(2026, 8, 15), additions)

    def test_out_dates_never_touched(self):
        """OUT dates are ignored entirely -- not added, not removed."""
        rows = make_rows([
            (8, 7, "OUT"),     # Fri OUT - not touched even in buffer zone
            (8, 8, "BOOKED"),  # The booking
            (8, 9, "OUT"),     # Sun OUT - not touched
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertNotIn(date(2026, 8, 7), additions)
        self.assertNotIn(date(2026, 8, 9), additions)
        self.assertNotIn(date(2026, 8, 7), removals)
        self.assertNotIn(date(2026, 8, 9), removals)

    def test_ok_cell_gets_maxed(self):
        """A cell with OK value in a buffer zone should be proposed as addition."""
        rows = make_rows([
            (8, 1, "OK"),      # In buffer zone, should be added
            (8, 8, "BOOKED"),  # The booking
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertIn(date(2026, 8, 1), additions)

    def test_no_bookings_no_changes(self):
        """No bookings means no additions and no removals (assuming clean matrix)."""
        rows = make_rows([
            (8, 1, ""),
            (8, 8, ""),
            (8, 15, ""),
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 0)
        self.assertEqual(len(additions), 0)
        self.assertEqual(len(removals), 0)

    def test_already_correct_no_changes(self):
        """If matrix already matches rules, no additions or removals."""
        rows = make_rows([
            (8, 1, "MAXED"),   # Correct buffer
            (8, 2, "MAXED"),   # Correct buffer
            (8, 8, "BOOKED"),  # Booking
            (8, 14, "MAXED"),  # Correct buffer (Fri after -- next week)
            (8, 15, "MAXED"),  # Correct buffer
            (8, 16, "MAXED"),  # Correct buffer (Sun after -- next week)
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(additions), 0)
        self.assertEqual(len(removals), 0)


class TestParseMatrixDate(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(parse_matrix_date("Sat 1/18", 2026), date(2026, 1, 18))

    def test_bad_format(self):
        self.assertIsNone(parse_matrix_date("bad", 2026))

    def test_empty(self):
        self.assertIsNone(parse_matrix_date("", 2026))


if __name__ == "__main__":
    unittest.main()
