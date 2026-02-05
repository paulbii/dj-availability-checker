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

### 4. `sample_second_booking_same_day.json`
**Purpose:** Test multiple bookings on same day
**Tests:** Multiple booking confirmation dialog
**DJ:** Paul on 2026-09-12
**How to test:**
1. First add a booking for Paul on 2026-09-12 (using sample_regular_booking.json, edit to Paul and that date)
2. Then run this file - should show dialog asking if you want to add a 2nd booking
3. If approved, matrix cell should change: BOOKED → BOOKED x 2

### 5. `sample_nestldown_minimony.json`
**Purpose:** 3-hour Nestldown event (minimony)
**Tests:** That short Nestldown events use normal timing, not the special 9-hour rule
**DJ:** Woody
**Event:** 4:00 PM - 7:00 PM (3 hours)
**Expected:** Normal timing (2:00 PM - 8:00 PM calendar)

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

  "setup_time": "12-hour format with AM/PM (e.g., '2:40 PM')",
  "clear_time": "12-hour format with AM/PM (e.g., '8:40 PM')",

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
