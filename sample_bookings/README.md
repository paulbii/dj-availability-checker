# Sample Booking Files

These sample JSON files can be used to test `gig_booking_manager.py` with the `--dry-run` flag, so you don't have to create fake events in the production database.

## How to Use

Test any sample file with dry-run mode:

```bash
python3 gig_booking_manager.py sample_bookings/sample_booking_template.json --dry-run
```

The `--dry-run` flag will:
- Validate the booking data
- Check matrix and calendar for conflicts
- Show what changes would be made
- **NOT** actually write to the availability matrix or create calendar events

## Available Sample Files

### 1. `sample_booking_template.json`
**Purpose:** General template you can copy and modify
**Tests:** Nestldown 6-hour event with ceremony sound
**DJ:** Paul
**Special:** Tests Nestldown calendar timing logic (2:40 PM - 8:40 PM → Calendar: 1:00 PM - 10:00 PM)

### 2. `sample_regular_booking.json`
**Purpose:** Standard booking at regular venue
**Tests:** Normal calendar timing rules (ceremony = 2 hours before, 1 hour after)
**DJ:** Henry
**Venue:** Mountain Winery

### 3. `sample_unassigned_booking.json`
**Purpose:** Booking without DJ assigned yet
**Tests:** TBA column increment logic
**DJ:** Unassigned
**Result:** Should increment TBA column (BOOKED, BOOKED x 2, etc.)

### 4. `sample_first_booking_paul.json` + `sample_second_booking_same_day.json`
**Purpose:** Test multiple bookings on same day (New Year's Eve 2026)
**Tests:** Multiple booking confirmation dialog
**DJ:** Paul on 2026-12-31
**How to test:**
1. **Run first booking WITHOUT --dry-run** to create actual matrix/calendar data:
   ```bash
   python3 gig_booking_manager.py sample_bookings/sample_first_booking_paul.json
   ```
   Result: Paul's cell shows "BOOKED", calendar has Martinez Wedding event

2. **Run second booking WITH --dry-run** to test the dialog:
   ```bash
   python3 gig_booking_manager.py sample_bookings/sample_second_booking_same_day.json --dry-run
   ```
   Result: Dialog appears asking "Paul already has an event... Add this new booking anyway?"

3. **If you want to complete the test** (run without --dry-run):
   - Matrix cell changes: BOOKED → BOOKED x 2
   - Calendar gets Chen & Lee event

4. **Clean up test data:**
   - Matrix: Clear Paul's cell on 12/31/2026
   - Calendar: Delete both test events from Gigs calendar

### 5. `sample_nestldown_minimony.json`
**Purpose:** 3-hour Nestldown event (minimony)
**Tests:** That short Nestldown events use normal timing, not the special 9-hour rule
**DJ:** Woody
**Event:** 4:00 PM - 7:00 PM (3 hours)
**Expected:** Normal timing (2:00 PM - 8:00 PM calendar)

### 6. `sample_new_date_12_17_26.json`
**Purpose:** Test auto-create date row feature
**Tests:** Creating a new row with formulas when date doesn't exist in matrix
**DJ:** Paul
**Date:** 12/17/2026 (Thursday)
**How to test:**
1. **Verify 12/17/26 doesn't exist** in the 2026 availability matrix
2. **Run with --dry-run first**:
   ```bash
   python3 gig_booking_manager.py sample_bookings/sample_new_date_12_17_26.json --dry-run
   ```
   Result: Should show "[DRY RUN] Would create new row for Thursday 12/17/2026"
3. **Run without --dry-run** to actually create the row:
   ```bash
   python3 gig_booking_manager.py sample_bookings/sample_new_date_12_17_26.json
   ```
   Result: New row created with formulas in columns B, C, E, G, H
4. **Verify in Google Sheets** that the row was inserted in chronological order and formulas work correctly

## Field Reference

```json
{
  "event_date": "YYYY-MM-DD format",
  "assigned_dj": "First name: Henry/Woody/Paul/Stefano/Felipe/Stephanie or 'Unassigned'",
  "secondary_dj": "Optional second DJ (rarely used)",

  "client_name": "Couple names or event name",

  "venue_name": "Venue name",
  "venue_street": "Street address",
  "venue_city_state_zip": "City, State ZIP",

  "setup_time": "12-hour format WITHOUT AM/PM (e.g., '2:40' or '3:00')",
  "clear_time": "12-hour format WITHOUT AM/PM (e.g., '8:40' or '9:00')",

  "sound_type": "'Ceremony' or 'Standard Speakers'",
  "has_ceremony_sound": true or false,

  "planner_name": "Planner/coordinator name or empty string"
}
```

## Testing Checklist

Before using gig_booking_manager in production, test these scenarios:

- [ ] Regular booking (sample_regular_booking.json)
- [ ] Nestldown 6-hour event (sample_booking_template.json)
- [ ] Nestldown minimony (sample_nestldown_minimony.json)
- [ ] Unassigned/TBA booking (sample_unassigned_booking.json)
- [ ] Multiple bookings same day (sample_second_booking_same_day.json)
- [ ] Auto-create missing date row (sample_new_date_12_17_26.json)
- [ ] Matrix/calendar mismatch (manually create mismatch to test error)
- [ ] Backup DJ selection dialog

## Creating Your Own Samples

Copy `sample_booking_template.json` and modify:
- Change `event_date` to a date in your test range
- Change `assigned_dj` to test different DJs
- Adjust times to test different calendar timing scenarios
- Use `"assigned_dj": "Unassigned"` to test TBA bookings

## Removing Test Data

After testing with `--dry-run`, if you accidentally run without the flag and create test bookings:

**Availability Matrix:**
- Manually clear the test date's DJ cells in Google Sheets

**Calendar:**
- Delete test events from Apple Calendar → Gigs calendar

**Gig Database:**
- No changes made (script only reads from database, never writes to it)
