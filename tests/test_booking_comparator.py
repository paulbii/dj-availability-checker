#!/usr/bin/env python3
"""
Tests for parse_dj_codes in booking_comparator.

Bug being fixed: the calendar title parser only accepted slash-joined DJ
brackets ([WM/HK]). A comma-joined bracket ([PB, WM]) did not match, so the
whole event was skipped and the comparator reported the DJs as missing from
the calendar (9/24/2026 CASA fundraiser, misdiagnosed for six weeks).
"""

import unittest

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
        # icalBuddy date lines never carry a bracket; make sure nothing false-matches
        self.assertIsNone(booking_comparator.parse_dj_codes("09/24 at 3:30 PM - 9:30 PM"))

    def test_long_token_not_a_dj_bracket(self):
        self.assertIsNone(booking_comparator.parse_dj_codes("[SETUP] Something"))


if __name__ == '__main__':
    unittest.main()
