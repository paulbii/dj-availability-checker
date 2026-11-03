#!/usr/bin/env python3
"""
Unit tests for cancel_booking.py calendar deletion.

Run with:
  python3 test_cancel_booking.py
  python3 -m pytest test_cancel_booking.py -v

Tests the deletion result protocol and error handling with Calendar.app
stood in for by a fake app. No Google Sheets or Calendar access required.
"""

import subprocess
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

import cancel_booking
from calendar_app import CalendarAppError
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


class FakeApp:
    """Stands in for calendar_app.CalendarApp: records the uids it was asked to delete."""

    def __init__(self, fail=None):
        self.deleted = []
        self.fail = fail

    def delete_events(self, uids):
        if self.fail:
            raise CalendarAppError(self.fail)
        self.deleted.extend(uids)
        return len(uids)


class TestDeleteBookingEvent(unittest.TestCase):
    """Result protocol: ('deleted', n) | ('not_found', 0) | ('ambiguous', titles) | ('error', msg).

    The day's events come from CalDAV as (uid, title); the matching ones are
    handed to CalendarApp.delete_events by uid. Calendar.app itself is never
    scanned (test_calendar_app proves the runner has no `whose`)."""

    def test_exact_match_deleted_by_id(self):
        app = FakeApp()
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE)), app=app)
        self.assertEqual((status, payload), ("deleted", 1))
        self.assertEqual(app.deleted, ["u1"])

    def test_swapped_name_order_is_deleted(self):
        app = FakeApp()
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", acceptable_event_titles(booking_stub("Julie and Jaylin")),
            fetch_day=listing_of(("u1", "[PB] Jaylin and Julie")), app=app)
        self.assertEqual((status, payload), ("deleted", 1))
        self.assertEqual(app.deleted, ["u1"])

    def test_match_is_case_insensitive(self):
        app = FakeApp()
        status, _ = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", "[pb] JULIE and Jaylin")), app=app)
        self.assertEqual(status, "deleted")
        self.assertEqual(app.deleted, ["u1"])

    def test_duplicate_exact_matches_all_deleted(self):
        app = FakeApp()
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE), ("u2", TITLE)), app=app)
        self.assertEqual((status, payload), ("deleted", 2))
        self.assertEqual(app.deleted, ["u1", "u2"])

    def test_empty_day_is_not_found(self):
        app = FakeApp()
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(), app=app)
        self.assertEqual((status, payload), ("not_found", 0))
        self.assertEqual(app.deleted, [])

    def test_other_dj_only_is_not_found(self):
        app = FakeApp()
        status, _ = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u5", "[HK] Julie and Jaylin")), app=app)
        self.assertEqual(status, "not_found")
        self.assertEqual(app.deleted, [])

    def test_initials_match_but_wrong_title_deletes_nothing(self):
        app = FakeApp()
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u2", "[PB] Chen and Lee")), app=app)
        self.assertEqual(status, "ambiguous")
        self.assertEqual(payload, ["[PB] Chen and Lee"])
        self.assertEqual(app.deleted, [])

    def test_ambiguous_lists_every_other_booking_for_the_dj(self):
        app = FakeApp()
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE],
            fetch_day=listing_of(("u2", "[PB] Chen and Lee"), ("u3", "[PB] Smith Wedding")), app=app)
        self.assertEqual(status, "ambiguous")
        self.assertEqual(payload, ["[PB] Chen and Lee", "[PB] Smith Wedding"])

    def test_backup_and_hold_events_are_never_candidates(self):
        app = FakeApp()
        status, _ = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE],
            fetch_day=listing_of(("u3", "[PB] BACKUP DJ"), ("u4", "[PB] Hold to DJ")), app=app)
        self.assertEqual(status, "not_found")
        self.assertEqual(app.deleted, [])

    def test_caldav_read_failure_is_error_not_not_found(self):
        app = FakeApp()
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=broken_listing, app=app)
        self.assertEqual(status, "error")
        self.assertIn("server down", payload)
        self.assertEqual(app.deleted, [])

    def test_calendar_app_failure_is_error_with_its_message(self):
        """The 7/29 and 11/3 incidents: a Calendar.app failure must never read as 'no events found'."""
        app = FakeApp(fail="Calendar.app did not answer within 60s")
        status, payload = delete_booking_calendar_event(
            DATE, "[PB]", [TITLE], fetch_day=listing_of(("u1", TITLE)), app=app)
        self.assertEqual(status, "error")
        self.assertIn("60s", payload)


class TestDeleteBackupEvent(unittest.TestCase):

    def test_deleted_by_id(self):
        app = FakeApp()
        status, payload = delete_backup_calendar_event(
            DATE, "Felipe", fetch_day=listing_of(("u9", "[FS] BACKUP DJ"), ("u1", TITLE)), app=app)
        self.assertEqual((status, payload), ("deleted", 1))
        self.assertEqual(app.deleted, ["u9"])

    def test_other_djs_backup_is_left_alone(self):
        app = FakeApp()
        status, _ = delete_backup_calendar_event(
            DATE, "Felipe", fetch_day=listing_of(("u8", "[HK] BACKUP DJ")), app=app)
        self.assertEqual(status, "not_found")
        self.assertEqual(app.deleted, [])

    def test_empty_day_is_not_found(self):
        app = FakeApp()
        status, _ = delete_backup_calendar_event(DATE, "Felipe", fetch_day=listing_of(), app=app)
        self.assertEqual(status, "not_found")

    def test_caldav_read_failure_is_error(self):
        app = FakeApp()
        status, payload = delete_backup_calendar_event(DATE, "Felipe", fetch_day=broken_listing, app=app)
        self.assertEqual(status, "error")
        self.assertIn("server down", payload)

    def test_calendar_app_failure_is_error(self):
        app = FakeApp(fail="boom")
        status, payload = delete_backup_calendar_event(
            DATE, "Felipe", fetch_day=listing_of(("u9", "[FS] BACKUP DJ")), app=app)
        self.assertEqual((status, payload), ("error", "boom"))


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
