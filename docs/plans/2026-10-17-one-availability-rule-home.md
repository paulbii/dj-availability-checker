# One Availability Rule Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A DJ availability rule change is one edit in `dj_core.py`, and it cannot reach GitHub with the frozen desktop apps left behind.

**Architecture:** `dj_core.dj_status()` becomes the single place that turns a Matrix cell plus a Gig DB booking into a display status (text, palette kind, booleans, mismatch warning). The three front ends (terminal `check_dj.py`, desktop GUI `check_dj_gui.py`, Streamlit `dj_app.py`) delete their own formatters and only paint the record. The build stamps a hash of the frozen sources into each `.app`; a pre-commit check refuses a commit whose staged sources differ from the installed apps' stamp; `release.sh` runs tests, builds, installs, commits, pushes in one go.

**Tech Stack:** Python 3.13 (`.venv/bin/python`), stdlib `unittest` (run with `.venv/bin/python -m unittest discover -s tests`; pytest is not installed), PyInstaller via `build_apps.sh`, bash, git hooks.

**Working directory for all commands:** `/Users/paulburchfield/Documents/projects/dj-availability-checker`

**Key facts the executor needs:**
- `check_dj_availability(dj_name, value, date_obj, is_bold, year, warn)` in `dj_core.py` is the existing yes/no rule and stays as is. `dj_status()` wraps it.
- The palette is `dj_core.PALETTE` (green, blue, red, amber, violet, yellow, gold, cyan, accent, dim). The terminal uses `Fore.<NAME>` built from it; the GUI uses CSS classes of the same names plus `warn` (orange); Streamlit uses `html_color(name, text)`.
- Today's three formatters: `check_dj.format_dj_status` (`check_dj.py:65-141`), `check_dj_gui.Api._format_dj_line` (`check_dj_gui.py:913-972`), `dj_app.format_dj_status_for_display` (`dj_app.py:46-139`). Each is called from exactly two places (a Stephanie branch and a generic branch in the date-check loop). All three get deleted.
- A fourth copy of the rules lives in the "DJ availability in range" feature: `check_dj.py:461-477`, `check_dj_gui.py:1066-1082`, `dj_app.py:573-590`. Each classifies a cell as booked/backup/available and has a Stefano-blank special case. Task 2b replaces those with `dj_core.dj_range_bucket()`.
- `setup_status_text(gig_booking)` in `dj_core.py` returns the SETUP display text or `None`.
- `dj_app.py` calls `st.set_page_config` at import, so tests must not import it. The guard test reads it as text.
- The repo lives under iCloud; `build_apps.sh` already handles the xattr/codesign retry. Files added to a bundle **after** signing break the signature, so the stamp is written before `codesign`.
- `.git/hooks/pre-commit` currently runs only `gitleaks`. Hooks are not tracked by git, so the check script lives in `scripts/` and the hook calls it.
- Do not commit the unrelated working-tree changes already present (`cancel_booking.scpt`, `gig_booking_manager.scpt`, `com.bigfundj.nestldown-roster.plist`, `archive/automator-apps/`). Stage files by name.
- Today's Stephanie change is already committed as `007fc11`. Task 0 is done; skip it.
- `.git/hooks/pre-commit` has no `set -e`, so its exit status is the last command's. Task 9 adds `set -e` so appending the new check does not make a gitleaks failure non-blocking.

**Display differences this unifies (intentional):**
- Blank available cell: was `"Henry:  - available"` (terminal/GUI) and `"BLANK - available"` (Streamlit); becomes `"Henry: available"` everywhere.
- WEDFAIRE and SETUP cells: were red/amber in Streamlit only; red/amber everywhere.
- An `AAG` cell in any DJ column: was red in Stephanie's branch, dim for every other DJ; red everywhere.
- Blank backup cell: was `"Henry:  - can backup (weekday)"` (terminal), `"BLANK - can backup (weekday)"` (Streamlit); becomes `"Henry: can backup (weekday)"`. The GUI gains the reason suffixes `(weekday)` / `(weekend)` it never had.
- Felipe blank in 2026/2027 keeps `"[BLANK] - can backup"`.
- **Stephanie 2026 with a non-blank cell** (terminal and GUI): was printed as the bare value, uncolored, with no availability check. Now gets the full check like 2027 and like Streamlit already did: `OK` green available (and nearby bookings are fetched), `OUT`/`MAXED` dim, `STANFORD`/`WEDFAIRE` red, `SETUP` amber.
- Stephanie with a SETUP gig (terminal and GUI): was red `BOOKED (venue)`; now amber/violet SETUP text like every other DJ and like Streamlit.
- Matrix-mismatch warnings follow one rule everywhere: a BOOKED gig does not warn on `booked`/`wedfaire`/`setup` cells; a SETUP gig does not warn on a `setup` cell only. (Terminal used to warn Stephanie on `SETUP`/`WEDFAIRE`; Streamlit used to stay quiet on a SETUP gig with a `BOOKED`/`WEDFAIRE` cell.)
- In the range query, an `AAG` cell in a DJ column now counts as booked (was unlisted). Terminal's Stephanie `not available (year)` line was uncolored, now dim.

---

### Task 0: Commit today's Stephanie rule change — DONE (`007fc11`), skip

**Files:** none new.

- [ ] **Step 1: Run the suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED)"`
Expected: `Ran 33 tests` then `OK`

- [ ] **Step 2: Commit by name**

```bash
git add dj_core.py check_dj.py check_dj_gui.py dj_app.py DJ_SYSTEM_REFERENCE.md tests/test_check_dj_availability.py
git commit -m "Stephanie 2027: blank cell = not available, same as 2026

Paul's rule 2026-10-17: for 2027 she is out except on dates she has
specifically said yes to (OK in the cell). Front ends print
'not available (2027)' for a blank cell instead of an empty status.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 1: `DJStatus` and `dj_status()` in dj_core — gig-booking and hard-cell cases

**Files:**
- Modify: `dj_core.py` (add after `check_dj_availability`, before `analyze_availability`, ~line 1077)
- Create: `tests/test_dj_status.py`

- [ ] **Step 1: Write the failing tests**

```python
#!/usr/bin/env python3
"""
Tests for dj_core.dj_status(): the one place a Matrix cell plus a Gig DB
booking becomes a display status. Every front end paints this record and
nothing else, so a rule change is one edit here.
"""

import unittest
from datetime import date

import dj_core
from dj_core import dj_status, DJStatus


SAT = date(2027, 6, 26)
SUN = date(2027, 6, 27)
WED = date(2027, 6, 30)


class TestGigBooking(unittest.TestCase):

    def test_booked_in_gig_db_wins_over_cell(self):
        s = dj_status("Paul", "BOOKED", SAT, "2027", gig_booking={"venue": "Nestldown"})
        self.assertEqual(s, DJStatus("BOOKED (Nestldown)", "red", False, False, ""))

    def test_booked_in_gig_db_with_blank_cell_warns(self):
        s = dj_status("Paul", "", SAT, "2027", gig_booking={"venue": "Nestldown"})
        self.assertEqual(s.warning, "matrix is blank")
        self.assertEqual(s.kind, "red")

    def test_booked_in_gig_db_with_other_cell_warns(self):
        s = dj_status("Paul", "OK", SAT, "2027", gig_booking={"venue": "Nestldown"})
        self.assertEqual(s.warning, 'matrix shows "OK"')

    def test_booked_in_gig_db_with_wedfaire_cell_does_not_warn(self):
        s = dj_status("Paul", "WEDFAIRE", SAT, "2027", gig_booking={"venue": "Expo"})
        self.assertEqual(s.warning, "")

    def test_setup_primary_is_amber(self):
        gig = {"venue": "Kohl Mansion", "is_setup": True, "role": "primary"}
        s = dj_status("Henry", "SETUP", SAT, "2027", gig_booking=gig)
        self.assertEqual(s.kind, "amber")
        self.assertEqual(s.text, dj_core.setup_status_text(gig))
        self.assertEqual(s.warning, "")

    def test_setup_helper_is_violet_and_warns_on_blank_cell(self):
        gig = {"venue": "Kohl Mansion", "is_setup": True, "role": "helper"}
        s = dj_status("Felipe", "", SAT, "2027", gig_booking=gig)
        self.assertEqual(s.kind, "violet")
        self.assertEqual(s.warning, "matrix is blank")


class TestHardCellStates(unittest.TestCase):

    def test_stefano_blank_is_maybe(self):
        self.assertEqual(dj_status("Stefano", "", SAT, "2027"),
                         DJStatus("[MAYBE]", "yellow", False, False, ""))

    def test_booked_cell_is_red_verbatim(self):
        s = dj_status("Henry", "BOOKED", SAT, "2027")
        self.assertEqual((s.text, s.kind, s.can_book), ("BOOKED", "red", False))

    def test_aag_cell_is_red(self):
        s = dj_status("Stephanie", "AAG", SAT, "2027")
        self.assertEqual((s.text, s.kind), ("AAG", "red"))

    def test_stanford_is_red(self):
        self.assertEqual(dj_status("Henry", "STANFORD", SAT, "2027").kind, "red")

    def test_reserved_is_red(self):
        s = dj_status("Stephanie", "RESERVED", SAT, "2027")
        self.assertEqual((s.text, s.kind), ("RESERVED", "red"))

    def test_wedfaire_is_red(self):
        self.assertEqual(dj_status("Paul", "WEDFAIRE", SAT, "2027").kind, "red")

    def test_setup_cell_without_gig_is_amber(self):
        self.assertEqual(dj_status("Paul", "SETUP", SAT, "2027").kind, "amber")

    def test_backup_cell_is_blue_verbatim(self):
        s = dj_status("Woody", "BACKUP", SAT, "2027")
        self.assertEqual((s.text, s.kind), ("BACKUP", "blue"))

    def test_felipe_blank_2027_is_backup(self):
        s = dj_status("Felipe", "", SAT, "2027")
        self.assertEqual(s, DJStatus("[BLANK] - can backup", "blue", False, True, ""))

    def test_last_is_green_low_priority(self):
        s = dj_status("Paul", "LAST", SAT, "2027")
        self.assertEqual((s.text, s.kind, s.can_book), ("LAST - available (low priority)", "green", True))

    def test_unknown_value_is_warn(self):
        s = dj_status("Paul", "VACAY", SAT, "2027")
        self.assertEqual(s.kind, "warn")
        self.assertIn("unknown status", s.text)
        self.assertEqual((s.can_book, s.can_backup), (False, False))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_dj_status 2>&1 | grep -E "Error|^Ran|^FAILED"`
Expected: `ImportError: cannot import name 'dj_status' from 'dj_core'` and `FAILED (errors=1)`

- [ ] **Step 3: Implement**

Add near the top of `dj_core.py` imports: `from dataclasses import dataclass` (it is not imported today; check with `grep -n "^from dataclasses" dj_core.py`).

Add after `check_dj_availability` (before `def analyze_availability`):

```python
@dataclass(frozen=True)
class DJStatus:
    """One DJ's display status for one date. Front ends paint this and
    nothing else: `kind` is a PALETTE name ("warn" maps to yellow/orange),
    `text` has no DJ-name prefix, `warning` is a matrix-mismatch note
    shown in yellow after the text when non-empty."""
    text: str
    kind: str
    can_book: bool
    can_backup: bool
    warning: str = ""


def _matrix_mismatch(clean_value):
    return f'matrix shows "{clean_value}"' if clean_value else "matrix is blank"


def dj_status(dj_name, value, date_obj, year, gig_booking=None, nearby_bookings=None):
    """Turn a Matrix cell (plus the Gig DB booking, if any) into a DJStatus.

    This is the single home of the display rules. The yes/no rule itself is
    check_dj_availability(); this wraps it and adds the wording and color.
    Rules that name a DJ belong here or in check_dj_availability, never in
    a front end (tests/test_no_dj_rules_in_front_ends.py enforces that).
    """
    value = str(value) if value else ""
    year = str(year)
    is_bold = "(BOLD)" in value
    clean = value.replace(" (BOLD)", "").strip()
    low = clean.lower()

    # 1. A Gig DB commitment wins over whatever the cell says.
    if gig_booking:
        setup_text = setup_status_text(gig_booking)
        if setup_text:
            kind = "violet" if gig_booking.get("role") == "helper" else "amber"
            warning = "" if low == "setup" else _matrix_mismatch(clean)
            return DJStatus(setup_text, kind, False, False, warning)
        venue = gig_booking.get("venue", "")
        warning = "" if low in ("booked", "wedfaire", "setup") else _matrix_mismatch(clean)
        return DJStatus(f"BOOKED ({venue})", "red", False, False, warning)

    # 2. Cell states that settle the answer on their own.
    if dj_name == "Stefano" and not clean:
        return DJStatus("[MAYBE]", "yellow", False, False)
    if "booked" in low or low == "aag":
        return DJStatus(value, "red", False, False)
    if low == "stanford":
        return DJStatus("STANFORD", "red", False, False)
    if "reserved" in low:
        return DJStatus("RESERVED", "red", False, False)
    if low == "wedfaire":
        return DJStatus("WEDFAIRE", "red", False, False)
    if low == "setup":
        return DJStatus("SETUP", "amber", False, False)
    if "backup" in low:
        return DJStatus(value, "blue", False, True)
    if dj_name == "Felipe" and year in ("2026", "2027") and not clean:
        return DJStatus("[BLANK] - can backup", "blue", False, True)
    if low == "last":
        return DJStatus(f"{value} - available (low priority)", "green", True, True)
    if clean and low not in KNOWN_CELL_VALUES:
        return DJStatus(f"{clean} ⚠️  unknown status — treating as unavailable", "warn", False, False)

    # 3. Everything else goes through the yes/no rule. (Task 2 fills this in.)
    raise NotImplementedError
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m unittest tests.test_dj_status 2>&1 | tail -3`
Expected: `Ran 17 tests` then `OK`

- [ ] **Step 5: Commit**

```bash
git add dj_core.py tests/test_dj_status.py
git commit -m "dj_core: DJStatus and dj_status() — gig-booking and hard-cell cases

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `dj_status()` — the computed cases (available, backup, dead-end)

**Files:**
- Modify: `dj_core.py` (replace the `raise NotImplementedError`)
- Modify: `tests/test_dj_status.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_dj_status.py` before `if __name__`:

```python
class TestComputedStates(unittest.TestCase):

    def test_blank_available_has_no_value_prefix(self):
        s = dj_status("Henry", "", SAT, "2027")
        self.assertEqual(s, DJStatus("available", "green", True, True, ""))

    def test_ok_available_keeps_value(self):
        s = dj_status("Stephanie", "OK", SAT, "2027")
        self.assertEqual((s.text, s.kind, s.can_book), ("OK - available", "green", True))

    def test_nearby_bookings_are_appended(self):
        s = dj_status("Paul", "", SAT, "2027", nearby_bookings=["6/25 Nestldown", "6/27 Kohl"])
        self.assertEqual(s.text, "available (booked: 6/25 Nestldown, 6/27 Kohl)")

    def test_henry_weekday_blank_is_backup_with_reason(self):
        s = dj_status("Henry", "", WED, "2027")
        self.assertEqual(s, DJStatus("can backup (weekday)", "blue", False, True, ""))

    def test_woody_plain_out_on_weekend_is_backup_with_reason(self):
        s = dj_status("Woody", "OUT", SAT, "2027")
        self.assertEqual(s, DJStatus("OUT - can backup (weekend)", "blue", False, True, ""))

    def test_woody_bold_out_on_weekend_is_dead_end(self):
        s = dj_status("Woody", "OUT (BOLD)", SAT, "2027")
        self.assertEqual(s, DJStatus("OUT (BOLD)", "dim", False, False, ""))

    def test_paul_out_is_dead_end(self):
        self.assertEqual(dj_status("Paul", "OUT", SAT, "2027"),
                         DJStatus("OUT", "dim", False, False, ""))

    def test_stefano_maxed_is_dead_end(self):
        self.assertEqual(dj_status("Stefano", "MAXED", SAT, "2027").kind, "dim")

    def test_stephanie_blank_2027_is_not_available(self):
        s = dj_status("Stephanie", "", SAT, "2027")
        self.assertEqual(s, DJStatus("not available (2027)", "dim", False, False, ""))

    def test_stephanie_blank_2026_is_not_available(self):
        s = dj_status("Stephanie", "", date(2026, 10, 24), "2026")
        self.assertEqual(s.text, "not available (2026)")

    def test_stephanie_blank_weekday_2027_is_not_available(self):
        self.assertEqual(dj_status("Stephanie", "", WED, "2027").text, "not available (2027)")

    def test_stephanie_out_2027_is_dead_end(self):
        self.assertEqual(dj_status("Stephanie", "OUT", SAT, "2027"),
                         DJStatus("OUT", "dim", False, False, ""))

    def test_felipe_ok_2027_is_available(self):
        self.assertEqual(dj_status("Felipe", "OK", SAT, "2027").can_book, True)

    def test_felipe_dad_2027_is_backup(self):
        s = dj_status("Felipe", "DAD", SAT, "2027")
        self.assertEqual(s, DJStatus("DAD - can backup", "blue", False, True, ""))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_dj_status 2>&1 | grep -E "^(Ran|OK|FAILED|NotImplementedError)" | sort | uniq -c`
Expected: `FAILED (errors=14)` with `NotImplementedError`

- [ ] **Step 3: Implement**

Replace `raise NotImplementedError` with:

```python
    # 3. Everything else goes through the yes/no rule.
    can_book, can_backup = check_dj_availability(dj_name, clean, date_obj, is_bold, year, warn=False)
    head = f"{value} - " if value else ""

    if can_book:
        nearby = f" (booked: {', '.join(nearby_bookings)})" if nearby_bookings else ""
        return DJStatus(f"{head}available{nearby}", "green", True, can_backup)

    if can_backup:
        reason = ""
        if low == "out" and is_weekend(date_obj):
            reason = " (weekend)"
        elif not clean and not is_weekend(date_obj):
            reason = " (weekday)"
        return DJStatus(f"{head}can backup{reason}", "blue", False, True)

    # Dead-end: OUT, MAXED, or a blank cell the rule says means out.
    return DJStatus(value if value else f"not available ({year})", "dim", False, False)
```

- [ ] **Step 4: Run to verify they pass, then the whole suite**

Run: `.venv/bin/python -m unittest tests.test_dj_status 2>&1 | tail -3`
Expected: `Ran 31 tests` then `OK`

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED)"`
Expected: `Ran 64 tests` then `OK`

- [ ] **Step 5: Commit**

```bash
git add dj_core.py tests/test_dj_status.py
git commit -m "dj_core: dj_status() computed cases — available, backup, dead-end

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2b: `dj_range_bucket()` — the range query's classification

**Files:**
- Modify: `dj_core.py` (add after `dj_status`)
- Modify: `tests/test_dj_status.py`

The "DJ availability in range" feature sorts each date into booked / backup / available (with `[MAYBE]` for a blank Stefano cell). Today each front end does that itself. The bucket is a function of `dj_status` plus the raw cell, and lives in dj_core. Behavior preserved except `AAG` (declared above).

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_dj_status.py` before `if __name__`:

```python
class TestRangeBucket(unittest.TestCase):

    def test_booked_cell(self):
        self.assertEqual(dj_range_bucket("Paul", "BOOKED", SAT, "2027"), "booked")

    def test_setup_cell_is_booked(self):
        self.assertEqual(dj_range_bucket("Paul", "SETUP", SAT, "2027"), "booked")

    def test_aag_cell_is_booked(self):
        self.assertEqual(dj_range_bucket("Stephanie", "AAG", SAT, "2027"), "booked")

    def test_backup_cell(self):
        self.assertEqual(dj_range_bucket("Woody", "BACKUP", SAT, "2027"), "backup")

    def test_ok_to_backup_cell_is_backup(self):
        self.assertEqual(dj_range_bucket("Felipe", "OK TO BACKUP", SAT, "2027"), "backup")

    def test_stefano_blank_is_maybe(self):
        self.assertEqual(dj_range_bucket("Stefano", "", SAT, "2027"), "maybe")

    def test_blank_available(self):
        self.assertEqual(dj_range_bucket("Henry", "", SAT, "2027"), "available")

    def test_felipe_blank_is_not_listed(self):
        self.assertIsNone(dj_range_bucket("Felipe", "", SAT, "2027"))

    def test_henry_weekday_blank_is_not_listed(self):
        self.assertIsNone(dj_range_bucket("Henry", "", WED, "2027"))

    def test_woody_bold_out_is_not_listed(self):
        self.assertIsNone(dj_range_bucket("Woody", "OUT", SAT, "2027", is_bold=True))

    def test_stephanie_blank_2027_is_not_listed(self):
        self.assertIsNone(dj_range_bucket("Stephanie", "", SAT, "2027"))
```

Change the import line to `from dj_core import dj_status, dj_range_bucket, DJStatus`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_dj_status 2>&1 | grep -E "Error|^Ran|^FAILED"`
Expected: `ImportError: cannot import name 'dj_range_bucket'`

- [ ] **Step 3: Implement**

Add after `dj_status` in `dj_core.py`:

```python
def dj_range_bucket(dj_name, value, date_obj, year, is_bold=False):
    """Which list a date goes in for the "DJ availability in range" query:
    "booked", "backup", "maybe", "available", or None (not listed).
    Bulk sheet data carries bold separately, so it is passed in."""
    value = str(value) if value else ""
    if is_bold and "(BOLD)" not in value:
        value = f"{value} (BOLD)"
    status = dj_status(dj_name, value, date_obj, year)
    if status.text == "[MAYBE]":
        return "maybe"
    if status.kind in ("red", "amber"):
        return "booked"
    if "backup" in value.lower():
        return "backup"
    if status.can_book:
        return "available"
    return None
```

- [ ] **Step 4: Run to verify they pass, then the whole suite**

Run: `.venv/bin/python -m unittest tests.test_dj_status 2>&1 | tail -3`
Expected: `Ran 42 tests` then `OK`

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED)"`
Expected: `Ran 75 tests` then `OK`

- [ ] **Step 5: Commit**

```bash
git add dj_core.py tests/test_dj_status.py
git commit -m "dj_core: dj_range_bucket() for the DJ-in-range query

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Terminal checker paints DJStatus

**Files:**
- Modify: `check_dj.py` — delete `format_dj_status` (lines 65-141); replace the Stephanie branch and the generic branch in `check_availability` (lines 198-253) with one branch; add `render_dj_line`; replace the classification in the range loop (lines 461-477).
- Create: `tests/test_render_dj_line.py`

- [ ] **Step 1: Write the failing test**

```python
#!/usr/bin/env python3
"""check_dj.render_dj_line paints a DJStatus for the terminal. Color is
forced off for the test, since check_dj decides at import from whether
stdout is a TTY."""

import unittest

import check_dj
from dj_core import DJStatus


class TestRenderDJLine(unittest.TestCase):

    def setUp(self):
        self._fore, self._style = check_dj.Fore, check_dj.Style
        check_dj.Fore = check_dj._Fore(False)
        check_dj.Style = check_dj._Style(False)

    def tearDown(self):
        check_dj.Fore, check_dj.Style = self._fore, self._style

    def test_text_is_prefixed_with_name(self):
        line = check_dj.render_dj_line("Henry", DJStatus("available", "green", True, True))
        self.assertEqual(line, "Henry: available")

    def test_warning_is_appended(self):
        line = check_dj.render_dj_line("Paul", DJStatus("BOOKED (Nestldown)", "red", False, False, "matrix is blank"))
        self.assertEqual(line, "Paul: BOOKED (Nestldown)  ⚠️  matrix is blank")

    def test_every_kind_has_a_color(self):
        for kind in ("red", "green", "blue", "yellow", "amber", "violet", "dim", "warn"):
            check_dj.render_dj_line("Paul", DJStatus("x", kind, False, False))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_render_dj_line 2>&1 | grep -E "Error|^Ran|^FAILED" | sort -u`
Expected: `AttributeError: module 'check_dj' has no attribute 'render_dj_line'` and `FAILED (errors=3)`

- [ ] **Step 3: Implement**

In `check_dj.py`, replace the whole `format_dj_status` function (from `def format_dj_status(` through the line `return f"{Fore.DIM}{dj_name}: {value}{Style.RESET_ALL}"`) with:

```python
_KIND_COLOR = {
    "red": "RED", "green": "GREEN", "blue": "BLUE", "yellow": "YELLOW",
    "amber": "AMBER", "violet": "VIOLET", "dim": "DIM", "warn": "YELLOW",
}


def render_dj_line(dj_name, status):
    """Paint a dj_core.DJStatus for the terminal. No rules live here."""
    color = getattr(Fore, _KIND_COLOR[status.kind])
    line = f"{color}{dj_name}: {status.text}{Style.RESET_ALL}"
    if status.warning:
        line += f"  {Fore.YELLOW}⚠️  {status.warning}{Style.RESET_ALL}"
    return line
```

Add `dj_status` and `dj_range_bucket` to the `from dj_core import (...)` list. After the edits below, `check_dj_availability`, `is_weekend`, `setup_status_text` and `KNOWN_CELL_VALUES` have no remaining use in the file (verify with `grep -n "check_dj_availability\|is_weekend\|setup_status_text\|KNOWN_CELL_VALUES" check_dj.py`, which should show only the import lines); remove them from the import list.

In `check_availability`, delete the entire `elif label == "Stephanie":` branch and the `else:` generic branch that follows it (through `response.append(formatted_line)`), and put this `else:` in their place, at the same indentation as `elif label == "AAG":`:

```python
            else:
                gig = assigned_bookings.get(label)
                status = dj_status(label, value, date_obj, sheet_name, gig)
                if status.can_book and not gig:
                    nearby = get_nearby_bookings_for_dj(label, date_obj, sheet_name, service, spreadsheet, spreadsheet_id)
                    status = dj_status(label, value, date_obj, sheet_name, gig, nearby)
                response.append(render_dj_line(label, status))
```

Delete the now-unused `year_int = int(sheet_name)` line in `check_availability` (line 176; the one in `main()` at ~625 stays).

In the per-DJ range function (the loop at lines 461-477, starting `for date_info in all_data:`), replace the body from `clean_value = str(value).replace(...)` through `available_dates.append(date_info['date'])` with:

```python
        bucket = dj_range_bucket(dj_name, value, date_info['date_obj'], sheet_name, is_bold)
        if bucket == "booked":
            booked_date_infos.append(date_info)
        elif bucket == "backup":
            backup_dates.append(date_info['date'])
        elif bucket == "maybe":
            available_dates.append(f"{date_info['date']} [MAYBE]")
        elif bucket == "available":
            available_dates.append(date_info['date'])
```

Keep the `value = ...` and `is_bold = ...` lines above it.

- [ ] **Step 4: Run tests, then the live checker**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED)"`
Expected: `Ran 78 tests` then `OK`

Run: `printf '1\n06-26\n1\n06-19\n1\n03-27\n2\n7\n' | .venv/bin/python check_2027.py 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "^(Henry|Woody|Paul|Stefano|Stephanie|Felipe):|^Available spots"`
Expected: three blocks. 6/26: `Stephanie: not available (2027)`, `Available spots: 0*`. 6/19: `Stephanie: OK - available`, spots include Stephanie. 3/27: `Stephanie: not available (2027)`, `Available spots: 2* (Henry, Paul)`. Henry and Paul blank read `Henry: available`.

Also run the per-DJ range query once for Stephanie, 03-01 to 06-30 (menu option 4; check the prompts in `main()` if they differ): expected 3/20 under booked or available depending on the Gig DB, 6/19 available, no other spring date listed for her.

- [ ] **Step 5: Commit**

```bash
git add check_dj.py tests/test_render_dj_line.py
git commit -m "terminal checker: paint dj_status(), drop its own formatter

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Desktop GUI paints DJStatus

**Files:**
- Modify: `check_dj_gui.py` — delete `Api._format_dj_line` (lines 913-972); replace the Stephanie and generic branches in `check_date` (lines 818-865); replace the classification in the range loop (lines 1066-1082).

No unit test for the GUI method (pywebview class; CLAUDE.md skips TDD for GUI wrappers). The guard test in Task 6 and the live run cover it.

- [ ] **Step 1: Implement**

Delete the whole `_format_dj_line` method. Add this method in its place:

```python
    @staticmethod
    def _render_dj_line(dj_name, status):
        """Paint a dj_core.DJStatus as a classified line dict. No rules here."""
        text = f"{dj_name}: {status.text}"
        if status.warning:
            text += f"  ⚠️  {status.warning}"
        return {"text": text, "cls": status.kind}
```

(`warn` is already a CSS class in the embedded stylesheet, line ~308; the other kinds match existing classes.)

In `check_date`, delete the `elif label == "Stephanie":` branch and the `else:  # Standard DJ` branch and replace both with:

```python
                else:
                    gig = assigned_bookings.get(label)
                    status = dj_status(label, value, date_obj, self.sheet_name, gig)
                    if status.can_book and not gig:
                        nearby = get_nearby_bookings_for_dj(label, date_obj, self.sheet_name, self.service, self.spreadsheet, self.spreadsheet_id)
                        status = dj_status(label, value, date_obj, self.sheet_name, gig, nearby)
                    lines.append(self._render_dj_line(label, status))
```

In the range loop (line ~1066, `for date_info in all_data:`), replace from `clean_value = str(value).replace(...)` through `available_dates.append(date_info['date'])` with the same eight-line `bucket = dj_range_bucket(...)` block as Task 3, using `self.sheet_name` for the year and 16 spaces of indent for `bucket =`.

Add `dj_status` and `dj_range_bucket` to the `from dj_core import (...)` list; remove `check_dj_availability`, `setup_status_text`, `KNOWN_CELL_VALUES` and `is_weekend` (the last was imported and never used). Verify with grep that only the import lines match before removing. Remove `year_int = int(self.sheet_name)` in `check_date` (line ~792).

- [ ] **Step 2: Compile and run the GUI from source**

Run: `.venv/bin/python -m py_compile check_dj_gui.py && echo compiled`
Expected: `compiled`

Run: `.venv/bin/python check_2027_gui.py &` then check 3/27 and 6/19 in the window. Expected the same lines as the terminal in Task 3. Quit the window.

- [ ] **Step 3: Commit**

```bash
git add check_dj_gui.py
git commit -m "desktop GUI: paint dj_status(), drop its own formatter

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Streamlit app paints DJStatus

**Files:**
- Modify: `dj_app.py` — delete `format_dj_status_for_display` (lines 46-139); replace the Stephanie and generic branches in the date-check loop (lines 246-276); replace the classification in the range loop (lines 573-590).

- [ ] **Step 1: Implement**

Replace `format_dj_status_for_display` with:

```python
def render_dj_status(status):
    """Paint a dj_core.DJStatus as HTML. No rules here."""
    kind = "yellow" if status.kind == "warn" else status.kind
    out = html_color(kind, status.text)
    if status.warning:
        out += "  " + html_color("yellow", f"⚠️ {status.warning}")
    return out
```

Replace the `elif label == "Stephanie":` branch and the following `else:` branch in the date-check loop with:

```python
                else:
                    gig = assigned_bookings.get(label)
                    status = dj_status(label, value, date_obj, year, gig)
                    if status.can_book and not gig:
                        nearby = get_nearby_bookings_for_dj(label, date_obj, year, service, spreadsheet, spreadsheet_id)
                        status = dj_status(label, value, date_obj, year, gig, nearby)
                    dj_items.append((label, render_dj_status(status)))
```

In the range loop (line ~573, `for date_info in all_data:`), replace from `clean_value = str(value).replace(...)` through `available_dates.append(date_info['date'])` with the same `bucket = dj_range_bucket(...)` block as Task 3, using `year` for the year and 12 spaces of indent for `bucket =`.

Add `dj_status` and `dj_range_bucket` to the import list; remove `check_dj_availability`, `is_weekend`, `setup_status_text`, `KNOWN_CELL_VALUES` (verify with grep that only the import lines remain). `year_int = int(year)` appears twice in `tab_check_date`: line 151 is used, **line 220 is dead; remove line 220 only.**

- [ ] **Step 2: Compile and run locally**

Run: `.venv/bin/python -m py_compile dj_app.py && echo compiled`
Expected: `compiled`

Run: `.venv/bin/streamlit run dj_app.py --server.headless true &` and open `http://localhost:8501`, year 2027, check 3/27. Expected: Stephanie reads `not available (2027)` in dim. Stop streamlit (`pkill -f "streamlit run dj_app.py"`).

- [ ] **Step 3: Commit**

```bash
git add dj_app.py
git commit -m "Streamlit app: paint dj_status(), drop its own copy of the rules

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Guard test — no DJ-name rules in front ends

**Files:**
- Create: `tests/test_no_dj_rules_in_front_ends.py`

- [ ] **Step 1: Write the test**

```python
#!/usr/bin/env python3
"""
Availability rules live in dj_core (check_dj_availability and dj_status).
A front end that tests a DJ's name is re-deriving a rule, which is how
the Streamlit app ended up with its own copy of the Stephanie rule in
2026. This test fails the moment that creeps back.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT_ENDS = ["check_dj.py", "check_dj_gui.py", "dj_app.py"]
DJ_NAMES = "Henry|Woody|Paul|Stefano|Felipe|Stephanie"
RULE = re.compile(rf'\b(dj_name|label|dj)\s*==\s*["\']({DJ_NAMES})["\']')


class TestNoDJRulesInFrontEnds(unittest.TestCase):

    def test_front_ends_do_not_branch_on_dj_name(self):
        hits = []
        for name in FRONT_ENDS:
            for n, line in enumerate(ROOT.joinpath(name).read_text().splitlines(), 1):
                if RULE.search(line):
                    hits.append(f"{name}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "DJ-name rule outside dj_core:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m unittest tests.test_no_dj_rules_in_front_ends 2>&1 | tail -3`
Expected: `OK`. If it lists hits, Tasks 3-5 left a branch behind; fix those files, not the test.

Sanity check that the test can fail: `git stash` is not needed; instead run
`.venv/bin/python - <<'EOF'
import re; from tests.test_no_dj_rules_in_front_ends import RULE
assert RULE.search('elif label == "Stephanie":')
print("regex matches a real branch")
EOF`
Expected: `regex matches a real branch`

- [ ] **Step 3: Commit**

```bash
git add tests/test_no_dj_rules_in_front_ends.py
git commit -m "test: front ends must not branch on a DJ name

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Source stamp in the frozen apps

**Files:**
- Create: `scripts/source_stamp.sh`
- Modify: `build_apps.sh`

The frozen apps contain `check_20XX_gui.py`, `check_dj_gui.py` and `dj_core.py` (`dj_core` imports no other local module; verified 2026-10-17). The stamp is a short hash of `dj_core.py` and `check_dj_gui.py`.

- [ ] **Step 1: Create the stamp script**

```bash
#!/bin/bash
# Print a short hash of the sources frozen into the DJ Availability apps.
#   scripts/source_stamp.sh           # working tree
#   scripts/source_stamp.sh --staged  # git index (what a commit would contain)
# Used by build_apps.sh (writes it into each bundle) and
# scripts/check_frozen_apps.sh (compares it in the pre-commit hook).
set -euo pipefail
cd "$(dirname "$0")/.."
FILES="dj_core.py check_dj_gui.py"
for f in $FILES; do
  if [ "${1:-}" = "--staged" ]; then git show ":$f"; else cat "$f"; fi
done | shasum -a 256 | cut -c1-16
```

`chmod +x scripts/source_stamp.sh`

- [ ] **Step 2: Verify**

Run: `scripts/source_stamp.sh; scripts/source_stamp.sh --staged`
Expected: two identical 16-hex-character lines (working tree equals index after Task 6's commit).

- [ ] **Step 3: Write the stamp into each bundle before signing**

In `build_apps.sh`, after the line `APP="dist/DJ Availability $YEAR.app"` and before the `SIGNED=0` loop, add:

```bash
  # Stamp the frozen sources so scripts/check_frozen_apps.sh can tell a
  # stale app from a current one. Must land before codesign.
  scripts/source_stamp.sh > "$APP/Contents/Resources/source-stamp.txt"
```

Also update the header comment of `build_apps.sh`: replace the three lines (5-7) starting `# Re-run this (then the install step in docs/plans/...` with:

```bash
# Normal path: ./release.sh (tests, build, install, commit, push). Run this
# alone only to inspect a build. The frozen apps do NOT pick up source edits;
# the pre-commit hook refuses rule changes until they are rebuilt and installed.
```

- [ ] **Step 4: Build and verify the stamp survives signing**

Run: `./build_apps.sh 2>&1 | tail -3`
Expected: `Done. Apps in release/:` and both app paths.

Run: `cat "release/DJ Availability 2027.app/Contents/Resources/source-stamp.txt"; scripts/source_stamp.sh; codesign -v "release/DJ Availability 2027.app" && echo signed`
Expected: the same hash twice, then `signed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/source_stamp.sh build_apps.sh
git commit -m "build: stamp the frozen sources into each app bundle

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: release.sh — tests, build, install, commit, push

**Files:**
- Create: `release.sh`

- [ ] **Step 1: Create**

```bash
#!/bin/bash
# One command to ship a change to every availability tool.
#   ./release.sh "commit message"
#
# 1. runs the test suite
# 2. freezes both DJ Availability apps (build_apps.sh) and installs them
#    into /Applications, replacing the old bundles
# 3. commits whatever is STAGED (stage with git add first; nothing is
#    staged for you) and pushes, which redeploys the Streamlit Cloud app
# Without a message, steps 1-2 run and the commit/push is skipped.
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-}"

# The apps are built from the working tree but the commit takes the index;
# the pre-commit check compares the two. Refuse to run with them apart.
if ! git diff --quiet -- dj_core.py check_dj_gui.py; then
  echo "dj_core.py or check_dj_gui.py has unstaged edits. git add them (or revert) first." >&2
  exit 1
fi

echo "== tests"
.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED)" | tee /tmp/release-tests.txt
grep -q "^OK" /tmp/release-tests.txt

echo "== build"
./build_apps.sh

echo "== install"
for YEAR in 2026 2027; do
  SRC="release/DJ Availability $YEAR.app"
  DST="/Applications/DJ Availability $YEAR.app"
  if pgrep -f "$DST/Contents/MacOS" >/dev/null; then
    echo "Quit 'DJ Availability $YEAR' first (it is running), then re-run." >&2
    exit 1
  fi
  rm -rf "$DST"
  ditto "$SRC" "$DST"
  codesign -v "$DST"
  echo "installed: $DST ($(cat "$DST/Contents/Resources/source-stamp.txt"))"
done

if [ -z "$MSG" ]; then
  echo "== no commit message given; skipping commit and push"
  exit 0
fi

if git diff --cached --quiet; then
  echo "== nothing staged; skipping commit and push (git add the files first)"
  exit 0
fi

echo "== commit"
git commit -m "$MSG

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"

echo "== push"
git push
echo "Done. Streamlit Cloud redeploys from main within a few minutes."
```

`chmod +x release.sh`

- [ ] **Step 2: Dry run without a message**

Run: `./release.sh 2>&1 | grep -E "^==|installed:|^OK|^Ran"`
Expected: `== tests`, `Ran N tests`, `OK`, `== build`, `== install`, two `installed:` lines each ending in the current stamp, `== no commit message given; skipping commit and push`. If a DJ Availability app is open, it stops with the quit message instead; quit the app and re-run.

- [ ] **Step 3: Commit**

```bash
git add release.sh
git commit -m "release.sh: tests, build, install, commit, push in one command

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Pre-commit check — staged rule sources must match the installed apps

**Files:**
- Create: `scripts/check_frozen_apps.sh`
- Modify: `.git/hooks/pre-commit` (untracked; local to this clone)
- Modify: `DJ_SYSTEM_REFERENCE.md` (Deployment section, ~line 245)

- [ ] **Step 1: Create the check**

```bash
#!/bin/bash
# Pre-commit check: if dj_core.py or check_dj_gui.py is staged, the
# installed DJ Availability apps must already contain exactly the staged
# sources. Otherwise a rule change reaches GitHub with the desktop apps
# behind it, which is what happened on 2026-10-17.
#   SKIP_FROZEN_CHECK=1 git commit ...   # machines without the apps (Henry)
set -euo pipefail
cd "$(dirname "$0")/.."

[ "${SKIP_FROZEN_CHECK:-}" = "1" ] && exit 0

if ! git diff --cached --name-only | grep -qxE "dj_core\.py|check_dj_gui\.py"; then
  exit 0
fi

WANT="$(scripts/source_stamp.sh --staged)"
for YEAR in 2026 2027; do
  STAMP_FILE="/Applications/DJ Availability $YEAR.app/Contents/Resources/source-stamp.txt"
  HAVE="$(cat "$STAMP_FILE" 2>/dev/null || echo missing)"
  if [ "$HAVE" != "$WANT" ]; then
    cat >&2 <<EOF
Frozen app is stale: DJ Availability $YEAR has $HAVE, staged sources are $WANT.
Run ./release.sh "message" (tests, build, install, commit, push) instead of
git commit. Bypass on a machine without the apps: SKIP_FROZEN_CHECK=1.
EOF
    exit 1
  fi
done
```

`chmod +x scripts/check_frozen_apps.sh`

- [ ] **Step 2: Wire the hook**

Rewrite `.git/hooks/pre-commit` as (the original had no `set -e`, so appending a line would have made a gitleaks failure non-blocking):

```sh
#!/bin/sh
set -e
# Block commits that contain secrets. Bypass with --no-verify only if you're certain.
gitleaks git --staged --redact --verbose
# Frozen DJ Availability apps must match staged rule sources (scripts/check_frozen_apps.sh).
./scripts/check_frozen_apps.sh
```

- [ ] **Step 3: Prove it refuses, then passes**

Refuse: add a comment line to `dj_core.py` (`echo "# stamp test" >> dj_core.py`), `git add dj_core.py`, then `git commit -m "should be refused"`.
Expected: commit refused with `Frozen app is stale: DJ Availability 2026 has <hash>, staged sources are <hash>.` Then undo: `git reset dj_core.py && git checkout dj_core.py`.

Pass: `git add scripts/check_frozen_apps.sh` and commit (Step 5). `dj_core.py` is not staged, so the check exits 0.

- [ ] **Step 4: Document**

In `DJ_SYSTEM_REFERENCE.md` section 8 (Deployment & Configuration), add under the Streamlit Cloud paragraph:

```markdown
### Shipping an availability-rule change

Rules live in `dj_core.py` only (`check_dj_availability` for yes/no, `dj_status` for wording and color). The three front ends paint `DJStatus` and `tests/test_no_dj_rules_in_front_ends.py` fails if one of them branches on a DJ name again.

The desktop apps are frozen PyInstaller bundles and do not see source edits. Each carries `Contents/Resources/source-stamp.txt`, a hash of `dj_core.py` + `check_dj_gui.py` (`scripts/source_stamp.sh`). The pre-commit hook (`scripts/check_frozen_apps.sh`) refuses a commit that stages either file unless the installed apps already carry that hash.

So the one path is: edit, `git add` by name, `./release.sh "message"`. It runs the tests, rebuilds and installs both apps, commits, and pushes (Streamlit Cloud redeploys from `main`). On a machine without the apps: `SKIP_FROZEN_CHECK=1 git commit`.
```

- [ ] **Step 5: Commit**

```bash
git add scripts/check_frozen_apps.sh DJ_SYSTEM_REFERENCE.md docs/plans/2026-10-17-one-availability-rule-home.md
git commit -m "pre-commit: refuse rule changes the frozen apps do not have yet

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Ship through the new path

- [ ] **Step 1: Confirm the apps are quit**

Run: `pgrep -fl "DJ Availability" || echo none running`
Expected: `none running` (if not, ask Paul to quit the app).

- [ ] **Step 2: Release**

Nothing should be staged at this point (`git diff --cached --quiet && echo clean`). Run `./release.sh` with no message: tests, build, install. Then stage nothing new and push the commits made in Tasks 0-9:

Run: `./release.sh 2>&1 | grep -E "^==|installed:|^OK|FAILED"` then `git push`
Expected: `OK`, two `installed:` lines with matching stamps, then the push succeeds.

- [ ] **Step 3: Verify end to end**

- `open "/Applications/DJ Availability 2027.app"`, check 3/27: `Stephanie: not available (2027)`, spots `2* (Henry, Paul)`.
- `cat "/Applications/DJ Availability 2027.app/Contents/Resources/source-stamp.txt"` equals `scripts/source_stamp.sh`.
- Streamlit Cloud: after a few minutes, check 3/27 for 2027 in the browser app. Stephanie dim `not available (2027)`.
- `git status --short` shows only the pre-existing unrelated changes (`.scpt`, `.plist`, `archive/automator-apps/`). The plan file was committed in Task 9.
