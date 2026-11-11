# One Backup Step Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assigning a backup DJ is one function in `gig_booking_manager.py`. Book Event, Assign DJ and Backup Assigner all call it, so a backup rule or bug fix is one edit, not three.

**Why now:** on 2026-11-11 a hand-made `[WM] BACKUP` calendar event on 6/26/27 made Assign DJ refuse Woody as backup and leave the Matrix saying OUT. The fix (`824d5df`) had to go into Assign DJ and Book Event separately. **Backup Assigner still has the bug**, because it's a third copy.

**Architecture:** `gig_booking_manager.py` is already the library all three tools import from (`can_backup`, `check_calendar_conflicts`, `create_allday_backup_event`, `split_backup_hits`). The backup *step* (choose candidates, check the calendar, write the Matrix, make the event, handle failures) moves there as `backup_candidates()`, `backup_cell_value()` and `assign_backup()`. Each tool keeps only its own dialog and its own reporting.

**Tech Stack:** Python 3.13 (`.venv/bin/python`), stdlib `unittest`, run as **two suites** (pytest is not installed):
- `.venv/bin/python -m unittest discover tests` (193 tests at `824d5df`)
- `.venv/bin/python -m unittest test_gig_booking_manager` (135 tests, root-level file)

**Working directory:** `/Users/paulburchfield/Documents/projects/dj-availability-checker`

**Key facts the executor needs:**
- **Three copies today:**
  - Book Event: `GigBookingManager.run()` in `gig_booking_manager.py`, the "Phase 2: Backup assessment" block (candidates inline, conflict check, Matrix write with an inline `replace_values` set) plus the "Backup event" block in Phase 3.
  - Assign DJ: `assign_dj.py`, `backup_candidates()`, `backup_cell_value()` / `_BACKUP_REPLACES`, `_assign_backup()`. This is the cleanest copy and the template for the shared one: it takes `conflicts` and `make_backup_event` as injectable callables, which is why it's already tested.
  - Backup Assigner: `backup_assigner.py`, `BackupAssigner` method around lines 278-335 (conflict check, inline `replace_values`, Matrix write, event).
- The `{"", "OUT", "OK", "DAD", "STANFORD", "LAST", "OK TO BACKUP", "BACKUP"}` replace set is written out three times. It becomes one constant.
- `gig_booking_manager.py` is **not** frozen into the DJ Availability apps (`scripts/source_stamp.sh`), so no app rebuild. The Stream Deck `.scpt` files call the `.py` in the repo directly, so a commit is live at once.
- Existing Book Event test harness: `test_gig_booking_manager.py` `TestSetupBookingWrite` runs `GigBookingManager(dry_run=True, test_mode=True).run(json_path)` and patches module functions with `mock.patch("gig_booking_manager.<name>")`. Characterization tests use the same pattern, but with `dry_run=False` + `test_mode=True` and `MockSheetsClient`, so the backup dialog path is reached. Patch `show_backup_dialog`, `check_calendar_conflicts`, `create_allday_backup_event`, `create_timed_calendar_event`, and anything else that touches the network (email folder, music link, booking-log form, nurture). Confirm by grepping `run()` that every outbound call is patched before running a non-dry-run test.
- Do not commit the unrelated working-tree changes (`assign_dj.scpt`, `gig_booking_manager.scpt`). Stage files by name.

**Behaviour changes this makes (intentional, flag to Paul before Task 4):**
1. **Book Event and Backup Assigner stop crashing if the backup calendar event fails.** Today an exception from `create_allday_backup_event` goes uncaught *after* the Matrix says BACKUP. Shared step: warn "create the event by hand", like Assign DJ already does.
2. **Any calendar-check error means "not checked, not written".** Today Book Event and Backup Assigner catch only `CalendarReadError`. Anything else crashes them.
3. **Book Event makes the backup event right after the Matrix write**, not after the primary event in Phase 3. Same events, different order.
4. **Backup Assigner gets the hand-made-BACKUP fix.**

Nothing else changes: same candidates, same Matrix values, same event titles, same dialogs.

---

### Task 0: Baseline

- [ ] Both suites green at `824d5df`: 193 and 135.
- [ ] `git status`: only the two `.scpt` files dirty.

### Task 1: Characterization tests for Book Event's backup step (before touching it)

Test file: `test_gig_booking_manager.py`, new class `TestBookEventBackupStep`. Non-dry-run, `test_mode=True`, `MockSheetsClient` row with TBA blank and the booked DJ's column ready, every outbound call patched.

- [ ] Pick Woody, calendar clear → Matrix write `BACKUP` in Woody's column, `create_allday_backup_event` called once with Woody.
- [ ] Pick Woody, calendar has `[WM] Smith Wedding` → no BACKUP write, no backup event, warning shown.
- [ ] Pick Woody, calendar has `[WM] BACKUP` only → BACKUP written, no backup event (the `824d5df` behaviour).
- [ ] Felipe cell `DAD-DUTY` → written `DAD-DUTY, BACKUP`.
- [ ] Row already has a BACKUP → no new BACKUP write.
- [ ] Dialog returns None → no BACKUP write, log says skipped.
- [ ] Run both suites. All new tests pass **against today's code**. If one fails, the test is wrong or there's a bug not in this list. Stop and report it to Paul. Don't fix it silently.
- [ ] Commit: `test: pin Book Event's backup step before sharing it`.

### Task 2: Characterization tests for Backup Assigner

New file `tests/test_backup_assigner.py`. Drive the per-date assign method with `MockSheetsClient` and patched dialog/conflicts/event.

- [ ] Same cases as Task 1, except the hand-made `[WM] BACKUP` case. Today it **fails** (conflict). Write it as `expectedFailure` with a comment pointing at Task 5.
- [ ] Assert the `stats` counters (`assigned`, `conflicts`, `skipped`) for each case.
- [ ] Commit.

### Task 3: Move the shared pieces into `gig_booking_manager.py`

- [ ] Move `backup_cell_value()` and `_BACKUP_REPLACES` (rename `BACKUP_REPLACES`) and `backup_candidates()` from `assign_dj.py` into `gig_booking_manager.py`, next to `can_backup`. `assign_dj.py` imports them. No logic change.
- [ ] Move `_assign_backup()` to `gig_booking_manager.assign_backup()`. Change the return value to `(status, summary)`, where status is one of `"assigned"`, `"already_on_calendar"`, `"conflict"`, `"check_failed"`, `"event_failed"`. Backup Assigner needs the status for its stats. Assign DJ uses `summary` as today.
- [ ] Parameters stay injectable (`conflicts`, `make_backup_event`, `log`, `warn`), defaulting to the real functions.
- [ ] Assign DJ tests in `tests/test_assign_dj.py` pass unchanged (they go through `assign_dj.assign`). Add unit tests for `assign_backup()` covering each status.
- [ ] Both suites green. Commit.

### Task 4: Book Event uses the shared step

**Check with Paul first:** behaviour changes 1-3 above.

- [ ] Replace the inline candidate loop with `backup_candidates(...)`. Dry run passes a `bold_lookup` that returns False and prints the existing "[DRY RUN] Would check bold" line, so dry-run output stays the same.
- [ ] Replace the conflict check + Matrix write with `assign_backup(...)`. `warn=show_warning_dialog` (skipped in dry run), `log=self.log`.
- [ ] Delete the Phase 3 "Backup event" block and the `backup_already_on_cal` variable.
- [ ] Task 1 tests still pass, unedited. Both suites green. Commit.

### Task 5: Backup Assigner uses the shared step

- [ ] Replace lines ~280-333 with `assign_backup(...)`. Map status to `stats` (`assigned` and `already_on_calendar` count as assigned, `conflict` adds to conflicts and skipped, `check_failed` and `event_failed` add to skipped).
- [ ] Remove `expectedFailure` from the hand-made-BACKUP test. It should now pass.
- [ ] Both suites green. Commit.

### Task 6: Guard so a fourth copy can't creep back

Pattern: `tests/test_no_dj_rules_in_front_ends.py`.

- [ ] New `tests/test_one_backup_step.py`: fails if `"OK TO BACKUP"` (the tell-tale of the replace set) or a call to `create_allday_backup_event(` appears in any `.py` other than `gig_booking_manager.py` (`assign_backup` is the only caller). Include a self-test that the pattern catches a real line.
- [ ] Both suites green. Commit.

### Task 7: Live check (Paul)

- [ ] `osascript assign_dj.scpt --dry-run` on an unassigned booking: same log as before.
- [ ] Next real Book Event with a backup: Matrix BACKUP plus `[XX] BACKUP DJ` event, same as before.
- [ ] `backup_assigner.py --dry-run` for 2027: same date list as before.
- [ ] Push.
