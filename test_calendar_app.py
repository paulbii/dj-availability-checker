#!/usr/bin/env python3
"""
Tests for calendar_app: the one place the Stream Deck buttons talk to Calendar.app.

subprocess.run, time.sleep and the clock are all injected, so these tests never
launch Calendar.app or wait. The fake `run` answers pgrep from `.running`,
records `open` launches, and answers osascript from a queue of replies.
"""

import subprocess
import unittest
from datetime import datetime
from unittest.mock import MagicMock

import calendar_app
from calendar_app import CalendarApp, CalendarAppError

# The exact text Calendar.app returned on 2026-11-03 (curly apostrophe and all).
MISS = 'Calendar got an error: Can’t get event id "u1" of calendar "Gigs". (-1728)'
OK = ("", 0, "")


def result(stdout="", returncode=0, stderr=""):
    r = MagicMock()
    r.stdout, r.returncode, r.stderr = stdout, returncode, stderr
    return r


class FakeRun:
    def __init__(self, running=True, replies=()):
        self.running = running
        self.replies = list(replies)     # (stdout, returncode, stderr) or "TIMEOUT"
        self.scripts = []                # every osascript body, in order
        self.timeouts = []               # the timeout kwarg of every osascript call
        self.open_cmds = []

    def __call__(self, cmd, **kw):
        if cmd[0] == "pgrep":
            return result(returncode=0 if self.running else 1)
        if cmd[0] == "open":
            self.open_cmds.append(cmd)
            self.running = True
            return result()
        assert cmd[0] == "osascript", cmd
        self.scripts.append(cmd[2])
        self.timeouts.append(kw.get("timeout"))
        reply = self.replies.pop(0) if self.replies else OK
        if reply == "TIMEOUT":
            raise subprocess.TimeoutExpired(cmd="osascript", timeout=kw.get("timeout"))
        return result(*reply)


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


def make_app(run, clock=None, sleeps=None, advance=0):
    """An app whose sleep records to `sleeps` and moves the clock by `advance`."""
    clock = clock or Clock()

    def sleep(seconds):
        if sleeps is not None:
            sleeps.append(seconds)
        clock.now += advance

    return CalendarApp(run=run, sleep=sleep, clock=clock)


class TestRunScript(unittest.TestCase):

    def test_success_returns_stdout_inside_the_gigs_envelope(self):
        run = FakeRun(replies=[("[HK] BACKUP DJ\n", 0, "")])
        out = make_app(run).run_script('get summary of event id "u1"')
        self.assertEqual(out, "[HK] BACKUP DJ")
        self.assertEqual(len(run.scripts), 1)
        self.assertIn('tell application "Calendar"', run.scripts[0])
        self.assertIn('tell calendar "Gigs"', run.scripts[0])
        self.assertIn('get summary of event id "u1"', run.scripts[0])
        self.assertNotIn("whose", run.scripts[0])

    def test_default_timeout_is_60s(self):
        run = FakeRun()
        make_app(run).run_script("x")
        self.assertEqual(run.timeouts, [60])

    def test_already_running_is_not_launched(self):
        run = FakeRun(running=True)
        app = make_app(run)
        app.run_script("x")
        self.assertEqual(run.open_cmds, [])
        self.assertIsNone(app.launched_at)

    def test_not_running_is_launched_hidden_before_the_script(self):
        run = FakeRun(running=False)
        clock = Clock(now=500.0)
        app = make_app(run, clock=clock)
        app.run_script("x")
        self.assertEqual(len(run.open_cmds), 1)
        self.assertEqual(run.open_cmds[0][0], "open")
        self.assertIn("-g", run.open_cmds[0])
        self.assertIn("-j", run.open_cmds[0])
        self.assertIn("Calendar", run.open_cmds[0])
        self.assertEqual(app.launched_at, 500.0)
        self.assertEqual(len(run.scripts), 1)

    def test_nonzero_exit_raises_with_the_osascript_error(self):
        run = FakeRun(replies=[("", 1, "Calendar got an error: Not authorized. (-1743)")])
        with self.assertRaises(CalendarAppError) as cm:
            make_app(run).run_script("x")
        self.assertIn("Not authorized", str(cm.exception))

    def test_timeout_raises_and_names_the_seconds(self):
        run = FakeRun(replies=["TIMEOUT"])
        with self.assertRaises(CalendarAppError) as cm:
            make_app(run).run_script("x")
        self.assertIn("60s", str(cm.exception))

    def test_event_id_miss_after_our_cold_launch_is_retried_until_it_resolves(self):
        # The 2026-11-03 incident: launched by us, the first lookups miss, then resolve.
        run = FakeRun(running=False, replies=[("", 1, MISS), ("", 1, MISS), ("ok", 0, "")])
        sleeps = []
        out = make_app(run, sleeps=sleeps).run_script("x")
        self.assertEqual(out, "ok")
        self.assertEqual(len(run.scripts), 3)
        self.assertEqual(sleeps, [calendar_app.RETRY_INTERVAL] * 2)

    def test_event_id_miss_when_calendar_was_already_running_is_not_retried(self):
        # Calendar.app has been up: a missing id is really missing (deleted by hand).
        run = FakeRun(running=True, replies=[("", 1, MISS)])
        sleeps = []
        with self.assertRaises(CalendarAppError) as cm:
            make_app(run, sleeps=sleeps).run_script("x")
        self.assertIn("-1728", str(cm.exception))
        self.assertEqual(len(run.scripts), 1)
        self.assertEqual(sleeps, [])

    def test_event_id_miss_past_the_load_window_raises(self):
        # Each retry moves the clock 50s; the window is 90s: launch at 100,
        # misses at 100 and 150 retry, the miss at 200 is past the window.
        run = FakeRun(running=False, replies=[("", 1, MISS)] * 5)
        sleeps = []
        with self.assertRaises(CalendarAppError):
            make_app(run, sleeps=sleeps, advance=50).run_script("x")
        self.assertEqual(len(run.scripts), 3)
        self.assertEqual(len(sleeps), 2)

    def test_other_errors_during_load_are_not_retried(self):
        run = FakeRun(running=False, replies=[("", 1, "Calendar got an error: Not authorized. (-1743)")])
        sleeps = []
        with self.assertRaises(CalendarAppError):
            make_app(run, sleeps=sleeps).run_script("x")
        self.assertEqual(len(run.scripts), 1)
        self.assertEqual(sleeps, [])

    def test_calendar_name_is_configurable(self):
        run = FakeRun()
        CalendarApp(calendar_name="Unavailable", run=run, sleep=lambda s: None,
                    clock=Clock()).run_script("x")
        self.assertIn('tell calendar "Unavailable"', run.scripts[0])


class TestEsc(unittest.TestCase):

    def test_double_quotes_and_backslashes_are_escaped(self):
        self.assertEqual(calendar_app.esc('Say "Hi" \\ now'), 'Say \\"Hi\\" \\\\ now')


if __name__ == "__main__":
    unittest.main(verbosity=2)
