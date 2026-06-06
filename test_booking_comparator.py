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


if __name__ == "__main__":
    unittest.main()
