#!/usr/bin/env python3
"""
Unit tests for cancel_booking.py calendar deletion.

Run with:
  python3 test_cancel_booking.py
  python3 -m pytest test_cancel_booking.py -v

Tests the deletion result protocol and error handling with subprocess
mocked. No Google Sheets or Calendar access required.
"""

import subprocess
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

import cancel_booking
from cancel_booking import (
    acceptable_event_titles,
    delete_booking_calendar_event,
    delete_backup_calendar_event,
)


def fake_result(stdout="", returncode=0, stderr=""):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    r.stderr = stderr
    return r


DATE = datetime(2026, 10, 16)
TITLE = "[PB] Julie and Jaylin"


def booking_stub(client_display, **overrides):
    """Minimal booking dict for title construction."""
    b = {
        "client_display": client_display,
        "dj_initials_bracket": "[PB]",
        "has_planner": False,
        "event_type": "",
        "sound_type": "Standard Speakers",
    }
    b.update(overrides)
    return b


class TestAcceptableEventTitles(unittest.TestCase):
    """The 10/16 Jaylin/Julie case: FileMaker had the couple's names in the
    opposite order from the calendar event. Both orders must match; anything
    else must not."""

    def test_couple_name_order_swap_accepted(self):
        titles = acceptable_event_titles(booking_stub("Jaylin and Julie"))
        self.assertIn("[PB] Jaylin and Julie", titles)
        self.assertIn("[PB] Julie and Jaylin", titles)
        self.assertEqual(len(titles), 2)

    def test_single_name_no_swap(self):
        titles = acceptable_event_titles(booking_stub("Chen & Lee Celebration"))
        self.assertEqual(titles, ["[PB] Chen & Lee Celebration"])

    def test_planner_suffix_on_both_orders(self):
        titles = acceptable_event_titles(
            booking_stub("Jaylin and Julie", has_planner=True))
        self.assertIn("[PB] Jaylin and Julie (planner)", titles)
        self.assertIn("[PB] Julie and Jaylin (planner)", titles)

    def test_multi_and_not_swapped(self):
        """'A and B and C' is ambiguous — don't generate permutations."""
        titles = acceptable_event_titles(booking_stub("Sam and Alex and Jo"))
        self.assertEqual(len(titles), 1)


def listing_of(*pairs):
    """A fake CalDAV day read: ignores the calendar and date, returns the pairs."""
    return lambda calendar_name, day: list(pairs)


def broken_listing(calendar_name, day):
    from calendar_read import CalendarReadError
    raise CalendarReadError("server down")


class TestDeleteBookingEvent(unittest.TestCase):
    """Result protocol: ('deleted', n) | ('not_found', 0) | ('ambiguous', titles) | ('error', msg).

    The day's events come from CalDAV as (uid, title); the matching ones are
    deleted in Calendar.app by `event id`. No `whose` scan anywhere."""

    @patch("cancel_booking.subprocess.run")
    def test_exact_match_deleted_by_id(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE)))
        self.assertEqual((status, payload), ("deleted", 1))
        script = mock_run.call_args.args[0][2]
        self.assertIn('event id "u1"', script)
        self.assertNotIn("whose", script)

    @patch("cancel_booking.subprocess.run")
    def test_swapped_name_order_is_deleted(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        status, _ = delete_booking_calendar_event(
            DATE, "[PB]", ["[PB] Jaylin and Julie", "[PB] Julie and Jaylin"],
            fetch_day=listing_of(("u1", "[PB] Jaylin and Julie")))
        self.assertEqual(status, "deleted")
        self.assertIn('event id "u1"', mock_run.call_args.args[0][2])

    @patch("cancel_booking.subprocess.run")
    def test_title_match_is_case_insensitive_like_applescript_was(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        status, _ = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", "[pb] JULIE and Jaylin")))
        self.assertEqual(status, "deleted")

    @patch("cancel_booking.subprocess.run")
    def test_duplicate_exact_matches_all_deleted(self, mock_run):
        mock_run.return_value = fake_result("DELETED:2")
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE), ("u2", TITLE)))
        self.assertEqual((status, payload), ("deleted", 2))
        script = mock_run.call_args.args[0][2]
        self.assertIn('"u1"', script)
        self.assertIn('"u2"', script)

    @patch("cancel_booking.subprocess.run")
    def test_no_events_at_all_touches_nothing(self, mock_run):
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE], fetch_day=listing_of())
        self.assertEqual(status, "not_found")
        mock_run.assert_not_called()

    @patch("cancel_booking.subprocess.run")
    def test_other_djs_event_is_not_a_candidate(self, mock_run):
        status, _ = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u5", "[HK] Julie and Jaylin")))
        self.assertEqual(status, "not_found")
        mock_run.assert_not_called()

    @patch("cancel_booking.subprocess.run")
    def test_initials_match_but_wrong_title_deletes_nothing(self, mock_run):
        """The second-booking-same-day case: [PB] Chen and Lee must survive."""
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u2", "[PB] Chen and Lee")))
        self.assertEqual((status, payload), ("ambiguous", ["[PB] Chen and Lee"]))
        mock_run.assert_not_called()

    @patch("cancel_booking.subprocess.run")
    def test_multiple_wrong_titles_all_reported(self, mock_run):
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE],
            fetch_day=listing_of(("u2", "[PB] Chen and Lee"), ("u3", "[PB] Smith Wedding")))
        self.assertEqual((status, payload), ("ambiguous", ["[PB] Chen and Lee", "[PB] Smith Wedding"]))

    @patch("cancel_booking.subprocess.run")
    def test_backup_and_hold_events_are_never_candidates(self, mock_run):
        status, _ = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE],
            fetch_day=listing_of(("u3", "[PB] BACKUP DJ"), ("u4", "[PB] Hold to DJ")))
        self.assertEqual(status, "not_found")
        mock_run.assert_not_called()

    @patch("cancel_booking.subprocess.run")
    def test_caldav_read_failure_is_error_not_not_found(self, mock_run):
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE], fetch_day=broken_listing)
        self.assertEqual(status, "error")
        self.assertIn("server down", payload)
        mock_run.assert_not_called()

    @patch("cancel_booking.subprocess.run")
    def test_timeout_is_error_not_not_found(self, mock_run):
        """The 7/29 incident: a timeout must never read as 'no events found'."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=180)
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE)))
        self.assertEqual(status, "error")
        self.assertIn("timed out", payload.lower())

    @patch("cancel_booking.subprocess.run")
    def test_nonzero_returncode_is_error(self, mock_run):
        mock_run.return_value = fake_result("", returncode=1, stderr="Not authorized")
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE)))
        self.assertEqual(status, "error")
        self.assertIn("Not authorized", payload)

    @patch("cancel_booking.subprocess.run")
    def test_garbage_stdout_is_error(self, mock_run):
        mock_run.return_value = fake_result("execution error: whatever")
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE)))
        self.assertEqual(status, "error")

    @patch("cancel_booking.subprocess.run")
    def test_timeout_is_180s(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        delete_booking_calendar_event(DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE)))
        self.assertEqual(mock_run.call_args.kwargs.get("timeout"), 180)


class TestDeleteBackupEvent(unittest.TestCase):

    @patch("cancel_booking.subprocess.run")
    def test_deleted_by_id(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        status, payload = delete_backup_calendar_event(
            DATE, "Felipe", fetch_day=listing_of(("u9", "[FS] BACKUP DJ"), ("u1", TITLE)))
        self.assertEqual((status, payload), ("deleted", 1))
        script = mock_run.call_args.args[0][2]
        self.assertIn('event id "u9"', script)
        self.assertNotIn('"u1"', script)
        self.assertNotIn("whose", script)

    @patch("cancel_booking.subprocess.run")
    def test_other_djs_backup_is_not_found(self, mock_run):
        status, _ = delete_backup_calendar_event(
            DATE, "Felipe", fetch_day=listing_of(("u8", "[HK] BACKUP DJ")))
        self.assertEqual(status, "not_found")
        mock_run.assert_not_called()

    @patch("cancel_booking.subprocess.run")
    def test_not_found(self, mock_run):
        status, _ = delete_backup_calendar_event(DATE, "Felipe", fetch_day=listing_of())
        self.assertEqual(status, "not_found")
        mock_run.assert_not_called()

    @patch("cancel_booking.subprocess.run")
    def test_caldav_read_failure_is_error(self, mock_run):
        status, payload = delete_backup_calendar_event(DATE, "Felipe", fetch_day=broken_listing)
        self.assertEqual(status, "error")
        mock_run.assert_not_called()

    @patch("cancel_booking.subprocess.run")
    def test_timeout_is_error(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=180)
        status, _ = delete_backup_calendar_event(
            DATE, "Felipe", fetch_day=listing_of(("u9", "[FS] BACKUP DJ")))
        self.assertEqual(status, "error")

    @patch("cancel_booking.subprocess.run")
    def test_timeout_is_180s(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        delete_backup_calendar_event(DATE, "Felipe", fetch_day=listing_of(("u9", "[FS] BACKUP DJ")))
        self.assertEqual(mock_run.call_args.kwargs.get("timeout"), 180)


class TestAskRemoveBackupTimeout(unittest.TestCase):

    @patch("cancel_booking.subprocess.run")
    def test_timeout_defaults_to_keep_and_says_so(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=1800)
        result = cancel_booking.ask_remove_backup("Fri 10/16", "Felipe")
        self.assertFalse(result)

    @patch("cancel_booking.subprocess.run")
    def test_long_timeout(self, mock_run):
        mock_run.return_value = fake_result("Keep Backup")
        cancel_booking.ask_remove_backup("Fri 10/16", "Felipe")
        self.assertEqual(mock_run.call_args.kwargs.get("timeout"), 1800)


if __name__ == "__main__":
    unittest.main(verbosity=2)
