#!/usr/bin/env python3
"""
Tests for Book Event's music-link step.

Book Event hands the FileMaker page it already read to dj-prep's `music`
command, so the couple link is on the clipboard before the confirmation email
is written. dj-prep does the work (tokens, folder, upload); these tests cover
when Book Event asks for it, what it asks for, and that a failure there never
fails the booking.
"""

import subprocess
import unittest

from gig_booking_manager import DJ_PREP_RUNNER, make_music_link, wants_music_link


def booking(dj="Paul", event_type="Wedding"):
    return {"dj_short_name": dj, "event_type": event_type}


class FakeRun:
    def __init__(self, returncode=0, raises=None):
        self.returncode = returncode
        self.raises = raises
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode)


class TestWantsMusicLink(unittest.TestCase):
    def test_paul_wedding(self):
        self.assertTrue(wants_music_link(booking()))

    def test_blank_event_type_counts_as_wedding(self):
        self.assertTrue(wants_music_link(booking(event_type="")))

    def test_other_dj(self):
        self.assertFalse(wants_music_link(booking(dj="Henry")))

    def test_not_a_wedding(self):
        self.assertFalse(wants_music_link(booking(event_type="Corporate")))
        self.assertFalse(wants_music_link(booking(event_type="Setup")))


class TestMakeMusicLink(unittest.TestCase):
    def test_runs_dj_prep_music_on_the_same_page(self):
        run = FakeRun()
        line = make_music_link("/tmp/page.html", run=run)
        self.assertEqual(run.calls, [[DJ_PREP_RUNNER, "music", "--fm-html", "/tmp/page.html"]])
        self.assertIn("clipboard", line)

    def test_dry_run_runs_nothing(self):
        run = FakeRun()
        line = make_music_link("/tmp/page.html", dry_run=True, run=run)
        self.assertEqual(run.calls, [])
        self.assertIn("would", line)

    def test_test_mode_stages_without_uploading(self):
        run = FakeRun()
        make_music_link("/tmp/page.html", test_mode=True, run=run)
        self.assertEqual(run.calls[0][-1], "--stage-only")

    def test_no_page_html_skips(self):
        run = FakeRun()
        line = make_music_link(None, run=run)
        self.assertEqual(run.calls, [])
        self.assertIn("Music link", line)

    def test_failure_is_reported_not_raised(self):
        line = make_music_link("/tmp/page.html", run=FakeRun(returncode=1))
        self.assertIn("FAILED", line)
        self.assertIn("Music link", line)

    def test_crash_is_reported_not_raised(self):
        line = make_music_link("/tmp/page.html", run=FakeRun(raises=subprocess.TimeoutExpired("x", 1)))
        self.assertIn("FAILED", line)


if __name__ == "__main__":
    unittest.main()
