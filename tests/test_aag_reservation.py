#!/usr/bin/env python3
"""
AAG reservations (Paul, 2026-11-11): RESERVED in a DJ's column plus names in
the AAG couple column means that DJ is reserved for an Allied Arts Guild
wedding Tiana has not handed off yet. RESERVED with no couple is an ordinary
hold. RESERVED in the AAG column is Tiana holding the date (no DJ yet).
"""

import unittest
from datetime import date

from dj_core import (DJStatus, aag_column_text, aag_couple_from_row, aag_reserved_dj,
                     dj_status, is_reserved_label, reserved_label)

SAT = date(2027, 3, 27)
ROW_2027 = ["Sat 3/27", "", "", "", "OUT", "", "RESERVED", "", "", "", "Coleen and Keigo", ""]


class TestAagCoupleColumn(unittest.TestCase):

    def test_reads_column_k_in_2027(self):
        self.assertEqual(aag_couple_from_row(ROW_2027, "2027"), "Coleen and Keigo")
        self.assertEqual(aag_couple_from_row(ROW_2027, 2027), "Coleen and Keigo")

    def test_short_row_and_other_years_are_blank(self):
        self.assertEqual(aag_couple_from_row(ROW_2027[:5], "2027"), "")
        self.assertEqual(aag_couple_from_row(ROW_2027, "2026"), "")


class TestAagReservedDj(unittest.TestCase):

    def test_dj_reserved_with_couple(self):
        sd = {"Henry": "", "Stefano": "RESERVED", "AAG": ""}
        self.assertEqual(aag_reserved_dj(sd, "Coleen and Keigo"), "Stefano")

    def test_reserved_without_couple_is_an_ordinary_hold(self):
        self.assertIsNone(aag_reserved_dj({"Henry": "RESERVED", "AAG": ""}, ""))

    def test_old_style_aag_column_names_no_dj(self):
        sd = {"Henry": "", "Stefano": "OUT", "AAG": "RESERVED"}
        self.assertIsNone(aag_reserved_dj(sd, "Brian and Ariana"))

    def test_bold_marker_ignored(self):
        self.assertEqual(aag_reserved_dj({"Paul": "RESERVED (BOLD)"}, "Kelly and Ryan"), "Paul")


class TestDisplay(unittest.TestCase):

    def test_status_names_the_couple(self):
        s = dj_status("Stefano", "RESERVED", SAT, "2027", aag_couple="Coleen and Keigo")
        self.assertEqual(s, DJStatus("RESERVED (AAG: Coleen and Keigo)", "red", False, False))

    def test_status_plain_hold_unchanged(self):
        self.assertEqual(dj_status("Henry", "RESERVED", SAT, "2027").text, "RESERVED")

    def test_couple_only_labels_the_reserved_dj(self):
        s = dj_status("Henry", "", SAT, "2027", aag_couple="Coleen and Keigo")
        self.assertNotIn("AAG", s.text)

    def test_reserved_label(self):
        self.assertEqual(reserved_label("Stefano", "Coleen and Keigo"),
                         "Stefano (RESERVED, AAG: Coleen and Keigo)")
        self.assertEqual(reserved_label("Henry", ""), "Henry (RESERVED)")

    def test_is_reserved_label_reads_both_forms(self):
        # booking_comparator skips these; missing the AAG form would report every
        # AAG reservation as a booking with no calendar event.
        self.assertTrue(is_reserved_label(reserved_label("Stefano", "Coleen and Keigo")))
        self.assertTrue(is_reserved_label(reserved_label("Henry")))
        self.assertFalse(is_reserved_label("Henry"))

    def test_aag_column_names_tianas_couple_when_no_dj_holds_it(self):
        sd = {"Stefano": "OUT", "AAG": "RESERVED"}
        self.assertEqual(aag_column_text("RESERVED", sd, "Brian and Ariana"),
                         "RESERVED (Brian and Ariana)")

    def test_aag_column_plain_when_a_dj_holds_the_couple(self):
        sd = {"Stefano": "RESERVED", "AAG": ""}
        self.assertEqual(aag_column_text("", sd, "Coleen and Keigo"), "")
        self.assertEqual(aag_column_text("RESERVED", {"AAG": "RESERVED"}, ""), "RESERVED")


if __name__ == "__main__":
    unittest.main()
