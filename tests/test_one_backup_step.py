#!/usr/bin/env python3
"""
The backup step (calendar check, Matrix BACKUP, all-day event) lives in
gig_booking_manager.assign_backup(). Until 2026-11-11 it was written out three
times (Book Event, Assign DJ, Backup Assigner) and a fix had to be made in each.
This test fails the moment a tool starts doing the step itself again.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = "gig_booking_manager.py"
# Building a compound BACKUP value ("DAD-DUTY, BACKUP") or making the event directly.
STEP = re.compile(r'\}, BACKUP"|create_allday_backup_event\(')


def own_hits(text):
    return [line.strip() for line in text.splitlines()
            if STEP.search(line) and not line.lstrip().startswith(("#", "def "))]


class TestOneBackupStep(unittest.TestCase):

    def test_no_tool_does_the_backup_step_itself(self):
        hits = []
        for path in sorted(ROOT.glob("*.py")):
            if path.name == HOME or path.name.startswith("test_"):
                continue
            hits += [f"{path.name}: {h}" for h in own_hits(path.read_text())]
        self.assertEqual(hits, [], "backup step outside assign_backup():\n" + "\n".join(hits))

    def test_home_builds_the_value_once(self):
        # backup_cell_value only. assign_backup takes the event maker by name.
        hits = own_hits(ROOT.joinpath(HOME).read_text())
        self.assertEqual(hits, ['return f"{v}, BACKUP"'])

    def test_pattern_catches_the_old_copies(self):
        self.assertTrue(own_hits('            new_val = f"{current_val}, BACKUP"'))
        self.assertTrue(own_hits('        title = create_allday_backup_event(date_obj, dj, t)'))
        self.assertFalse(own_hits('def create_allday_backup_event(date_obj, dj_name):'))


if __name__ == "__main__":
    unittest.main()
