#!/usr/bin/env python3
"""
Calendar.app writes for the Stream Deck buttons.

Book Event, Assign DJ and Cancel Booking find events over CalDAV
(calendar_read.py, under a second) and then edit them in Calendar.app by
`event id`, the only path that carries attendee invitations. This module is
the one place that builds and runs those osascripts, so three things are
decided once:

1. The launch guard. `tell application "Calendar"` starts the app when it is
   not running, and an `event id` lookup then fails with -1728 until the CalDAV
   store has loaded. Measured 2026-11-03: Calendar launched 09:30:09, the lookup
   failed at 09:30:31, the same id resolved two minutes later. Here the app is
   launched hidden *before* the script, and an `event id` miss is retried for
   LOAD_WINDOW seconds, but only when this process did the launching. If
   Calendar.app was already up, a missing id is really missing.
2. One timeout and one exception type (CalendarAppError) for every caller.
3. One osascript call per event, so a retry never repeats a write that
   already happened.

Nothing here runs a `whose` clause: that walks every event since 1989 and
took 30s to 2 minutes (see docs/superpowers/plans/2026-10-04-calendar-reads-via-caldav.md).
"""

import subprocess
import time

CALENDAR_NAME = "Gigs"
SCRIPT_TIMEOUT = 60      # one event-id edit answers in well under a second; a cold launch in ~25s
LAUNCH_TIMEOUT = 30
LOAD_WINDOW = 90         # seconds after a cold launch during which an event-id miss is retried
RETRY_INTERVAL = 3


class CalendarAppError(Exception):
    """Calendar.app refused or failed an edit. The message is the osascript error text."""


def esc(text):
    """Escape a value for use inside an AppleScript string literal."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def is_running(run=subprocess.run):
    return run(["pgrep", "-x", "Calendar"], capture_output=True, text=True).returncode == 0


def launch(run=subprocess.run):
    # -g: do not bring it to the front; -j: launch hidden. The buttons are
    # pressed with FileMaker on screen and nothing should steal focus.
    run(["open", "-g", "-j", "-a", "Calendar"], capture_output=True, text=True, timeout=LAUNCH_TIMEOUT)


class CalendarApp:
    """One per button run. Remembers whether it launched Calendar.app itself."""

    def __init__(self, calendar_name=CALENDAR_NAME, run=subprocess.run,
                 sleep=time.sleep, clock=time.monotonic):
        self.calendar_name = calendar_name
        self._run = run
        self._sleep = sleep
        self._clock = clock
        self.launched_at = None   # set only when this object started Calendar.app

    # -- launch guard ---------------------------------------------------------

    def ensure_running(self):
        if not is_running(self._run):
            launch(self._run)
            self.launched_at = self._clock()

    def _still_loading(self):
        return self.launched_at is not None and self._clock() - self.launched_at < LOAD_WINDOW

    @staticmethod
    def _event_id_miss(stderr):
        return "-1728" in stderr and "event id" in stderr

    # -- the one osascript runner --------------------------------------------

    def run_script(self, body, timeout=SCRIPT_TIMEOUT):
        """
        Run `body` inside `tell application "Calendar" / tell calendar <name>`.
        Returns stdout stripped. Raises CalendarAppError on any failure.
        """
        self.ensure_running()
        script = (
            'tell application "Calendar"\n'
            f'    tell calendar "{esc(self.calendar_name)}"\n'
            f'{body}\n'
            '    end tell\n'
            'end tell'
        )
        while True:
            try:
                result = self._run(["osascript", "-e", script],
                                   capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise CalendarAppError(f"Calendar.app did not answer within {timeout}s")
            if result.returncode == 0:
                return result.stdout.strip()
            err = result.stderr.strip() or f"osascript exit {result.returncode}"
            if self._event_id_miss(err) and self._still_loading():
                self._sleep(RETRY_INTERVAL)
                continue
            raise CalendarAppError(err)
