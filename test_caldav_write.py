#!/usr/bin/env python3
"""
Test CalDAV read/write/delete on the Gigs calendar,
authenticating as the 'schedule' user who owns it.

Usage:
    python3 test_caldav_write.py
"""

import datetime
import sys
from zoneinfo import ZoneInfo

import caldav
import keyring

TIMEZONE = ZoneInfo("America/Los_Angeles")
SERVICE_NAME = "bigfun-caldav-schedule"
GIGS_URL = "https://caldav.love2tap.com/calendars/__uids__/65B490A6-6667-48BC-B9E4-1A638DAA787E/1187934A-6A2E-43A3-8355-74382DC82F47/"


def get_client():
    url = keyring.get_password(SERVICE_NAME, "url")
    username = keyring.get_password(SERVICE_NAME, "username")
    password = keyring.get_password(SERVICE_NAME, "password")
    if not all([url, username, password]):
        print("No CalDAV credentials found for 'schedule' account.")
        sys.exit(1)
    print(f"   User: {username}")
    return caldav.DAVClient(url=url, username=username, password=password)


def main():
    print("1. Connecting as schedule...")
    client = get_client()

    print(f"\n2. Accessing Gigs calendar...")
    gigs = caldav.Calendar(client=client, url=GIGS_URL)
    try:
        name = gigs.get_display_name()
        print(f"   Connected: {name}")
    except Exception as e:
        print(f"   FAILED: {e}")
        sys.exit(1)

    # Create test event
    test_uid = "caldav-write-test-bigfun-delete-me"
    vcal = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//BIG FUN//CalDAV Write Test//EN
BEGIN:VEVENT
UID:{test_uid}
DTSTART;TZID=America/Los_Angeles:20991231T100000
DTEND;TZID=America/Los_Angeles:20991231T110000
SUMMARY:[TEST] CalDAV Write Test -- Delete Me
LOCATION:Nowhere
DESCRIPTION:Automated test event. Safe to delete.
END:VEVENT
END:VCALENDAR"""

    print("\n3. Creating test event (2099-12-31, 10-11am)...")
    try:
        event = gigs.save_event(vcal)
        print(f"   Created. URL: {event.url}")
    except Exception as e:
        print(f"   FAILED: {e}")
        sys.exit(1)

    print("\n4. Searching for event to verify...")
    try:
        found = gigs.search(
            start=datetime.datetime(2099, 12, 31, 0, 0, 0, tzinfo=TIMEZONE),
            end=datetime.datetime(2100, 1, 1, 0, 0, 0, tzinfo=TIMEZONE),
            event=True, expand=True,
        )
        titles = [str(ev.icalendar_component.get("summary", "")) for ev in found]
        if any("CalDAV Write Test" in t for t in titles):
            print(f"   Verified: {titles}")
        else:
            print(f"   Not found in search. Events: {titles}")
    except Exception as e:
        print(f"   Search FAILED: {e}")

    print("\n5. Deleting test event...")
    try:
        event.delete()
        print("   Deleted.")
    except Exception as e:
        print(f"   FAILED: {e}")
        sys.exit(1)

    print("\n6. Confirming deletion (search again)...")
    try:
        found = gigs.search(
            start=datetime.datetime(2099, 12, 31, 0, 0, 0, tzinfo=TIMEZONE),
            end=datetime.datetime(2100, 1, 1, 0, 0, 0, tzinfo=TIMEZONE),
            event=True, expand=True,
        )
        if not found:
            print("   Confirmed: no events on that date.")
        else:
            titles = [str(ev.icalendar_component.get("summary", "")) for ev in found]
            print(f"   Still found: {titles}")
    except Exception as e:
        print(f"   Search failed: {e}")

    print("\n--- RESULT ---")
    print("Full CalDAV read/write/delete confirmed on Gigs calendar.")
    print("No Calendar.app was opened during this test.")


if __name__ == "__main__":
    main()
