# dj-availability-checker

Custom Python tools for DJ scheduling, availability checking, and booking automation at BIG FUN Disc Jockeys.

## Read first

- `DJ_SYSTEM_REFERENCE.md` — complete system reference. Read this before touching anything.
- `dj_core.py` — shared business logic. Match these patterns instead of writing new ones.

## Notes

- Python binary: `/Users/paulburchfield/miniconda3/bin/python3`
- Data sources: Google Sheets (Availability Matrix, Inquiry Tracker), FileMaker (Gig Database)
- Several tools wire to Stream Deck via AppleScript (`.scpt` wrappers). Changes to script entry points need to keep the wrappers working.
- Tools that write data (`gig_booking_manager.py`, `cancel_booking.py`, `stefano_maxed_enforcer.py`): TDD, or at minimum a `--dry-run` path before running for real.
- Stale git lock files happen occasionally. Fix: `rm -f .git/index.lock .git/HEAD.lock`.

## Before merging

- Run the relevant `check_*.py` against a known date and confirm output matches expectations.
- For write-path changes: run with `--dry-run` (or equivalent) and show the planned writes before executing.
