# Calendar reads: icalBuddy → CalDAV

**Date:** 2026-10-04
**Status:** Implemented 2026-10-04 (uncommitted). Decisions: all callers; halt with dialog.

## Why

icalBuddy 1.10.1 (latest, unmaintained) returns zero calendars on macOS 27.2 even with Terminal at Full Access. Measured 2026-10-04: `icalBuddy calendars` returned a full list once, right after `tccutil reset`, then `0` on six consecutive runs. Every read that goes through it fails silently:

| Caller | Calendars | What happens on failure today |
|---|---|---|
| `booking_comparator.fetch_master_calendar` | Gigs, Wedding Faires | Drops to a 2-of-3 report (`Systems compared: Gig DB + Matrix`). Visible, but the run is useless. |
| `gig_booking_manager.check_calendar_conflicts` | Gigs, Unavailable | **Returns `[]` = "no conflicts."** Doesn't check the return code. A booking can go through against a real conflict with no warning. |
| `stefano_maxed_enforcer` Unavailable read | Unavailable | Prints a warning, treats Unavailable as empty. |

CalDAV reads were proven 2026-10-04 from VS Code, no Terminal or TCC involved: the Gigs calendar returned 283 events for 2026, including `[PB, WM] CASA of San Mateo County Fundraiser` on 9/24. `nestldown_roster.py` has used the same credentials (Keychain `bigfun-caldav`) and direct-URL pattern in production since spring.

## Calendar URLs (all under the shared owner `65B490A6-…`)

- Gigs: `…/1187934A-6A2E-43A3-8355-74382DC82F47/` (already in `nestldown_roster.py`)
- Wedding Faires: `…/67B6FC2C-1D53-4E52-8BE5-B76D5F967DB0/`
- Unavailable: `…/E7F24781-3EAF-44E2-8264-B5CC03D48A81/`

These calendars are not in Paul's own principal's calendar list (it's a shared set), so look up by direct URL, not by name.

## Design

One small shared module, because there are three callers:

**`calendar_read.py`**
- `fetch_events(calendar_names, start_date, end_date) -> list[(date, summary)]`. Uses keyring creds, a `CALENDAR_URLS` dict, `search(..., expand=True)` so recurring events expand.
- Date rule: an all-day `DTSTART` is a `date`, used as is. A timed `DTSTART` gets converted to America/Los_Angeles, then its date is used. Multi-day events count on their start date, which is what the icalBuddy parse did (it took the first date on the line).
- **It raises on any failure** (no creds, HTTP error, unknown calendar). It never returns empty to mean "couldn't read." Each caller decides what failure means for it.

**Per caller:**
1. `booking_comparator`: split the current title-parsing loop into a pure `parse_calendar_events(events, initials_to_name) -> (bookings, backups)`, keeping the existing rules (bracket codes via `parse_dj_codes`, `BACKUP` → backups, `HOLD TO DJ` skipped, `U*` → TBA, unknown → `?XX`). `fetch_master_calendar` = `fetch_events` + parse. On an exception: print the error and return `(None, None)`, so the 2-of-3 report and the loop's done-rule still catch it.
2. `gig_booking_manager.check_calendar_conflicts`: same keyword filter on summaries. **On an exception, it does not return "clear."** It surfaces "Calendar check FAILED — verify manually" in the booking flow. That's a behavior change and needs Paul's OK; see Decisions.
3. `stefano_maxed_enforcer`: swap the Unavailable read. Same failure rule as the booking manager.

icalBuddy stays installed but goes unused. No AppleScript writes are touched.

## Environment

- `.venv` (rebuilt 2026-09-19) is missing `caldav` even though `requirements.txt` lists it. Install with `.venv/bin/pip install -r requirements.txt`.
- Check which Python the Stream Deck / AppleScript launchers for `gig_booking_manager` and `stefano_maxed_enforcer` use, and confirm `caldav` imports there. `run_nestldown_roster.sh` uses miniconda, which already has it.

## Tests (TDD, per CLAUDE.md: shared logic, cross-source check, write-flow guard)

Write these first, against fixture `(date, summary)` lists and fake VEVENTs:
- `parse_calendar_events`: single `[PB]`, slash `[WM/HK]`, comma `[PB, WM]`, `[WM] BACKUP DJ` → backups, `[SB] PAID BACKUP DJ` all-day → backups, `HOLD TO DJ` skipped, `[UP]` → TBA, `[AD]` → `?AD`, no bracket ignored, sorted output.
- Date normalisation: all-day date; timed event 2026-11-21 22:00 PDT stored in UTC (which is 11/22 in UTC) → 11/21; a recurring event expands to every occurrence.
- `fetch_events` raises on a mocked HTTP error / missing creds, and never returns `[]` for a failure.
- `check_calendar_conflicts`: a conflict is found; BACKUP/HOLD/DAD-DUTY are ignored; **a read failure is not reported as clear.**
- Existing `test_booking_comparator.py`, `test_gig_booking_manager.py`, `test_stefano_enforcer.py` stay green.

## Acceptance

1. Comparator for 2026 and 2027 run **from Claude Code (VS Code)**. Both reports say `Systems compared: Gig DB + Matrix + Calendar`.
2. Diff against the last good calendar run (`EA/loops/systems-crosscheck/runs/2026-09-23-*`). Every difference gets explained: 9/24 should clear (comma fix `70c5046`); backups 3/7, 9/25, 9/5, 9/6 should show the same as 9/23 unless the sheet changed since then; anything else is investigated before calling it done.
3. `check_calendar_conflicts` in dry/test mode for a date with a known Gigs event (9/24, `[PB]`) returns the CASA title.
4. Full test suite passes.

## Follow-on (EA repo, after acceptance)

- `loop-systems-crosscheck` skill: Step 1 is run by Claude directly. Drop the Terminal-only rule and tonight's icalBuddy troubleshooting note.
- Reminder text: "Tell Claude: run the crosscheck loop."
- The Stream Deck button is now optional. Retire the stale miniconda copy.
- `DJ_SYSTEM_REFERENCE.md`: calendar reads are CalDAV, not icalBuddy.

## Decisions for Paul

1. **Scope:** all three callers (recommended, since the booking manager's silent "clear" is the real risk), or just the comparator for now?
2. **Booking-manager failure behavior:** when the calendar can't be read, stop and show a "Calendar check FAILED" dialog that you have to dismiss (recommended), or just print a warning and continue?

## Outcome (2026-10-04)

- A fourth caller turned up: `backup_assigner.py` uses `check_calendar_conflicts`. On a read failure it now shows a dialog and skips that date.
- The review found a bug that predates this change: `check_calendar_conflicts` matched on the substring `"[PB]"`, so joint events (`[PB, WM]`, `[WM/HK]`) never counted as conflicts, and a co-DJ could be assigned as backup. It now matches on `parse_dj_codes`, and only counts events that start that day.
- The comparator drops events that start in another year.
- Acceptance: (1) both years compare all 3 systems, run from VS Code. (2) Compared with 9/23, the backups are identical. 9/24 did not clear: the comma parse now shows Woody (who is in the Gig DB's DJ2/roadie slot), which is a labeling question. 11/21 Henry is new, a Gig DB-only booking. (3) A live `check_calendar_conflicts(9/24, "[PB]")` returns the CASA title. (4) All suites pass.
- Confirmed 2026-10-05: a real Stream Deck run of `gig_booking_manager` read the `bigfun-caldav` Keychain item with no access prompt (Paul).
