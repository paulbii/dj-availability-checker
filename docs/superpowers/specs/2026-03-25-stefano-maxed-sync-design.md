# Stefano MAXED Enforcer v2: Full Sync

**Date:** 2026-03-25
**Status:** Draft
**File:** `stefano_maxed_enforcer.py` (rewrite in place)

## Problem

The current `stefano_maxed_enforcer.py` only adds MAXED dates forward from bookings. When a booking is canceled, the MAXED dates it created remain in the matrix and on the calendar. Paul has to manually identify and clean those up. The script should recalculate from scratch on every run and propose both additions and removals.

## Rules

Two rules govern Stefano's availability. These are unchanged from the current implementation.

1. **Weekend buffer (1-week gap):** If Stefano is BOOKED on any Fri/Sat/Sun, the Fri/Sat/Sun of the immediately preceding week and immediately following week are MAXED. This prevents back-to-back weekend bookings.
2. **Monthly cap (2/month):** If a calendar month has 2 or more Fri/Sat/Sun bookings, all remaining Fri/Sat/Sun dates in that month are MAXED.

Only Fri/Sat/Sun dates are considered for both triggering rules and being MAXED. Weekday bookings and weekday dates are out of scope.

## Design

### Data Flow

```
Read matrix → Collect BOOKED dates → Recalculate full rule set → Diff against current state → Display additions + removals → User selects → Execute approved changes
```

### Recalculation (replaces `find_suggestions()`)

New function: `calculate_sync(rows, year)`

1. Collect all BOOKED Fri/Sat/Sun dates from Stefano's column
2. For each booked date, compute adjacent weekend dates (prior week + next week Fri/Sat/Sun) using `adjacent_weekend_dates()`. Date math handles month boundaries naturally.
3. For each month with 2+ bookings, collect all Fri/Sat/Sun dates in that month
4. Union of steps 2 and 3 = `should_be_maxed` set
5. Exclude from `should_be_maxed` any date whose current cell value is in SKIP_VALUES (BOOKED, BACKUP, RESERVED, STANFORD) -- these dates are already committed and should not be touched

Returns:
- `additions`: dict of `{date: (row_number, current_value, [reasons])}` -- dates in `should_be_maxed` where cell is currently blank or OK
- `removals`: dict of `{date: (row_number, current_value, [reasons])}` -- dates where cell is MAXED but date is NOT in `should_be_maxed`
- `booked_fss`: list of booked Fri/Sat/Sun dates (for summary display)

### Diff Rules

| Current Cell | In `should_be_maxed`? | Action |
|---|---|---|
| blank or OK | Yes | **Add** → write MAXED, create calendar event |
| MAXED | Yes | No action (already correct) |
| MAXED | No | **Remove** → restore default value, delete calendar event |
| blank or OK | No | No action (already correct) |
| OUT | Either | No action (OUT is a manual/personal block, not rule-based) |
| BOOKED/BACKUP/RESERVED/STANFORD | Either | No action (skip values) |

### Removal Reasons

For removals, the reason string explains why the date no longer needs to be MAXED. Format: "no active booking requires this date to be blocked"

For additions, reasons are the same as the current implementation (e.g., "prior weekend buffer (Aug 8 booking)", "monthly cap (August has 2 bookings)").

### Default Cell Values on Removal

When clearing a MAXED cell, restore to the appropriate default for that day of week:

- Saturday → blank (empty string)
- Friday → OUT
- Sunday → OUT

Use the existing `get_default_cell_value(dj_name, date_obj)` from `cancel_booking.py`. As a prerequisite refactor, move this function into `dj_core.py` so both scripts can import it from a shared location.

### Display (replaces `display_and_select()`)

Two-section numbered list:

```
── Dates to MAXED ──────────────────────────────────
  [ 1]  Sat Aug 1  (currently: OK)
         → prior weekend buffer (Aug 8 booking)
  [ 2]  Sun Aug 2
         → prior weekend buffer (Aug 8 booking)

── Dates to Open Up ────────────────────────────────
  [ 3]  Sat Aug 15  (currently: MAXED)
         → no active booking requires this date to be blocked
  [ 4]  Sun Aug 16  (currently: MAXED)
         → no active booking requires this date to be blocked

  4 changes suggested.
  Enter numbers to apply (e.g. 1,3,5), 'all', or press Enter to skip:
```

Numbering is continuous across both sections so the selection picker works the same way.

### Execution

Each approved change executes two operations:

**For additions:**
1. `write_maxed()` -- write MAXED to Stefano's cell (unchanged from current)
2. `create_calendar_event()` -- create all-day `[SB] MAXED OUT` on Unavailable calendar with Stefano as attendee (unchanged from current)

**For removals:**
1. `clear_maxed()` -- write the default cell value to Stefano's cell (new function, mirrors `write_maxed()`)
2. `delete_calendar_event()` -- find and delete `[SB] MAXED OUT` event on Unavailable calendar for that date (new function)

### Calendar Deletion (AppleScript)

New function: `delete_calendar_event(event_date, dry_run=False)`

Searches the "Unavailable" calendar (hardcoded, consistent with `create_calendar_event()`) for events on the target date where the summary contains "[SB]" and "MAXED". Deletes all matches. Pattern follows `cancel_booking.py`'s `delete_booking_calendar_event()`.

### CLI Interface

```
python3 stefano_maxed_enforcer.py [--year 2026] [--dry-run]
```

No new flags. Full sync is the default behavior.

### Summary Output

After reading the matrix and before showing suggestions:

```
  Booked dates (Fri/Sat/Sun): 3
  Jul 18, Aug 22, Sep 12
  Currently MAXED: 8
  Correctly MAXED: 6
  To add: 2
  To remove: 2
```

## Preserved

- All configuration constants (STEFANO_COL_LETTER, STEFANO_COL_INDEX, STEFANO_COL_NUM, STEFANO_EMAIL)
- SKIP_VALUES set
- `parse_matrix_date()` helper
- `is_fss()` helper
- `adjacent_weekend_dates()` helper
- `read_stefano_column()` bulk read
- `write_maxed()` function
- `create_calendar_event()` function and AppleScript pattern
- Interactive selection UX (numbered list, all/specific/skip)
- `--year` and `--dry-run` flags
- Google Sheets connection via `init_google_sheets_from_file()`

## Changed

| Current | New | Why |
|---|---|---|
| `find_suggestions()` | `calculate_sync()` | Returns both additions and removals |
| `display_and_select()` | Updated | Two-section display (add + remove) |
| -- | `delete_calendar_event()` | Removal needs calendar cleanup |
| -- | `clear_maxed()` | Removal needs matrix cleanup |
| `ALREADY_MAXED_VALUES` | Retired | MAXED and OUT now have distinct behavior; the combined set no longer applies |
| `get_default_cell_value()` in `cancel_booking.py` | Moved to `dj_core.py` | Shared utility needed by both scripts |

## Edge Cases

1. **Month boundaries:** The weekend buffer rule uses date math (`adjacent_weekend_dates()`), so a booking on Aug 1 (Friday) naturally produces buffer dates in July. No special handling needed since we read the full year.
2. **Year boundaries:** A booking on Jan 2 (Friday) would produce buffer dates in late December of the prior year. Those dates won't exist in `date_map` (which only contains the target year) and will be silently skipped. Acceptable limitation -- Paul can handle the rare year-boundary case manually.
3. **Multiple bookings same month:** If a month has 3 bookings, the monthly cap rule still applies (all remaining Fri/Sat/Sun are MAXED). If one is canceled bringing it to 2, the cap still holds. Only when it drops below 2 does the cap release.
4. **BOOKED dates in `should_be_maxed`:** A date that's BOOKED and also falls in a buffer zone stays BOOKED. SKIP_VALUES always take priority.
5. **OUT dates:** Never touched. OUT means personal unavailability, not rule-based. The script ignores them entirely.
6. **Calendar event not found on deletion:** Print a warning but don't fail. The matrix update is the source of truth; the calendar event is a convenience.
