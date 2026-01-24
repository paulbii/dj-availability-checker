# Fully Booked Dates Feature

## What's New

Added a new menu option to `check_2026.py` (and can be easily added to `check_2027.py`) that identifies all dates with **zero available capacity** - perfect for managing your situation where multiple couples might be in conversation about the same date.

## Changes Made

### 1. **dj_core.py**
Added new function: `get_fully_booked_dates()`

**Key features:**
- Fetches all dates in a single pass (only 2 API calls for the entire year)
- Avoids Google API rate limits
- Processes data locally for speed
- Supports date range filtering
- Uses your existing availability logic to identify zero-capacity dates

### 2. **check_2026.py**
Added:
- Menu option #5: "List fully booked dates"
- New function `show_fully_booked_dates()` for formatted display
- Updated menu numbering (Exit moved to #6)

## How to Use

### Basic Usage
1. Run `check_2026.py`
2. Select option **5** (List fully booked dates)
3. Enter date range:
   - Press Enter at both prompts to check the **entire year**
   - Or enter specific MM-DD dates to narrow the search

### Example Output

```
==================================================
FULLY BOOKED DATES - 2026
Date range: 01-01 to 12-31
==================================================

Found 23 fully booked date(s):

Sat 4/11
  Total bookings: 5
  Booked DJs: Henry, Woody, Paul, Stefano
  TBA bookings: 1
  Backup assigned: 1

Sat 5/16
  Total bookings: 4
  Booked DJs: Henry, Paul, Stefano
  AAG: RESERVED
  Backup assigned: 1

...

==================================================
TIP: Review your open inquiries for these dates to notify couples.
==================================================
```

## Use Case: Managing Multiple Couples on Same Date

**Scenario:** You have 1 spot left on Saturday 6/20, but 3 couples actively in conversation.

**Workflow:**
1. When couple #1 confirms and takes the last spot
2. Run option #5 to get fresh list of fully booked dates
3. Cross-reference with your open inquiries
4. Proactively reach out to the other 2 couples about alternative dates

## Performance

- **Entire year scan:** ~5-10 seconds
- **Date range (e.g., peak season):** ~2-5 seconds
- **API calls:** Only 2 for the entire operation (well within Google's limits)

## Technical Details

### Rate Limit Avoidance
The function uses a bulk data fetch strategy:
- **Call 1:** Fetch all cell values for the year range
- **Call 2:** Fetch all formatting data (for bold detection)
- **Then:** Process everything locally in memory

This is **much** more efficient than the naive approach which would make ~700-1000 API calls.

### What Gets Flagged as "Fully Booked"

A date is considered fully booked when `available_spots == 0`, which happens when:
- All available DJs are marked as BOOKED or unavailable
- TBA bookings consume remaining capacity
- AAG RESERVED holds a Saturday spot (2026+)
- No DJs are available who could take a booking

## Easy Extension to check_2027.py

The same code can be copied to `check_2027.py` - just:
1. Add `get_fully_booked_dates` to the import statement
2. Add `show_fully_booked_dates()` function
3. Update the menu
4. Add the elif choice == "5" block in main()

The function automatically handles year-specific differences (like Stephanie's 2027 weekend-only status, Felipe's 2027 backup role, etc.) because it uses your existing `analyze_availability()` logic.

## Notes

- The function reads the **availability matrix only** (not FileMaker or Master Calendar)
- Results reflect the current state of your Google Sheet
- Perfect for a quick "what's full right now?" check when bookings are coming in
- Complements your existing tools (doesn't replace cross-system validation)
