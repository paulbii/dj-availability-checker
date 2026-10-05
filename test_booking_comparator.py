#!/usr/bin/env python3
"""
Tests for booking_comparator.py DJ2 (assigned_roadie_or_dj2) handling.

Covers:
  - parse_gig_db_records: DJ1 always kept; DJ2 kept only when it maps to a
    rostered DJ (allowlist), with the middle-initial name form ("Henry S. Kim").
  - compare_systems explain-not-demand: a gig-db DJ2 person counts toward the
    gig-db set for a date ONLY when that DJ is also in the availability matrix
    for the date. A DJ2 person absent from the matrix is a roadie -> ignored,
    so an owner/DJ who roadies never produces a false mismatch.
"""

import io
import unittest

from booking_comparator import parse_gig_db_records, compare_systems


def _report(gig_db, gig_secondary, matrix, cal=None):
    buf = io.StringIO()
    compare_systems(gig_db, matrix, master_cal=cal,
                    gig_secondary=gig_secondary, output=buf)
    return buf.getvalue()


class TestParseGigDbRecords(unittest.TestCase):
    def test_codj_in_dj2_is_kept_as_secondary(self):
        records = [{
            "event_date": "2026-01-25",
            "assigned_dj": "Woody Miraglia",
            "assigned_roadie_or_dj2": "Henry S. Kim",
            "event_type": "Other",
        }]
        primary, secondary = parse_gig_db_records(records)
        self.assertEqual(primary["1/25"], ["Woody"])
        self.assertEqual(secondary["1/25"], ["Henry"])

    def test_roadie_in_dj2_is_dropped(self):
        records = [{
            "event_date": "2026-03-01",
            "assigned_dj": "Woody Miraglia",
            "assigned_roadie_or_dj2": "Ryan Roadie",  # not on the roster
        }]
        primary, secondary = parse_gig_db_records(records)
        self.assertEqual(primary["3/1"], ["Woody"])
        self.assertNotIn("3/1", secondary)

    def test_empty_dj2_yields_no_secondary(self):
        records = [{
            "event_date": "2026-02-02",
            "assigned_dj": "Woody Miraglia",
            "assigned_roadie_or_dj2": "",
            "event_type": "Setup",
        }]
        primary, secondary = parse_gig_db_records(records)
        self.assertEqual(primary["2/2"], ["Woody"])
        self.assertNotIn("2/2", secondary)

    def test_missing_dj2_key_is_safe(self):
        records = [{"event_date": "2026-04-04", "assigned_dj": "Paul Burchfield"}]
        primary, secondary = parse_gig_db_records(records)
        self.assertEqual(primary["4/4"], ["Paul"])
        self.assertNotIn("4/4", secondary)


class TestExplainNotDemand(unittest.TestCase):
    def test_codj_confirmed_by_matrix_is_in_sync(self):
        # 1/25: Woody (DJ1) + Henry (DJ2), both in matrix and calendar.
        out = _report(
            gig_db={"1/25": ["Woody"]},
            gig_secondary={"1/25": ["Henry"]},
            matrix={"1/25": ["Henry", "Woody"]},
            cal={"1/25": ["Henry", "Woody"]},
        )
        self.assertIn("ALL SYSTEMS IN SYNC", out)

    def test_owner_roadie_not_in_matrix_is_ignored(self):
        # Henry sits in DJ2 as a roadie: not in the matrix -> must not flag.
        out = _report(
            gig_db={"3/1": ["Woody"]},
            gig_secondary={"3/1": ["Henry"]},
            matrix={"3/1": ["Woody"]},
            cal={"3/1": ["Woody"]},
        )
        self.assertIn("ALL SYSTEMS IN SYNC", out)

    def test_codj_missing_from_matrix_still_flags(self):
        # Real error: DJ2 co-DJ is on the calendar but missing from the matrix.
        # Explain-not-demand drops him from the gig-db side (not in matrix), so
        # the calendar's extra surfaces as a discrepancy worth investigating.
        out = _report(
            gig_db={"5/5": ["Woody"]},
            gig_secondary={"5/5": ["Henry"]},
            matrix={"5/5": ["Woody"]},
            cal={"5/5": ["Henry", "Woody"]},
        )
        self.assertNotIn("ALL SYSTEMS IN SYNC", out)


def _report_with_backups(gig_db, gig_secondary, matrix, cal, matrix_backups):
    buf = io.StringIO()
    compare_systems(gig_db, matrix, master_cal=cal, matrix_backups=matrix_backups,
                    cal_backups=matrix_backups, gig_secondary=gig_secondary,
                    output=buf)
    return buf.getvalue()


class TestHelperOnCalendar(unittest.TestCase):
    """A DJ2 helper (setup/teardown) goes on the calendar title so the time is
    blocked, but is not BOOKED in the matrix. Explained when the matrix holds
    their day (BACKUP); still flagged when the matrix shows them free."""

    def test_helper_blocked_as_backup_is_in_sync(self):
        # 9/24/2026 CASA: Paul DJ1, Woody DJ2 helping, "[PB, WM]" on the
        # calendar, Woody BACKUP in the matrix.
        out = _report_with_backups(
            gig_db={"9/24": ["Henry", "Paul"]},
            gig_secondary={"9/24": ["Woody"]},
            matrix={"9/24": ["Henry", "Paul"]},
            cal={"9/24": ["Henry", "Paul", "Woody"]},
            matrix_backups={"9/24": ["Woody"]},
        )
        self.assertIn("ALL SYSTEMS IN SYNC", out)

    def test_helper_free_in_matrix_still_flags(self):
        # Same shape, but the matrix shows Woody free that day: he could be
        # booked elsewhere, so it must still surface.
        out = _report_with_backups(
            gig_db={"9/24": ["Henry", "Paul"]},
            gig_secondary={"9/24": ["Woody"]},
            matrix={"9/24": ["Henry", "Paul"]},
            cal={"9/24": ["Henry", "Paul", "Woody"]},
            matrix_backups={},
        )
        self.assertIn("DJ ASSIGNMENT MISMATCHES", out)

    def test_backup_not_in_dj2_still_flags(self):
        # Woody is backup but NOT the DJ2 on the gig db: a calendar title
        # naming him is unexplained.
        out = _report_with_backups(
            gig_db={"9/24": ["Paul"]},
            gig_secondary={},
            matrix={"9/24": ["Paul"]},
            cal={"9/24": ["Paul", "Woody"]},
            matrix_backups={"9/24": ["Woody"]},
        )
        self.assertIn("DJ ASSIGNMENT MISMATCHES", out)

    def test_other_mismatch_on_date_still_shows_helper_on_cal_line(self):
        # The helper is explained, but the date has a real problem too; the
        # Cal line must show what the calendar actually says.
        out = _report_with_backups(
            gig_db={"9/24": ["Henry", "Paul"]},
            gig_secondary={"9/24": ["Woody"]},
            matrix={"9/24": ["Paul"]},
            cal={"9/24": ["Henry", "Paul", "Woody"]},
            matrix_backups={"9/24": ["Woody"]},
        )
        self.assertIn("Cal:     Henry, Paul, Woody", out)


if __name__ == "__main__":
    unittest.main()
