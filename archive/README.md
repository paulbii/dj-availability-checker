# Archive

This folder contains legacy code that has been superseded by newer implementations.

## gig_to_calendar (Archived Feb 2026)

**Original purpose:** Add booking data to Apple Calendar

**Replaced by:** `gig_booking_manager.py`

**Why archived:** The functionality was consolidated into gig_booking_manager, which now handles both calendar creation AND availability matrix updates in a single workflow. The original gig_to_calendar only handled calendar events.

**Files:**
- `gig_to_calendar.py` - Python script for calendar event creation
- `gig_to_calendar.scpt` - AppleScript wrapper that extracted data from Safari
- `GIG_TO_CALENDAR_REFERENCE.md` - Original documentation

**If you need to reference the old implementation:** Check git history or these archived files.
