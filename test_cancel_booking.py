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


class TestDeleteBookingEvent(unittest.TestCase):
    """Result protocol: ('deleted', n) | ('not_found', 0) | ('ambiguous', titles) | ('error', msg)."""

    @patch("cancel_booking.subprocess.run")
    def test_exact_match_deleted(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(status, "deleted")
        self.assertEqual(payload, 1)

    @patch("cancel_booking.subprocess.run")
    def test_script_carries_all_acceptable_titles(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        delete_booking_calendar_event(
            DATE, "[PB]", ["[PB] Jaylin and Julie", "[PB] Julie and Jaylin"])
        script = mock_run.call_args.args[0][2]
        self.assertIn("[PB] Jaylin and Julie", script)
        self.assertIn("[PB] Julie and Jaylin", script)

    @patch("cancel_booking.subprocess.run")
    def test_duplicate_exact_matches_all_deleted(self, mock_run):
        mock_run.return_value = fake_result("DELETED:2")
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(status, "deleted")
        self.assertEqual(payload, 2)

    @patch("cancel_booking.subprocess.run")
    def test_no_events_at_all(self, mock_run):
        mock_run.return_value = fake_result("NONE")
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(status, "not_found")

    @patch("cancel_booking.subprocess.run")
    def test_initials_match_but_wrong_title_deletes_nothing(self, mock_run):
        """The second-booking-same-day case: [PB] Chen and Lee must survive."""
        mock_run.return_value = fake_result("FOUND:[PB] Chen and Lee")
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(status, "ambiguous")
        self.assertEqual(payload, ["[PB] Chen and Lee"])

    @patch("cancel_booking.subprocess.run")
    def test_multiple_wrong_titles_all_reported(self, mock_run):
        mock_run.return_value = fake_result("FOUND:[PB] Chen and Lee||[PB] Smith Wedding")
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(status, "ambiguous")
        self.assertEqual(payload, ["[PB] Chen and Lee", "[PB] Smith Wedding"])

    @patch("cancel_booking.subprocess.run")
    def test_timeout_is_error_not_not_found(self, mock_run):
        """The 7/29 incident: a timeout must never read as 'no events found'."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=180)
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(status, "error")
        self.assertIn("timed out", payload.lower())

    @patch("cancel_booking.subprocess.run")
    def test_nonzero_returncode_is_error(self, mock_run):
        mock_run.return_value = fake_result("", returncode=1, stderr="Not authorized")
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(status, "error")
        self.assertIn("Not authorized", payload)

    @patch("cancel_booking.subprocess.run")
    def test_garbage_stdout_is_error(self, mock_run):
        mock_run.return_value = fake_result("execution error: whatever")
        status, payload = delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(status, "error")

    @patch("cancel_booking.subprocess.run")
    def test_timeout_is_180s(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        self.assertEqual(mock_run.call_args.kwargs.get("timeout"), 180)

    @patch("cancel_booking.subprocess.run")
    def test_script_contains_exact_title_and_guards(self, mock_run):
        """The generated AppleScript must carry the exact title and still
        exclude BACKUP DJ / Hold to DJ from the ambiguous listing."""
        mock_run.return_value = fake_result("DELETED:1")
        delete_booking_calendar_event(DATE, "[PB]", [TITLE])
        script = mock_run.call_args.args[0][2]
        self.assertIn(TITLE, script)
        self.assertIn("BACKUP DJ", script)
        self.assertIn("Hold to DJ", script)
        self.assertIn("October 16, 2026", script)


class TestDeleteBackupEvent(unittest.TestCase):

    @patch("cancel_booking.subprocess.run")
    def test_deleted(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        status, payload = delete_backup_calendar_event(DATE, "Felipe")
        self.assertEqual(status, "deleted")
        self.assertEqual(payload, 1)

    @patch("cancel_booking.subprocess.run")
    def test_not_found(self, mock_run):
        mock_run.return_value = fake_result("NONE")
        status, payload = delete_backup_calendar_event(DATE, "Felipe")
        self.assertEqual(status, "not_found")

    @patch("cancel_booking.subprocess.run")
    def test_timeout_is_error(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=180)
        status, payload = delete_backup_calendar_event(DATE, "Felipe")
        self.assertEqual(status, "error")

    @patch("cancel_booking.subprocess.run")
    def test_timeout_is_180s(self, mock_run):
        mock_run.return_value = fake_result("DELETED:1")
        delete_backup_calendar_event(DATE, "Felipe")
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
