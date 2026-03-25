# Stefano MAXED Enforcer v2 (Full Sync) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `stefano_maxed_enforcer.py` from one-directional (add MAXED) to bidirectional sync that recalculates from scratch and proposes both additions and removals.

**Architecture:** Single-file rewrite of `stefano_maxed_enforcer.py` with a prerequisite refactor moving `get_default_cell_value()` into `dj_core.py`. The core change replaces `find_suggestions()` with `calculate_sync()` which returns both additions and removals. Display and execution logic updated to handle both directions.

**Tech Stack:** Python 3, gspread (Google Sheets API), AppleScript via subprocess (macOS Calendar)

**Spec:** `docs/superpowers/specs/2026-03-25-stefano-maxed-sync-design.md`

---

### Task 1: Move `get_default_cell_value` to `dj_core.py`

**Files:**
- Modify: `dj_core.py` (add function after line ~173, end of shared utilities section)
- Modify: `cancel_booking.py` (remove function, import from dj_core)
- Modify: `stefano_maxed_enforcer.py` (add import)

- [ ] **Step 1: Add `get_default_cell_value` to `dj_core.py`**

Copy the function from `cancel_booking.py:53-78` into `dj_core.py` after the `date_to_sheet_format()` function (line ~173), inside the "SHARED UTILITY FUNCTIONS" section.

```python
def get_default_cell_value(dj_name, date_obj):
    """
    Return the default cell value for a DJ on a given date.
    Matches the spreadsheet formulas:
      - Woody:    weekends -> OUT, weekdays -> ""
      - Stefano:  weekdays (Mon-Fri) and Sundays -> OUT, Saturdays -> ""
      - Felipe:   weekdays (Mon-Fri) -> OUT, weekends -> ""
      - Others:   always ""
    """
    weekday = date_obj.weekday()  # 0=Monday, 6=Sunday
    is_weekend = weekday >= 5     # Saturday=5, Sunday=6

    if dj_name == "Woody":
        return "OUT" if is_weekend else ""

    if dj_name == "Stefano":
        # OUT on weekdays (Mon-Fri) and Sunday, blank on Saturday
        if weekday == 5:  # Saturday
            return ""
        return "OUT"

    if dj_name == "Felipe":
        return "OUT" if not is_weekend else ""

    # Henry, Paul, Stephanie -- always blank
    return ""
```

- [ ] **Step 2: Update `cancel_booking.py` to import from `dj_core`**

Remove the `get_default_cell_value` function definition and its preceding comment block (lines 49-78) from `cancel_booking.py`. Add to the existing import from dj_core:

```python
from dj_core import get_dj_initials, get_default_cell_value
```

(Check the existing imports at the top of `cancel_booking.py` and add `get_default_cell_value` to whichever import line already pulls from `dj_core`.)

- [ ] **Step 3: Verify `cancel_booking.py` still works**

Run: `python3 -c "from cancel_booking import get_default_cell_value; from datetime import date; print(get_default_cell_value('Stefano', date(2026, 8, 8)))"`

Expected: empty string (Aug 8 2026 is a Saturday)

- [ ] **Step 4: Commit**

```bash
git add dj_core.py cancel_booking.py
git commit -m "refactor: move get_default_cell_value to dj_core for shared use"
```

---

### Task 2: Write tests for `calculate_sync`

**Files:**
- Create: `test_stefano_enforcer.py`

All tests use pure logic functions with no Google Sheets or Calendar dependencies. Build fake row data to simulate matrix state.

- [ ] **Step 1: Write test file with helper and core sync tests**

Create `test_stefano_enforcer.py`:

```python
#!/usr/bin/env python3
"""
Unit tests for stefano_maxed_enforcer.py

Run with:
  python3 -m pytest test_stefano_enforcer.py -v

Tests all sync logic (recalculation, diffing) without
requiring Google Sheets or Calendar access.
"""

import unittest
from datetime import date

# These will be imported after Task 3 implementation.
# For now, write tests against the expected API.
from stefano_maxed_enforcer import (
    calculate_sync,
    is_fss,
    adjacent_weekend_dates,
    parse_matrix_date,
)


def make_rows(entries, year=2026):
    """
    Build fake row data from a compact format.

    entries: list of (month, day, value) tuples
    Returns: list of (date_obj, row_number, cell_value) matching
             read_stefano_column() output format.
    """
    rows = []
    for i, (m, d, val) in enumerate(entries):
        rows.append((date(year, m, d), i + 2, val))
    return rows


class TestIsFSS(unittest.TestCase):
    def test_friday(self):
        self.assertTrue(is_fss(date(2026, 8, 7)))   # Friday

    def test_saturday(self):
        self.assertTrue(is_fss(date(2026, 8, 8)))   # Saturday

    def test_sunday(self):
        self.assertTrue(is_fss(date(2026, 8, 9)))   # Sunday

    def test_weekday(self):
        self.assertFalse(is_fss(date(2026, 8, 10)))  # Monday


class TestAdjacentWeekendDates(unittest.TestCase):
    def test_saturday_booking(self):
        """Booking on Sat Aug 8 should buffer Fri/Sat/Sun of prior and next week."""
        prior, nxt = adjacent_weekend_dates(date(2026, 8, 8))
        self.assertEqual(prior, [date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2)])
        self.assertEqual(nxt, [date(2026, 8, 14), date(2026, 8, 15), date(2026, 8, 16)])

    def test_month_boundary(self):
        """Booking on Sat Aug 1 should produce prior dates in July."""
        prior, nxt = adjacent_weekend_dates(date(2026, 8, 1))
        self.assertEqual(prior[0], date(2026, 7, 24))  # Prior Friday


class TestCalculateSync(unittest.TestCase):

    def test_single_booking_adds_buffers(self):
        """One booking on Aug 8 should propose MAXED for adjacent weekends."""
        rows = make_rows([
            (8, 1, ""),       # Sat - should be added
            (8, 2, ""),       # Sun - should be added
            (8, 7, "OUT"),    # Fri - OUT, skip
            (8, 8, "BOOKED"), # Sat - the booking
            (8, 9, "OUT"),    # Sun - OUT, skip
            (8, 14, ""),      # Fri - should be added
            (8, 15, ""),      # Sat - should be added
            (8, 16, ""),      # Sun - should be added
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 1)
        self.assertIn(date(2026, 8, 1), additions)
        self.assertIn(date(2026, 8, 15), additions)
        self.assertEqual(len(removals), 0)

    def test_cancellation_removes_buffers(self):
        """
        Aug 8 was booked, adjacent dates were MAXED.
        After cancellation (Aug 8 now blank), those MAXED dates should be removals.
        """
        rows = make_rows([
            (8, 1, "MAXED"),  # Was buffered, should be removed
            (8, 2, "MAXED"),  # Was buffered, should be removed
            (8, 8, ""),       # Booking canceled
            (8, 14, ""),      # Fri
            (8, 15, "MAXED"), # Was buffered, should be removed
            (8, 16, "MAXED"), # Was buffered, should be removed
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 0)
        self.assertEqual(len(additions), 0)
        self.assertIn(date(2026, 8, 1), removals)
        self.assertIn(date(2026, 8, 15), removals)

    def test_cancellation_with_nearby_booking_keeps_shared_buffer(self):
        """
        Aug 8 canceled but Aug 22 still booked.
        Aug 15 should stay MAXED (buffer for Aug 22).
        Aug 1 should be removed (no longer needed).
        """
        rows = make_rows([
            (8, 1, "MAXED"),  # Should be removed
            (8, 2, "MAXED"),  # Should be removed
            (8, 8, ""),       # Canceled
            (8, 14, ""),      # Fri before Aug 15
            (8, 15, "MAXED"), # Should stay (buffer for Aug 22)
            (8, 16, "MAXED"), # Should stay (buffer for Aug 22)
            (8, 22, "BOOKED"),# Still booked
            (8, 28, ""),      # Fri after
            (8, 29, ""),      # Sat after - should be added
            (8, 30, ""),      # Sun after - should be added
        ])
        additions, removals, booked = calculate_sync(rows, "2026")

        # Aug 1, 2 should be removals (no booking needs them)
        self.assertIn(date(2026, 8, 1), removals)
        self.assertIn(date(2026, 8, 2), removals)

        # Aug 15, 16 should NOT be removals (Aug 22 needs them)
        self.assertNotIn(date(2026, 8, 15), removals)
        self.assertNotIn(date(2026, 8, 16), removals)

        # Aug 29, 30 should be additions (buffer after Aug 22)
        self.assertIn(date(2026, 8, 29), additions)
        self.assertIn(date(2026, 8, 30), additions)

    def test_monthly_cap_two_bookings(self):
        """Two bookings in a month should MAXED all remaining Fri/Sat/Sun."""
        rows = make_rows([
            (9, 4, ""),        # Fri - should be added (cap)
            (9, 5, ""),        # Sat - should be added (cap)
            (9, 6, ""),        # Sun - should be added (cap)
            (9, 12, "BOOKED"), # Sat - booking 1
            (9, 19, ""),       # Sat - should be added (buffer + cap)
            (9, 26, "BOOKED"), # Sat - booking 2
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 2)
        # All non-booked Fri/Sat/Sun should be additions
        self.assertIn(date(2026, 9, 4), additions)
        self.assertIn(date(2026, 9, 5), additions)
        self.assertIn(date(2026, 9, 19), additions)

    def test_monthly_cap_drops_below_two(self):
        """
        Month had 2 bookings (Sep 12 + Sep 26), all dates MAXED.
        Sep 26 canceled. Only buffer around Sep 12 should remain.
        """
        rows = make_rows([
            (9, 4, "MAXED"),   # Fri - was cap'd. Now buffer for Sep 12: keep
            (9, 5, "MAXED"),   # Sat - buffer for Sep 12: keep
            (9, 6, "MAXED"),   # Sun - buffer for Sep 12: keep
            (9, 12, "BOOKED"), # Sat - still booked
            (9, 18, "MAXED"),  # Fri - buffer for Sep 12: keep
            (9, 19, "MAXED"),  # Sat - buffer for Sep 12: keep
            (9, 20, "MAXED"),  # Sun - buffer for Sep 12: keep
            (9, 25, "MAXED"),  # Fri - no longer needed: remove
            (9, 26, ""),       # Sat - canceled
            (9, 27, "MAXED"),  # Sun - no longer needed: remove
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 1)

        # Buffer dates around Sep 12 should NOT be removals
        self.assertNotIn(date(2026, 9, 5), removals)
        self.assertNotIn(date(2026, 9, 19), removals)

        # Sep 25, 27 should be removals
        self.assertIn(date(2026, 9, 25), removals)
        self.assertIn(date(2026, 9, 27), removals)

    def test_skip_values_not_touched(self):
        """BOOKED/BACKUP/RESERVED dates in buffer zones are never proposed."""
        rows = make_rows([
            (8, 1, "BACKUP"),  # In buffer zone but BACKUP -- skip
            (8, 8, "BOOKED"),  # The booking
            (8, 15, "RESERVED"),  # In buffer zone but RESERVED -- skip
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertNotIn(date(2026, 8, 1), additions)
        self.assertNotIn(date(2026, 8, 15), additions)

    def test_out_dates_never_touched(self):
        """OUT dates are ignored entirely -- not added, not removed."""
        rows = make_rows([
            (8, 7, "OUT"),     # Fri OUT - not touched even in buffer zone
            (8, 8, "BOOKED"),  # The booking
            (8, 9, "OUT"),     # Sun OUT - not touched
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertNotIn(date(2026, 8, 7), additions)
        self.assertNotIn(date(2026, 8, 9), additions)
        self.assertNotIn(date(2026, 8, 7), removals)
        self.assertNotIn(date(2026, 8, 9), removals)

    def test_ok_cell_gets_maxed(self):
        """A cell with OK value in a buffer zone should be proposed as addition."""
        rows = make_rows([
            (8, 1, "OK"),      # In buffer zone, should be added
            (8, 8, "BOOKED"),  # The booking
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertIn(date(2026, 8, 1), additions)

    def test_no_bookings_no_changes(self):
        """No bookings means no additions and no removals (assuming clean matrix)."""
        rows = make_rows([
            (8, 1, ""),
            (8, 8, ""),
            (8, 15, ""),
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(booked), 0)
        self.assertEqual(len(additions), 0)
        self.assertEqual(len(removals), 0)

    def test_already_correct_no_changes(self):
        """If matrix already matches rules, no additions or removals."""
        rows = make_rows([
            (8, 1, "MAXED"),   # Correct buffer
            (8, 2, "MAXED"),   # Correct buffer
            (8, 8, "BOOKED"),  # Booking
            (8, 14, "MAXED"),  # Correct buffer (Fri after -- next week)
            (8, 15, "MAXED"),  # Correct buffer
            (8, 16, "MAXED"),  # Correct buffer (Sun after -- next week)
        ])
        additions, removals, booked = calculate_sync(rows, "2026")
        self.assertEqual(len(additions), 0)
        self.assertEqual(len(removals), 0)


class TestParseMatrixDate(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(parse_matrix_date("Sat 1/18", 2026), date(2026, 1, 18))

    def test_bad_format(self):
        self.assertIsNone(parse_matrix_date("bad", 2026))

    def test_empty(self):
        self.assertIsNone(parse_matrix_date("", 2026))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/paulburchfield/Documents/projects/dj-availability-checker && python3 -m pytest test_stefano_enforcer.py -v`

Expected: ImportError for `calculate_sync` (function doesn't exist yet). All `TestCalculateSync` tests fail. Helper tests (`TestIsFSS`, `TestAdjacentWeekendDates`, `TestParseMatrixDate`) should pass since those functions already exist.

- [ ] **Step 3: Commit test file**

```bash
git add test_stefano_enforcer.py
git commit -m "test: add tests for stefano enforcer sync logic"
```

---

### Task 3: Implement `calculate_sync`

**Files:**
- Modify: `stefano_maxed_enforcer.py` (replace `find_suggestions` with `calculate_sync`, remove `ALREADY_MAXED_VALUES`)

- [ ] **Step 1: Remove `ALREADY_MAXED_VALUES` and replace `find_suggestions` with `calculate_sync`**

In `stefano_maxed_enforcer.py`:

1. Delete line 41: `ALREADY_MAXED_VALUES = {"MAXED", "OUT"}`
2. Replace the entire `find_suggestions` function (lines 125-183) with:

```python
def calculate_sync(rows, year):
    """
    Recalculate which dates should be MAXED based on current bookings,
    then diff against the matrix to find additions and removals.

    Returns:
        additions:  {date: (row_number, current_value, [reasons])}
        removals:   {date: (row_number, current_value, [reasons])}
        booked_fss: list of confirmed booked Fri/Sat/Sun dates
    """
    date_map = {d: (row, val) for d, row, val in rows}

    # Only Fri/Sat/Sun bookings trigger rules
    booked_fss = [
        d for d, row, val in rows
        if val == "BOOKED" and is_fss(d)
    ]

    # Build the set of dates that SHOULD be MAXED, with reasons
    pending_reasons = defaultdict(set)  # date -> set of reason strings

    # -- Rule 1: Weekend buffer --
    for booked_date in booked_fss:
        prior, nxt = adjacent_weekend_dates(booked_date)
        label = booked_date.strftime("%b %-d")

        for adj in prior:
            if adj in date_map:
                pending_reasons[adj].add(f"prior weekend buffer ({label} booking)")

        for adj in nxt:
            if adj in date_map:
                pending_reasons[adj].add(f"next weekend buffer ({label} booking)")

    # -- Rule 2: Monthly cap --
    by_month = defaultdict(list)
    for d in booked_fss:
        by_month[d.month].append(d)

    for month, booked_dates in by_month.items():
        if len(booked_dates) >= 2:
            month_name = booked_dates[0].strftime("%B")
            reason = f"monthly cap ({month_name} has {len(booked_dates)} bookings)"
            for d, row, val in rows:
                if d.month == month and is_fss(d):
                    pending_reasons[d].add(reason)

    # Build should_be_maxed, excluding SKIP values
    should_be_maxed = set()
    for d in pending_reasons:
        if d in date_map:
            _, val = date_map[d]
            if val not in SKIP_VALUES:
                should_be_maxed.add(d)

    # -- Diff against current state --
    additions = {}
    removals = {}

    for d, row, val in rows:
        if not is_fss(d):
            continue

        if val in SKIP_VALUES:
            continue

        if d in should_be_maxed:
            # Should be MAXED
            if val not in ("MAXED", "OUT"):  # Already blocked -- no action needed
                # Currently blank or OK -- needs to be added
                additions[d] = (row, val, sorted(pending_reasons.get(d, set())))
            # If already MAXED or OUT, no action needed
        else:
            # Should NOT be MAXED
            if val == "MAXED":
                removals[d] = (row, val, ["no active booking requires this date to be blocked"])

    return additions, removals, sorted(booked_fss)
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/paulburchfield/Documents/projects/dj-availability-checker && python3 -m pytest test_stefano_enforcer.py -v`

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add stefano_maxed_enforcer.py
git commit -m "feat: replace find_suggestions with calculate_sync for bidirectional sync"
```

---

### Task 4: Add `clear_maxed` and `delete_calendar_event`

**Files:**
- Modify: `stefano_maxed_enforcer.py` (add two new functions)

- [ ] **Step 1: Add `delete_calendar_event` after `create_calendar_event`**

Add this function in the CALENDAR section, after `create_calendar_event`:

```python
def delete_calendar_event(event_date, dry_run=False):
    """Delete [SB] MAXED OUT event(s) from the Unavailable calendar via AppleScript."""
    if dry_run:
        print(f"      [DRY RUN] Calendar: delete [SB] MAXED OUT on {event_date.strftime('%b %-d, %Y')}")
        return True
    try:
        date_str = event_date.strftime("%B %d, %Y")
        script = f'''
        tell application "Calendar"
            tell calendar "Unavailable"
                set matchingEvents to (every event whose start date >= date "{date_str} 12:00:00 AM" and start date < date "{date_str} 11:59:59 PM" and summary contains "[SB]" and summary contains "MAXED")
                set deletedCount to 0
                repeat with anEvent in matchingEvents
                    delete anEvent
                    set deletedCount to deletedCount + 1
                end repeat
                return deletedCount
            end tell
        end tell
        '''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30,
        )
        count = result.stdout.strip()
        if count.isdigit() and int(count) > 0:
            return True
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        print(f"      Calendar: no matching event found to delete")
        return True
    except Exception as e:
        print(f"      Calendar warning: {e}")
        return True  # Don't fail -- matrix is source of truth
```

- [ ] **Step 2: Add `clear_maxed` after `write_maxed`**

Add this function in the SHEET WRITE section, after `write_maxed`. Import `get_default_cell_value` from `dj_core` at the top of the file.

Update the import line:

```python
from dj_core import init_google_sheets_from_file, get_default_cell_value
```

Then add the function:

```python
def clear_maxed(spreadsheet, year, row_number, event_date, dry_run=False):
    """Restore Stefano's cell to its default value (reversing a MAXED entry)."""
    default_val = get_default_cell_value("Stefano", event_date)
    display_val = default_val if default_val else "(blank)"

    if dry_run:
        print(f"      [DRY RUN] Matrix: row {row_number} -> {display_val}")
        return True

    sheet = spreadsheet.worksheet(year)
    sheet.update_cell(row_number, STEFANO_COL_NUM, default_val)
    return True
```

- [ ] **Step 3: Verify imports work**

Run: `python3 -c "from stefano_maxed_enforcer import delete_calendar_event, clear_maxed; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add stefano_maxed_enforcer.py
git commit -m "feat: add clear_maxed and delete_calendar_event for removal support"
```

---

### Task 5: Update `display_and_select` for two-section display

**Files:**
- Modify: `stefano_maxed_enforcer.py` (rewrite `display_and_select`)

- [ ] **Step 1: Replace `display_and_select` with updated version**

Replace the entire `display_and_select` function (and the `# INTERACTIVE SELECTION` section) with:

```python
def display_and_select(additions, removals):
    """
    Display additions and removals in two sections, prompt for selection.
    Returns list of (action, date, row_number, current_value) to apply.
    action is "add" or "remove".
    """
    if not additions and not removals:
        print("\nNo changes needed -- Stefano's column is in sync.")
        return []

    ordered = []

    def print_group(label, group, action):
        if not group:
            return
        print(f"\n-- {label} {'-' * (52 - len(label))}")
        for d in sorted(group):
            row, val, reasons = group[d]
            idx = len(ordered) + 1
            current = f"  (currently: {val})" if val else ""
            print(f"  [{idx:2d}]  {d.strftime('%a %b %-d')}{current}")
            for r in reasons:
                print(f"         -> {r}")
            ordered.append((action, d, row, val))

    print_group("Dates to MAXED", additions, "add")
    print_group("Dates to Open Up", removals, "remove")

    print(f"\n  {len(ordered)} change(s) suggested.")
    print("  Enter numbers to apply (e.g. 1,3,5), 'all', or press Enter to skip: ", end="")

    raw = input().strip().lower()

    if not raw or raw == "none":
        return []

    if raw == "all":
        return ordered

    try:
        indices = [int(x.strip()) - 1 for x in raw.split(",")]
        selected = [ordered[i] for i in indices if 0 <= i < len(ordered)]
        return selected
    except ValueError:
        print("Could not parse input. No changes made.")
        return []
```

- [ ] **Step 2: Commit**

```bash
git add stefano_maxed_enforcer.py
git commit -m "feat: update display_and_select for two-section add/remove display"
```

---

### Task 6: Rewrite `main()` to use sync flow

**Files:**
- Modify: `stefano_maxed_enforcer.py` (rewrite main function and module docstring)

- [ ] **Step 1: Update module docstring**

Replace lines 1-18 with:

```python
"""
Stefano MAXED Enforcer (Full Sync)

Recalculates which dates in Stefano's availability matrix column should be
MAXED based on current bookings, then proposes both additions and removals.

Rules applied:
  1. Weekend buffer: If Stefano is booked any Fri/Sat/Sun, the Fri/Sat/Sun of
     the immediately preceding week AND immediately following week are MAXED
     (unless already booked).
  2. Monthly cap: If a calendar month already has 2+ bookings, all remaining
     Fri/Sat/Sun dates in that month are MAXED.

On every run, the script:
  - Reads current matrix state
  - Recalculates from scratch which dates should be MAXED
  - Diffs against current state
  - Proposes additions (new MAXED dates) and removals (stale MAXED dates)
  - Applies selected changes to matrix and calendar

Usage:
  python3 stefano_maxed_enforcer.py [--year 2026] [--dry-run]
"""
```

- [ ] **Step 2: Replace `main()` function**

Replace the entire `main()` function with:

```python
def main():
    parser = argparse.ArgumentParser(description="Stefano MAXED Enforcer (Full Sync)")
    parser.add_argument("--year", default="2026", choices=["2026", "2027"],
                        help="Which year tab to scan (default: 2026)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    args = parser.parse_args()

    year = args.year
    dry_run = args.dry_run

    print(f"\nStefano MAXED Enforcer -- {year}")
    if dry_run:
        print("    (DRY RUN -- no changes will be made)\n")

    # Connect
    print("Connecting to Google Sheets...")
    try:
        service, spreadsheet, spreadsheet_id, client = init_google_sheets_from_file()
    except Exception as e:
        print(f"Could not connect: {e}")
        sys.exit(1)

    # Read
    print(f"Reading Stefano's column ({STEFANO_COL_LETTER}) for {year}...")
    rows = read_stefano_column(spreadsheet, year)

    # Analyze
    additions, removals, booked_fss = calculate_sync(rows, year)

    currently_maxed = sum(1 for _, _, v in rows if v == "MAXED")
    correctly_maxed = currently_maxed - len(removals)

    print(f"\n  Booked dates (Fri/Sat/Sun): {len(booked_fss)}")
    if booked_fss:
        print(f"  {', '.join(d.strftime('%b %-d') for d in booked_fss)}")
    print(f"  Currently MAXED: {currently_maxed}")
    print(f"  Correctly MAXED: {correctly_maxed}")
    print(f"  To add: {len(additions)}")
    print(f"  To remove: {len(removals)}")

    # Select
    selected = display_and_select(additions, removals)

    if not selected:
        print("\nNo changes made.")
        return

    # Apply
    print(f"\nApplying {len(selected)} change(s)...\n")
    ok_matrix = 0
    ok_cal = 0

    for action, d, row_number, current_val in selected:
        print(f"  {d.strftime('%a %b %-d, %Y')}:")

        if action == "add":
            if write_maxed(spreadsheet, year, row_number, dry_run):
                print(f"      Matrix -> MAXED")
                ok_matrix += 1
            if create_calendar_event(d, dry_run):
                print(f"      Calendar event created")
                ok_cal += 1
        elif action == "remove":
            if clear_maxed(spreadsheet, year, row_number, d, dry_run):
                default = get_default_cell_value("Stefano", d)
                display = default if default else "(blank)"
                print(f"      Matrix -> {display}")
                ok_matrix += 1
            if delete_calendar_event(d, dry_run):
                print(f"      Calendar event deleted")
                ok_cal += 1

    tag = "[DRY RUN] " if dry_run else ""
    print(f"\n{tag}Done -- {ok_matrix} matrix update(s), {ok_cal} calendar operation(s).")
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/paulburchfield/Documents/projects/dj-availability-checker && python3 -m pytest test_stefano_enforcer.py -v`

Expected: All tests pass.

- [ ] **Step 4: Dry-run smoke test against live matrix**

Run: `cd /Users/paulburchfield/Documents/projects/dj-availability-checker && python3 stefano_maxed_enforcer.py --dry-run`

Expected: Connects to Google Sheets, reads Stefano's column, shows summary of current state, displays any suggested additions/removals. No changes written.

- [ ] **Step 5: Commit**

```bash
git add stefano_maxed_enforcer.py
git commit -m "feat: rewrite main() for full bidirectional sync"
```

---

### Task 7: Final verification and cleanup

**Files:**
- Review: `stefano_maxed_enforcer.py` (full file)
- Review: `cancel_booking.py` (verify import works)

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/paulburchfield/Documents/projects/dj-availability-checker && python3 -m pytest test_stefano_enforcer.py test_gig_booking_manager.py -v`

Expected: All tests pass in both test files (confirming the `dj_core` refactor didn't break anything).

- [ ] **Step 2: Run cancel_booking.py import check**

Run: `python3 -c "from cancel_booking import get_default_cell_value, delete_booking_calendar_event; print('cancel_booking imports OK')"`

Expected: `cancel_booking imports OK`

- [ ] **Step 3: Run dry-run for both years**

Run:
```bash
cd /Users/paulburchfield/Documents/projects/dj-availability-checker
python3 stefano_maxed_enforcer.py --year 2026 --dry-run
python3 stefano_maxed_enforcer.py --year 2027 --dry-run
```

Expected: Both complete without errors, show accurate summaries.

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: final cleanup for stefano enforcer v2"
```
