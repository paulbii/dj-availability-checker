#!/usr/bin/env python3
"""
EventKit read-only prototype — go/no-go gate for replacing the AppleScript
calendar deletes in cancel_booking.py.

Proves out three things:
  1. Calendar permission works in this launch path (Terminal, Stream Deck).
  2. The date-bounded query is fast (the AppleScript whose-clause takes 30s+).
  3. Exact-title matching finds the right event on a real date.

READ-ONLY. Queries and prints. Never writes, never deletes.

Run from Terminal:
    ./.venv/bin/python eventkit_prototype.py [M/D/YYYY]

Run the Stream Deck launch path (same wrapper style as cancel_booking.scpt):
    osascript -e 'do shell script "cd ~/Documents/projects/dj-availability-checker && ./.venv/bin/python eventkit_prototype.py > /tmp/eventkit_prototype.log 2>&1"'
    open /tmp/eventkit_prototype.log

Default date: 10/16/2026 (known to hold 6 events).
"""

import sys
import time
from datetime import datetime

import objc
import EventKit
from Foundation import NSDate, NSRunLoop

CALENDAR_NAME = "Gigs"

# EKAuthorizationStatus values (EKEntityTypeEvent = 0)
AUTH_LABELS = {
    0: "notDetermined",
    1: "restricted",
    2: "denied",
    3: "fullAccess (authorized)",
    4: "writeOnly",
}


def request_access(store):
    """Request calendar access, blocking until macOS answers. Returns bool."""
    result = {}

    def handler(granted, error):
        result["granted"] = bool(granted)
        result["error"] = error

    # macOS 14+ API, with the legacy call as fallback for older systems.
    if store.respondsToSelector_("requestFullAccessToEventsWithCompletion:"):
        store.requestFullAccessToEventsWithCompletion_(handler)
    else:
        store.requestAccessToEntityType_completion_(0, handler)

    # Pump the run loop so the completion handler can fire.
    deadline = time.time() + 120  # generous: the user may need to click a dialog
    while "granted" not in result and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.1)
        )
    return result.get("granted", False)


def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 else "10/16/2026"
    target = datetime.strptime(date_arg, "%m/%d/%Y")

    print(f"EventKit prototype — read-only")
    print(f"Python: {sys.executable}")
    print(f"Target date: {target:%a %m/%d/%Y}, calendar: {CALENDAR_NAME}")
    print()

    # ── 1. Permission ──
    status = EventKit.EKEventStore.authorizationStatusForEntityType_(0)
    print(f"[1] Authorization status: {status} = {AUTH_LABELS.get(status, '?')}")

    store = EventKit.EKEventStore.alloc().init()

    if status == 0:  # notDetermined — this run should trigger the macOS dialog
        print("    Requesting access (a macOS permission dialog may appear)...")
        granted = request_access(store)
        print(f"    Granted: {granted}")
        if not granted:
            print("\nNO-GO: access not granted in this launch path.")
            sys.exit(2)
    elif status in (1, 2):
        print("\nNO-GO: calendar access denied/restricted for this launch path.")
        print("Fix: System Settings → Privacy & Security → Calendars, or")
        print("delete the stale grant with: tccutil reset Calendar")
        sys.exit(2)
    elif status == 4:
        print("\nNO-GO: write-only access — cannot query events.")
        sys.exit(2)

    # ── 2. Find the calendar ──
    # Remote (CalDAV/iCloud) sources load asynchronously; refresh and give the
    # run loop time to settle before concluding a calendar doesn't exist.
    store.refreshSourcesIfNecessary()
    gigs = []
    t0 = time.monotonic()
    for _ in range(100):  # up to 10s
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.1)
        )
        calendars = store.calendarsForEntityType_(0)
        gigs = [c for c in calendars if str(c.title()) == CALENDAR_NAME]
        if gigs:
            break
    t_cal = time.monotonic() - t0

    print(f"\n[2] Calendars by source (after {t_cal:.1f}s settle):")
    for s in store.sources():
        names = sorted(str(c.title()) for c in s.calendarsForEntityType_(0))
        print(f"      {s.title()}: {names if names else '(none visible)'}")

    if not gigs:
        print(f"\nNO-GO: no calendar named '{CALENDAR_NAME}' visible to this process.")
        print("If the source above shows '(none visible)' for the BIG FUN account,")
        print("this launch path can't see CalDAV calendars — permission attribution.")
        sys.exit(2)
    # The Gigs name may exist on more than one account; search all of them.
    print(f"    '{CALENDAR_NAME}' calendar(s) found: {len(gigs)}")

    # ── 3. The date-bounded query (the part AppleScript can't do fast) ──
    day_start = datetime(target.year, target.month, target.day, 0, 0, 0)
    day_end = datetime(target.year, target.month, target.day, 23, 59, 59)
    ns_start = NSDate.dateWithTimeIntervalSince1970_(day_start.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(day_end.timestamp())

    t0 = time.monotonic()
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        ns_start, ns_end, gigs
    )
    events = store.eventsMatchingPredicate_(predicate)
    t_query = time.monotonic() - t0

    print(f"\n[3] Query took {t_query * 1000:.0f} ms "
          f"(AppleScript equivalent: timed out at 30,000 ms on 7/29)")
    print(f"    Events on {target:%m/%d/%Y}: {len(events)}")
    for ev in events:
        start = ev.startDate()
        all_day = "all-day" if ev.isAllDay() else str(start)
        print(f"      • {ev.title()}   [{all_day}]   id={ev.eventIdentifier()}")

    # ── 4. Exact-title match demo ──
    demo_title = "[PB] Julie and Jaylin"
    matches = [ev for ev in events if str(ev.title()) == demo_title]
    print(f"\n[4] Exact-title match for {demo_title!r}: {len(matches)} event(s)")
    print("    (0 is CORRECT if you already deleted it by hand)")

    print("\nGO: EventKit works in this launch path.")


if __name__ == "__main__":
    main()
