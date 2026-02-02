#!/usr/bin/env python3
"""
HARD GATE TEST — Column Map Consistency
========================================
This test MUST pass before Phase 2 (rewiring gig_booking_manager.py).

It verifies that dj_core's letter-based column definitions (COLUMNS_2025,
COLUMNS_2026, COLUMNS_2027) produce the same 1-indexed column numbers as
the booking manager's hardcoded COLUMN_MAPS.

If this fails, the merge is UNSAFE — column misalignment would cause the
booking manager to write BOOKED/BACKUP to the wrong DJ column.
"""

import unittest


def get_column_number_map(columns_dict):
    """
    Convert dj_core's letter-based column dict to 1-indexed number map.
    
    Input:  {"A": "Date", "D": "Henry", "E": "Woody", ...}
    Output: {"Date": 1, "Henry": 4, "Woody": 5, ...}
    """
    return {name: ord(letter) - ord('A') + 1 for letter, name in columns_dict.items()}


class TestColumnMapGate(unittest.TestCase):
    """
    APPROVAL CONDITION: This test must pass before Phase 2 proceeds.
    Hardcoded expected values from the booking manager's COLUMN_MAPS.
    """

    def test_2025_column_map(self):
        from dj_core import COLUMNS_2025
        derived = get_column_number_map(COLUMNS_2025)
        expected = {
            "Date": 1, "Henry": 4, "Woody": 5, "Paul": 6,
            "Stefano": 7, "Felipe": 8, "TBA": 9, "Stephanie": 11,
        }
        self.assertEqual(derived, expected,
                         f"2025 column map mismatch!\nDerived:  {derived}\nExpected: {expected}")

    def test_2026_column_map(self):
        from dj_core import COLUMNS_2026
        derived = get_column_number_map(COLUMNS_2026)
        expected = {
            "Date": 1, "Henry": 4, "Woody": 5, "Paul": 6,
            "Stefano": 7, "Felipe": 8, "TBA": 9, "Stephanie": 11, "AAG": 12,
        }
        self.assertEqual(derived, expected,
                         f"2026 column map mismatch!\nDerived:  {derived}\nExpected: {expected}")

    def test_2027_column_map(self):
        from dj_core import COLUMNS_2027
        derived = get_column_number_map(COLUMNS_2027)
        expected = {
            "Date": 1, "Henry": 4, "Woody": 5, "Paul": 6,
            "Stefano": 7, "Stephanie": 8, "TBA": 9, "AAG": 10, "Felipe": 12,
        }
        self.assertEqual(derived, expected,
                         f"2027 column map mismatch!\nDerived:  {derived}\nExpected: {expected}")


if __name__ == "__main__":
    unittest.main()
