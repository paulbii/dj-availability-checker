#!/usr/bin/env python3
"""
Unit tests for gig_booking_manager.py

Run with:
  python3 test_gig_booking_manager.py
  python3 -m pytest test_gig_booking_manager.py -v

Tests all business logic (parsing, rules, time calculations) without
requiring Google Sheets or Calendar access.
"""

import unittest
import json
import os
import tempfile
from datetime import datetime

from gig_booking_manager import (
    # Utility functions
    get_dj_short_name,
    get_dj_initials,
    get_unassigned_initials,
    is_weekend,
    date_to_sheet_format,
    extract_client_first_names,
    parse_tba_value,
    increment_tba,
    # Parsing
    parse_booking_data,
    # Time calculations
    calculate_arrival_offset,
    convert_times_to_24h,
    calculate_event_times,
    # DJ rules
    can_backup,
    is_paid_backup,
    get_backup_title,
    calculate_spots_remaining,
    check_existing_backup,
    # Mock client
    MockSheetsClient,
    GigBookingManager,
    COLUMN_MAPS,
)


# =============================================================================
# DJ Name Mapping Tests
# =============================================================================

class TestDJNameMapping(unittest.TestCase):
    """Test mapping FileMaker full names to short names."""

    def test_standard_names(self):
        self.assertEqual(get_dj_short_name("Paul Burchfield"), "Paul")
        self.assertEqual(get_dj_short_name("Henry S. Kim"), "Henry")
        self.assertEqual(get_dj_short_name("Woody Miraglia"), "Woody")
        self.assertEqual(get_dj_short_name("Stefano Bortolin"), "Stefano")
        self.assertEqual(get_dj_short_name("Felipe Silva"), "Felipe")
        self.assertEqual(get_dj_short_name("Stephanie de Jesus"), "Stephanie")

    def test_unassigned(self):
        self.assertEqual(get_dj_short_name("Unassigned"), "Unassigned")
        self.assertEqual(get_dj_short_name("unassigned"), "Unassigned")

    def test_empty_or_missing(self):
        self.assertEqual(get_dj_short_name(""), "Unknown")
        self.assertEqual(get_dj_short_name(None), "Unknown")
        self.assertEqual(get_dj_short_name("  "), "Unknown")

    def test_unknown_name(self):
        self.assertEqual(get_dj_short_name("John Smith"), "Unknown")

    def test_initials(self):
        self.assertEqual(get_dj_initials("Henry"), "HK")
        self.assertEqual(get_dj_initials("Woody"), "WM")
        self.assertEqual(get_dj_initials("Paul"), "PB")
        self.assertEqual(get_dj_initials("Stefano"), "SB")
        self.assertEqual(get_dj_initials("Felipe"), "FS")
        self.assertEqual(get_dj_initials("Stephanie"), "SD")
        self.assertEqual(get_dj_initials("Unknown"), "UP")

    def test_unassigned_initials(self):
        self.assertEqual(get_unassigned_initials("Paul Burchfield"), "UP")
        self.assertEqual(get_unassigned_initials("Henry S. Kim"), "UH")
        self.assertEqual(get_unassigned_initials(""), "UP")
        self.assertEqual(get_unassigned_initials(None), "UP")


# =============================================================================
# Date Utility Tests
# =============================================================================

class TestDateUtilities(unittest.TestCase):
    """Test date-related utility functions."""

    def test_is_weekend(self):
        self.assertTrue(is_weekend(datetime(2026, 2, 21)))   # Saturday
        self.assertTrue(is_weekend(datetime(2026, 2, 22)))   # Sunday
        self.assertFalse(is_weekend(datetime(2026, 2, 23)))  # Monday
        self.assertFalse(is_weekend(datetime(2026, 2, 20)))  # Friday

    def test_date_to_sheet_format(self):
        self.assertEqual(date_to_sheet_format(datetime(2026, 2, 21)), "Sat 2/21")
        self.assertEqual(date_to_sheet_format(datetime(2026, 1, 3)), "Sat 1/3")
        self.assertEqual(date_to_sheet_format(datetime(2026, 12, 25)), "Fri 12/25")
        self.assertEqual(date_to_sheet_format(datetime(2026, 10, 10)), "Sat 10/10")


# =============================================================================
# Client Name Tests
# =============================================================================

class TestClientNameExtraction(unittest.TestCase):
    """Test extracting first names for calendar titles."""

    def test_couple(self):
        self.assertEqual(
            extract_client_first_names("Catherine MacDougall and Jacob Asmuth"),
            "Catherine and Jacob"
        )
        self.assertEqual(
            extract_client_first_names("Anya Hee and Hilal Ahmad"),
            "Anya and Hilal"
        )

    def test_non_couple(self):
        self.assertEqual(
            extract_client_first_names("Bird Family Seder"),
            "Bird Family Seder"
        )
        self.assertEqual(
            extract_client_first_names("HCF Volunteer Summit"),
            "HCF Volunteer Summit"
        )

    def test_edge_case_and_in_name(self):
        # "Tom and Jerry" — both sides have 1 word, not treated as couple
        self.assertEqual(
            extract_client_first_names("Tom and Jerry"),
            "Tom and Jerry"
        )

    def test_no_and(self):
        self.assertEqual(
            extract_client_first_names("Johnson Wedding"),
            "Johnson Wedding"
        )


# =============================================================================
# TBA Parsing & Increment Tests
# =============================================================================

class TestTBAParsing(unittest.TestCase):
    """Test TBA column value parsing and incrementing."""

    def test_parse_empty(self):
        self.assertEqual(parse_tba_value(""), 0)
        self.assertEqual(parse_tba_value(None), 0)

    def test_parse_booked(self):
        self.assertEqual(parse_tba_value("BOOKED"), 1)

    def test_parse_booked_x_n(self):
        self.assertEqual(parse_tba_value("BOOKED x 2"), 2)
        self.assertEqual(parse_tba_value("BOOKED x 3"), 3)

    def test_parse_aag(self):
        self.assertEqual(parse_tba_value("AAG"), 1)

    def test_parse_combined(self):
        self.assertEqual(parse_tba_value("BOOKED, AAG"), 2)
        self.assertEqual(parse_tba_value("BOOKED x 2, AAG"), 3)

    def test_increment_empty(self):
        self.assertEqual(increment_tba(""), "BOOKED")
        self.assertEqual(increment_tba(None), "BOOKED")

    def test_increment_booked(self):
        self.assertEqual(increment_tba("BOOKED"), "BOOKED x 2")

    def test_increment_booked_x_2(self):
        self.assertEqual(increment_tba("BOOKED x 2"), "BOOKED x 3")

    def test_increment_aag_only(self):
        self.assertEqual(increment_tba("AAG"), "BOOKED, AAG")

    def test_increment_booked_aag(self):
        self.assertEqual(increment_tba("BOOKED, AAG"), "BOOKED x 2, AAG")


# =============================================================================
# Time Calculation Tests
# =============================================================================

class TestTimeCalculations(unittest.TestCase):
    """Test arrival offset and 12-hour to 24-hour time conversion."""

    def test_arrival_quad(self):
        self.assertEqual(calculate_arrival_offset("Quad Speakers", False), 120)
        self.assertEqual(calculate_arrival_offset("Quad + Side + Sub", True), 120)

    def test_arrival_no_main_sound(self):
        self.assertEqual(calculate_arrival_offset("No Main Sound", False), 60)
        self.assertEqual(calculate_arrival_offset("No Main Sound", True), 90)

    def test_arrival_standard(self):
        self.assertEqual(calculate_arrival_offset("Standard Speakers", False), 90)
        self.assertEqual(calculate_arrival_offset("Standard Speakers", True), 120)
        self.assertEqual(calculate_arrival_offset("Standard + Sub", False), 90)
        self.assertEqual(calculate_arrival_offset("Corporate Setup", True), 120)

    def test_12h_to_24h_both_pm(self):
        # 4:00 - 10:00 → 4pm - 10pm → (16,0), (22,0)
        start, end = convert_times_to_24h("4:00", "10:00")
        self.assertEqual(start, (16, 0))
        self.assertEqual(end, (22, 0))

    def test_12h_to_24h_crosses_noon(self):
        # 9:00 - 3:00 → 9am - 3pm → (9,0), (15,0)
        start, end = convert_times_to_24h("9:00", "3:00")
        self.assertEqual(start, (9, 0))
        self.assertEqual(end, (15, 0))

    def test_12h_to_24h_noon_boundary(self):
        # 9:30 - 12:30 → 9:30am - 12:30pm → (9,30), (12,30)
        start, end = convert_times_to_24h("9:30", "12:30")
        self.assertEqual(start, (9, 30))
        self.assertEqual(end, (12, 30))

    def test_12h_to_24h_midnight_cap(self):
        # 5:00 - 12:00 → 5pm - midnight → (17,0), (23,59)
        start, end = convert_times_to_24h("5:00", "12:00")
        self.assertEqual(start, (17, 0))
        self.assertEqual(end, (23, 59))

    def test_event_times_standard_evening(self):
        booking = {
            "date": datetime(2026, 2, 21),
            "start_time": "4:00",
            "end_time": "10:00",
            "sound_type": "Standard Speakers",
            "has_ceremony": False,
        }
        cal_start, cal_end = calculate_event_times(booking)
        # 4pm - 90min arrival = 2:30pm
        self.assertEqual(cal_start.hour, 14)
        self.assertEqual(cal_start.minute, 30)
        # 10pm + 60min teardown = 11pm
        self.assertEqual(cal_end.hour, 23)
        self.assertEqual(cal_end.minute, 0)

    def test_event_times_ceremony(self):
        booking = {
            "date": datetime(2026, 2, 21),
            "start_time": "4:00",
            "end_time": "10:00",
            "sound_type": "Standard Speakers",
            "has_ceremony": True,
        }
        cal_start, cal_end = calculate_event_times(booking)
        # 4pm - 120min arrival = 2pm
        self.assertEqual(cal_start.hour, 14)
        self.assertEqual(cal_start.minute, 0)

    def test_event_times_midnight_cap(self):
        booking = {
            "date": datetime(2026, 2, 21),
            "start_time": "5:00",
            "end_time": "11:00",
            "sound_type": "Standard Speakers",
            "has_ceremony": False,
        }
        cal_start, cal_end = calculate_event_times(booking)
        # 11pm + 60min = midnight → capped at 11:59pm
        self.assertEqual(cal_end.hour, 23)
        self.assertEqual(cal_end.minute, 59)


# =============================================================================
# Backup Eligibility Tests
# =============================================================================

class TestBackupEligibility(unittest.TestCase):
    """Test DJ backup eligibility rules for each DJ and scenario."""

    SAT = datetime(2026, 2, 21)   # Saturday
    WED = datetime(2026, 2, 18)   # Wednesday

    # --- Henry ---
    def test_henry_blank_weekend(self):
        ok, note = can_backup("Henry", "", False, self.SAT, 2026)
        self.assertTrue(ok)

    def test_henry_blank_weekday(self):
        ok, note = can_backup("Henry", "", False, self.WED, 2026)
        self.assertTrue(ok)

    def test_henry_out(self):
        ok, note = can_backup("Henry", "OUT", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_henry_booked(self):
        ok, note = can_backup("Henry", "BOOKED", False, self.SAT, 2026)
        self.assertFalse(ok)

    # --- Woody ---
    def test_woody_blank(self):
        ok, note = can_backup("Woody", "", False, self.SAT, 2026)
        self.assertTrue(ok)

    def test_woody_plain_out_weekend(self):
        ok, note = can_backup("Woody", "OUT", False, self.SAT, 2026)
        self.assertTrue(ok)

    def test_woody_bold_out_weekend(self):
        ok, note = can_backup("Woody", "OUT", True, self.SAT, 2026)
        self.assertFalse(ok)

    def test_woody_out_weekday(self):
        ok, note = can_backup("Woody", "OUT", False, self.WED, 2026)
        self.assertFalse(ok)

    def test_woody_booked(self):
        ok, note = can_backup("Woody", "BOOKED", False, self.SAT, 2026)
        self.assertFalse(ok)

    # --- Paul ---
    def test_paul_blank(self):
        ok, note = can_backup("Paul", "", False, self.SAT, 2026)
        self.assertTrue(ok)

    def test_paul_out(self):
        ok, note = can_backup("Paul", "OUT", False, self.SAT, 2026)
        self.assertFalse(ok)

    # --- Stefano ---
    def test_stefano_blank(self):
        ok, note = can_backup("Stefano", "", False, self.SAT, 2026)
        self.assertTrue(ok)
        self.assertEqual(note, "check with Stefano")

    def test_stefano_out(self):
        ok, note = can_backup("Stefano", "OUT", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_stefano_booked(self):
        ok, note = can_backup("Stefano", "BOOKED", False, self.SAT, 2026)
        self.assertFalse(ok)

    # --- Felipe (2026+) ---
    def test_felipe_blank_2026(self):
        ok, note = can_backup("Felipe", "", False, self.SAT, 2026)
        self.assertTrue(ok)

    def test_felipe_ok_2026(self):
        ok, note = can_backup("Felipe", "OK", False, self.SAT, 2026)
        self.assertTrue(ok)

    def test_felipe_dad_2026(self):
        ok, note = can_backup("Felipe", "DAD", False, self.SAT, 2026)
        self.assertTrue(ok)

    def test_felipe_ok_to_backup_2026(self):
        ok, note = can_backup("Felipe", "OK TO BACKUP", False, self.SAT, 2026)
        self.assertTrue(ok)

    def test_felipe_out_2026(self):
        ok, note = can_backup("Felipe", "OUT", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_felipe_maxed_2026(self):
        ok, note = can_backup("Felipe", "MAXED", False, self.SAT, 2026)
        self.assertFalse(ok)

    # --- Stephanie ---
    def test_stephanie_2026(self):
        ok, note = can_backup("Stephanie", "", False, self.SAT, 2026)
        self.assertFalse(ok)

    def test_stephanie_blank_weekend_2027(self):
        sat_2027 = datetime(2027, 3, 6)  # Saturday
        ok, note = can_backup("Stephanie", "", False, sat_2027, 2027)
        self.assertTrue(ok)

    def test_stephanie_blank_weekday_2027(self):
        wed_2027 = datetime(2027, 3, 3)  # Wednesday
        ok, note = can_backup("Stephanie", "", False, wed_2027, 2027)
        self.assertFalse(ok)

    def test_stephanie_out_2027(self):
        sat_2027 = datetime(2027, 3, 6)
        ok, note = can_backup("Stephanie", "OUT", False, sat_2027, 2027)
        self.assertFalse(ok)


# =============================================================================
# Paid/Unpaid Backup Tests
# =============================================================================

class TestBackupPayment(unittest.TestCase):
    """Test paid vs unpaid backup classification."""

    def test_unpaid_backups(self):
        self.assertFalse(is_paid_backup("Henry"))
        self.assertFalse(is_paid_backup("Woody"))
        self.assertFalse(is_paid_backup("Paul"))

    def test_paid_backups(self):
        self.assertTrue(is_paid_backup("Stefano"))
        self.assertTrue(is_paid_backup("Felipe"))
        self.assertTrue(is_paid_backup("Stephanie"))

    def test_backup_titles(self):
        self.assertEqual(get_backup_title("Woody"), "[WM] BACKUP DJ")
        self.assertEqual(get_backup_title("Henry"), "[HK] BACKUP DJ")
        self.assertEqual(get_backup_title("Stefano"), "[SB] PAID BACKUP DJ")
        self.assertEqual(get_backup_title("Felipe"), "[FS] PAID BACKUP DJ")


# =============================================================================
# Spots Remaining Tests
# =============================================================================

class TestSpotsRemaining(unittest.TestCase):
    """Test available spot calculation."""

    def test_all_available(self):
        row_data = {
            "Henry": "", "Woody": "", "Paul": "", "Stefano": "",
            "Felipe": "", "TBA": "",
        }
        # Henry, Woody, Paul = 3 available (Stefano blank = MAYBE, Felipe blank in 2026 = backup only)
        spots = calculate_spots_remaining(row_data, 2026)
        self.assertEqual(spots, 3)

    def test_one_booked(self):
        row_data = {
            "Henry": "", "Woody": "", "Paul": "BOOKED", "Stefano": "",
            "Felipe": "", "TBA": "",
        }
        spots = calculate_spots_remaining(row_data, 2026)
        self.assertEqual(spots, 2)

    def test_tba_consumes_spot(self):
        row_data = {
            "Henry": "", "Woody": "", "Paul": "", "Stefano": "",
            "Felipe": "", "TBA": "BOOKED",
        }
        spots = calculate_spots_remaining(row_data, 2026)
        self.assertEqual(spots, 2)

    def test_aag_reserved(self):
        row_data = {
            "Henry": "", "Woody": "", "Paul": "", "Stefano": "",
            "Felipe": "", "TBA": "", "AAG": "RESERVED",
        }
        spots = calculate_spots_remaining(row_data, 2026)
        self.assertEqual(spots, 2)

    def test_fully_booked(self):
        row_data = {
            "Henry": "BOOKED", "Woody": "BOOKED", "Paul": "BOOKED",
            "Stefano": "BOOKED", "Felipe": "", "TBA": "",
        }
        spots = calculate_spots_remaining(row_data, 2026)
        self.assertEqual(spots, 0)

    def test_felipe_ok_counts(self):
        row_data = {
            "Henry": "", "Woody": "", "Paul": "", "Stefano": "",
            "Felipe": "OK", "TBA": "",
        }
        spots = calculate_spots_remaining(row_data, 2026)
        self.assertEqual(spots, 4)  # Henry, Woody, Paul + Felipe OK


# =============================================================================
# Existing Backup Check Tests
# =============================================================================

class TestExistingBackup(unittest.TestCase):

    def test_no_backup(self):
        row_data = {"Henry": "", "Woody": "OUT", "Paul": "BOOKED"}
        self.assertIsNone(check_existing_backup(row_data))

    def test_has_backup(self):
        row_data = {"Henry": "", "Woody": "BACKUP", "Paul": "BOOKED"}
        self.assertEqual(check_existing_backup(row_data), "Woody")

    def test_multiple_backups(self):
        # Edge case — first one found wins
        row_data = {"Henry": "BACKUP", "Woody": "BACKUP", "Paul": "BOOKED"}
        self.assertEqual(check_existing_backup(row_data), "Henry")


# =============================================================================
# Booking Data Parsing Tests
# =============================================================================

class TestBookingParsing(unittest.TestCase):
    """Test parsing FM format and clean format booking JSON."""

    def _write_json(self, data):
        """Write JSON to a temp file and return the path."""
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        return path

    def test_fm_format(self):
        data = {
            "FMeventDate": "11/18/2026",
            "FMstartTime": "4:00",
            "FMendTime": "10:00",
            "FMclient": "Test Booking and Delete Me",
            "FMvenue": "Fake Venue (TEST)",
            "FMvenueAddress": "123 Test Street***Testville, CA 99999",
            "FMDJ1": "Paul Burchfield",
            "FMDJ2": "",
            "FMsound": "Standard Speakers",
            "FMcersound": "1",
            "MailCoordinator": "Fake Planner <fake@test.com>",
        }
        path = self._write_json(data)
        try:
            booking = parse_booking_data(path)
            self.assertEqual(booking["dj_short_name"], "Paul")
            self.assertEqual(booking["dj_initials"], "PB")
            self.assertEqual(booking["dj_initials_bracket"], "[PB]")
            self.assertEqual(booking["client_display"], "Test and Delete")
            self.assertEqual(booking["venue_name"], "Fake Venue")
            self.assertEqual(booking["venue_street"], "123 Test Street")
            self.assertTrue(booking["has_ceremony"])
            self.assertTrue(booking["has_planner"])
            self.assertFalse(booking["is_unassigned"])
            self.assertEqual(booking["date"], datetime(2026, 11, 18))
        finally:
            os.unlink(path)

    def test_fm_format_unassigned(self):
        data = {
            "FMeventDate": "12/08/2026",
            "FMstartTime": "5:00",
            "FMendTime": "11:00",
            "FMclient": "Fake Unassigned and Test Client",
            "FMvenue": "Test Venue TBA",
            "FMvenueAddress": "456 Nowhere Blvd***Faketown, CA 99998",
            "FMDJ1": "Unassigned",
            "FMDJ2": "Paul Burchfield",
            "FMsound": "Standard Speakers",
            "FMcersound": "0",
            "MailCoordinator": "",
        }
        path = self._write_json(data)
        try:
            booking = parse_booking_data(path)
            self.assertEqual(booking["dj_short_name"], "Unassigned")
            self.assertEqual(booking["dj_initials"], "UP")
            self.assertTrue(booking["is_unassigned"])
            self.assertFalse(booking["has_planner"])
        finally:
            os.unlink(path)

    def test_clean_format(self):
        data = {
            "event_date": "2026-02-21",
            "client_name": "Catherine MacDougall and Jacob Asmuth",
            "assigned_dj": "Paul Burchfield",
            "venue_name": "Kohl Mansion",
            "venue_street": "2750 Adeline Drive",
            "venue_city_state_zip": "Burlingame, CA 94010",
            "setup_time": "4:00",
            "clear_time": "10:00",
            "sound_type": "Standard Speakers",
            "has_ceremony_sound": True,
            "planner_name": "Jutta Lammerts",
        }
        path = self._write_json(data)
        try:
            booking = parse_booking_data(path)
            self.assertEqual(booking["dj_short_name"], "Paul")
            self.assertEqual(booking["client_display"], "Catherine and Jacob")
            self.assertTrue(booking["has_ceremony"])
            self.assertTrue(booking["has_planner"])
        finally:
            os.unlink(path)

    def test_fm_format_venue_parenthetical_stripped(self):
        data = {
            "FMeventDate": "11/16/2026",
            "FMstartTime": "4:00",
            "FMendTime": "10:00",
            "FMclient": "Test Client",
            "FMvenue": "Fake Winery (Skyline TEST)",
            "FMvenueAddress": "789 Hilltop Road***Testburg, CA 99997",
            "FMDJ1": "Woody Miraglia",
            "FMDJ2": "",
            "FMsound": "Standard Speakers",
            "FMcersound": "0",
            "MailCoordinator": "",
        }
        path = self._write_json(data)
        try:
            booking = parse_booking_data(path)
            self.assertEqual(booking["venue_name"], "Fake Winery")
        finally:
            os.unlink(path)


# =============================================================================
# Mock Client Tests
# =============================================================================

class TestMockSheetsClient(unittest.TestCase):
    """Test the mock sheets client for dry-run functionality."""

    def test_default_row_data(self):
        mock = MockSheetsClient()
        data = mock.get_row_data(5, 2026)
        self.assertEqual(data["Henry"], "")
        self.assertEqual(data["Woody"], "")

    def test_custom_row_data(self):
        mock = MockSheetsClient()
        mock.set_mock_row(2026, 5, {"Henry": "BOOKED", "Woody": "OUT", "Paul": ""})
        data = mock.get_row_data(5, 2026)
        self.assertEqual(data["Henry"], "BOOKED")
        self.assertEqual(data["Woody"], "OUT")

    def test_write_tracking(self):
        mock = MockSheetsClient()
        mock.write_cell(5, 6, "BOOKED", 2026)
        mock.write_cell(5, 5, "BACKUP", 2026)
        self.assertEqual(len(mock.writes), 2)
        self.assertEqual(mock.writes[0]["value"], "BOOKED")
        self.assertEqual(mock.writes[1]["value"], "BACKUP")

    def test_bold_default(self):
        mock = MockSheetsClient()
        self.assertFalse(mock.is_cell_bold(2026, 5, 5))

    def test_bold_custom(self):
        mock = MockSheetsClient()
        mock.set_mock_bold(2026, 5, 5, True)
        self.assertTrue(mock.is_cell_bold(2026, 5, 5))


# =============================================================================
# Integration-Level Dry Run Tests
# =============================================================================

class TestDryRunFlow(unittest.TestCase):
    """Test the full flow using dry-run mode (no external calls)."""

    def _write_json(self, data):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        return path

    def test_normal_booking_dry_run(self):
        data = {
            "event_date": "2026-11-18",
            "client_name": "Test Booking and Delete Me",
            "assigned_dj": "Paul Burchfield",
            "venue_name": "Fake Venue",
            "venue_street": "123 Test Street",
            "venue_city_state_zip": "Testville, CA 99999",
            "setup_time": "4:00",
            "clear_time": "10:00",
            "sound_type": "Standard Speakers",
            "has_ceremony_sound": True,
            "planner_name": "Fake Planner",
        }
        path = self._write_json(data)
        try:
            manager = GigBookingManager(dry_run=True)
            success = manager.run(path)
            self.assertTrue(success)

            # Verify the mock write happened
            self.assertEqual(len(manager.sheets.writes), 1)
            write = manager.sheets.writes[0]
            self.assertEqual(write["value"], "BOOKED")
            self.assertEqual(write["col"], COLUMN_MAPS[2026]["Paul"])
        finally:
            os.unlink(path)

    def test_conflict_detected_dry_run(self):
        data = {
            "event_date": "2026-11-18",
            "client_name": "Test Conflict Client",
            "assigned_dj": "Paul Burchfield",
            "venue_name": "Test Venue",
            "setup_time": "4:00",
            "clear_time": "10:00",
            "sound_type": "Standard Speakers",
            "has_ceremony_sound": False,
        }
        path = self._write_json(data)
        try:
            manager = GigBookingManager(dry_run=True)
            # Pre-populate Paul's cell with BOOKED
            manager.sheets.set_mock_row(2026, 5, {
                "Henry": "", "Woody": "", "Paul": "BOOKED",
                "Stefano": "", "Felipe": "", "TBA": "", "Stephanie": "",
            })
            success = manager.run(path)
            self.assertFalse(success)  # Should halt on conflict
            self.assertEqual(len(manager.sheets.writes), 0)  # No writes
        finally:
            os.unlink(path)

    def test_unassigned_booking_dry_run(self):
        data = {
            "event_date": "2026-12-08",
            "client_name": "Fake Unassigned and Test Client",
            "assigned_dj": "Unassigned",
            "secondary_dj": "Paul Burchfield",
            "venue_name": "Test Venue TBA",
            "setup_time": "5:00",
            "clear_time": "11:00",
            "sound_type": "Standard Speakers",
            "has_ceremony_sound": False,
        }
        path = self._write_json(data)
        try:
            manager = GigBookingManager(dry_run=True)
            success = manager.run(path)
            self.assertTrue(success)

            # Should write to TBA column, not a DJ column
            self.assertEqual(len(manager.sheets.writes), 1)
            write = manager.sheets.writes[0]
            self.assertEqual(write["value"], "BOOKED")
            self.assertEqual(write["col"], COLUMN_MAPS[2026]["TBA"])
        finally:
            os.unlink(path)

    def test_unassigned_tba_increment_dry_run(self):
        data = {
            "event_date": "2026-12-08",
            "client_name": "Test TBA Increment Client",
            "assigned_dj": "Unassigned",
            "venue_name": "Test Venue",
            "setup_time": "5:00",
            "clear_time": "11:00",
            "sound_type": "Standard Speakers",
            "has_ceremony_sound": False,
        }
        path = self._write_json(data)
        try:
            manager = GigBookingManager(dry_run=True)
            # TBA already has one booking
            manager.sheets.set_mock_row(2026, 5, {
                "Henry": "", "Woody": "", "Paul": "",
                "Stefano": "", "Felipe": "", "TBA": "BOOKED", "Stephanie": "",
            })
            success = manager.run(path)
            self.assertTrue(success)

            write = manager.sheets.writes[0]
            self.assertEqual(write["value"], "BOOKED x 2")
        finally:
            os.unlink(path)


# =============================================================================
# Column Map Validation Tests
# =============================================================================

class TestColumnMaps(unittest.TestCase):
    """Verify column mappings are correct for each year."""

    def test_2026_columns(self):
        cols = COLUMN_MAPS[2026]
        self.assertEqual(cols["Date"], 1)     # A
        self.assertEqual(cols["Henry"], 4)    # D
        self.assertEqual(cols["Woody"], 5)    # E
        self.assertEqual(cols["Paul"], 6)     # F
        self.assertEqual(cols["Stefano"], 7)  # G
        self.assertEqual(cols["Felipe"], 8)   # H
        self.assertEqual(cols["TBA"], 9)      # I
        self.assertEqual(cols["Stephanie"], 11)  # K
        self.assertEqual(cols["AAG"], 12)     # L

    def test_2027_columns(self):
        cols = COLUMN_MAPS[2027]
        self.assertEqual(cols["Stephanie"], 8)   # H (moved from K)
        self.assertEqual(cols["AAG"], 10)         # J (moved from L)
        self.assertEqual(cols["Felipe"], 12)      # L (moved from H)

    def test_all_years_have_required_columns(self):
        required = ["Date", "Henry", "Woody", "Paul", "Stefano", "TBA"]
        for year, cols in COLUMN_MAPS.items():
            for col in required:
                self.assertIn(col, cols, f"Missing {col} in {year} column map")


if __name__ == "__main__":
    unittest.main()
