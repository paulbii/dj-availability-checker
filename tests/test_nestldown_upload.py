#!/usr/bin/env python3
"""
Upload step of nestldown_roster.py against a fake FTP server.

iPage sometimes takes the whole file and then closes the control connection
before it sends "226 Transfer complete" (seen on the assignments page,
2026-11-12). That is a finished upload, not a failure, so a failed attempt is
checked against the server and only retried when the page is not there.
"""

import ftplib
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nestldown_roster as nr

PAGE = "<html>roster Ⓟ</html>"


class FakeServer:
    def __init__(self, stor_script):
        self.remote = None
        self.stor_script = list(stor_script)   # "ok" | "drop_after" | "drop_before" | "perm"

    def connect(self, *args, **kwargs):
        return FakeFTP(self)


class FakeFTP:
    def __init__(self, server):
        self.server = server

    def login(self, user, pw):
        pass

    def cwd(self, path):
        pass

    def storbinary(self, cmd, fp):
        step = self.server.stor_script.pop(0)
        if step == "perm":
            raise ftplib.error_perm("550 Permission denied")
        if step == "drop_before":
            raise EOFError
        self.server.remote = fp.read()
        if step == "drop_after":
            raise EOFError

    def retrbinary(self, cmd, callback):
        if self.server.remote is None:
            raise ftplib.error_perm("550 No such file")
        callback(self.server.remote)

    def quit(self):
        pass


class UploadHtmlTest(unittest.TestCase):
    def upload(self, script):
        server = FakeServer(script)
        with mock.patch.object(nr.ftplib, "FTP", server.connect), \
             mock.patch.object(nr.keyring, "get_password", return_value="x"), \
             mock.patch.object(nr.time, "sleep"):
            ok = nr.upload_html(PAGE)
        return server, ok

    def test_clean_upload(self):
        server, ok = self.upload(["ok"])
        self.assertTrue(ok)
        self.assertEqual(server.remote, PAGE.encode("utf-8"))

    def test_connection_dropped_after_the_file_arrived_is_success(self):
        server, ok = self.upload(["drop_after"])
        self.assertTrue(ok)
        self.assertEqual(server.stor_script, [])

    def test_connection_dropped_before_the_file_arrived_retries(self):
        server, ok = self.upload(["drop_before", "ok"])
        self.assertTrue(ok)
        self.assertEqual(server.remote, PAGE.encode("utf-8"))

    def test_gives_up_after_three_attempts(self):
        server, ok = self.upload(["drop_before"] * 3)
        self.assertFalse(ok)
        self.assertEqual(server.stor_script, [])

    def test_permission_error_is_not_retried(self):
        server, ok = self.upload(["perm", "ok"])
        self.assertFalse(ok)
        self.assertEqual(server.stor_script, ["ok"])


if __name__ == "__main__":
    unittest.main()
