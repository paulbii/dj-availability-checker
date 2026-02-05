"""
New test cases for unknown cell value handling.
Add these to test_gig_booking_manager.py.

Tests verify that unrecognized matrix values are treated as unavailable
rather than silently falling through to permissive defaults.
"""


# === Add to TestBackupEligibility class ===

    # --- Unknown values (all DJs) ---
    def test_henry_unknown_value(self):
        ok, note = can_backup("Henry", "VACATION", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_woody_unknown_value(self):
        ok, note = can_backup("Woody", "HOLD", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_paul_unknown_value(self):
        ok, note = can_backup("Paul", "BOKKED", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_stefano_unknown_value(self):
        ok, note = can_backup("Stefano", "PENDING", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_felipe_unknown_value_2026(self):
        ok, note = can_backup("Felipe", "TBD", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_stephanie_unknown_value_2027(self):
        sat_2027 = datetime(2027, 3, 6)
        ok, note = can_backup("Stephanie", "MAYBE", False, sat_2027, 2027)
        self.assertFalse(ok)


# === Add as a new test class (or add to an existing dj_core test file) ===

class TestCheckDjAvailabilityUnknownValues(unittest.TestCase):
    """Verify check_dj_availability rejects unrecognized cell values."""

    SAT = datetime(2026, 6, 6)   # Saturday
    WED = datetime(2026, 6, 3)   # Wednesday

    def test_henry_unknown(self):
        can_book, can_backup = check_dj_availability("Henry", "VACATION", self.SAT, False, "2026")
        self.assertFalse(can_book)
        self.assertFalse(can_backup)

    def test_woody_unknown(self):
        can_book, can_backup = check_dj_availability("Woody", "HOLD", self.SAT, False, "2026")
        self.assertFalse(can_book)
        self.assertFalse(can_backup)

    def test_paul_unknown(self):
        can_book, can_backup = check_dj_availability("Paul", "BOKKED", self.SAT, False, "2026")
        self.assertFalse(can_book)
        self.assertFalse(can_backup)

    def test_stefano_unknown(self):
        can_book, can_backup = check_dj_availability("Stefano", "MAYBE", self.SAT, False, "2026")
        self.assertFalse(can_book)
        self.assertFalse(can_backup)

    def test_felipe_unknown_2026(self):
        can_book, can_backup = check_dj_availability("Felipe", "PENDING", self.SAT, False, "2026")
        self.assertFalse(can_book)
        self.assertFalse(can_backup)

    def test_stephanie_unknown_2027(self):
        sat_2027 = datetime(2027, 3, 6)
        can_book, can_backup = check_dj_availability("Stephanie", "TBD", sat_2027, False, "2027")
        self.assertFalse(can_book)
        self.assertFalse(can_backup)

    def test_typo_booked(self):
        """A misspelling of BOOKED should not be treated as available."""
        can_book, can_backup = check_dj_availability("Paul", "BOOKD", self.SAT, False, "2026")
        self.assertFalse(can_book)
        self.assertFalse(can_backup)

    def test_known_values_still_work(self):
        """Sanity check that recognized values aren't rejected by the guard."""
        # Paul blank on weekend = available
        can_book, can_backup = check_dj_availability("Paul", "", self.SAT, False, "2026")
        self.assertTrue(can_book)
        self.assertTrue(can_backup)

        # Paul OUT = unavailable
        can_book, can_backup = check_dj_availability("Paul", "OUT", self.SAT, False, "2026")
        self.assertFalse(can_book)
        self.assertFalse(can_backup)

        # Felipe OK in 2026 = available
        can_book, can_backup = check_dj_availability("Felipe", "OK", self.SAT, False, "2026")
        self.assertTrue(can_book)
        self.assertTrue(can_backup)
