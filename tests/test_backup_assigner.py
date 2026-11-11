#!/usr/bin/env python3
"""
Backup Assigner's per-date step (process_date), with the dialog, calendar and
Matrix stubbed. Pins today's behaviour before the write moves to the shared
assign_backup() (docs/plans/2026-11-11-one-backup-step.md).
"""

import contextlib
import io
import unittest
from datetime import datetime
from unittest import mock

import backup_assigner
from dj_core import COLUMN_MAPS
from gig_booking_manager import MockSheetsClient

COLS = COLUMN_MAPS[2027]


class TestProcessDate(unittest.TestCase):

    def setUp(self):
        self.clash = []
        self.events = []
        self.warnings = []
        self.choice = "Woody"

        def event(date_obj, dj, test_mode=False, app=None):
            self.events.append(dj)
            return f"[{dj[:2].upper()}] BACKUP DJ"

        stubs = {
            "show_backup_dialog": lambda *a, **k: self.choice,
            "check_calendar_conflicts": lambda d, br: list(self.clash),
            "create_allday_backup_event": event,
            "show_warning_dialog": self.warnings.append,
        }
        for name, fn in stubs.items():
            p = mock.patch(f"backup_assigner.{name}", side_effect=fn)
            p.start()
            self.addCleanup(p.stop)

        self.ba = backup_assigner.BackupAssigner(2027, test_mode=True)
        self.ba.sheets = MockSheetsClient()
        self.ba.booking_details = {}

    def run_date(self, **cells):
        row = {"Henry": "BOOKED", "Woody": "", "Paul": "", "Stefano": "",
               "Stephanie": "", "TBA": "", "AAG": "", "Felipe": ""}
        row.update(cells)
        info = {"date_obj": datetime(2027, 1, 23), "date": "Sat 1/23",
                "selected_data": row, "bold_status": {}, "booked_djs": ["Henry"]}
        with contextlib.redirect_stdout(io.StringIO()):
            return self.ba.process_date(info, 1, 1)

    def writes(self):
        return [(w["col"], w["value"]) for w in self.ba.sheets.writes]

    def test_pick_writes_matrix_and_event(self):
        self.run_date()
        self.assertEqual(self.writes(), [(COLS["Woody"], "BACKUP")])
        self.assertEqual(self.events, ["Woody"])
        self.assertEqual(self.ba.stats["assigned"], 1)

    def test_real_booking_blocks(self):
        self.clash = ["[WM] Smith Wedding"]
        self.run_date()
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.events, [])
        self.assertEqual(len(self.warnings), 1)
        self.assertEqual((self.ba.stats["conflicts"], self.ba.stats["skipped"]), (1, 1))

    @unittest.expectedFailure  # blocked as a conflict today; fixed by Task 5
    def test_hand_made_backup_event_writes_matrix_only(self):
        self.clash = ["[WM] BACKUP"]
        self.run_date()
        self.assertEqual(self.writes(), [(COLS["Woody"], "BACKUP")])
        self.assertEqual(self.events, [])
        self.assertEqual(self.ba.stats["assigned"], 1)

    def test_dad_duty_keeps_its_value(self):
        self.choice = "Felipe"
        self.run_date(Felipe="DAD-DUTY")
        self.assertEqual(self.writes(), [(COLS["Felipe"], "DAD-DUTY, BACKUP")])

    def test_skip_writes_nothing(self):
        self.choice = None
        self.run_date()
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.ba.stats["skipped"], 1)

    def test_stop_returns_stop(self):
        self.choice = "STOP"
        self.assertEqual(self.run_date(), "STOP")
        self.assertEqual(self.writes(), [])


if __name__ == "__main__":
    unittest.main()
