# CalDAV Calendar Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all AppleScript calendar operations with CalDAV writes and icalBuddy reads so Calendar.app never opens during script execution.

**Architecture:** New shared module `calendar_caldav.py` handles all CalDAV connections, event creation, and deletion. Existing functions in `gig_booking_manager.py`, `cancel_booking.py`, and `stefano_maxed_enforcer.py` keep their signatures but swap AppleScript internals for `calendar_caldav` calls. icalBuddy read operations stay untouched.

**Tech Stack:** Python 3, `caldav` library, `keyring`, icalBuddy CLI, CalDAV server at love2tap.com

**Spec:** `docs/superpowers/specs/2026-03-17-caldav-calendar-migration-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `calendar_caldav.py` | Create | CalDAV connection, create/delete operations, icalBuddy UID lookup |
| `test_caldav_migration.py` | Create | Pre-migration validation tests (Tests 0-4 from spec) |
| `gig_booking_manager.py` | Modify (lines 68, 709-837) | Replace 3 AppleScript functions with `calendar_caldav` calls |
| `cancel_booking.py` | Modify (lines 36, 82-147) | Replace 2 AppleScript functions with `calendar_caldav` calls |
| `stefano_maxed_enforcer.py` | Modify (lines 37-38, 193-220) | Replace 1 AppleScript function with `calendar_caldav` call |
| `pytest.ini` | Create | pytest configuration with integration test marker |
| `tests/__init__.py` | Create | Test package init |
| `tests/conftest.py` | Create | Shared fixtures (mock CalDAV client, sample dates) |
| `tests/test_calendar_caldav_unit.py` | Create | Mocked unit tests for all calendar_caldav functions |
| `tests/test_calendar_caldav_integration.py` | Create | Real server integration tests (run manually) |

---

## Task 1: Pre-migration validation script

Run Tests 0-4 from the spec to confirm CalDAV works for all required operations before touching production code. This task produces a test script that Paul runs and checks results manually (invitation emails, calendar appearance).

**Files:**
- Create: `test_caldav_migration.py`
- Reference: `test_caldav_write.py` (existing CalDAV test for patterns)

- [ ] **Step 1: Write Test 0 -- calendar discovery**

Create `test_caldav_migration.py` with a function that connects as `schedule` and lists all calendars. Print each calendar's display name and URL.

```python
#!/usr/bin/env python3
"""
Pre-migration validation tests for CalDAV calendar migration.
Run these tests BEFORE modifying any production code.

All test invitations go to paul@bigfundj.com.
Test events use date 2099-12-31 (far future, safe to clean up).

Usage:
    python3 test_caldav_migration.py           # Run all tests
    python3 test_caldav_migration.py test0      # Run single test
"""

import datetime
import subprocess
import sys
import uuid
from zoneinfo import ZoneInfo

import caldav
import keyring

TIMEZONE = ZoneInfo("America/Los_Angeles")
SERVICE_NAME = "bigfun-caldav-schedule"
TEST_ATTENDEE = "paul@bigfundj.com"
ORGANIZER = "schedule@bigfundj.com"

# Known calendar URLs (Gigs known, Unavailable discovered in Test 0)
BASE_URL = "https://caldav.love2tap.com/calendars/__uids__/65B490A6-6667-48BC-B9E4-1A638DAA787E"
GIGS_URL = f"{BASE_URL}/1187934A-6A2E-43A3-8355-74382DC82F47/"
UNAVAILABLE_URL = None  # Set after Test 0 discovery


def get_client():
    url = keyring.get_password(SERVICE_NAME, "url")
    username = keyring.get_password(SERVICE_NAME, "username")
    password = keyring.get_password(SERVICE_NAME, "password")
    if not all([url, username, password]):
        print("ERROR: No CalDAV credentials found for 'schedule' account.")
        print("Run keyring setup first.")
        sys.exit(1)
    return caldav.DAVClient(url=url, username=username, password=password)


def test0_calendar_discovery():
    """List all calendars visible to the schedule account."""
    print("=" * 60)
    print("TEST 0: Calendar Discovery")
    print("=" * 60)

    client = get_client()
    principal = client.principal()
    calendars = principal.calendars()

    print(f"\nFound {len(calendars)} calendar(s):\n")
    unavailable_url = None
    for cal in calendars:
        name = cal.get_display_name()
        print(f"  Name: {name}")
        print(f"  URL:  {cal.url}")
        print()
        if name and "unavailable" in name.lower():
            unavailable_url = str(cal.url)

    if unavailable_url:
        print(f"PASS: Unavailable calendar found at {unavailable_url}")
        print(f"      Update UNAVAILABLE_URL in this script and in calendar_caldav.py")
    else:
        print("WARN: 'Unavailable' calendar not found under schedule account.")
        print("      May need paul account credentials or delegation grant.")

    return unavailable_url
```

- [ ] **Step 2: Write Test 1 -- timed event with attendee**

Add function that creates a timed event on Gigs with ATTENDEE and ORGANIZER.

```python
def test1_timed_event_with_attendee():
    """Create a timed event on Gigs with attendee invitation."""
    print("=" * 60)
    print("TEST 1: Timed Event with Attendee (Gigs)")
    print("=" * 60)

    client = get_client()
    gigs = caldav.Calendar(client=client, url=GIGS_URL)

    test_uid = f"caldav-migration-test1-{uuid.uuid4().hex[:8]}"
    vcal = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//BIG FUN//CalDAV Migration Test//EN
BEGIN:VEVENT
UID:{test_uid}
DTSTART;TZID=America/Los_Angeles:20991231T140000
DTEND;TZID=America/Los_Angeles:20991231T230000
SUMMARY:[PB] Test Booking - Migration Test
LOCATION:Nestldown, 27500 Old Santa Cruz Hwy, Los Gatos CA 95033
ORGANIZER;CN=BIG FUN:mailto:{ORGANIZER}
ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{TEST_ATTENDEE}
END:VEVENT
END:VCALENDAR"""

    print(f"\nCreating timed event (2099-12-31, 2-11pm)...")
    print(f"  Attendee: {TEST_ATTENDEE}")
    print(f"  UID: {test_uid}")

    try:
        event = gigs.save_event(vcal)
        print(f"  Created. URL: {event.url}")
    except Exception as e:
        print(f"  FAILED: {e}")
        return None

    print(f"\nMANUAL CHECK:")
    print(f"  1. Does the event appear in Fantastical on Dec 31, 2099?")
    print(f"  2. Did {TEST_ATTENDEE} receive a calendar invitation email?")
    print(f"  3. Is the title '[PB] Test Booking - Migration Test'?")
    print(f"  4. Is the location 'Nestldown, 27500 Old Santa Cruz Hwy, Los Gatos CA 95033'?")
    print(f"\n  UID for cleanup: {test_uid}")

    return test_uid
```

- [ ] **Step 3: Write Test 2 -- all-day event with attendee**

Add function that creates an all-day event. Uses Unavailable calendar if discovered, falls back to Gigs.

```python
def test2_allday_event_with_attendee(unavailable_url=None):
    """Create an all-day event with attendee invitation."""
    print("=" * 60)
    print("TEST 2: All-Day Event with Attendee")
    print("=" * 60)

    client = get_client()

    if unavailable_url:
        cal = caldav.Calendar(client=client, url=unavailable_url)
        cal_name = "Unavailable"
    else:
        print("  WARN: Unavailable calendar not found, using Gigs instead.")
        cal = caldav.Calendar(client=client, url=GIGS_URL)
        cal_name = "Gigs"

    test_uid = f"caldav-migration-test2-{uuid.uuid4().hex[:8]}"
    vcal = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//BIG FUN//CalDAV Migration Test//EN
BEGIN:VEVENT
UID:{test_uid}
DTSTART;VALUE=DATE:20991230
DTEND;VALUE=DATE:20991231
SUMMARY:[SB] MAXED OUT - Migration Test
ORGANIZER;CN=BIG FUN:mailto:{ORGANIZER}
ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{TEST_ATTENDEE}
END:VEVENT
END:VCALENDAR"""

    print(f"\nCreating all-day event on {cal_name} (2099-12-30)...")
    print(f"  Attendee: {TEST_ATTENDEE}")
    print(f"  UID: {test_uid}")

    try:
        event = cal.save_event(vcal)
        print(f"  Created. URL: {event.url}")
    except Exception as e:
        print(f"  FAILED: {e}")
        return None

    print(f"\nMANUAL CHECK:")
    print(f"  1. Does the event appear as all-day on Dec 30, 2099?")
    print(f"  2. Did {TEST_ATTENDEE} receive a calendar invitation?")
    print(f"\n  UID for cleanup: {test_uid}")

    return test_uid
```

- [ ] **Step 4: Write Test 3 -- icalBuddy UID output**

Add function that runs icalBuddy with `-uid` flag and parses output.

```python
def test3_icalbuddy_uid(expected_uids=None):
    """Check if icalBuddy -uid returns usable UIDs."""
    print("=" * 60)
    print("TEST 3: icalBuddy UID Output")
    print("=" * 60)

    # Query the test event dates
    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/icalBuddy", "-ic", "Gigs,Unavailable",
             "-uid",
             "-eep", "notes,url,location,attendees",
             "-b", "", "-nc",
             "eventsFrom:2099-12-29", "to:2099-12-31"],
            capture_output=True, text=True, timeout=10,
        )
        print(f"\nRaw icalBuddy output:\n---")
        print(result.stdout)
        print("---")

        if result.returncode != 0:
            print(f"  FAILED: icalBuddy returned {result.returncode}")
            print(f"  stderr: {result.stderr}")
            return False

        if not result.stdout.strip():
            print("  WARN: No events found. Are the test events synced locally?")
            print("  icalBuddy reads from the local calendar store.")
            print("  Wait for sync and retry, or check calendar permissions.")
            return False

        # Check if UIDs appear in output
        if expected_uids:
            for uid in expected_uids:
                if uid and uid in result.stdout:
                    print(f"  FOUND UID: {uid}")
                elif uid:
                    print(f"  MISSING UID: {uid}")
                    print(f"  The UID may use a different format in icalBuddy.")

        print(f"\nDOCUMENT: Copy the output format above.")
        print(f"  The parser in calendar_caldav.find_events_by_date()")
        print(f"  needs to extract UID and title from this format.")
        return True

    except FileNotFoundError:
        print("  FAILED: icalBuddy not installed")
        return False
    except subprocess.TimeoutExpired:
        print("  FAILED: icalBuddy timed out")
        return False
```

- [ ] **Step 5: Write Test 4 -- delete by UID**

Add function that attempts both delete strategies (URL construction and .search()).

```python
def test4_delete_by_uid(test_uid, calendar_url=GIGS_URL):
    """Test deleting an event by UID via CalDAV."""
    print("=" * 60)
    print("TEST 4: Delete by UID")
    print("=" * 60)

    if not test_uid:
        print("  SKIP: No test UID provided (previous test may have failed)")
        return

    client = get_client()
    cal = caldav.Calendar(client=client, url=calendar_url)

    # Strategy A: URL construction
    constructed_url = f"{calendar_url}{test_uid}.ics"
    print(f"\nStrategy A: Delete by constructed URL")
    print(f"  URL: {constructed_url}")

    try:
        event = caldav.Event(client=client, url=constructed_url, parent=cal)
        event.delete()
        print(f"  PASS: Deleted via constructed URL.")
        print(f"  USE THIS STRATEGY in calendar_caldav.py")
        return "url"
    except Exception as e:
        print(f"  Failed: {e}")

    # Strategy B: Search + delete
    print(f"\nStrategy B: Search + object delete")
    try:
        found = cal.search(
            start=datetime.datetime(2099, 12, 29, 0, 0, 0, tzinfo=TIMEZONE),
            end=datetime.datetime(2100, 1, 2, 0, 0, 0, tzinfo=TIMEZONE),
            event=True, expand=True,
        )
        for ev in found:
            ev_uid = str(ev.icalendar_component.get("uid", ""))
            if test_uid in ev_uid:
                ev.delete()
                print(f"  PASS: Found and deleted via search.")
                print(f"  USE THIS STRATEGY in calendar_caldav.py")
                return "search"
        print(f"  Event not found in search results.")
    except Exception as e:
        print(f"  Failed: {e}")

    print(f"\n  FAIL: Neither strategy could delete the event.")
    return None
```

- [ ] **Step 6: Write main runner**

```python
def cleanup_test_event(test_uid, calendar_url=GIGS_URL):
    """Clean up a test event by UID (tries both strategies)."""
    if not test_uid:
        return
    client = get_client()
    cal = caldav.Calendar(client=client, url=calendar_url)
    try:
        found = cal.search(
            start=datetime.datetime(2099, 12, 29, 0, 0, 0, tzinfo=TIMEZONE),
            end=datetime.datetime(2100, 1, 2, 0, 0, 0, tzinfo=TIMEZONE),
            event=True, expand=True,
        )
        for ev in found:
            ev_uid = str(ev.icalendar_component.get("uid", ""))
            if test_uid in ev_uid:
                ev.delete()
                print(f"  Cleaned up: {test_uid}")
                return
    except Exception:
        pass


def main():
    tests = sys.argv[1:] if len(sys.argv) > 1 else ["test0", "test1", "test2", "test3", "test4"]

    unavailable_url = None
    test1_uid = None
    test2_uid = None

    if "test0" in tests:
        unavailable_url = test0_calendar_discovery()
        print()

    if "test1" in tests:
        test1_uid = test1_timed_event_with_attendee()
        print()

    if "test2" in tests:
        test2_uid = test2_allday_event_with_attendee(unavailable_url)
        print()

    if "test3" in tests:
        expected = [uid for uid in [test1_uid, test2_uid] if uid]
        test3_icalbuddy_uid(expected)
        print()

    if "test4" in tests:
        if test1_uid:
            strategy = test4_delete_by_uid(test1_uid, GIGS_URL)
            print()
        if test2_uid:
            cal_url = unavailable_url or GIGS_URL
            test4_delete_by_uid(test2_uid, cal_url)
            print()

    # Offer cleanup for any remaining test events
    print("=" * 60)
    print("CLEANUP")
    print("=" * 60)
    print("Test events on 2099-12-30 and 2099-12-31 should be cleaned up.")
    print("Test 4 deletes them if it runs. If not, run:")
    print("  python3 test_caldav_migration.py test4")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run Test 0 to discover Unavailable calendar URL**

Run: `cd /Users/paulburchfield/Documents/projects/dj-availability-checker && python3 test_caldav_migration.py test0`

Expected: List of calendars with names and URLs. Record the Unavailable calendar URL.

- [ ] **Step 8: Update UNAVAILABLE_URL and run Tests 1-2**

Update the `UNAVAILABLE_URL` constant in `test_caldav_migration.py` with the URL from Test 0.

Run: `python3 test_caldav_migration.py test1 test2`

Expected: Two events created. Paul checks email for invitation delivery and Fantastical for event appearance.

**STOP HERE.** Wait for Paul to confirm:
1. Both events visible in Fantastical
2. Invitation emails received (or not -- determines fallback needed)

- [ ] **Step 9: Run Tests 3-4**

Run: `python3 test_caldav_migration.py test3 test4`

Expected: icalBuddy output with UIDs documented. Delete strategy determined (URL construction or search+delete). Test events cleaned up.

**STOP HERE.** Document findings:
- icalBuddy UID format: ___
- Delete strategy that works: ___
- Invitation delivery confirmed: yes/no

- [ ] **Step 10: Commit validation script**

```bash
git add test_caldav_migration.py
git commit -m "Add pre-migration validation tests for CalDAV calendar migration"
```

---

## Task 2: Build `calendar_caldav.py` -- connection and create functions

Build the core module with connection handling and event creation. The delete functions come in Task 3 (they depend on Test 3/4 findings).

**Files:**
- Create: `calendar_caldav.py`
- Reference: `test_caldav_write.py` (connection pattern)
- Reference: `test_caldav_migration.py` (VCALENDAR templates)

- [ ] **Step 1: Write connection scaffolding**

```python
#!/usr/bin/env python3
"""
CalDAV calendar operations for BIG FUN booking system.

Replaces all AppleScript calendar calls with CalDAV writes and
icalBuddy reads. Calendar.app is never opened.

Calendars:
  - Gigs: booking events, backup DJ events, hold events
  - Unavailable: MAXED OUT events (Stefano enforcer)

Connection: authenticates as 'schedule' user via macOS Keychain.
"""

import datetime
import subprocess
import time
import uuid
from zoneinfo import ZoneInfo

import caldav
import keyring

TIMEZONE = ZoneInfo("America/Los_Angeles")
SERVICE_NAME = "bigfun-caldav-schedule"
ORGANIZER_EMAIL = "schedule@bigfundj.com"

BASE_URL = "https://caldav.love2tap.com/calendars/__uids__/65B490A6-6667-48BC-B9E4-1A638DAA787E"
CALENDAR_URLS = {
    "Gigs": f"{BASE_URL}/1187934A-6A2E-43A3-8355-74382DC82F47/",
    "Unavailable": f"{BASE_URL}/PLACEHOLDER/",  # UPDATE after Test 0
}

# Lazy-initialized connection
_client = None


def _get_client():
    """Get or create the CalDAV client (lazy singleton)."""
    global _client
    if _client is not None:
        return _client

    url = keyring.get_password(SERVICE_NAME, "url")
    username = keyring.get_password(SERVICE_NAME, "username")
    password = keyring.get_password(SERVICE_NAME, "password")
    if not all([url, username, password]):
        raise RuntimeError(
            "CalDAV credentials not found in Keychain. "
            f"Expected service: {SERVICE_NAME}"
        )
    _client = caldav.DAVClient(url=url, username=username, password=password)
    return _client


def _get_calendar(calendar_name):
    """Get a calendar object by name."""
    if calendar_name not in CALENDAR_URLS:
        raise ValueError(f"Unknown calendar: {calendar_name}. Expected: {list(CALENDAR_URLS.keys())}")
    client = _get_client()
    return caldav.Calendar(client=client, url=CALENDAR_URLS[calendar_name])


def _retry_on_error(fn, max_retries=1, delay=5):
    """Retry a CalDAV operation once on connection/timeout errors."""
    try:
        return fn()
    except (ConnectionError, TimeoutError, caldav.lib.error.DAVError) as e:
        if max_retries <= 0:
            raise
        print(f"  CalDAV error, retrying in {delay}s: {e}")
        time.sleep(delay)
        global _client
        _client = None  # Force reconnect
        return fn()
```

- [ ] **Step 2: Write `create_timed_event()`**

```python
def create_timed_event(
    calendar_name,
    title,
    location,
    start_dt,
    end_dt,
    attendee_email=None,
):
    """
    Create a timed calendar event via CalDAV.

    Args:
        calendar_name: "Gigs" or "Unavailable"
        title: Event title (e.g., "[PB] Smith")
        location: Venue name and address
        start_dt: datetime object (naive or tz-aware, treated as America/Los_Angeles)
        end_dt: datetime object
        attendee_email: DJ email for invitation, or None to skip

    Returns:
        str: The event UID
    """
    event_uid = str(uuid.uuid4())

    # Format datetimes for iCalendar
    start_str = start_dt.strftime("%Y%m%dT%H%M%S")
    end_str = end_dt.strftime("%Y%m%dT%H%M%S")

    # Build optional attendee block
    attendee_line = ""
    if attendee_email:
        attendee_line = (
            f"ORGANIZER;CN=BIG FUN:mailto:{ORGANIZER_EMAIL}\n"
            f"ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{attendee_email}"
        )

    # Escape special characters in text fields
    title_ical = title.replace(",", "\\,").replace(";", "\\;")
    location_ical = location.replace(",", "\\,").replace(";", "\\;")

    vcal_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BIG FUN//Gig Booking Manager//EN",
        "BEGIN:VEVENT",
        f"UID:{event_uid}",
        f"DTSTART;TZID=America/Los_Angeles:{start_str}",
        f"DTEND;TZID=America/Los_Angeles:{end_str}",
        f"SUMMARY:{title_ical}",
        f"LOCATION:{location_ical}",
    ]
    if attendee_line:
        vcal_lines.extend(attendee_line.split("\n"))
    vcal_lines.extend(["END:VEVENT", "END:VCALENDAR"])
    vcal = "\n".join(vcal_lines)

    cal = _get_calendar(calendar_name)
    _retry_on_error(lambda: cal.save_event(vcal))

    return event_uid
```

- [ ] **Step 3: Write `create_allday_event()`**

```python
def create_allday_event(
    calendar_name,
    title,
    date_obj,
    attendee_email=None,
):
    """
    Create an all-day calendar event via CalDAV.

    Args:
        calendar_name: "Gigs" or "Unavailable"
        title: Event title (e.g., "[SB] MAXED OUT")
        date_obj: date object for the event day
        attendee_email: Email for invitation, or None to skip

    Returns:
        str: The event UID
    """
    event_uid = str(uuid.uuid4())

    # All-day: DTSTART is event day, DTEND is next day (RFC 5545)
    start_str = date_obj.strftime("%Y%m%d")
    next_day = date_obj + datetime.timedelta(days=1)
    end_str = next_day.strftime("%Y%m%d")

    attendee_line = ""
    if attendee_email:
        attendee_line = (
            f"ORGANIZER;CN=BIG FUN:mailto:{ORGANIZER_EMAIL}\n"
            f"ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{attendee_email}"
        )

    title_ical = title.replace(",", "\\,").replace(";", "\\;")

    vcal_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BIG FUN//Gig Booking Manager//EN",
        "BEGIN:VEVENT",
        f"UID:{event_uid}",
        f"DTSTART;VALUE=DATE:{start_str}",
        f"DTEND;VALUE=DATE:{end_str}",
        f"SUMMARY:{title_ical}",
    ]
    if attendee_line:
        vcal_lines.extend(attendee_line.split("\n"))
    vcal_lines.extend(["END:VEVENT", "END:VCALENDAR"])
    vcal = "\n".join(vcal_lines)

    cal = _get_calendar(calendar_name)
    _retry_on_error(lambda: cal.save_event(vcal))

    return event_uid
```

- [ ] **Step 4: Manual smoke test -- create and verify**

Run in Python REPL:
```bash
cd /Users/paulburchfield/Documents/projects/dj-availability-checker
python3 -c "
import calendar_caldav
uid = calendar_caldav.create_timed_event(
    'Gigs', '[TEST] Module Smoke Test', 'Nowhere',
    __import__('datetime').datetime(2099, 12, 31, 14, 0),
    __import__('datetime').datetime(2099, 12, 31, 23, 0),
    'paul@bigfundj.com',
)
print(f'Created timed event: {uid}')
"
```

Expected: Event created on Gigs calendar, paul@bigfundj.com receives invitation. Verify in Fantastical.

- [ ] **Step 5: Commit**

```bash
git add calendar_caldav.py
git commit -m "Add calendar_caldav module with connection and create functions"
```

---

## Task 3: Build `calendar_caldav.py` -- delete functions

Add icalBuddy-based event lookup and CalDAV deletion. The exact implementation of `find_events_by_date` and `delete_event_by_uid` depends on findings from Task 1 Tests 3-4.

**Files:**
- Modify: `calendar_caldav.py`

**IMPORTANT:** Before starting this task, check the documented findings from Task 1 Step 9:
- What format does icalBuddy `-uid` output use?
- Which delete strategy works (URL construction or search+delete)?

If icalBuddy UIDs are unusable, replace the icalBuddy lookup with CalDAV `.search()`.

- [ ] **Step 1: Write `find_events_by_date()`**

This is the icalBuddy-based implementation. If Test 3 showed icalBuddy UIDs are unusable, write the CalDAV `.search()` fallback version instead (see Step 1b).

```python
def find_events_by_date(date_obj, calendar_names="Gigs"):
    """
    Find events on a date using icalBuddy with -uid flag.

    Args:
        date_obj: date object to search
        calendar_names: comma-separated calendar names for icalBuddy

    Returns:
        list of {"uid": str, "title": str} dicts.
        Empty list on failure.
    """
    date_str = date_obj.strftime("%Y-%m-%d")

    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/icalBuddy", "-ic", calendar_names,
             "-uid",
             "-eep", "notes,url,location,attendees",
             "-b", "", "-nc",
             f"eventsFrom:{date_str}", f"to:{date_str}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        # Parse icalBuddy output
        # FORMAT: Determined by Test 3 findings. Update parser accordingly.
        # Typical format with -uid:
        #   Event Title
        #       <datetime info>
        #       uid: <the-uid-string>
        events = []
        current_title = None
        for line in result.stdout.strip().split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if not line.startswith(" ") and not line.startswith("\t"):
                # Title line (not indented)
                current_title = stripped
            elif "uid:" in stripped.lower():
                uid = stripped.split(":", 1)[1].strip()
                if current_title and uid:
                    events.append({"uid": uid, "title": current_title})
                    current_title = None

        return events

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
```

- [ ] **Step 1b (FALLBACK): Write CalDAV search version if icalBuddy UIDs fail**

Only use this if Test 3 showed icalBuddy `-uid` output is unusable.

```python
def find_events_by_date(date_obj, calendar_names="Gigs"):
    """
    Find events on a date using CalDAV search.
    Fallback for when icalBuddy -uid output is unusable.
    """
    events = []
    start = datetime.datetime.combine(date_obj, datetime.time.min, tzinfo=TIMEZONE)
    end = datetime.datetime.combine(date_obj, datetime.time.max, tzinfo=TIMEZONE)

    for cal_name in calendar_names.split(","):
        cal_name = cal_name.strip()
        if cal_name not in CALENDAR_URLS:
            continue
        cal = _get_calendar(cal_name)
        try:
            found = _retry_on_error(
                lambda: cal.search(start=start, end=end, event=True, expand=True)
            )
            for ev in found:
                comp = ev.icalendar_component
                uid = str(comp.get("uid", ""))
                title = str(comp.get("summary", ""))
                if uid:
                    events.append({"uid": uid, "title": title})
        except Exception:
            continue

    return events
```

- [ ] **Step 2: Write `delete_event_by_uid()`**

```python
def delete_event_by_uid(calendar_name, uid):
    """
    Delete an event by UID via CalDAV.

    Primary: construct URL as {calendar_url}/{uid}.ics
    Fallback: search + match UID + event.delete()

    Returns True if deleted, False if not found.
    """
    cal = _get_calendar(calendar_name)
    client = _get_client()
    cal_url = CALENDAR_URLS[calendar_name]

    # Strategy A: URL construction
    constructed_url = f"{cal_url}{uid}.ics"
    try:
        event = caldav.Event(client=client, url=constructed_url, parent=cal)
        _retry_on_error(lambda: event.delete())
        return True
    except Exception:
        pass

    # Strategy B: Search all events in a wide range, find by UID
    try:
        now = datetime.datetime.now(tz=TIMEZONE)
        start = now - datetime.timedelta(days=365)
        end = now + datetime.timedelta(days=365 * 5)
        found = cal.search(start=start, end=end, event=True, expand=True)
        for ev in found:
            ev_uid = str(ev.icalendar_component.get("uid", ""))
            if uid == ev_uid:
                ev.delete()
                return True
    except Exception:
        pass

    return False
```

- [ ] **Step 3: Write `delete_matching_events()`**

```python
def delete_matching_events(date_obj, calendar_name, match_fn):
    """
    Find events on a date, filter with match_fn, delete matches.

    Args:
        date_obj: date to search
        calendar_name: "Gigs" or "Unavailable"
        match_fn: function({"uid": str, "title": str}) -> bool

    Returns:
        int: count of deleted events
    """
    events = find_events_by_date(date_obj, calendar_name)
    deleted = 0

    for event in events:
        if match_fn(event):
            if delete_event_by_uid(calendar_name, event["uid"]):
                deleted += 1

    return deleted
```

- [ ] **Step 4: Commit**

```bash
git add calendar_caldav.py
git commit -m "Add delete functions to calendar_caldav module"
```

---

## Task 4: Migrate `gig_booking_manager.py`

Replace the internals of 3 functions. Keep all signatures.

**Files:**
- Modify: `gig_booking_manager.py` (lines 68, 709-837)

- [ ] **Step 1: Add import**

At the top of `gig_booking_manager.py`, after the existing imports (around line 33), add:

```python
import calendar_caldav
```

- [ ] **Step 2: Remove `CALENDAR_NAME` constant**

Remove line 68: `CALENDAR_NAME = "Gigs"`

- [ ] **Step 3: Replace `create_timed_calendar_event()` internals**

Keep the function signature on line 709. Replace lines 710-766 with:

```python
def create_timed_calendar_event(booking, cal_start, cal_end, test_mode=False):
    """Create the primary timed calendar event via CalDAV."""
    # Build title: [INITIALS] ClientName (planner)
    title = f"{booking['dj_initials_bracket']} {booking['client_display']}"
    if booking["has_planner"]:
        title += " (planner)"

    # Build location
    location_parts = [booking["venue_name"]]
    if booking["venue_street"]:
        location_parts.append(booking["venue_street"])
    if booking["venue_city_state_zip"]:
        location_parts.append(booking["venue_city_state_zip"])
    location = ", ".join(location_parts)

    # Determine invitee
    dj_short = booking["dj_short_name"]
    if dj_short in DJ_EMAILS and dj_short not in ("Unassigned", "Unknown"):
        invitee_email = "paul@bigfundj.com" if test_mode else DJ_EMAILS[dj_short]
    else:
        invitee_email = None

    calendar_caldav.create_timed_event(
        "Gigs", title, location, cal_start, cal_end, invitee_email
    )

    return title
```

- [ ] **Step 4: Replace `create_allday_backup_event()` internals**

Replace lines 769-804 with:

```python
def create_allday_backup_event(date_obj, dj_name, test_mode=False):
    """Create an all-day backup calendar event via CalDAV."""
    title = get_backup_title(dj_name)

    if test_mode:
        invitee_email = "paul@bigfundj.com"
    else:
        invitee_email = DJ_EMAILS.get(dj_name)

    calendar_caldav.create_allday_event("Gigs", title, date_obj, invitee_email)

    return title
```

- [ ] **Step 5: Replace `delete_hold_calendar_event()` internals**

Replace lines 807-837 with:

```python
def delete_hold_calendar_event(date_obj, initials_bracket):
    """
    Delete a 'Hold to DJ' calendar event for a DJ on a given date.
    Called when converting a RESERVED status to BOOKED.
    Returns True if an event was deleted, False otherwise.
    """
    try:
        count = calendar_caldav.delete_matching_events(
            date_obj, "Gigs",
            lambda e: "Hold to DJ" in e["title"] and initials_bracket in e["title"]
        )
        return count > 0
    except Exception as e:
        print(f"  WARNING: Could not delete hold event: {e}")
        return False
```

- [ ] **Step 6: Verify no remaining AppleScript calendar references**

Search the file for any remaining `osascript` calls related to calendars (dialog functions should still have them, that's fine).

Run: `grep -n "osascript" gig_booking_manager.py`

Expected: Only dialog functions (`show_warning_dialog`, `show_choice_dialog`, etc.) should remain.

- [ ] **Step 7: Commit**

```bash
git add gig_booking_manager.py
git commit -m "Migrate gig_booking_manager calendar functions from AppleScript to CalDAV"
```

---

## Task 5: Migrate `cancel_booking.py`

Replace the internals of 2 delete functions.

**Files:**
- Modify: `cancel_booking.py` (lines 36, 82-147)

- [ ] **Step 1: Update imports**

Remove `CALENDAR_NAME` from the import on line 36. Add `import calendar_caldav`.

Change:
```python
from gig_booking_manager import (
    CALENDAR_NAME,
    BOOKING_LOG_FORM_URL,
```

To:
```python
import calendar_caldav

from gig_booking_manager import (
    BOOKING_LOG_FORM_URL,
```

- [ ] **Step 2: Replace `delete_booking_calendar_event()` internals**

Replace lines 82-117 with:

```python
def delete_booking_calendar_event(date_obj, initials_bracket):
    """
    Delete the booking calendar event for a DJ on a given date.
    Matches events by date and DJ initials bracket (e.g., [PB]).
    Skips events containing 'BACKUP DJ' or 'Hold to DJ'.
    Returns the count of deleted events.
    """
    try:
        count = calendar_caldav.delete_matching_events(
            date_obj, "Gigs",
            lambda e: initials_bracket in e["title"]
                and "BACKUP DJ" not in e["title"]
                and "Hold to DJ" not in e["title"]
        )
        return count
    except Exception as e:
        print(f"  WARNING: Could not delete calendar event: {e}")
        return 0
```

- [ ] **Step 3: Replace `delete_backup_calendar_event()` internals**

Replace lines 120-147 with:

```python
def delete_backup_calendar_event(date_obj, backup_dj):
    """Delete the backup DJ's all-day calendar event on a given date."""
    backup_initials = f"[{get_dj_initials(backup_dj)}]"
    try:
        count = calendar_caldav.delete_matching_events(
            date_obj, "Gigs",
            lambda e: "BACKUP DJ" in e["title"] and backup_initials in e["title"]
        )
        return count
    except Exception as e:
        print(f"  WARNING: Could not delete backup calendar event: {e}")
        return 0
```

- [ ] **Step 4: Verify no remaining AppleScript calendar references**

Run: `grep -n "osascript" cancel_booking.py`

Expected: No matches (cancel_booking.py has no dialog functions).

- [ ] **Step 5: Commit**

```bash
git add cancel_booking.py
git commit -m "Migrate cancel_booking calendar functions from AppleScript to CalDAV"
```

---

## Task 6: Migrate `stefano_maxed_enforcer.py`

Replace 1 function.

**Files:**
- Modify: `stefano_maxed_enforcer.py` (lines 37-38, 193-220)

- [ ] **Step 1: Update imports and remove constants**

Add `import calendar_caldav` at the top.

Remove lines 37-38:
```python
UNAVAILABLE_CALENDAR = "Unavailable"
CALENDAR_TITLE       = "[SB] MAXED OUT"
```

Keep `STEFANO_EMAIL` (line 35).

- [ ] **Step 2: Replace `create_calendar_event()` internals**

Replace lines 193-220 with:

```python
def create_calendar_event(event_date, dry_run=False):
    """Create an all-day [SB] MAXED OUT event on the Unavailable calendar."""
    if dry_run:
        print(f"      [DRY RUN] Calendar: [SB] MAXED OUT on {event_date.strftime('%b %-d, %Y')}")
        return True
    try:
        calendar_caldav.create_allday_event(
            "Unavailable", "[SB] MAXED OUT", event_date, STEFANO_EMAIL
        )
        return True
    except Exception as e:
        print(f"      Calendar error: {e}")
        return False
```

- [ ] **Step 3: Verify no remaining AppleScript calendar references**

Run: `grep -n "osascript" stefano_maxed_enforcer.py`

Expected: No matches.

- [ ] **Step 4: Commit**

```bash
git add stefano_maxed_enforcer.py
git commit -m "Migrate stefano_maxed_enforcer calendar function from AppleScript to CalDAV"
```

---

## Task 7: Set up test infrastructure and write tests

Set up pytest and write both mocked unit tests (run anytime, no server needed) and real integration tests (run manually, hit the CalDAV server).

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_calendar_caldav_unit.py`
- Create: `tests/test_calendar_caldav_integration.py`
- Create: `pytest.ini`

- [ ] **Step 1: Install pytest**

```bash
pip install pytest
```

- [ ] **Step 2: Create pytest config**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
markers =
    integration: tests that hit the real CalDAV server (deselect with -m "not integration")
```

- [ ] **Step 3: Create test scaffolding**

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:

```python
"""Shared fixtures for calendar_caldav tests."""
import datetime
import pytest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def mock_caldav_client():
    """Mock CalDAV client that doesn't hit the server."""
    with patch("calendar_caldav._get_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_calendar(mock_caldav_client):
    """Mock calendar object with save_event and search."""
    mock_cal = MagicMock()
    mock_cal.url = "https://caldav.love2tap.com/calendars/__uids__/65B490A6/1187934A/"
    mock_cal.client = mock_caldav_client

    with patch("calendar_caldav._get_calendar", return_value=mock_cal):
        yield mock_cal


@pytest.fixture
def sample_date():
    return datetime.date(2026, 6, 15)


@pytest.fixture
def sample_start_dt():
    return datetime.datetime(2026, 6, 15, 14, 0, tzinfo=TZ)


@pytest.fixture
def sample_end_dt():
    return datetime.datetime(2026, 6, 15, 23, 0, tzinfo=TZ)
```

- [ ] **Step 4: Write unit tests for create functions**

Create `tests/test_calendar_caldav_unit.py`:

```python
"""Unit tests for calendar_caldav module. No server connection needed."""
import datetime
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest

import calendar_caldav

TZ = ZoneInfo("America/Los_Angeles")


class TestCreateTimedEvent:
    """Tests for create_timed_event()."""

    def test_returns_uid(self, mock_calendar, sample_start_dt, sample_end_dt):
        uid = calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith", "Nestldown", sample_start_dt, sample_end_dt
        )
        assert uid is not None
        assert len(uid) > 0

    def test_calls_save_event(self, mock_calendar, sample_start_dt, sample_end_dt):
        calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith", "Nestldown", sample_start_dt, sample_end_dt
        )
        mock_calendar.save_event.assert_called_once()

    def test_vcal_contains_title(self, mock_calendar, sample_start_dt, sample_end_dt):
        calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith", "Nestldown", sample_start_dt, sample_end_dt
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "SUMMARY:[PB] Smith" in vcal

    def test_vcal_contains_location(self, mock_calendar, sample_start_dt, sample_end_dt):
        calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith", "Nestldown, Los Gatos",
            sample_start_dt, sample_end_dt
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "LOCATION:" in vcal
        assert "Nestldown" in vcal

    def test_vcal_contains_attendee_when_provided(
        self, mock_calendar, sample_start_dt, sample_end_dt
    ):
        calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith", "Nestldown",
            sample_start_dt, sample_end_dt,
            attendee_email="paul@bigfundj.com"
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "ATTENDEE" in vcal
        assert "paul@bigfundj.com" in vcal
        assert "ORGANIZER" in vcal

    def test_vcal_no_attendee_when_none(
        self, mock_calendar, sample_start_dt, sample_end_dt
    ):
        calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith", "Nestldown",
            sample_start_dt, sample_end_dt,
            attendee_email=None
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "ATTENDEE" not in vcal

    def test_vcal_has_correct_time_format(
        self, mock_calendar, sample_start_dt, sample_end_dt
    ):
        calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith", "Nestldown",
            sample_start_dt, sample_end_dt
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "DTSTART;TZID=America/Los_Angeles:20260615T140000" in vcal
        assert "DTEND;TZID=America/Los_Angeles:20260615T230000" in vcal

    def test_vcal_escapes_special_characters(
        self, mock_calendar, sample_start_dt, sample_end_dt
    ):
        calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith; Jones", "Venue, 123 Main St, City",
            sample_start_dt, sample_end_dt
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "\\;" in vcal
        assert "\\," in vcal

    def test_unknown_calendar_raises(self, mock_calendar, sample_start_dt, sample_end_dt):
        with patch("calendar_caldav._get_calendar", side_effect=ValueError("Unknown calendar")):
            with pytest.raises(ValueError):
                calendar_caldav.create_timed_event(
                    "Fake", "[PB] Smith", "Nestldown",
                    sample_start_dt, sample_end_dt
                )

    def test_planner_tag_in_title(self, mock_calendar, sample_start_dt, sample_end_dt):
        calendar_caldav.create_timed_event(
            "Gigs", "[PB] Smith (planner)", "Nestldown",
            sample_start_dt, sample_end_dt
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "(planner)" in vcal


class TestCreateAlldayEvent:
    """Tests for create_allday_event()."""

    def test_returns_uid(self, mock_calendar, sample_date):
        uid = calendar_caldav.create_allday_event(
            "Gigs", "[HK] BACKUP DJ", sample_date
        )
        assert uid is not None

    def test_calls_save_event(self, mock_calendar, sample_date):
        calendar_caldav.create_allday_event(
            "Gigs", "[HK] BACKUP DJ", sample_date
        )
        mock_calendar.save_event.assert_called_once()

    def test_vcal_uses_date_format(self, mock_calendar, sample_date):
        calendar_caldav.create_allday_event(
            "Gigs", "[HK] BACKUP DJ", sample_date
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "DTSTART;VALUE=DATE:20260615" in vcal
        # DTEND should be next day per RFC 5545
        assert "DTEND;VALUE=DATE:20260616" in vcal

    def test_vcal_contains_attendee(self, mock_calendar, sample_date):
        calendar_caldav.create_allday_event(
            "Gigs", "[HK] BACKUP DJ", sample_date,
            attendee_email="henry@bigfundj.com"
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "henry@bigfundj.com" in vcal

    def test_vcal_maxed_out_title(self, mock_calendar, sample_date):
        calendar_caldav.create_allday_event(
            "Unavailable", "[SB] MAXED OUT", sample_date,
            attendee_email="stefano@bigfundj.com"
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "[SB] MAXED OUT" in vcal

    def test_vcal_paid_backup_title(self, mock_calendar, sample_date):
        calendar_caldav.create_allday_event(
            "Gigs", "[FS] PAID BACKUP DJ", sample_date,
            attendee_email="felipe@bigfundj.com"
        )
        vcal = mock_calendar.save_event.call_args[0][0]
        assert "PAID BACKUP DJ" in vcal


class TestFindEventsByDate:
    """Tests for find_events_by_date() icalBuddy parsing."""

    def test_returns_empty_on_icalbuddy_failure(self, sample_date):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            result = calendar_caldav.find_events_by_date(sample_date)
            assert result == []

    def test_returns_empty_on_timeout(self, sample_date):
        with patch("subprocess.run") as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="icalBuddy", timeout=10)
            result = calendar_caldav.find_events_by_date(sample_date)
            assert result == []

    def test_returns_empty_on_not_found(self, sample_date):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = calendar_caldav.find_events_by_date(sample_date)
            assert result == []

    def test_returns_empty_on_empty_output(self, sample_date):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = calendar_caldav.find_events_by_date(sample_date)
            assert result == []


class TestDeleteMatchingEvents:
    """Tests for delete_matching_events() filtering logic."""

    def test_deletes_matching_events(self, sample_date):
        fake_events = [
            {"uid": "uid-1", "title": "[PB] Smith"},
            {"uid": "uid-2", "title": "[PB] BACKUP DJ"},
            {"uid": "uid-3", "title": "[HK] Jones"},
        ]
        with patch("calendar_caldav.find_events_by_date", return_value=fake_events), \
             patch("calendar_caldav.delete_event_by_uid", return_value=True) as mock_delete:

            count = calendar_caldav.delete_matching_events(
                sample_date, "Gigs",
                lambda e: "[PB]" in e["title"] and "BACKUP DJ" not in e["title"]
            )
            assert count == 1
            mock_delete.assert_called_once_with("Gigs", "uid-1")

    def test_hold_to_dj_match(self, sample_date):
        fake_events = [
            {"uid": "uid-1", "title": "[PB] Hold to DJ - Smith Wedding"},
            {"uid": "uid-2", "title": "[HK] Hold to DJ - Jones Wedding"},
        ]
        with patch("calendar_caldav.find_events_by_date", return_value=fake_events), \
             patch("calendar_caldav.delete_event_by_uid", return_value=True) as mock_delete:

            count = calendar_caldav.delete_matching_events(
                sample_date, "Gigs",
                lambda e: "Hold to DJ" in e["title"] and "[PB]" in e["title"]
            )
            assert count == 1
            mock_delete.assert_called_once_with("Gigs", "uid-1")

    def test_backup_dj_match(self, sample_date):
        fake_events = [
            {"uid": "uid-1", "title": "[PB] Smith"},
            {"uid": "uid-2", "title": "[HK] BACKUP DJ"},
            {"uid": "uid-3", "title": "[PB] BACKUP DJ"},
        ]
        with patch("calendar_caldav.find_events_by_date", return_value=fake_events), \
             patch("calendar_caldav.delete_event_by_uid", return_value=True) as mock_delete:

            count = calendar_caldav.delete_matching_events(
                sample_date, "Gigs",
                lambda e: "BACKUP DJ" in e["title"] and "[HK]" in e["title"]
            )
            assert count == 1
            mock_delete.assert_called_once_with("Gigs", "uid-2")

    def test_returns_zero_when_no_matches(self, sample_date):
        fake_events = [
            {"uid": "uid-1", "title": "[PB] Smith"},
        ]
        with patch("calendar_caldav.find_events_by_date", return_value=fake_events), \
             patch("calendar_caldav.delete_event_by_uid") as mock_delete:

            count = calendar_caldav.delete_matching_events(
                sample_date, "Gigs",
                lambda e: "[HK]" in e["title"]
            )
            assert count == 0
            mock_delete.assert_not_called()

    def test_returns_zero_when_no_events(self, sample_date):
        with patch("calendar_caldav.find_events_by_date", return_value=[]):
            count = calendar_caldav.delete_matching_events(
                sample_date, "Gigs",
                lambda e: True
            )
            assert count == 0

    def test_cancel_booking_match_excludes_backup_and_hold(self, sample_date):
        """Simulates the exact match logic from cancel_booking.delete_booking_calendar_event."""
        fake_events = [
            {"uid": "uid-1", "title": "[PB] Smith Wedding"},
            {"uid": "uid-2", "title": "[PB] BACKUP DJ"},
            {"uid": "uid-3", "title": "[PB] Hold to DJ - Smith"},
            {"uid": "uid-4", "title": "[HK] Jones Wedding"},
        ]
        with patch("calendar_caldav.find_events_by_date", return_value=fake_events), \
             patch("calendar_caldav.delete_event_by_uid", return_value=True) as mock_delete:

            initials_bracket = "[PB]"
            count = calendar_caldav.delete_matching_events(
                sample_date, "Gigs",
                lambda e: initials_bracket in e["title"]
                    and "BACKUP DJ" not in e["title"]
                    and "Hold to DJ" not in e["title"]
            )
            assert count == 1
            mock_delete.assert_called_once_with("Gigs", "uid-1")


class TestRetryOnError:
    """Tests for _retry_on_error() behavior."""

    def test_no_retry_on_success(self):
        fn = MagicMock(return_value="ok")
        result = calendar_caldav._retry_on_error(fn)
        assert result == "ok"
        fn.assert_called_once()

    def test_retries_on_connection_error(self):
        fn = MagicMock(side_effect=[ConnectionError("fail"), "ok"])
        with patch("time.sleep"):
            result = calendar_caldav._retry_on_error(fn)
        assert result == "ok"
        assert fn.call_count == 2

    def test_raises_after_max_retries(self):
        fn = MagicMock(side_effect=ConnectionError("fail"))
        with patch("time.sleep"):
            with pytest.raises(ConnectionError):
                calendar_caldav._retry_on_error(fn, max_retries=1)
```

- [ ] **Step 5: Write integration tests**

Create `tests/test_calendar_caldav_integration.py`:

```python
"""
Integration tests for calendar_caldav module.
These hit the real CalDAV server. Run manually:
    pytest tests/test_calendar_caldav_integration.py -m integration -v

All test invitations go to paul@bigfundj.com.
Test events use 2099-12-31 (far future, safe to clean up).
"""
import datetime
import pytest
from zoneinfo import ZoneInfo

import calendar_caldav

TZ = ZoneInfo("America/Los_Angeles")
TEST_DATE = datetime.date(2099, 12, 31)
TEST_EMAIL = "paul@bigfundj.com"


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the module-level client between tests."""
    calendar_caldav._client = None
    yield
    calendar_caldav._client = None


@pytest.mark.integration
class TestIntegrationCreate:

    def test_create_timed_event(self):
        uid = calendar_caldav.create_timed_event(
            "Gigs",
            "[PB] Integration Test Timed",
            "Test Location",
            datetime.datetime(2099, 12, 31, 14, 0),
            datetime.datetime(2099, 12, 31, 23, 0),
            TEST_EMAIL,
        )
        assert uid is not None
        # Clean up
        calendar_caldav.delete_event_by_uid("Gigs", uid)

    def test_create_allday_event(self):
        uid = calendar_caldav.create_allday_event(
            "Gigs",
            "[PB] Integration Test AllDay",
            TEST_DATE,
            TEST_EMAIL,
        )
        assert uid is not None
        # Clean up
        calendar_caldav.delete_event_by_uid("Gigs", uid)


@pytest.mark.integration
class TestIntegrationDelete:

    def test_create_and_delete_by_uid(self):
        uid = calendar_caldav.create_timed_event(
            "Gigs",
            "[PB] Delete Test",
            "Test Location",
            datetime.datetime(2099, 12, 31, 14, 0),
            datetime.datetime(2099, 12, 31, 23, 0),
        )
        deleted = calendar_caldav.delete_event_by_uid("Gigs", uid)
        assert deleted is True

    def test_delete_nonexistent_returns_false(self):
        deleted = calendar_caldav.delete_event_by_uid("Gigs", "nonexistent-uid-12345")
        assert deleted is False


@pytest.mark.integration
class TestIntegrationDeleteMatching:

    def test_delete_matching_by_title(self):
        # Create two events, delete only the one matching
        uid1 = calendar_caldav.create_allday_event(
            "Gigs", "[PB] BACKUP DJ", TEST_DATE
        )
        uid2 = calendar_caldav.create_allday_event(
            "Gigs", "[HK] BACKUP DJ", TEST_DATE
        )

        count = calendar_caldav.delete_matching_events(
            TEST_DATE, "Gigs",
            lambda e: "[PB]" in e["title"] and "BACKUP DJ" in e["title"]
        )
        assert count == 1

        # Clean up the other one
        calendar_caldav.delete_event_by_uid("Gigs", uid2)
```

- [ ] **Step 6: Run unit tests**

Run: `cd /Users/paulburchfield/Documents/projects/dj-availability-checker && pytest tests/test_calendar_caldav_unit.py -v`

Expected: All tests pass. No network calls made.

- [ ] **Step 7: Run integration tests**

Run: `pytest tests/test_calendar_caldav_integration.py -m integration -v`

Expected: All tests pass. Test events created and cleaned up on the real server.

- [ ] **Step 8: Commit**

```bash
git add pytest.ini tests/
git commit -m "Add pytest infrastructure and calendar_caldav unit + integration tests"
```

---

## Task 8: End-to-end validation

Run the actual scripts in test/dry-run mode to verify the migration works.

**Files:**
- Reference: All modified files

- [ ] **Step 1: Test gig_booking_manager in dry-run mode**

Run: `cd /Users/paulburchfield/Documents/projects/dj-availability-checker && python3 gig_booking_manager.py sample_bookings/normal_booking.json --dry-run`

Expected: Script runs without errors. No Calendar.app opens. Dry-run output prints calendar actions.

- [ ] **Step 2: Test gig_booking_manager in test mode with a real booking**

Run with `--test` flag against a sample booking JSON. This creates real calendar events but routes invitations to paul@bigfundj.com.

Expected: Calendar event appears in Fantastical. No Calendar.app opened. Paul receives invitation.

- [ ] **Step 3: Test cancel_booking in dry-run mode**

Run: `python3 cancel_booking.py sample_bookings/normal_booking.json --dry-run`

Expected: Script runs without errors. Reports what it would delete.

- [ ] **Step 4: Test stefano_maxed_enforcer in dry-run mode**

Run: `python3 stefano_maxed_enforcer.py --dry-run`

Expected: Script runs, prints [DRY RUN] messages for calendar events. No Calendar.app opens.

- [ ] **Step 5: Clean up any test events**

Delete any test events created during validation from the calendar.

Run: `python3 test_caldav_migration.py test4` (or manually delete in Fantastical)

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "Complete CalDAV calendar migration: all AppleScript calendar calls replaced"
```
