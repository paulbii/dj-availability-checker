# Calendar.app Launch Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One shared Calendar.app write layer for the three Stream Deck buttons (Book Event, Assign DJ, Cancel Booking) that survives Calendar.app being closed when the button is pressed, plus a warning dialog that never ends a run when it goes unanswered.

**Architecture:** A new module `calendar_app.py` owns every osascript call that edits the Gigs calendar: it launches Calendar.app hidden if it is not running, wraps each edit in the `tell application "Calendar" / tell calendar "Gigs"` envelope, runs one osascript per event so a retry never repeats a write, and retries an `event id` miss (-1728) only while Calendar.app is still loading after a launch *this process* started. The three buttons keep their own flow and result protocols; they just stop building AppleScript themselves. `show_warning_dialog` in `gig_booking_manager.py` gets the same long timeout the other dialogs have and swallows expiry.

**Tech Stack:** Python 3.13 (`.venv/bin/python`), `unittest` (no pytest in the venv), `subprocess` + `osascript`, `calendar_read.py` for CalDAV reads (unchanged).

**Why (the incident):** 2026-11-03 09:30, Cancel Booking on Netta and Gawesha, Thu 6/17/27. Calendar.app was not running. The script's `tell application "Calendar"` launched it at 09:30:09; the `event id` lookup ran before the CalDAV store had loaded and failed with `Can't get event id "103B6070-…" of calendar "Gigs". (-1728)`. Both ids resolved fine two minutes later. The matrix was already cleared, and the warning dialog's 60s timeout then raised and ended the run before the backup event, the turned-away check and the booking log form. The by-id path was committed 2026-11-02 (`84db2dd`); this was its first live run with Calendar.app closed. Book Event's hold delete and Assign DJ's retitle carry the same bare lookup.

**Test commands (run from the repo root):**
- Root suites: `.venv/bin/python -m unittest test_cancel_booking test_gig_booking_manager test_calendar_app -v`
- Assign DJ: `.venv/bin/python -m unittest tests.test_assign_dj -v`
- Baselines before this plan: 153 (cancel + manager), 54 (assign).

**Repo hygiene:** the working tree already has unrelated uncommitted changes (`nestldown_roster.py`, `com.bigfundj.nestldown-roster.plist`, the three `.scpt` files, `archive/automator-apps/`). Never `git add -A`. Every commit below names its files.

---

## File Structure

| File | Role |
|---|---|
| Create `calendar_app.py` | The Calendar.app write layer: `CALENDAR_NAME`, `CalendarAppError`, `CalendarApp` (launch guard, `run_script`, `delete_events`, `retitle_and_invite`, `create_event`). |
| Create `test_calendar_app.py` | Unit tests for the module with a fake `subprocess.run`, fake clock, fake sleep. |
| Modify `cancel_booking.py` | Replace `_run_calendar_delete` / `_delete_by_id_script` / `CALENDAR_TIMEOUT` with `CalendarApp.delete_events`; keep the `(status, payload)` result protocol. |
| Modify `test_cancel_booking.py` | Delete tests inject a fake app instead of patching `subprocess.run`. |
| Modify `gig_booking_manager.py` | Import `CALENDAR_NAME` from `calendar_app`; `delete_hold_calendar_event` and the two create functions go through `CalendarApp`; the hold-release call site shows a dialog on failure; `show_warning_dialog` stops raising on timeout. |
| Modify `test_gig_booking_manager.py` | Hold-delete tests use a fake app; new tests for the create functions and the dialog timeout. |
| Modify `assign_dj.py` | `modify_script` / `run_osascript` replaced by `CalendarApp.retitle_and_invite`; `assign(..., osa=)` becomes `assign(..., app=)`. |
| Modify `tests/test_assign_dj.py` | `FakeOsa` becomes `FakeApp` recording `(uid, title, invitee)` edits. |
| Modify `CHANGELOG.md`, `DJ_SYSTEM_REFERENCE.md` | Record the change and the new file. |

---

### Task 0: Commit the nurture-step removal already in the tree

`cancel_booking.py` has an uncommitted change from earlier today (step 6, the Nurture Tracker cleanup, removed; steps renumbered /5). Commit it alone so Task 3's diff is only this plan's work.

**Files:**
- Commit: `cancel_booking.py`

- [ ] **Step 1: Confirm the diff is only the nurture removal**

Run: `git diff cancel_booking.py | grep "^+" | grep -v "^+++" | grep -v "/5\]"`
Expected: no output (the only added lines are the five `[n/5]` renumbers). Then `git diff cancel_booking.py | grep "^@@"` shows two hunks: the removed `[6/6]` block in `run`, and the removed `_cancel_nurture_emails` function (its body lines do not all say "nurture"; that is fine).

- [ ] **Step 2: Run the suite**

Run: `.venv/bin/python -m unittest test_cancel_booking`
Expected: `Ran 26 tests` … `OK`

- [ ] **Step 3: Commit**

```bash
git add cancel_booking.py
git commit -m "Cancel Booking: drop the nurture-email cleanup step

The Nurture Tracker was never put into service (no sender runs), so the
step only cost a Sheets call per cancellation. Steps renumbered 1-5.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 1: `calendar_app.py` — `run_script` and the launch guard

**Files:**
- Create: `calendar_app.py`
- Create: `test_calendar_app.py`

- [ ] **Step 1: Write the failing tests**

Create `test_calendar_app.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m unittest test_calendar_app -v 2>&1 | tail -3`
Expected: `ModuleNotFoundError: No module named 'calendar_app'`

- [ ] **Step 3: Write `calendar_app.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m unittest test_calendar_app -v 2>&1 | tail -3`
Expected: `Ran 12 tests` … `OK`

- [ ] **Step 5: Commit**

```bash
git add calendar_app.py test_calendar_app.py
git commit -m "calendar_app: Calendar.app runner with a launch guard

Launches Calendar.app hidden when it is not running and retries an
event-id miss (-1728) while the store is still loading after a launch
this process started. 2026-11-03: Cancel Booking's first live run with
Calendar closed failed on exactly that race.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `calendar_app.py` — the three edits

**Files:**
- Modify: `calendar_app.py` (append to the `CalendarApp` class)
- Modify: `test_calendar_app.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `test_calendar_app.py`, above the `if __name__` block:

```python
class TestDeleteEvents(unittest.TestCase):

    def test_one_osascript_per_event_and_the_count_back(self):
        run = FakeRun()
        n = make_app(run).delete_events(["u1", "u2"])
        self.assertEqual(n, 2)
        self.assertEqual(len(run.scripts), 2)
        self.assertIn('delete (event id "u1")', run.scripts[0])
        self.assertNotIn('"u2"', run.scripts[0])
        self.assertIn('delete (event id "u2")', run.scripts[1])

    def test_empty_list_touches_nothing(self):
        run = FakeRun()
        self.assertEqual(make_app(run).delete_events([]), 0)
        self.assertEqual(run.scripts, [])

    def test_failure_on_the_second_event_raises_after_the_first_was_deleted(self):
        run = FakeRun(replies=[OK, ("", 1, "boom")])
        with self.assertRaises(CalendarAppError):
            make_app(run).delete_events(["u1", "u2"])
        self.assertEqual(len(run.scripts), 2)


class TestRetitleAndInvite(unittest.TestCase):

    def test_script_sets_summary_and_adds_the_attendee(self):
        run = FakeRun()
        make_app(run).retitle_and_invite("u1", "[HK] Cienna and Joseph", "henry@bigfundj.com")
        self.assertEqual(len(run.scripts), 1)
        s = run.scripts[0]
        self.assertIn('set ev to event id "u1"', s)
        self.assertIn('set summary of ev to "[HK] Cienna and Joseph"', s)
        self.assertIn('make new attendee at end of attendees with properties {email:"henry@bigfundj.com"}', s)

    def test_title_quotes_are_escaped(self):
        run = FakeRun()
        make_app(run).retitle_and_invite("u1", '[PB] The "Big" Day', "paul@bigfundj.com")
        self.assertIn('set summary of ev to "[PB] The \\"Big\\" Day"', run.scripts[0])


class TestCreateEvent(unittest.TestCase):

    START = datetime(2027, 6, 17, 17, 0)
    END = datetime(2027, 6, 17, 22, 0)

    def test_timed_event_with_location_and_invitee(self):
        run = FakeRun()
        make_app(run).create_event("[WM] Netta and Gawesha", self.START, self.END,
                                   location="Nestldown, 1 Nestldown Dr, Los Gatos, CA 95033",
                                   invitee_email="woody@bigfundj.com")
        s = run.scripts[0]
        self.assertIn('make new event with properties {summary:"[WM] Netta and Gawesha", '
                      'location:"Nestldown, 1 Nestldown Dr, Los Gatos, CA 95033", '
                      'start date:date "June 17, 2027 05:00:00 PM", '
                      'end date:date "June 17, 2027 10:00:00 PM"}', s)
        self.assertIn('tell newEvent', s)
        self.assertIn('{email:"woody@bigfundj.com"}', s)

    def test_timed_event_without_invitee_has_no_attendee_block(self):
        run = FakeRun()
        make_app(run).create_event("[UP] Netta and Gawesha", self.START, self.END, location="Nestldown")
        self.assertNotIn("attendee", run.scripts[0])

    def test_allday_event(self):
        run = FakeRun()
        make_app(run).create_event("[HK] BACKUP DJ", self.START, None, allday=True,
                                   invitee_email="henry@bigfundj.com")
        s = run.scripts[0]
        self.assertIn('{summary:"[HK] BACKUP DJ", start date:date "June 17, 2027 12:00:00 AM", '
                      'end date:date "June 17, 2027 11:59:00 PM", allday event:true}', s)
        self.assertNotIn("location", s)
        self.assertIn('{email:"henry@bigfundj.com"}', s)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m unittest test_calendar_app 2>&1 | tail -3`
Expected: `FAILED (errors=8)` with `AttributeError: 'CalendarApp' object has no attribute 'delete_events'` (and the other two names).

- [ ] **Step 3: Append the three methods to `CalendarApp`**

```python
    # -- the edits the buttons need ------------------------------------------

    def delete_events(self, uids):
        """Delete each uid in its own osascript. Returns how many were deleted.
        Raises on the first failure; the ones before it are gone."""
        count = 0
        for uid in uids:
            self.run_script(f'        delete (event id "{esc(uid)}")')
            count += 1
        return count

    def retitle_and_invite(self, uid, title, invitee_email):
        self.run_script(
            f'        set ev to event id "{esc(uid)}"\n'
            f'        set summary of ev to "{esc(title)}"\n'
            f'        tell ev\n'
            f'            make new attendee at end of attendees with properties {{email:"{esc(invitee_email)}"}}\n'
            f'        end tell'
        )

    def create_event(self, title, start, end, location="", allday=False, invitee_email=None):
        """`start`/`end` are datetimes. An all-day event covers the day of `start`; `end` is ignored."""
        if allday:
            day = start.strftime("%B %d, %Y")
            when = (f'start date:date "{day} 12:00:00 AM", '
                    f'end date:date "{day} 11:59:00 PM", allday event:true')
        else:
            when = (f'start date:date "{start.strftime("%B %d, %Y %I:%M:%S %p")}", '
                    f'end date:date "{end.strftime("%B %d, %Y %I:%M:%S %p")}"')
        props = f'summary:"{esc(title)}", '
        if location:
            props += f'location:"{esc(location)}", '
        props += when
        body = f'        set newEvent to make new event with properties {{{props}}}'
        if invitee_email:
            body += (
                '\n        tell newEvent\n'
                f'            make new attendee at end of attendees with properties {{email:"{esc(invitee_email)}"}}\n'
                '        end tell'
            )
        self.run_script(body)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m unittest test_calendar_app 2>&1 | tail -3`
Expected: `Ran 20 tests` … `OK`

- [ ] **Step 5: Commit**

```bash
git add calendar_app.py test_calendar_app.py
git commit -m "calendar_app: delete, retitle-and-invite, create

One osascript per event; the AppleScript the three buttons used to build
themselves, now in one place.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Cancel Booking deletes through `CalendarApp`

**Files:**
- Modify: `cancel_booking.py:56-198` (the calendar section)
- Modify: `test_cancel_booking.py` (classes `TestDeleteBookingEvent`, `TestDeleteBackupEvent`)

- [ ] **Step 1: Rewrite the two delete test classes**

In `test_cancel_booking.py`, replace the import block that reads `from cancel_booking import (` … `)` so it also imports the new names, add a fake app, and replace the whole of `TestDeleteBookingEvent` and `TestDeleteBackupEvent` (everything from `class TestDeleteBookingEvent` up to `class TestAskRemoveBackupTimeout`) with the code below. Keep `fake_result`, `DATE`, `TITLE`, `booking_stub`, `listing_of`, `broken_listing` and `TestAcceptableEventTitles` as they are.

Import block becomes:

```python
import cancel_booking
from calendar_app import CalendarAppError
from cancel_booking import (
    acceptable_event_titles,
    delete_booking_calendar_event,
    delete_backup_calendar_event,
)
```

Add after `broken_listing`:

```python
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
```

The two classes:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m unittest test_cancel_booking 2>&1 | tail -3`
Expected: errors of the form `TypeError: delete_booking_calendar_event() got an unexpected keyword argument 'app'`.

- [ ] **Step 3: Rewrite the calendar section of `cancel_booking.py`**

Add to the imports (after `import calendar_read`):

```python
from calendar_app import CalendarApp, CalendarAppError
```

Delete everything from the comment block `# ── Calendar deletion ───…` (line 56) through the end of `_delete_by_id_script` (line 137), that is `CALENDAR_TIMEOUT`, `_run_calendar_delete`, `acceptable_event_titles` and `_delete_by_id_script`, and replace it with:

```python
# ── Calendar deletion ────────────────────────────────────────────────────────
#
# The day's events are read over CalDAV (under a second) and the matching ones
# deleted in Calendar.app by `event id` through calendar_app.CalendarApp, which
# also launches Calendar.app when it is closed and waits for it to load. The
# earlier whose-clause scan walked the entire Gigs calendar: 30s was not
# enough, and on 2026-07-29 the delete timed out and was misreported as "no
# events found." On 2026-11-03 a bare `event id` lookup raced a cold launch.


def _delete(uids, app):
    """
    Delete the uids and speak the result protocol:
        ("deleted", n) | ("error", msg)
    A Calendar.app failure is ALWAYS ("error", ...) — never "not_found".
    """
    app = app or CalendarApp()
    try:
        return ("deleted", app.delete_events(uids))
    except CalendarAppError as e:
        return ("error", str(e))


def acceptable_event_titles(booking):
    """
    Every title the booking's calendar event may legitimately carry.

    Always the title gig_booking_manager would create today. When the client
    reads "A and B", also the "B and A" variant: the 10/16/2026 cancellation
    showed FileMaker's name order can differ from the order at booking time
    ("Jaylin and Julie" vs the event's "Julie and Jaylin"). Names with more
    than one "and" are left alone — permuting them would guess.
    """
    titles = [primary_event_title(booking)]

    parts = booking["client_display"].split(" and ")
    if len(parts) == 2:
        swapped = dict(booking)
        swapped["client_display"] = f"{parts[1]} and {parts[0]}"
        titles.append(primary_event_title(swapped))

    return titles
```

Then in `delete_booking_calendar_event`:
- signature becomes `def delete_booking_calendar_event(date_obj, initials_bracket, expected_titles, fetch_day=calendar_read.fetch_day_events, app=None):`
- docstring line `Returns (status, payload) per _run_calendar_delete.` becomes `Returns (status, payload) per _delete, plus ("not_found", 0) and ("ambiguous", titles).`
- `return _run_calendar_delete(_delete_by_id_script(exact))` becomes `return _delete(exact, app)`

And in `delete_backup_calendar_event`:
- signature becomes `def delete_backup_calendar_event(date_obj, backup_dj, fetch_day=calendar_read.fetch_day_events, app=None):`
- docstring `Returns (status, payload) per _run_calendar_delete.` becomes `Returns (status, payload) per _delete, or ("not_found", 0).`
- `return _run_calendar_delete(_delete_by_id_script(uids))` becomes `return _delete(uids, app)`

In `CancelBookingManager.run`, both real calls share one app so a launch is counted once. Right after `calendar_failed = False` in step 5 add:

```python
        app = None if self.dry_run else CalendarApp()
```

and change the two calls to `delete_booking_calendar_event(date_obj, initials_bracket, expected_titles, app=app)` and `delete_backup_calendar_event(date_obj, backup_dj, app=app)`.

Check nothing else referenced the removed names:

Run: `grep -n "_run_calendar_delete\|_delete_by_id_script\|CALENDAR_TIMEOUT" *.py tests/*.py`
Expected: no output.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m unittest test_cancel_booking 2>&1 | tail -3`
Expected: `Ran 22 tests` … `OK` (26 before: 11 booking-delete tests replace 14 and 5 backup-delete tests replace 6; the osascript protocol tests, the timeout tests and the 180s check now live in `test_calendar_app`). `subprocess`, `patch`, `MagicMock` and `fake_result` are now unused in `test_cancel_booking.py`; remove them.

Then a dry run, which must not touch Calendar.app at all:

Run: `.venv/bin/python cancel_booking.py sample_bookings/sample_regular_booking.json --dry-run 2>&1 | grep -E "\[5/5\]|Would delete|SUMMARY"`
Expected: the `[5/5]` line, a `[DRY RUN] Would delete event titled "[HK] Anderson & Martinez"` line, and the summary. Calendar.app's process start time must be unchanged: `ps -o lstart= -p "$(pgrep -x Calendar)"` before and after.

- [ ] **Step 5: Commit**

```bash
git add cancel_booking.py test_cancel_booking.py
git commit -m "Cancel Booking: delete through calendar_app

Same result protocol; the AppleScript, timeout and launch guard now live
in one place.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Book Event: hold delete and event creation through `CalendarApp`

**Files:**
- Modify: `gig_booking_manager.py:76` (`CALENDAR_NAME`), `:826-960` (create + hold delete), `:1585-1597` (hold-release call site), `:1761`, `:1777` (create calls)
- Modify: `test_gig_booking_manager.py` (class `TestDeleteHoldCalendarEvent`, plus a new class)

- [ ] **Step 1: Write the failing tests**

In `test_gig_booking_manager.py`, replace the whole `TestDeleteHoldCalendarEvent` class with:

```python
class FakeCalendarApp:
    """Stands in for calendar_app.CalendarApp; records every edit."""

    def __init__(self, fail=None):
        self.deleted = []
        self.created = []
        self.fail = fail

    def delete_events(self, uids):
        if self.fail:
            from calendar_app import CalendarAppError
            raise CalendarAppError(self.fail)
        self.deleted.extend(uids)
        return len(uids)

    def create_event(self, title, start, end, location="", allday=False, invitee_email=None):
        if self.fail:
            from calendar_app import CalendarAppError
            raise CalendarAppError(self.fail)
        self.created.append(dict(title=title, start=start, end=end, location=location,
                                 allday=allday, invitee_email=invitee_email))


class TestDeleteHoldCalendarEvent(unittest.TestCase):
    """RESERVED -> BOOKED removes the 'Hold to DJ' event: found over CalDAV,
    deleted in Calendar.app by id through CalendarApp."""

    DATE = datetime(2026, 9, 26)

    @staticmethod
    def listing_of(*pairs):
        return lambda calendar_name, day: list(pairs)

    def test_hold_found_is_deleted_by_id(self):
        import gig_booking_manager
        app = FakeCalendarApp()
        deleted = gig_booking_manager.delete_hold_calendar_event(
            self.DATE, "[PB]",
            fetch_day=self.listing_of(("u7", "[PB] Hold to DJ"), ("u1", "[PB] Chen and Lee")), app=app)
        self.assertTrue(deleted)
        self.assertEqual(app.deleted, ["u7"])

    def test_no_hold_touches_calendar_app_not_at_all(self):
        import gig_booking_manager
        app = FakeCalendarApp()
        deleted = gig_booking_manager.delete_hold_calendar_event(
            self.DATE, "[PB]", fetch_day=self.listing_of(("u8", "[HK] Hold to DJ")), app=app)
        self.assertFalse(deleted)
        self.assertEqual(app.deleted, [])

    def test_caldav_failure_is_false_and_writes_nothing(self):
        import gig_booking_manager
        from calendar_read import CalendarReadError
        app = FakeCalendarApp()
        def broken(calendar_name, day):
            raise CalendarReadError("server down")
        deleted = gig_booking_manager.delete_hold_calendar_event(self.DATE, "[PB]", fetch_day=broken, app=app)
        self.assertFalse(deleted)
        self.assertEqual(app.deleted, [])

    def test_calendar_app_failure_raises_instead_of_reading_as_no_hold(self):
        # Before 2026-11-03 this returned False and the booking carried on with
        # the hold still on the calendar and one log line nobody reads.
        import gig_booking_manager
        from calendar_app import CalendarAppError
        app = FakeCalendarApp(fail="Calendar.app did not answer within 60s")
        with self.assertRaises(CalendarAppError):
            gig_booking_manager.delete_hold_calendar_event(
                self.DATE, "[PB]", fetch_day=self.listing_of(("u7", "[PB] Hold to DJ")), app=app)


class TestCreateCalendarEvents(unittest.TestCase):
    """The two create functions build title, location and invitee and hand them
    to CalendarApp.create_event; the AppleScript itself is calendar_app's job."""

    def booking(self, dj="Woody"):
        initials = {"Woody": "WM", "Paul": "PB", "Unassigned": "UP"}[dj]
        return {
            "client_display": "Netta and Gawesha", "dj_initials_bracket": f"[{initials}]",
            "dj_short_name": dj, "has_planner": False, "event_type": "Wedding",
            "sound_type": "Standard Speakers", "venue_name": "Nestldown",
            "venue_street": "1 Nestldown Dr", "venue_city_state_zip": "Los Gatos, CA 95033",
            "dj2_full_name": "", "date": datetime(2027, 6, 17),
        }

    def test_timed_event_carries_title_location_and_dj_invite(self):
        import gig_booking_manager
        app = FakeCalendarApp()
        start, end = datetime(2027, 6, 17, 17, 0), datetime(2027, 6, 17, 22, 0)
        title = gig_booking_manager.create_timed_calendar_event(self.booking("Woody"), start, end, app=app)
        self.assertEqual(title, "[WM] Netta and Gawesha")
        self.assertEqual(app.created, [dict(
            title="[WM] Netta and Gawesha", start=start, end=end,
            location="Nestldown, 1 Nestldown Dr, Los Gatos, CA 95033",
            allday=False, invitee_email="woody@bigfundj.com")])

    def test_test_mode_invites_paul(self):
        import gig_booking_manager
        app = FakeCalendarApp()
        gig_booking_manager.create_timed_calendar_event(
            self.booking("Woody"), datetime(2027, 6, 17, 17), datetime(2027, 6, 17, 22),
            test_mode=True, app=app)
        self.assertEqual(app.created[0]["invitee_email"], "paul@bigfundj.com")

    def test_unassigned_booking_invites_nobody(self):
        import gig_booking_manager
        app = FakeCalendarApp()
        gig_booking_manager.create_timed_calendar_event(
            self.booking("Unassigned"), datetime(2027, 6, 17, 17), datetime(2027, 6, 17, 22), app=app)
        self.assertIsNone(app.created[0]["invitee_email"])

    def test_backup_event_is_allday_and_invites_the_backup(self):
        import gig_booking_manager
        app = FakeCalendarApp()
        title = gig_booking_manager.create_allday_backup_event(datetime(2027, 6, 17), "Henry", app=app)
        self.assertEqual(title, "[HK] BACKUP DJ")
        self.assertEqual(app.created[0]["title"], "[HK] BACKUP DJ")
        self.assertTrue(app.created[0]["allday"])
        self.assertEqual(app.created[0]["invitee_email"], "henry@bigfundj.com")
        self.assertEqual(app.created[0]["start"], datetime(2027, 6, 17))

    def test_create_failure_raises_runtime_error_as_before(self):
        import gig_booking_manager
        app = FakeCalendarApp(fail="boom")
        with self.assertRaises(RuntimeError) as cm:
            gig_booking_manager.create_allday_backup_event(datetime(2027, 6, 17), "Henry", app=app)
        self.assertIn("boom", str(cm.exception))
```

Check the test file's existing helper names do not collide: `grep -n "^class FakeCalendarApp\|^class TestCreateCalendarEvents" test_gig_booking_manager.py` must show each once. The `self.booking()` fixture already carries every key `primary_event_title`, `setup_event_bracket`, `is_setup_booking` and `setup_helper_short` read.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m unittest test_gig_booking_manager 2>&1 | tail -3`
Expected: `TypeError: … got an unexpected keyword argument 'app'` on the new tests.

- [ ] **Step 3: Rewire `gig_booking_manager.py`**

Line 76, replace `CALENDAR_NAME = "Gigs"` with:

```python
from calendar_app import CALENDAR_NAME, CalendarApp, CalendarAppError  # CALENDAR_NAME re-exported for the other buttons
```

Replace `create_timed_calendar_event` (lines 826-881) with:

```python
def create_timed_calendar_event(booking, cal_start, cal_end, test_mode=False, app=None):
    """Create the primary timed calendar event. Returns the title. Raises RuntimeError on failure."""
    title = primary_event_title(booking)

    location_parts = [booking["venue_name"]]
    if booking["venue_street"]:
        location_parts.append(booking["venue_street"])
    if booking["venue_city_state_zip"]:
        location_parts.append(booking["venue_city_state_zip"])
    location = ", ".join(location_parts)

    dj_short = booking["dj_short_name"]
    if dj_short in DJ_EMAILS and dj_short not in ("Unassigned", "Unknown"):
        invitee_email = "paul@bigfundj.com" if test_mode else DJ_EMAILS[dj_short]
    else:
        invitee_email = None

    app = app or CalendarApp()
    try:
        app.create_event(title, cal_start, cal_end, location=location, invitee_email=invitee_email)
    except CalendarAppError as e:
        raise RuntimeError(f"Calendar event creation failed: {e}")
    return title
```

Replace `create_allday_backup_event` (lines 884-919) with:

```python
def create_allday_backup_event(date_obj, dj_name, test_mode=False, app=None):
    """Create the all-day backup event. Returns the title. Raises RuntimeError on failure."""
    title = get_backup_title(dj_name)
    invitee_email = "paul@bigfundj.com" if test_mode else DJ_EMAILS.get(dj_name)

    app = app or CalendarApp()
    try:
        app.create_event(title, date_obj, None, allday=True, invitee_email=invitee_email)
    except CalendarAppError as e:
        raise RuntimeError(f"Backup event creation failed: {e}")
    return title
```

Replace the whole `delete_hold_calendar_event` function (from its `def` through the closing `return False` of its final `except` block, lines ~922-962) with:

```python
def delete_hold_calendar_event(date_obj, initials_bracket, fetch_day=calendar_read.fetch_day_events, app=None):
    """
    Delete the 'Hold to DJ' calendar event for a DJ on a date.
    Called when converting a RESERVED status to BOOKED.

    The day's events are read over CalDAV and the hold deleted in Calendar.app
    by `event id` through CalendarApp (a whole-calendar `whose` scan took 30s+).
    Returns True if a hold was deleted, False if there was none to delete or the
    calendar could not be read. Raises CalendarAppError if Calendar.app failed:
    the caller must tell Paul, because the hold is still on the calendar.
    """
    try:
        listing = fetch_day(CALENDAR_NAME, date_obj.date())
    except calendar_read.CalendarReadError as e:
        print(f"  WARNING: Could not read the calendar to find the hold event: {e}")
        return False

    bracket = initials_bracket.lower()
    uids = [uid for uid, title in listing
            if "hold to dj" in title.lower() and bracket in title.lower()]
    if not uids:
        return False

    app = app or CalendarApp()
    return app.delete_events(uids) > 0
```

At the hold-release call site (lines 1585-1597), replace:

```python
                    else:
                        deleted = delete_hold_calendar_event(
                            booking["date"], booking["dj_initials_bracket"]
                        )
                        if deleted:
                            self.log(f"Calendar: deleted Hold to DJ event for {dj_short}")
                            print(f"  ✓ Deleted Hold to DJ calendar event")
                        else:
                            print(f"  ℹ️  No Hold to DJ event found to delete")
```

with:

```python
                    else:
                        try:
                            deleted = delete_hold_calendar_event(
                                booking["date"], booking["dj_initials_bracket"]
                            )
                        except CalendarAppError as e:
                            print(f"  ⚠️  HOLD EVENT NOT DELETED — {e}")
                            self.log(f"⚠️ HOLD EVENT NOT DELETED ({e}) — "
                                     f"delete the Hold to DJ event for {dj_short} by hand")
                            show_warning_dialog(
                                f"Booking Manager — Calendar:\n\n"
                                f"The Hold to DJ event for {dj_short} could not be deleted:\n{e}\n\n"
                                f"The booking continues. Delete the hold in Calendar by hand."
                            )
                        else:
                            if deleted:
                                self.log(f"Calendar: deleted Hold to DJ event for {dj_short}")
                                print(f"  ✓ Deleted Hold to DJ calendar event")
                            else:
                                print(f"  ℹ️  No Hold to DJ event found to delete")
```

`show_warning_dialog` is defined later in the same module; Python resolves it at call time, so the forward reference is fine (the existing code already calls it from `run`).

The two create calls in Phase 3 (lines ~1761 and ~1777) stay as they are: each constructs its own `CalendarApp()` by default. That is two pgrep calls per booking, which is fine; one launch at most because the first one starts the app.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m unittest test_gig_booking_manager 2>&1 | tail -3`
Expected: `Ran 133 tests` … `OK` (127 before: 3 hold tests replaced by 4, plus 5 create tests).

Also run the two consumers of the re-exported name:

Run: `.venv/bin/python -m unittest test_cancel_booking tests.test_assign_dj 2>&1 | tail -1`
Expected: `OK`

Then a Book Event dry run against a sample, which must not touch Calendar.app:

Run: `.venv/bin/python gig_booking_manager.py sample_bookings/sample_regular_booking.json --dry-run 2>&1 | grep -E "Phase 3|Would create|ERROR"`
Expected: the Phase 3 line and `[DRY RUN] Would create: …` lines, no ERROR.

- [ ] **Step 5: Commit**

```bash
git add gig_booking_manager.py test_gig_booking_manager.py
git commit -m "Book Event: calendar writes through calendar_app

Hold delete, booking event and backup event all go through CalendarApp.
A failed hold delete now shows a dialog instead of a log line and a
false 'no hold found'. CALENDAR_NAME moves to calendar_app (re-exported).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Assign DJ retitles through `CalendarApp`

**Files:**
- Modify: `assign_dj.py:36-80` (imports/comment), `:190-220` (calendar section), `:223` (signature), `:326-328` (the edit)
- Modify: `tests/test_assign_dj.py`

- [ ] **Step 1: Rewrite the fake and the assertions in `tests/test_assign_dj.py`**

Replace `class FakeOsa` with:

```python
class FakeApp:
    """Stands in for calendar_app.CalendarApp (records every retitle-and-invite)
    and for the CalDAV day read (answers the listing, records what was asked for)."""

    def __init__(self, listing):
        self.listing = listing  # list of (uid, summary) on the date
        self.edits = []         # (uid, title, invitee_email)
        self.day_calls = []

    def retitle_and_invite(self, uid, title, invitee_email):
        self.edits.append((uid, title, invitee_email))

    def fetch_day(self, calendar_name, day):
        self.day_calls.append((calendar_name, day))
        return list(self.listing)
```

Then, in the whole file:
- every `FakeOsa(` becomes `FakeApp(`
- every `osa=self.osa` becomes `app=self.osa`, and `osa=osa` becomes `app=osa` (the attribute name `self.osa` can stay; renaming it is churn with no payoff)

Replace these test bodies in `TestAssignFlow`:

```python
    def test_calendar_retitled_and_invited(self):
        self.run_assign(booking("Henry"))
        self.assertEqual(self.osa.edits, [("u1", "[HK] Cienna and Joseph", "henry@bigfundj.com")])

    def test_day_listing_is_read_over_caldav(self):
        self.run_assign(booking("Henry"))
        self.assertEqual(self.osa.day_calls, [("Gigs", datetime(2027, 1, 23).date())])

    def test_calendar_event_is_edited_by_its_caldav_uid(self):
        self.run_assign(booking("Henry"))
        self.assertEqual([e[0] for e in self.osa.edits], ["u1"])
```

(`test_day_listing_is_read_over_caldav_not_scanned_in_calendar_app` and `test_calendar_event_is_edited_by_id_not_by_scan` are the two being replaced; the no-`whose` guarantee now lives in `test_calendar_app`.)

And these single assertions:
- in `test_caldav_read_failure_raises_and_writes_nothing`: `self.assertEqual(self.osa.scripts, [])` → `self.assertEqual(self.osa.edits, [])`
- in `test_test_mode_invites_paul`: the two lines after `self.run_assign(...)` become `self.assertEqual(self.osa.edits[0][2], "paul@bigfundj.com")`
- in `test_dry_run_writes_nothing`, `test_tba_empty_but_calendar_unassigned_halts`, `test_already_done_is_a_no_op`: `self.assertEqual([s for s in self.osa.scripts if "LISTING" not in s], [])` → `self.assertEqual(self.osa.edits, [])`
- in `test_dj_already_backup_refuses`: `self.assertFalse(any("set summary" in s for s in self.osa.scripts))` → `self.assertEqual(self.osa.edits, [])`

Verify nothing is left: `grep -n "\.scripts\|FakeOsa\|osa=" tests/test_assign_dj.py`
Expected: no output.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_assign_dj 2>&1 | tail -3`
Expected: `TypeError: assign() got an unexpected keyword argument 'app'`.

- [ ] **Step 3: Rewire `assign_dj.py`**

Imports: add `from calendar_app import CalendarApp` after `import calendar_read`. Remove `CALENDAR_NAME` from the `from gig_booking_manager import (...)` list only if nothing else in the file uses it; it is still used by the CalDAV listing (`fetch_day(CALENDAR_NAME, …)`), so keep it.

Replace the calendar section (the banner comment starting `# CALENDAR (read over CalDAV; edit via AppleScript…`, `modify_script` and `run_osascript`, lines ~190-220) with:

```python
# =============================================================================
# CALENDAR: read over CalDAV, edit in Calendar.app by `event id` through
# calendar_app.CalendarApp (the only path that carries attendees; it also
# launches Calendar.app when closed). A `whose` clause walks the whole Gigs
# calendar: 30s for a day listing, and `first event whose uid is` ran 1m54s and
# then failed on a valid uid (measured 2026-11-02).
# =============================================================================
```

Signature: `def assign(booking, sheets, osa=run_osascript, fetch_day=…` becomes `def assign(booking, sheets, app=None, fetch_day=…`.

Phase 3 (lines ~326-328):

```python
    # ---- Phase 3: calendar --------------------------------------------------
    app = app or CalendarApp()
    try:
        app.retitle_and_invite(uid, new_title, invitee)
    except Exception as e:
```

(The `except Exception` and the halt message after it stay as they are.) `app` is created after the dry-run return, so a dry run never touches Calendar.app.

`import subprocess` (line 48) was only used by `run_osascript`; remove it. Then `grep -n "osa\|subprocess" assign_dj.py` must show no `run_osascript`, `modify_script` or `subprocess` lines; fix the module docstring if it mentions osascript as an injection seam.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m unittest tests.test_assign_dj 2>&1 | tail -3`
Expected: `Ran 54 tests` … `OK`

Live dry run against the real matrix and calendar (reads only, and it must not launch Calendar.app):

Run: `.venv/bin/python assign_dj.py sample_bookings/sample_assign_dj.json --dry-run 2>&1 | tail -5`
Expected: ends with `[DRY RUN] No writes, no backup dialog.` or a HALTED line about the sample's date; no traceback.

- [ ] **Step 5: Commit**

```bash
git add assign_dj.py tests/test_assign_dj.py
git commit -m "Assign DJ: retitle and invite through calendar_app

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `show_warning_dialog` never ends a run

**Files:**
- Modify: `gig_booking_manager.py:969-976`
- Modify: `test_gig_booking_manager.py` (append a class)

- [ ] **Step 1: Write the failing tests**

Append to `test_gig_booking_manager.py` (above `if __name__`, or at the end if the file's `if __name__` block is not last; check with `grep -n "^if __name__" test_gig_booking_manager.py`):

```python
class TestShowWarningDialog(unittest.TestCase):
    """2026-11-03: the dialog's 60s timeout raised and ended a cancellation
    before the backup event, the turned-away check and the booking log form."""

    @mock.patch("gig_booking_manager.subprocess.run")
    def test_expiry_is_swallowed_and_printed(self, mock_run):
        import io, contextlib
        import gig_booking_manager
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="osascript", timeout=1800)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            gig_booking_manager.show_warning_dialog("Cancel Booking — Calendar:\n\nCould not delete")
        self.assertIn("expired", out.getvalue().lower())
        self.assertIn("Cancel Booking — Calendar:", out.getvalue())

    @mock.patch("gig_booking_manager.subprocess.run")
    def test_waits_long_enough_to_step_away(self, mock_run):
        import gig_booking_manager
        gig_booking_manager.show_warning_dialog("x")
        self.assertEqual(mock_run.call_args.kwargs.get("timeout"), 1800)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m unittest test_gig_booking_manager.TestShowWarningDialog 2>&1 | tail -3`
Expected: `FAILED (errors=1, failures=1)` — the first raises `TimeoutExpired`, the second sees 60.

- [ ] **Step 3: Rewrite `show_warning_dialog`**

```python
WARNING_DIALOG_TIMEOUT = 1800   # same as the backup dialogs: Paul may have stepped away


def show_warning_dialog(message):
    """
    Show a warning dialog and wait for OK. Never raises: an unanswered dialog
    is printed and the script carries on, so the steps after it still run.
    2026-11-03: a 60s timeout here raised and ended a cancellation before the
    backup event, the turned-away check and the booking log form.
    """
    msg_esc = message.replace('"', '\\"')
    script = f'''
    display dialog "{msg_esc}" with title "⚠️ Booking Manager Warning" buttons {{"OK"}} default button "OK" with icon caution
    '''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                       timeout=WARNING_DIALOG_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"  WARNING: Warning dialog expired unacknowledged: {message.splitlines()[0]}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m unittest test_gig_booking_manager test_cancel_booking test_calendar_app tests.test_assign_dj 2>&1 | tail -3`
Expected: `Ran 231 tests` … `OK` (135 + 22 + 20 + 54).

- [ ] **Step 5: Commit**

```bash
git add gig_booking_manager.py test_gig_booking_manager.py
git commit -m "Warning dialog: 30-minute timeout, never raises

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Docs, the live cold-start check, and the wrap-up

**Files:**
- Modify: `CHANGELOG.md` (under `## [Unreleased]`)
- Modify: `DJ_SYSTEM_REFERENCE.md` (§4 Cancel Booking, §10 file inventory)

- [ ] **Step 1: The live cold-start check (read-only)**

This reproduces the incident against the real Calendar.app with a `get`, never a write. Pick a date that has a Gigs event (Sat 1/23/27 has Paul's Oceano booking).

```bash
osascript -e 'tell application "Calendar" to quit'; sleep 5; pgrep -x Calendar || echo "Calendar closed"
.venv/bin/python - <<'EOF'
import datetime, time
import calendar_read
from calendar_app import CalendarApp
listing = calendar_read.fetch_day_events("Gigs", datetime.date(2027, 1, 23))
uid, title = listing[0]
print("CalDAV:", uid, title)
app = CalendarApp()
t0 = time.monotonic()
print("Calendar.app:", app.run_script(f'        get summary of event id "{uid}"'))
print(f"launched_at set: {app.launched_at is not None}; took {time.monotonic() - t0:.1f}s")
EOF
```

Expected: `CalDAV: <uid> [PB] …`, then `Calendar.app: [PB] …` (the same title), `launched_at set: True`, and a time under 90s. If it raises `CalendarAppError` with -1728, the load took longer than `LOAD_WINDOW`: note the elapsed time and raise `LOAD_WINDOW` to 1.5× it, re-run, and record the measurement in the CHANGELOG entry.

Then repeat the same snippet with Calendar.app already running. Expected: same title, `launched_at set: False`, well under 2s.

- [ ] **Step 2: CHANGELOG**

Under `## [Unreleased]` → `### Fixed`, add as the first bullet:

```markdown
- **Buttons pressed with Calendar.app closed.** Cancel Booking, Assign DJ and Book Event's
  hold delete edit the Gigs calendar by `event id`. With Calendar.app closed, the script's
  `tell application "Calendar"` launched it and the lookup ran before the CalDAV store had
  loaded: `Can't get event id … (-1728)` on an event that resolved fine two minutes later
  (Cancel Booking, Netta and Gawesha 6/17/27, 2026-11-03; the matrix was cleared, the calendar
  was not). All three buttons now go through `calendar_app.CalendarApp`, which launches
  Calendar.app hidden first and retries an event-id miss while the store loads, only when it
  did the launching. One osascript per event, one timeout, one error type. A failed hold delete
  in Book Event now shows a dialog instead of a log line. The warning dialog waits 30 minutes
  and never raises: its 60s timeout had ended the same cancellation before the backup event
  and the booking log form. (2026-11-03)
```

- [ ] **Step 3: DJ_SYSTEM_REFERENCE**

In §4 Cancel Booking, after the `**Flags:**` line, add:

```markdown
**Calendar.app may be closed.** All three buttons edit the calendar through `calendar_app.py`, which launches Calendar.app hidden and waits for it to load. Nothing to do before pressing a button.
```

In §4's `### 5-Step Process` nothing changes (it was renumbered in Task 0's commit; confirm it reads 1-5 and no longer mentions nurture: `grep -n -i nurture DJ_SYSTEM_REFERENCE.md` → no output).

In §10 Complete File Inventory (a `| File | Purpose |` table), `calendar_read.py` has no row today. Add these three rows after the `cancel_booking.scpt` row:

```markdown
| calendar_read.py | CalDAV reads: day listings as (uid, title) |
| **calendar_app.py** | Calendar.app writes for the buttons: launch guard, delete / retitle / create by `event id` |
| test_calendar_app.py | Tests for calendar_app |
```


- [ ] **Step 4: Full suite one last time**

Run: `.venv/bin/python -m unittest test_gig_booking_manager test_cancel_booking test_calendar_app tests.test_assign_dj 2>&1 | tail -3`
Expected: `Ran 231 tests` … `OK`

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md DJ_SYSTEM_REFERENCE.md
git commit -m "Docs: calendar_app and the cold-start fix

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 6: Report to Paul**

Nothing to reinstall: the three buttons run from source through `~/bin/dj-checker-button`, and the `.scpt` files did not change. Report the live check's two timings and the final test count.

---

## Out of scope (deliberately)

- Merging the three `.applescript` button scripts into one. They are the same 87 lines with names changed, but merging them changes every Stream Deck button command for no behaviour gain.
- A launch guard for a Calendar.app that someone *else* started seconds earlier. `launched_at` is only set when this process launched it; the window between "already running" and "finished loading" is a few seconds and has not bitten.
- Removing the Nurture Tracker hooks from Book Event (`_schedule_nurture_emails`). Paul has not asked; it costs one Sheets call on his own weddings.
