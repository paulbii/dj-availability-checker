#!/usr/bin/env python3
"""
Tests for dj_core.dj_status(): the one place a Matrix cell plus a Gig DB
booking becomes a display status. Every front end paints this record and
nothing else, so a rule change is one edit here.
"""

import unittest
from datetime import date

import dj_core
from dj_core import dj_status, DJStatus


SAT = date(2027, 6, 26)
SUN = date(2027, 6, 27)
WED = date(2027, 6, 30)


class TestGigBooking(unittest.TestCase):

    def test_booked_in_gig_db_wins_over_cell(self):
        s = dj_status("Paul", "BOOKED", SAT, "2027", gig_booking={"venue": "Nestldown"})
        self.assertEqual(s, DJStatus("BOOKED (Nestldown)", "red", False, False, ""))

    def test_booked_in_gig_db_with_blank_cell_warns(self):
        s = dj_status("Paul", "", SAT, "2027", gig_booking={"venue": "Nestldown"})
        self.assertEqual(s.warning, "matrix is blank")
        self.assertEqual(s.kind, "red")

    def test_booked_in_gig_db_with_other_cell_warns(self):
        s = dj_status("Paul", "OK", SAT, "2027", gig_booking={"venue": "Nestldown"})
        self.assertEqual(s.warning, 'matrix shows "OK"')

    def test_booked_in_gig_db_with_wedfaire_cell_does_not_warn(self):
        s = dj_status("Paul", "WEDFAIRE", SAT, "2027", gig_booking={"venue": "Expo"})
        self.assertEqual(s.warning, "")

    def test_setup_primary_is_amber(self):
        gig = {"venue": "Kohl Mansion", "is_setup": True, "role": "primary"}
        s = dj_status("Henry", "SETUP", SAT, "2027", gig_booking=gig)
        self.assertEqual(s.kind, "amber")
        self.assertEqual(s.text, dj_core.setup_status_text(gig))
        self.assertEqual(s.warning, "")

    def test_setup_helper_is_violet_and_warns_on_blank_cell(self):
        gig = {"venue": "Kohl Mansion", "is_setup": True, "role": "helper"}
        s = dj_status("Felipe", "", SAT, "2027", gig_booking=gig)
        self.assertEqual(s.kind, "violet")
        self.assertEqual(s.warning, "matrix is blank")


class TestHardCellStates(unittest.TestCase):

    def test_stefano_blank_is_maybe(self):
        self.assertEqual(dj_status("Stefano", "", SAT, "2027"),
                         DJStatus("[MAYBE]", "yellow", False, False, ""))

    def test_booked_cell_is_red_verbatim(self):
        s = dj_status("Henry", "BOOKED", SAT, "2027")
        self.assertEqual((s.text, s.kind, s.can_book), ("BOOKED", "red", False))

    def test_aag_cell_is_red(self):
        s = dj_status("Stephanie", "AAG", SAT, "2027")
        self.assertEqual((s.text, s.kind), ("AAG", "red"))

    def test_stanford_is_red(self):
        self.assertEqual(dj_status("Henry", "STANFORD", SAT, "2027").kind, "red")

    def test_reserved_is_red(self):
        s = dj_status("Stephanie", "RESERVED", SAT, "2027")
        self.assertEqual((s.text, s.kind), ("RESERVED", "red"))

    def test_wedfaire_is_red(self):
        self.assertEqual(dj_status("Paul", "WEDFAIRE", SAT, "2027").kind, "red")

    def test_setup_cell_without_gig_is_amber(self):
        self.assertEqual(dj_status("Paul", "SETUP", SAT, "2027").kind, "amber")

    def test_backup_cell_is_blue_verbatim(self):
        s = dj_status("Woody", "BACKUP", SAT, "2027")
        self.assertEqual((s.text, s.kind), ("BACKUP", "blue"))

    def test_felipe_blank_2027_is_backup(self):
        s = dj_status("Felipe", "", SAT, "2027")
        self.assertEqual(s, DJStatus("[BLANK] - can backup", "blue", False, True, ""))

    def test_last_is_green_low_priority(self):
        s = dj_status("Paul", "LAST", SAT, "2027")
        self.assertEqual((s.text, s.kind, s.can_book), ("LAST - available (low priority)", "green", True))

    def test_unknown_value_is_warn(self):
        s = dj_status("Paul", "VACAY", SAT, "2027")
        self.assertEqual(s.kind, "warn")
        self.assertIn("unknown status", s.text)
        self.assertEqual((s.can_book, s.can_backup), (False, False))


class TestComputedStates(unittest.TestCase):

    def test_blank_available_has_no_value_prefix(self):
        s = dj_status("Henry", "", SAT, "2027")
        self.assertEqual(s, DJStatus("available", "green", True, True, ""))

    def test_ok_available_keeps_value(self):
        s = dj_status("Stephanie", "OK", SAT, "2027")
        self.assertEqual((s.text, s.kind, s.can_book), ("OK - available", "green", True))

    def test_nearby_bookings_are_appended(self):
        s = dj_status("Paul", "", SAT, "2027", nearby_bookings=["6/25 Nestldown", "6/27 Kohl"])
        self.assertEqual(s.text, "available (booked: 6/25 Nestldown, 6/27 Kohl)")

    def test_henry_weekday_blank_is_backup_with_reason(self):
        s = dj_status("Henry", "", WED, "2027")
        self.assertEqual(s, DJStatus("can backup (weekday)", "blue", False, True, ""))

    def test_woody_plain_out_on_weekend_is_backup_with_reason(self):
        s = dj_status("Woody", "OUT", SAT, "2027")
        self.assertEqual(s, DJStatus("OUT - can backup (weekend)", "blue", False, True, ""))

    def test_woody_bold_out_on_weekend_is_dead_end(self):
        s = dj_status("Woody", "OUT (BOLD)", SAT, "2027")
        self.assertEqual(s, DJStatus("OUT (BOLD)", "dim", False, False, ""))

    def test_paul_out_is_dead_end(self):
        self.assertEqual(dj_status("Paul", "OUT", SAT, "2027"),
                         DJStatus("OUT", "dim", False, False, ""))

    def test_stefano_maxed_is_dead_end(self):
        self.assertEqual(dj_status("Stefano", "MAXED", SAT, "2027").kind, "dim")

    def test_stephanie_blank_2027_is_not_available(self):
        s = dj_status("Stephanie", "", SAT, "2027")
        self.assertEqual(s, DJStatus("not available (2027)", "dim", False, False, ""))

    def test_stephanie_blank_2026_is_not_available(self):
        s = dj_status("Stephanie", "", date(2026, 10, 24), "2026")
        self.assertEqual(s.text, "not available (2026)")

    def test_stephanie_blank_weekday_2027_is_not_available(self):
        self.assertEqual(dj_status("Stephanie", "", WED, "2027").text, "not available (2027)")

    def test_stephanie_out_2027_is_dead_end(self):
        self.assertEqual(dj_status("Stephanie", "OUT", SAT, "2027"),
                         DJStatus("OUT", "dim", False, False, ""))

    def test_felipe_ok_2027_is_available(self):
        self.assertEqual(dj_status("Felipe", "OK", SAT, "2027").can_book, True)

    def test_felipe_dad_2027_is_backup(self):
        s = dj_status("Felipe", "DAD", SAT, "2027")
        self.assertEqual(s, DJStatus("DAD - can backup", "blue", False, True, ""))


if __name__ == "__main__":
    unittest.main()
