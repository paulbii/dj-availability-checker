#!/usr/bin/env python3
"""
Tests for check_dj_availability (dj_core), Stephanie's year rules.

Rule change 2026-10-17 (Paul): for 2027, Stephanie is unavailable on every date
except the ones she has specifically said yes to, until she tells us otherwise.
A blank cell in her 2027 column therefore means NOT available, the same as the
2026 rule. She says yes by putting OK in the cell.
"""

import unittest
from datetime import date

import dj_core


SATURDAY_2027 = date(2027, 6, 26)
SUNDAY_2027 = date(2027, 6, 27)
WEDNESDAY_2027 = date(2027, 6, 30)


class TestStephanie2027(unittest.TestCase):

    def test_blank_saturday_2027_is_not_available(self):
        can_book, can_backup = dj_core.check_dj_availability(
            "Stephanie", "", SATURDAY_2027, year="2027")
        self.assertEqual((can_book, can_backup), (False, False))

    def test_blank_sunday_2027_is_not_available(self):
        can_book, can_backup = dj_core.check_dj_availability(
            "Stephanie", "", SUNDAY_2027, year="2027")
        self.assertEqual((can_book, can_backup), (False, False))

    def test_blank_weekday_2027_is_not_available(self):
        can_book, can_backup = dj_core.check_dj_availability(
            "Stephanie", "", WEDNESDAY_2027, year="2027")
        self.assertEqual((can_book, can_backup), (False, False))

    def test_ok_saturday_2027_is_available(self):
        can_book, can_backup = dj_core.check_dj_availability(
            "Stephanie", "OK", SATURDAY_2027, year="2027")
        self.assertEqual((can_book, can_backup), (True, True))

    def test_out_saturday_2027_is_not_available(self):
        can_book, can_backup = dj_core.check_dj_availability(
            "Stephanie", "OUT", SATURDAY_2027, year="2027")
        self.assertEqual((can_book, can_backup), (False, False))

    def test_blank_saturday_2026_still_not_available(self):
        can_book, can_backup = dj_core.check_dj_availability(
            "Stephanie", "", date(2026, 10, 24), year="2026")
        self.assertEqual((can_book, can_backup), (False, False))


if __name__ == "__main__":
    unittest.main()
