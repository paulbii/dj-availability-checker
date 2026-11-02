#!/usr/bin/env python3
"""
Tests for the booking email folder on Fastmail (love2tap account).

The IMAP write itself is not exercised here; the pieces that decide what gets
written are: the folder name, the server path (BIG FUN sits beside INBOX on
Fastmail, with '/' as the delimiter), and the Keychain-backed credentials.
"""

import unittest
from datetime import datetime

import dj_core
from gig_booking_manager import email_folder_name, email_folder_path, folder_create_outcome, parse_list_delimiter


def booking(client="Taylor and Will", planner=False, date="2027-01-10"):
    d = datetime.strptime(date, "%Y-%m-%d")
    return {"date": d, "year": d.year, "client_display": client, "has_planner": planner}


class TestEmailFolderName(unittest.TestCase):
    def test_mm_dd_yy_colon_names(self):
        self.assertEqual(email_folder_name(booking()), "01-10-27: Taylor and Will")

    def test_planner_suffix(self):
        self.assertEqual(email_folder_name(booking(planner=True)), "01-10-27: Taylor and Will (planner)")


class TestEmailFolderPath(unittest.TestCase):
    def test_beside_inbox_with_server_delimiter(self):
        self.assertEqual(email_folder_path(2027, "01-10-27: Taylor and Will", "/"),
                         "BIG FUN/2027/01-10-27: Taylor and Will")

    def test_dot_delimiter(self):
        self.assertEqual(email_folder_path(2027, "x", "."), "BIG FUN.2027.x")


class TestLoadImapCredentials(unittest.TestCase):
    def test_missing_keychain_entry_is_none(self):
        self.assertIsNone(dj_core.load_imap_credentials(get_password=lambda: None))
        self.assertIsNone(dj_core.load_imap_credentials(get_password=lambda: ""))

    def test_fastmail_host_and_login(self):
        c = dj_core.load_imap_credentials(get_password=lambda: "secret")
        self.assertEqual(c["host"], "imap.fastmail.com")
        self.assertEqual(c["port"], 993)
        self.assertEqual(c["username"], "paul@love2tap.com")
        self.assertEqual(c["password"], "secret")


class TestParseListDelimiter(unittest.TestCase):
    """The hierarchy delimiter comes from the server's LIST reply, which Fastmail
    sends with an unquoted name; the old parser needed quotes and fell back to '.',
    which created a top-level folder literally named 'BIG FUN.2027.x' (2026-11-01)."""

    def test_fastmail_unquoted_name(self):
        self.assertEqual(parse_list_delimiter(b'(\\HasNoChildren) "/" INBOX'), "/")

    def test_fastmail_root_query(self):
        self.assertEqual(parse_list_delimiter(b'(\\Noselect) "/" ""'), "/")

    def test_quoted_name_dot_delimiter(self):
        self.assertEqual(parse_list_delimiter('(\\HasNoChildren) "." "INBOX"'), ".")

    def test_nil_or_garbage_is_none(self):
        self.assertIsNone(parse_list_delimiter(b'(\\Noinferiors) NIL INBOX'))
        self.assertIsNone(parse_list_delimiter(b""))
        self.assertIsNone(parse_list_delimiter(None))


class TestFolderCreateOutcome(unittest.TestCase):
    """CREATE replies: Fastmail says it in words, Bluehost used a response code."""

    def test_ok_is_created(self):
        self.assertEqual(folder_create_outcome("OK", [b"Completed"]), "created")

    def test_fastmail_already_exists_in_words(self):
        self.assertEqual(folder_create_outcome("NO", [b"Mailbox already exists"]), "exists")

    def test_bluehost_alreadyexists_code(self):
        self.assertEqual(folder_create_outcome("NO", [b"[ALREADYEXISTS] Mailbox exists"]), "exists")

    def test_other_failure_is_none(self):
        self.assertIsNone(folder_create_outcome("NO", [b"Permission denied"]))
        self.assertIsNone(folder_create_outcome("NO", [None]))
        self.assertIsNone(folder_create_outcome("BAD", []))


if __name__ == "__main__":
    unittest.main()
