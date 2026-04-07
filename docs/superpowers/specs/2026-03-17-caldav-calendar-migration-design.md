# CalDAV Calendar Migration

Replace all AppleScript calendar operations with CalDAV writes and icalBuddy reads. Eliminates Calendar.app from opening during script execution.

## Problem

Seven functions across three files use AppleScript (`osascript`) to create and delete calendar events. Every AppleScript call opens Calendar.app, which is disruptive and slow. The scripts already use icalBuddy for reads (conflict checks, year queries), and a working CalDAV connection to the same server exists. The tools to replace AppleScript are already in place.

## Scope

### In scope

- Replace 7 AppleScript calendar functions with CalDAV (writes/deletes) and icalBuddy (delete lookups)
- New shared module `calendar_caldav.py`
- Attendee/invitation support (DJs receive calendar invitations)
- test_mode support (route invitations to paul@bigfundj.com)
- Pre-migration validation tests

### Out of scope

- Changing any icalBuddy read operations (conflict checks, booking comparator)
- Changing dialog/UI AppleScript functions
- Changing Google Sheets operations
- Changing the booking/cancellation flow logic
- Archived scripts

## Current state

| File | Function | Operation | Calendar | Method |
|------|----------|-----------|----------|--------|
| gig_booking_manager.py | `create_timed_calendar_event()` | Create timed event | Gigs | AppleScript |
| gig_booking_manager.py | `create_allday_backup_event()` | Create all-day backup event | Gigs | AppleScript |
| gig_booking_manager.py | `delete_hold_calendar_event()` | Delete "Hold to DJ" event | Gigs | AppleScript |
| cancel_booking.py | `delete_booking_calendar_event()` | Delete booking event | Gigs | AppleScript |
| cancel_booking.py | `delete_backup_calendar_event()` | Delete backup event | Gigs | AppleScript |
| stefano_maxed_enforcer.py | `create_calendar_event()` | Create MAXED OUT event | Unavailable | AppleScript |
| backup_assigner.py | (imports from gig_booking_manager) | Create + check | Gigs | Inherited |

### Functions that do NOT change

| File | Function | Method | Why unchanged |
|------|----------|--------|---------------|
| gig_booking_manager.py | `check_calendar_conflicts()` | icalBuddy | Already silent, no Calendar.app |
| booking_comparator.py | `fetch_master_calendar()` | icalBuddy | Already silent, no Calendar.app |
| gig_booking_manager.py | `show_warning_dialog()` etc. | AppleScript | UI dialogs, not calendar |

## Target state

### New module: `calendar_caldav.py`

Location: `/Users/paulburchfield/Documents/projects/dj-availability-checker/calendar_caldav.py`

Dependencies: `caldav`, `keyring`, `subprocess` (for icalBuddy), `uuid`, `zoneinfo`

#### Connection

- Authenticates as `schedule` user via Keychain (service: `bigfun-caldav-schedule`)
- Server: `https://caldav.love2tap.com`
- Principal UID: `65B490A6-6667-48BC-B9E4-1A638DAA787E`
- Two calendars: Gigs and Unavailable
  - Gigs URL known: `1187934A-6A2E-43A3-8355-74382DC82F47`
  - Unavailable URL: must be discovered during Test 0 (list calendars on the `schedule` principal). If not visible under `schedule`, may require the `paul` account credentials or a delegation grant.
- Timezone: `America/Los_Angeles`
- Connection is lazy-initialized (created on first call, reused after)
- Retry: all CalDAV operations retry once after a 5-second delay on connection/timeout errors. Retry logic lives inside `calendar_caldav.py` so callers don't handle it.

#### Create functions

```python
def create_timed_event(
    calendar_name: str,    # "Gigs" or "Unavailable"
    title: str,
    location: str,
    start_dt: datetime,
    end_dt: datetime,
    attendee_email: str | None = None,
) -> str:
    """Create a timed event. Returns the event UID."""
```

```python
def create_allday_event(
    calendar_name: str,
    title: str,
    date_obj: date,
    attendee_email: str | None = None,
) -> str:
    """Create an all-day event. Returns the event UID."""
```

Both functions:
- Build a VCALENDAR/VEVENT string with a generated UUID
- Include ORGANIZER (schedule@bigfundj.com) and ATTENDEE if email provided
- Set RSVP=TRUE on attendee to trigger invitation
- Call `calendar.save_event(vcal_string)`
- Return the UID

#### VCALENDAR structure (timed event example)

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//BIG FUN//Gig Booking Manager//EN
BEGIN:VEVENT
UID:{generated-uuid}
DTSTART;TZID=America/Los_Angeles:20260328T140000
DTEND;TZID=America/Los_Angeles:20260328T230000
SUMMARY:[PB] Smith
LOCATION:Nestldown, 27500 Old Santa Cruz Hwy, Los Gatos CA 95033
ORGANIZER;CN=BIG FUN:mailto:schedule@bigfundj.com
ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:paul@bigfundj.com
END:VEVENT
END:VCALENDAR
```

#### VCALENDAR structure (all-day event example)

All-day events use `VALUE=DATE` (no time component). DTEND is the day after the event per RFC 5545.

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//BIG FUN//Gig Booking Manager//EN
BEGIN:VEVENT
UID:{generated-uuid}
DTSTART;VALUE=DATE:20260328
DTEND;VALUE=DATE:20260329
SUMMARY:[SB] MAXED OUT
ORGANIZER;CN=BIG FUN:mailto:schedule@bigfundj.com
ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:stefano@bigfundj.com
END:VEVENT
END:VCALENDAR
```

#### Delete functions

```python
def find_events_by_date(
    date_obj: date,
    calendar_names: str = "Gigs",  # comma-separated for icalBuddy
) -> list[dict]:
    """
    Find events on a date using icalBuddy with -uid flag.
    Returns list of {"uid": str, "title": str} dicts.
    Returns empty list on subprocess failure (icalBuddy not found, timeout, etc.).

    If icalBuddy -uid output is unusable (Test 3 failure), this function
    falls back to CalDAV .search() for both lookup and UID retrieval.
    In that case, delete_event_by_uid receives a known-good UID from
    the CalDAV object directly.
    """
```

```python
def delete_event_by_uid(calendar_name: str, uid: str) -> bool:
    """
    Delete an event by UID via CalDAV.
    Primary strategy: construct URL as {calendar_url}/{uid}.ics and delete.
    Fallback: if URL construction fails (UID format mismatch), use
    CalDAV .search() to find the event by date range, match by UID, then
    call event.delete() on the returned object.
    Returns True if deleted, False if not found.
    """
```

```python
def delete_matching_events(
    date_obj: date,
    calendar_name: str,
    match_fn: callable,  # receives {"uid": str, "title": str}, returns bool
) -> int:
    """
    Find events on date, filter with match_fn, delete matches.
    Returns count of deleted events.
    """
```

### Migration strategy: wrapper approach

All existing function signatures stay the same. The AppleScript internals get replaced with `calendar_caldav` calls. This preserves the API surface so importers (backup_assigner.py, cancel_booking.py) continue to work with zero call-site changes.

### Changes to gig_booking_manager.py

**Add:** `import calendar_caldav`

**Replace internals of `create_timed_calendar_event(booking, cal_start, cal_end, test_mode=False)`:**

Keep the function signature. Remove the AppleScript code. The new body:
1. Builds title and location strings (same logic as today)
2. Resolves attendee email (same test_mode routing as today)
3. Calls `calendar_caldav.create_timed_event("Gigs", title, location, cal_start, cal_end, invitee_email)`
4. Returns title (same as today)

**Replace internals of `create_allday_backup_event(date_obj, dj_name, test_mode=False)`:**

Keep the function signature. Remove the AppleScript code. The new body:
1. Builds title via `get_backup_title(dj_name)` (same as today)
2. Resolves attendee email (same test_mode routing)
3. Calls `calendar_caldav.create_allday_event("Gigs", title, date_obj, invitee_email)`
4. Returns title (same as today)

**Replace internals of `delete_hold_calendar_event(date_obj, initials_bracket)`:**

Keep the function signature. Remove the AppleScript code. The new body:
```python
count = calendar_caldav.delete_matching_events(
    date_obj, "Gigs",
    lambda e: "Hold to DJ" in e["title"] and initials_bracket in e["title"]
)
return count > 0
```

**Remove:** `CALENDAR_NAME = "Gigs"` constant (line 68). No longer needed internally. However, `cancel_booking.py` imports it. Remove the import from cancel_booking.py at the same time (it won't need it, since its delete functions will also use `calendar_caldav` internally).

### Changes to cancel_booking.py

**Remove:** `CALENDAR_NAME` from imports (line 36)

**Add:** `import calendar_caldav`

**Replace internals of `delete_booking_calendar_event(date_obj, initials_bracket)`:**

Keep the function signature. Remove the AppleScript code. The new body:
```python
count = calendar_caldav.delete_matching_events(
    date_obj, "Gigs",
    lambda e: initials_bracket in e["title"]
        and "BACKUP DJ" not in e["title"]
        and "Hold to DJ" not in e["title"]
)
return count
```

**Replace internals of `delete_backup_calendar_event(date_obj, backup_dj)`:**

Keep the function signature. Remove the AppleScript code. The new body:
```python
backup_initials = f"[{get_dj_initials(backup_dj)}]"
count = calendar_caldav.delete_matching_events(
    date_obj, "Gigs",
    lambda e: "BACKUP DJ" in e["title"] and backup_initials in e["title"]
)
return count
```

### Changes to stefano_maxed_enforcer.py

**Remove:**
- `UNAVAILABLE_CALENDAR` constant (line 37)
- `CALENDAR_TITLE` constant (line 38)

**Add:** `import calendar_caldav`

**Keep:** `STEFANO_EMAIL` constant (still used for attendee), `dry_run` logic in caller

**Replace internals of `create_calendar_event(event_date, dry_run=False)`:**

Keep the function signature. Remove the AppleScript code. The new body:
```python
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

Note: `stefano_maxed_enforcer.py` does not have a `--test` flag today. No test_mode routing is added for this function. If test_mode is needed later, it can be added as a follow-up.

### Changes to backup_assigner.py

No changes. It imports `create_allday_backup_event` and `check_calendar_conflicts` from `gig_booking_manager`. Since those functions keep their signatures, backup_assigner works without modification.

## Pre-migration test plan

These tests must pass before any production code changes. All test invitations go to paul@bigfundj.com.

### Test 0: Calendar discovery

List all calendars visible to the `schedule` account. Confirm both Gigs and Unavailable are accessible. Record the Unavailable calendar URL. If Unavailable is not visible, determine what account/delegation is needed.

### Test 1: CalDAV timed event with attendee

Create a timed event on Gigs calendar for a date far in the future (December 31, 2099). Add paul@bigfundj.com as attendee. Verify:
- Event appears in Fantastical/Calendar
- Paul receives a calendar invitation email
- Event has correct title, location, start/end times

### Test 2: CalDAV all-day event with attendee

Create an all-day event on Unavailable calendar for December 30, 2099 (requires Test 0 to confirm calendar access). Add paul@bigfundj.com as attendee. Verify:
- Event appears as all-day
- Paul receives invitation

### Test 3: icalBuddy UID output

Run icalBuddy with `-uid` flag against the test events from Tests 1 and 2. Verify:
- icalBuddy returns a UID for each event
- The UID matches the one used in the VCALENDAR (or can be mapped to the CalDAV URL)
- Document the exact icalBuddy output format so the parser can be written to match

### Test 4: CalDAV delete by UID

Using the UID from Test 3, attempt to delete via constructed URL (`{calendar_url}/{uid}.ics`). If that fails, fall back to CalDAV `.search()` to find the event and call `event.delete()`. Verify:
- Event is removed from the calendar
- No errors
- Document which delete strategy works so implementation uses the right one

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Server doesn't send invitations when ATTENDEE is set | DJs stop receiving calendar invites | Test 1 catches this. Fallback: server config change or separate email notification |
| icalBuddy UID doesn't match CalDAV event filename | Deletes break | Test 3 catches this. Fallback: use CalDAV `.search()` for delete lookups |
| CalDAV connection timeout during booking | Booking succeeds in Sheets but no calendar event | Add retry logic (1 retry with 5s delay). Log failure clearly so Paul can create manually |
| Unavailable calendar on different principal/account | Stefano events fail | Verify Unavailable calendar is accessible under the `schedule` account during test setup |

## Dependencies

Already installed:
- `caldav` Python library
- `keyring` Python library
- `icalBuddy` CLI (`/opt/homebrew/bin/icalBuddy`)
- Keychain credentials for `bigfun-caldav-schedule`

No new dependencies required.
