#!/usr/bin/env python3
"""gig_booking_manager.assign_backup: the one backup step all three tools call."""

import unittest
from datetime import datetime

from dj_core import COLUMN_MAPS
from gig_booking_manager import MockSheetsClient, assign_backup, backup_candidates

COLS = COLUMN_MAPS[2027]
DAY = datetime(2027, 1, 23)


class TestAssignBackup(unittest.TestCase):

    def setUp(self):
        self.sheets = MockSheetsClient()
        self.log, self.warnings, self.events = [], [], []

    def run_step(self, clash=(), row=None, event_error=None, check_error=None):
        def conflicts(d, br):
            if check_error:
                raise check_error
            return list(clash)

        def make_event(d, dj, test_mode=False):
            if event_error:
                raise event_error
            self.events.append(dj)
            return "[WM] BACKUP DJ"

        return assign_backup("Woody", DAY, "Sat 1/23", self.sheets, 5, COLS, row or {"Woody": "OUT"},
                             2027, log=self.log.append, warn=self.warnings.append,
                             conflicts=conflicts, make_backup_event=make_event)

    def writes(self):
        return [(w["col"], w["value"]) for w in self.sheets.writes]

    def test_assigned(self):
        self.assertEqual(self.run_step()[0], "assigned")
        self.assertEqual(self.writes(), [(COLS["Woody"], "BACKUP")])
        self.assertEqual(self.events, ["Woody"])

    def test_already_on_calendar(self):
        self.assertEqual(self.run_step(clash=["[WM] BACKUP"])[0], "already_on_calendar")
        self.assertEqual(self.writes(), [(COLS["Woody"], "BACKUP")])
        self.assertEqual(self.events, [])
        self.assertEqual(self.warnings, [])

    def test_conflict(self):
        self.assertEqual(self.run_step(clash=["[WM] Smith"])[0], "conflict")
        self.assertEqual((self.writes(), self.events, len(self.warnings)), ([], [], 1))

    def test_check_failed_writes_nothing(self):
        self.assertEqual(self.run_step(check_error=RuntimeError("CalDAV down"))[0], "check_failed")
        self.assertEqual((self.writes(), self.events, len(self.warnings)), ([], [], 1))

    def test_event_failed_after_matrix(self):
        self.assertEqual(self.run_step(event_error=RuntimeError("osascript"))[0], "event_failed")
        self.assertEqual(self.writes(), [(COLS["Woody"], "BACKUP")])
        self.assertIn("by hand", self.warnings[0])

    def test_compound_cell_keeps_value(self):
        self.run_step(row={"Woody": "DAD-DUTY"})
        self.assertEqual(self.writes(), [(COLS["Woody"], "DAD-DUTY, BACKUP")])


class TestBackupCandidates(unittest.TestCase):

    def test_excludes_every_booked_dj(self):
        row = {dj: "" for dj in COLS}
        names = [c for c, _ in backup_candidates(row, ["Henry", "Paul"], 2027, DAY, COLS,
                                                 bold_lookup=lambda dj: False)]
        self.assertNotIn("Henry", names)
        self.assertNotIn("Paul", names)
        self.assertIn("Woody", names)


if __name__ == "__main__":
    unittest.main()
