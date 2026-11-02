#!/usr/bin/env python3
"""
Tests for assign_dj: moving a TBA booking to the DJ Paul assigned in FileMaker.

The matrix and the calendar are both written, so the pure pieces (TBA step-down,
the DJ cell value, the title rewrite, picking the right unassigned event) are
pinned here, and the flow runs against the mock Sheets client and a fake
osascript so every write is asserted without touching the live systems.
"""

import unittest
from datetime import datetime

import assign_dj
from gig_booking_manager import MockSheetsClient


def booking(dj="Henry", client="Cienna and Joseph", planner=False, date="2027-01-23"):
    """A parsed booking as parse_booking_data would return it, after Paul set DJ1."""
    d = datetime.strptime(date, "%Y-%m-%d")
    initials = {"Henry": "HK", "Paul": "PB", "Woody": "WM", "Stefano": "SB", "Stephanie": "SM"}[dj]
    return {
        "date": d,
        "date_display": d.strftime("%a ") + f"{d.month}/{d.day}",
        "year": d.year,
        "dj_full_name": dj,
        "dj_short_name": dj,
        "dj_initials": initials,
        "dj_initials_bracket": f"[{initials}]",
        "dj2_full_name": "",
        "client_full": client,
        "client_display": client,
        "venue_name": "Oceano Hotel",
        "venue_raw": "Oceano Hotel",
        "venue_street": "280 Capistrano Rd",
        "venue_city_state_zip": "Half Moon Bay, CA 94019",
        "start_time": "17:00",
        "end_time": "22:00",
        "sound_type": "Standard Speakers",
        "has_ceremony": False,
        "has_planner": planner,
        "is_unassigned": dj == "Unassigned",
        "email1": "",
        "email2": "",
        "event_type": "Wedding",
    }


class FakeOsa:
    """Stands in for osascript (records every script run) and for the CalDAV
    day read (answers the listing, records what was asked for)."""

    def __init__(self, listing):
        self.listing = listing  # list of (uid, summary) on the date
        self.scripts = []
        self.day_calls = []

    def __call__(self, script):
        self.scripts.append(script)
        return ""

    def fetch_day(self, calendar_name, day):
        self.day_calls.append((calendar_name, day))
        return list(self.listing)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

class TestDecrementTba(unittest.TestCase):

    def test_single_booked_clears(self):
        self.assertEqual(assign_dj.decrement_tba("BOOKED"), "")

    def test_x2_to_single(self):
        self.assertEqual(assign_dj.decrement_tba("BOOKED x 2"), "BOOKED")

    def test_x3_to_x2(self):
        self.assertEqual(assign_dj.decrement_tba("BOOKED x 3"), "BOOKED x 2")

    def test_aag_is_kept(self):
        self.assertEqual(assign_dj.decrement_tba("BOOKED, AAG"), "AAG")
        self.assertEqual(assign_dj.decrement_tba("BOOKED x 2, AAG"), "BOOKED, AAG")

    def test_case_and_whitespace(self):
        self.assertEqual(assign_dj.decrement_tba("  booked X 2 "), "BOOKED")

    def test_nothing_to_move_raises(self):
        for v in ("", "AAG", "OUT", "RESERVED"):
            with self.assertRaises(ValueError):
                assign_dj.decrement_tba(v)


class TestAssignedCellValue(unittest.TestCase):

    def test_blank_becomes_booked(self):
        self.assertEqual(assign_dj.assigned_cell_value(""), "BOOKED")

    def test_ok_is_overwritten(self):
        # Paul, 2026-11-01: an OK in anyone's cell is overwritten
        self.assertEqual(assign_dj.assigned_cell_value("OK"), "BOOKED")

    def test_reserved_and_other_values_are_overwritten(self):
        for v in ("RESERVED", "OK TO BACKUP", "DAD", "OUT"):
            self.assertEqual(assign_dj.assigned_cell_value(v), "BOOKED")

    def test_existing_booking_increments(self):
        self.assertEqual(assign_dj.assigned_cell_value("BOOKED"), "BOOKED x 2")
        self.assertEqual(assign_dj.assigned_cell_value("BOOKED x 2"), "BOOKED x 3")


class TestRetitle(unittest.TestCase):

    def test_up_to_initials(self):
        self.assertEqual(assign_dj.retitle("[UP] Cienna and Joseph", "[HK]"), "[HK] Cienna and Joseph")

    def test_other_booker_initial(self):
        self.assertEqual(assign_dj.retitle("[UH] Taylor and Will (planner)", "[PB]"),
                         "[PB] Taylor and Will (planner)")

    def test_rest_of_title_untouched(self):
        self.assertEqual(assign_dj.retitle("[UP] Notre Dame Winter Formal Setup (planner)", "[HK]"),
                         "[HK] Notre Dame Winter Formal Setup (planner)")

    def test_already_assigned_title_raises(self):
        with self.assertRaises(ValueError):
            assign_dj.retitle("[HK] Cienna and Joseph", "[PB]")

    def test_joint_unassigned_bracket_raises(self):
        with self.assertRaises(ValueError):
            assign_dj.retitle("[UP/SB] Big one", "[HK]")


class TestIsUnassignedTitle(unittest.TestCase):

    def test_forms(self):
        self.assertTrue(assign_dj.is_unassigned_title("[UP] X"))
        self.assertTrue(assign_dj.is_unassigned_title("[UW] X"))
        self.assertFalse(assign_dj.is_unassigned_title("[PB] X"))
        self.assertFalse(assign_dj.is_unassigned_title("Unavailable"))
        self.assertFalse(assign_dj.is_unassigned_title("[UP/SB] X"))


class TestPickUnassignedEvent(unittest.TestCase):

    def test_single_match(self):
        listing = [("u1", "[UP] Cienna and Joseph"), ("u2", "[HK] Notre Dame Winter Formal")]
        self.assertEqual(assign_dj.pick_unassigned_event(listing, "Cienna and Joseph"), ("u1", "[UP] Cienna and Joseph"))

    def test_two_unassigned_picks_by_client(self):
        listing = [("u1", "[UP] Cienna and Joseph"), ("u2", "[UP] Notre Dame Winter Formal")]
        self.assertEqual(assign_dj.pick_unassigned_event(listing, "Notre Dame Winter Formal")[0], "u2")

    def test_match_is_case_insensitive(self):
        listing = [("u1", "[UP] cienna and joseph (planner)")]
        self.assertEqual(assign_dj.pick_unassigned_event(listing, "Cienna and Joseph")[0], "u1")

    def test_no_unassigned_event_returns_none(self):
        listing = [("u2", "[HK] Cienna and Joseph")]
        self.assertIsNone(assign_dj.pick_unassigned_event(listing, "Cienna and Joseph"))

    def test_unassigned_but_wrong_client_returns_none(self):
        # Never guess: a lone [U?] event for someone else is not this booking.
        listing = [("u1", "[UP] Someone Else")]
        self.assertIsNone(assign_dj.pick_unassigned_event(listing, "Cienna and Joseph"))


# ---------------------------------------------------------------------------
# The flow
# ---------------------------------------------------------------------------

class TestAssignFlow(unittest.TestCase):

    def setUp(self):
        self.sheets = MockSheetsClient()
        self.sheets.set_mock_row(2027, 5, {"Henry": "", "Woody": "OUT", "Paul": "",
                                           "Stefano": "OK", "Stephanie": "", "TBA": "BOOKED", "AAG": "", "Felipe": ""})
        self.osa = FakeOsa([("u1", "[UP] Cienna and Joseph"), ("u9", "[WM] BACKUP DJ")])
        self.log = []

    def run_assign(self, b, dry_run=False, test_mode=False):
        # Phase 4 is covered in TestBackupPhase; here it is stubbed so no test
        # ever reaches the real dialog or calendar.
        return assign_dj.assign(b, self.sheets, osa=self.osa, fetch_day=self.osa.fetch_day,
                                dry_run=dry_run, test_mode=test_mode, log=self.log.append,
                                choose_backup=FakeChooser(None),
                                conflicts=lambda d, br: [],
                                make_backup_event=lambda d, dj, test_mode=False: "stub",
                                make_email_folder=lambda b, dry_run=False: None)

    def test_moves_booking_from_tba_to_dj(self):
        ok = self.run_assign(booking("Henry"))
        self.assertTrue(ok)
        writes = {(w["col"], w["value"]) for w in self.sheets.writes}
        # 2027 columns: Henry = D (4), TBA = I (9)
        self.assertEqual(writes, {(9, ""), (4, "BOOKED")})

    def test_calendar_retitled_and_invited(self):
        self.run_assign(booking("Henry"))
        modify = [s for s in self.osa.scripts if "LISTING" not in s]
        self.assertEqual(len(modify), 1)
        self.assertIn('"u1"', modify[0])
        self.assertIn("[HK] Cienna and Joseph", modify[0])
        self.assertIn("henry@bigfundj.com", modify[0])

    def test_day_listing_is_read_over_caldav_not_scanned_in_calendar_app(self):
        self.run_assign(booking("Henry"))
        self.assertEqual(self.osa.day_calls, [("Gigs", datetime(2027, 1, 23).date())])
        self.assertFalse(any("whose" in s for s in self.osa.scripts))

    def test_calendar_event_is_edited_by_id_not_by_scan(self):
        self.run_assign(booking("Henry"))
        modify = [s for s in self.osa.scripts if "set summary" in s][0]
        self.assertIn('event id "u1"', modify)
        self.assertNotIn("whose", modify)

    def test_caldav_read_failure_raises_and_writes_nothing(self):
        from calendar_read import CalendarReadError
        def broken(calendar_name, day):
            raise CalendarReadError("server down")
        with self.assertRaises(CalendarReadError):
            assign_dj.assign(booking("Henry"), self.sheets, osa=self.osa, fetch_day=broken,
                             log=self.log.append, choose_backup=FakeChooser(None),
                             conflicts=lambda d, br: [], make_backup_event=lambda d, dj, test_mode=False: "stub",
                             make_email_folder=lambda b, dry_run=False: None)
        self.assertEqual(self.sheets.writes, [])
        self.assertEqual(self.osa.scripts, [])

    def test_test_mode_invites_paul(self):
        self.run_assign(booking("Henry"), test_mode=True)
        modify = [s for s in self.osa.scripts if "LISTING" not in s][0]
        self.assertIn("paul@bigfundj.com", modify)
        self.assertNotIn("henry@bigfundj.com", modify)

    def test_ok_cell_overwritten(self):
        ok = self.run_assign(booking("Stefano"))
        self.assertTrue(ok)
        self.assertIn({"row": 5, "col": 7, "value": "BOOKED", "year": 2027}, self.sheets.writes)

    def test_dj_with_existing_booking_increments(self):
        self.sheets.set_mock_row(2027, 5, {"Henry": "", "Woody": "", "Paul": "BOOKED",
                                           "Stefano": "", "Stephanie": "", "TBA": "BOOKED x 2", "AAG": "", "Felipe": ""})
        self.run_assign(booking("Paul"))
        writes = {(w["col"], w["value"]) for w in self.sheets.writes}
        self.assertEqual(writes, {(9, "BOOKED"), (6, "BOOKED x 2")})

    def test_dry_run_writes_nothing(self):
        ok = self.run_assign(booking("Henry"), dry_run=True)
        self.assertTrue(ok)
        self.assertEqual(self.sheets.writes, [])
        self.assertEqual([s for s in self.osa.scripts if "LISTING" not in s], [])

    def test_still_unassigned_refuses(self):
        b = booking("Henry"); b["dj_short_name"] = "Unassigned"; b["is_unassigned"] = True
        self.assertFalse(self.run_assign(b))
        self.assertEqual(self.sheets.writes, [])

    def test_no_calendar_event_means_no_matrix_write(self):
        # Both systems or neither: a missing calendar event halts before the matrix.
        self.osa = FakeOsa([("u9", "[WM] BACKUP DJ")])
        self.assertFalse(self.run_assign(booking("Henry")))
        self.assertEqual(self.sheets.writes, [])

    def test_tba_empty_but_calendar_unassigned_halts(self):
        self.sheets.set_mock_row(2027, 5, {"Henry": "", "Woody": "", "Paul": "",
                                           "Stefano": "", "Stephanie": "", "TBA": "", "AAG": "", "Felipe": ""})
        self.assertFalse(self.run_assign(booking("Henry")))
        self.assertEqual(self.sheets.writes, [])
        self.assertEqual([s for s in self.osa.scripts if "LISTING" not in s], [])

    def test_already_done_is_a_no_op(self):
        # Second press: TBA has nothing and the calendar already carries the DJ.
        self.sheets.set_mock_row(2027, 5, {"Henry": "BOOKED", "Woody": "", "Paul": "",
                                           "Stefano": "", "Stephanie": "", "TBA": "", "AAG": "", "Felipe": ""})
        self.osa = FakeOsa([("u1", "[HK] Cienna and Joseph")])
        ok = self.run_assign(booking("Henry"))
        self.assertTrue(ok)
        self.assertEqual(self.sheets.writes, [])
        self.assertEqual([s for s in self.osa.scripts if "LISTING" not in s], [])
        self.assertTrue(any("already" in line.lower() for line in self.log))

    def test_dj_already_backup_refuses(self):
        self.sheets.set_mock_row(2027, 5, {"Henry": "BACKUP", "Woody": "", "Paul": "",
                                           "Stefano": "", "Stephanie": "", "TBA": "BOOKED", "AAG": "", "Felipe": ""})
        self.assertFalse(self.run_assign(booking("Henry")))
        self.assertEqual(self.sheets.writes, [])
        self.assertFalse(any("set summary" in s for s in self.osa.scripts))
        self.assertTrue(any("backup" in line.lower() for line in self.log))

    def test_dj_compound_backup_refuses(self):
        self.sheets.set_mock_row(2027, 5, {"Henry": "", "Woody": "DAD, BACKUP", "Paul": "",
                                           "Stefano": "", "Stephanie": "", "TBA": "BOOKED", "AAG": "", "Felipe": ""})
        self.assertFalse(self.run_assign(booking("Woody")))
        self.assertEqual(self.sheets.writes, [])

    def test_no_date_row_refuses(self):
        self.sheets.find_date_row = lambda d, y: None
        self.assertFalse(self.run_assign(booking("Henry")))
        self.assertEqual(self.sheets.writes, [])


class TestBackupCellValue(unittest.TestCase):
    def test_default_markers_replaced(self):
        for v in ("", "OUT", "OK", "DAD", "STANFORD", "LAST", "OK TO BACKUP"):
            self.assertEqual(assign_dj.backup_cell_value(v), "BACKUP", v)

    def test_other_values_kept_and_appended(self):
        self.assertEqual(assign_dj.backup_cell_value("DAD-DUTY"), "DAD-DUTY, BACKUP")


class FakeChooser:
    """Stands in for show_backup_dialog: records the call, returns a canned answer."""

    def __init__(self, answer=None):
        self.answer = answer
        self.calls = []

    def __call__(self, date_display, spots, candidates, existing, booking_context=None):
        self.calls.append({"date": date_display, "spots": spots, "candidates": candidates,
                           "existing": existing, "context": booking_context})
        return self.answer


class TestBackupPhase(unittest.TestCase):
    """After the DJ is on both systems, the button offers a backup for the date."""

    def setUp(self):
        self.sheets = MockSheetsClient()
        # Sat 1/23/27: Henry being assigned; Woody plain OUT on a weekend can back up;
        # Paul blank; Stefano OK (not a backup value); Stephanie blank on a weekend; Felipe blank.
        self.sheets.set_mock_row(2027, 5, {"Henry": "", "Woody": "OUT", "Paul": "",
                                           "Stefano": "OK", "Stephanie": "", "TBA": "BOOKED", "AAG": "", "Felipe": ""})
        self.osa = FakeOsa([("u1", "[UP] Cienna and Joseph")])
        self.log = []
        self.events = []
        self.conflict_answer = []

    def run_assign(self, b, chooser, dry_run=False, test_mode=False, conflicts=None, make_event=None):
        def default_conflicts(date_obj, bracket):
            return self.conflict_answer
        def default_event(date_obj, dj, test_mode=False):
            self.events.append((date_obj, dj, test_mode))
            return f"[{dj[:2].upper()}] BACKUP DJ"
        return assign_dj.assign(b, self.sheets, osa=self.osa, fetch_day=self.osa.fetch_day,
                                dry_run=dry_run, test_mode=test_mode,
                                log=self.log.append, choose_backup=chooser,
                                conflicts=conflicts or default_conflicts,
                                make_backup_event=make_event or default_event,
                                make_email_folder=lambda b, dry_run=False: None)

    def backup_writes(self):
        return [(w["col"], w["value"]) for w in self.sheets.writes if "BACKUP" in w["value"]]

    def test_candidates_exclude_assigned_dj_and_follow_can_backup(self):
        ch = FakeChooser(None)
        self.assertTrue(self.run_assign(booking("Henry"), ch))
        names = [c[0] for c in ch.calls[0]["candidates"]]
        self.assertEqual(names, ["Woody", "Paul", "Stephanie", "Felipe"])
        self.assertNotIn("Henry", names)
        self.assertNotIn("Stefano", names)  # OK is not a backup value for Stefano
        self.assertIsNone(ch.calls[0]["existing"])
        self.assertIn("Oceano Hotel", ch.calls[0]["context"])

    def test_existing_backup_is_reported_not_rewritten(self):
        self.sheets.set_mock_row(2027, 5, {"Henry": "", "Woody": "BACKUP", "Paul": "",
                                           "Stefano": "", "Stephanie": "", "TBA": "BOOKED", "AAG": "", "Felipe": ""})
        ch = FakeChooser("Paul")  # even if a name came back, an existing backup wins
        self.assertTrue(self.run_assign(booking("Henry"), ch))
        self.assertEqual(ch.calls[0]["existing"], "Woody")
        self.assertEqual(self.backup_writes(), [])
        self.assertEqual(self.events, [])

    def test_skip_writes_nothing(self):
        self.assertTrue(self.run_assign(booking("Henry"), FakeChooser(None)))
        self.assertEqual(self.backup_writes(), [])
        self.assertEqual(self.events, [])
        self.assertTrue(any("Backup: skipped" in line for line in self.log))

    def test_cancel_writes_nothing_and_assignment_stands(self):
        self.assertTrue(self.run_assign(booking("Henry"), FakeChooser("STOP")))
        self.assertEqual(self.backup_writes(), [])
        self.assertEqual(self.events, [])
        # the assignment itself still happened
        self.assertIn((9, ""), {(w["col"], w["value"]) for w in self.sheets.writes})

    def test_pick_writes_matrix_then_calendar(self):
        self.assertTrue(self.run_assign(booking("Henry"), FakeChooser("Paul")))
        self.assertEqual(self.backup_writes(), [(6, "BACKUP")])  # Paul = F (6) in 2027
        self.assertEqual(self.events, [(booking("Henry")["date"], "Paul", False)])

    def test_pick_in_test_mode_passes_test_flag_to_event(self):
        self.assertTrue(self.run_assign(booking("Henry"), FakeChooser("Paul"), test_mode=True))
        self.assertEqual(self.events[0][2], True)

    def test_dad_becomes_dad_backup(self):
        self.sheets.set_mock_row(2027, 5, {"Henry": "", "Woody": "", "Paul": "",
                                           "Stefano": "", "Stephanie": "", "TBA": "BOOKED", "AAG": "", "Felipe": "DAD"})
        self.assertTrue(self.run_assign(booking("Henry"), FakeChooser("Felipe")))
        self.assertEqual(self.backup_writes(), [(12, "BACKUP")])  # DAD is a default marker, replaced

    def test_calendar_conflict_blocks_backup(self):
        self.conflict_answer = ["[PB] Someone Else"]
        self.assertTrue(self.run_assign(booking("Henry"), FakeChooser("Paul")))
        self.assertEqual(self.backup_writes(), [])
        self.assertEqual(self.events, [])
        self.assertTrue(any("conflict" in line.lower() for line in self.log))

    def test_calendar_unreadable_blocks_backup(self):
        def boom(date_obj, bracket):
            raise RuntimeError("CalDAV down")
        self.assertTrue(self.run_assign(booking("Henry"), FakeChooser("Paul"), conflicts=boom))
        self.assertEqual(self.backup_writes(), [])
        self.assertEqual(self.events, [])
        self.assertTrue(any("not checked" in line.lower() or "failed" in line.lower() for line in self.log))

    def test_event_failure_after_matrix_write_is_reported(self):
        def boom(date_obj, dj, test_mode=False):
            raise RuntimeError("osascript failed")
        self.assertTrue(self.run_assign(booking("Henry"), FakeChooser("Paul"), make_event=boom))
        self.assertEqual(self.backup_writes(), [(6, "BACKUP")])
        self.assertTrue(any("by hand" in line.lower() for line in self.log))

    def test_dry_run_lists_candidates_without_dialog(self):
        ch = FakeChooser("Paul")
        self.assertTrue(self.run_assign(booking("Henry"), ch, dry_run=True))
        self.assertEqual(ch.calls, [])
        self.assertEqual(self.sheets.writes, [])
        self.assertTrue(any("Woody" in line and "Paul" in line and "candidates" in line.lower() for line in self.log))


class TestEmailFolderStep(unittest.TestCase):
    """Paul's bookings get the love2tap folder; the log says what really happened."""

    def setUp(self):
        self.sheets = MockSheetsClient()
        self.sheets.set_mock_row(2027, 5, {"Henry": "", "Woody": "", "Paul": "",
                                           "Stefano": "", "Stephanie": "", "TBA": "BOOKED", "AAG": "", "Felipe": ""})
        self.log = []
        self.calls = []

    def run_assign(self, b, folder_result=None, raise_error=False):
        def make_folder(booking, dry_run=False):
            self.calls.append(booking["dj_short_name"])
            if raise_error:
                raise RuntimeError("IMAP down")
            return folder_result
        osa = FakeOsa([("u1", "[UP] Cienna and Joseph")])
        return assign_dj.assign(b, self.sheets, osa=osa, fetch_day=osa.fetch_day,
                                log=self.log.append, choose_backup=FakeChooser(None),
                                conflicts=lambda d, br: [], make_backup_event=lambda d, dj, test_mode=False: "x",
                                make_email_folder=make_folder)

    def test_only_for_paul(self):
        self.run_assign(booking("Henry"))
        self.assertEqual(self.calls, [])
        self.sheets.writes.clear()
        self.run_assign(booking("Paul"), folder_result="01-23-27: Cienna and Joseph")
        self.assertEqual(self.calls, ["Paul"])

    def test_success_logged_with_name(self):
        self.run_assign(booking("Paul"), folder_result="01-23-27: Cienna and Joseph")
        self.assertTrue(any("Email folder: created '01-23-27: Cienna and Joseph'" in l for l in self.log))

    def test_none_result_logged_as_not_created(self):
        self.assertTrue(self.run_assign(booking("Paul"), folder_result=None))
        self.assertFalse(any("created '" in l for l in self.log))
        self.assertTrue(any("not created" in l.lower() for l in self.log))

    def test_exception_does_not_undo_assignment(self):
        self.assertTrue(self.run_assign(booking("Paul"), raise_error=True))
        self.assertTrue(any("not created" in l.lower() and "IMAP down" in l for l in self.log))
        self.assertIn((9, ""), {(w["col"], w["value"]) for w in self.sheets.writes})


if __name__ == "__main__":
    unittest.main()
