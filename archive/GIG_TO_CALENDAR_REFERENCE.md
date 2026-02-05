# Gig DB to Calendar — Development Reference

> **Purpose:** Document the design, logic, and decisions behind the Gig DB to Calendar automation tool. Use this as context for future development, debugging, or extending the tool.

---

## Overview

This tool automates the creation of Apple Calendar events from FileMaker Pro booking records. Instead of manually entering event details into the calendar after booking a gig, Paul opens the booking record in Safari and presses a Stream Deck button. The calendar event is created automatically with the correct title, times, location, and DJ invite.

Before creating the event, the script checks the Gigs calendar for existing events assigned to the same DJ on the same date. If a conflict is found, the user is warned and can choose to cancel or proceed.

**Files:**
- `gig_to_calendar.py` — Python script that processes booking data and creates calendar events via AppleScript
- `gig_to_calendar.scpt` — AppleScript that extracts data from Safari, checks for conflicts, and passes data to the Python script

**Location:** `/Users/paulburchfield/Documents/projects/gig-db-to-calendar/`

---

## Architecture

```
Safari (FileMaker booking page)
    │
    │  AppleScript extracts JavaScript variables from page source
    │
    ▼
Conflict Check (AppleScript queries "Gigs" calendar)
    │
    │  If conflict: warning dialog → Cancel or Create Anyway
    │  If no conflict: proceed silently
    │
    ▼
/tmp/gig_booking.json (temp file)
    │
    │  Python script reads JSON, applies business rules
    │
    ▼
Apple Calendar (AppleScript creates event in "Gigs" calendar)
```

### How Data Gets Extracted

FileMaker Pro's web interface embeds booking data as JavaScript variables in the page source. The AppleScript runs JavaScript in Safari to read these variables and serialize them as JSON. No custom API endpoint is needed — the data is already on the page.

Example of what's in the page source:
```javascript
FMeventDate = "02/21/2026";
FMstartTime = "4:00";
FMendTime = "10:00";
FMclient = "Catherine MacDougall and Jacob Asmuth";
FMvenue = "Kohl Mansion (FOG OK)";
FMvenueAddress = "2750 Adeline Drive***Burlingame, CA 94010";
FMDJ1 = "Paul Burchfield";
FMDJ2 = "";
FMsound = "Standard Speakers";
FMcersound = "1";
MailCoordinator = "Jutta Lammerts <jutta@daylikenoother.com>";
```

### Fields Extracted by the AppleScript

| JS Variable | Purpose |
|-------------|---------|
| `FMeventDate` | Event date (MM/DD/YYYY) |
| `FMstartTime` | Event start time (12-hour, no AM/PM) |
| `FMendTime` | Event end time (12-hour, no AM/PM) |
| `FMclient` | Client name(s) |
| `FMvenue` | Venue name (may include parenthetical notes) |
| `FMvenueAddress` | Venue address (street***city, state zip) |
| `FMDJ1` | Assigned DJ (full name, or "Unassigned") |
| `FMDJ2` | Secondary DJ / responsible party for unassigned events |
| `FMsound` | Sound system type |
| `FMcersound` | Ceremony sound flag ("0" or "1") |
| `MailCoordinator` | Planner/coordinator info (empty = no planner) |

### Other Fields Available but Not Currently Used

These are present in the page source and could be extracted in the future:

| JS Variable | Content |
|-------------|---------|
| `FMaddress` | Client home address (street***city, state zip) |
| `FMname1` / `FMname2` | Individual names of each person in the couple |
| `FMphone1` / `FMphone2` | Phone numbers (home***cell***work, delimited by ***) |
| `FMtype` | Event type ("Wedding", "Other", etc.) |
| `FMfeeAmount` | Contract amount |
| `FMlights` | Lighting package ("Yes with Fog", "None", etc.) |
| `FMuplights` | Number of uplights ("0", "12", etc.) |
| `FMproj` | Projector info |
| `FMstreaming` | Streaming info |
| `FMvenuePhone` | Venue phone number |
| `FMvenueContact` | Venue coordinator name(s) |
| `MailHelper` | Client email addresses ("Name <email>, Name <email>") |
| `MailBilling` | Billing contact email |
| `FMreserved` / `FMconfirmed` / `FMplayed` / `FMpaid` | Status flags |
| `FMcustomText` / `FMnoteText` | Free-text notes |

**Note on the `***` delimiter:** FileMaker uses `***` (three asterisks) as a multi-field delimiter. For example, `FMphone1 = "***408-839-4200******"` represents home phone (empty), cell phone (408-839-4200), and work phone (empty). The venue address similarly uses `***` between street and city/state/zip, with an unused middle line.

---

## Conflict Check

### How It Works

Before creating the calendar event, the AppleScript:

1. Extracts `FMDJ1` and `FMeventDate` from the Safari page
2. Maps the DJ name to their two-letter initials (e.g., Henry → HK)
3. Queries the "Gigs" calendar for all events on that date
4. Checks if any event title starts with the DJ's bracket prefix (e.g., `[HK]`)
5. If conflicts are found, displays a warning dialog with event details
6. User chooses **Cancel** (event not created) or **Create Anyway** (proceeds normally)

### When the Check Is Skipped

- **Unassigned or Unknown DJs:** Multiple unassigned events on the same date is normal business. No conflict check is performed.
- **`--force` flag:** Bypasses the conflict check entirely. Useful for re-running after failures or when you already know about the conflict.
- **Missing event date:** If `FMeventDate` is empty, the check is skipped (can't query without a date).

### What Constitutes a Conflict

- **Same day:** Any existing event on the same calendar date, regardless of time overlap. A DJ doing a 12pm event and a 7pm event on the same day would trigger the warning.
- **Matching DJ prefix:** The event title must start with `[XX]` where XX matches the assigned DJ's initials.
- **Both timed and all-day events** are checked.

### Warning Dialog

When a conflict is found, the dialog shows:

```
⚠️ Henry has 1 existing event on this date:

  • [HK] Anya and Hilal (planner)
    2:30 PM – 11:00 PM

Create the new event anyway?

[Cancel]  [Create Anyway]
```

If the user cancels, a notification confirms: "Event creation cancelled."

### DJ Initials Mapping (Duplicated in AppleScript)

The initials mapping exists in both `gig_to_calendar.py` (for title generation) and `gig_to_calendar.scpt` (for conflict checking). If a new DJ is added, **both files must be updated**.

| DJ | Initials |
|----|----------|
| Henry | HK |
| Woody | WM |
| Paul | PB |
| Stefano | SB |
| Felipe | FS |
| Stephanie | SD |

---

## Calendar Event Mapping

### Event Title

Format: `[INITIALS] ClientName` with optional `(planner)` suffix.

**DJ Initials:**

| DJ | Initials |
|----|----------|
| Henry (Kim) | HK |
| Woody (Miraglia) | WM |
| Paul (Burchfield) | PB |
| Stefano (Bortolin) | SB |
| Felipe (Silva) | FS |
| Stephanie (de Jesus) | SD |
| Unknown (no DJ field) | UP |
| Unassigned (with DJ2) | U + DJ2's first initial (e.g., UP, UH) |

**DJ Email Addresses:** All follow the pattern `firstname@bigfundj.com`.

**Client Name Extraction:**
- Couples: "Anya Hee and Hilal Ahmad" → "Anya and Hilal" (extracts first names)
- Non-couples: "Bird Family Seder" → "Bird Family Seder" (uses full name)
- Detection: splits on " and " — if both sides have 2+ words, it's treated as a couple

**Planner Indicator:**
- `MailCoordinator` field is checked — if non-empty, `(planner)` is appended to the title
- The planner's actual name is not used in the title; it's just a reminder that a planner is involved

**Examples:**
- `[HK] Anya and Hilal (planner)` — Henry's event, has a planner
- `[PB] Bird Family Seder` — Paul's corporate event, no planner
- `[UP] Miriam and Justin` — Unassigned, Paul responsible

### Event Times

Calendar event times differ from the gig database event times. The calendar reflects DJ arrival and departure, not the event itself.

**Start time = Event start minus arrival offset**
**End time = Event end plus 1 hour (departure)**

#### Arrival Time Logic

Priority order (first match wins):

| Condition | Arrival Offset |
|-----------|---------------|
| FMsound contains "quad" (case-insensitive) | 120 minutes |
| FMsound = "No Main Sound" AND FMcersound = "0" | 60 minutes |
| FMsound = "No Main Sound" AND FMcersound = "1" | 90 minutes |
| FMcersound = "1" (standard sound) | 120 minutes |
| FMcersound = "0" (standard sound) | 90 minutes |

**Why:** More equipment = more setup time. Quad speakers require the most setup. "No Main Sound" means we're only bringing ceremony sound or nothing at all.

**Note:** There is one additional scenario that triggers 120-minute arrival that is not captured by this logic (identified during development but deemed acceptable to handle manually).

#### Departure Time Logic

- End time + 1 hour for teardown
- **Midnight cap:** If the resulting end time is midnight (24:00) or later, it's set to 11:59 PM to avoid the calendar event spilling into the next day

#### 12-Hour Time Conversion (No AM/PM)

The gig database stores times in 12-hour format without AM/PM indicators. The script infers AM/PM:

| Condition | Interpretation | Example |
|-----------|---------------|---------|
| Start > End numerically | Crosses noon: start AM, end PM | 9:00→3:00 = 9am-3pm |
| End = 12 and Start < 12 | Crosses noon at 12 | 9:30→12:30 = 9:30am-12:30pm |
| Start ≤ End | Both PM (evening) | 4:00→10:00 = 4pm-10pm |
| End = 12:00 | Midnight, cap at 11:59 PM | 5:00→12:00 = 5pm-11:59pm |

**Known limitations:**
- Rare events crossing midnight (e.g., 6pm to 1am) are misinterpreted as crossing noon (6am to 1pm). Happens 1-2 times per year; manually fixed.
- Rare morning events where both times are before noon (e.g., 7am to 10am) are misinterpreted as PM (7pm to 10pm). Manually fixed.

### Location

- Venue name with parenthetical notes stripped: "Kohl Mansion (FOG OK)" → "Kohl Mansion"
- Street address from first part of FMvenueAddress (before ***)
- City/state/zip from second part of FMvenueAddress (after ***)
- Combined as: "Kohl Mansion, 2750 Adeline Drive, Burlingame, CA 94010"

### Invitee

- Assigned DJ gets added as a calendar invitee using their @bigfundj.com email
- "Unknown" or "Unassigned" DJs: no invitee is added
- Test mode (`--test` flag) routes all invites to paul@bigfundj.com

### Target Calendar

Events are created in the "Gigs" calendar in Apple Calendar.app.

---

## DJ Assignment States

| FMDJ1 | FMDJ2 | Meaning | Title Prefix | Invitee |
|-------|-------|---------|-------------|---------|
| "Paul Burchfield" | "" | Paul assigned | [PB] | paul@bigfundj.com |
| "Henry S. Kim" | "" | Henry assigned | [HK] | henry@bigfundj.com |
| "Unassigned" | "Paul Burchfield" | Unassigned, Paul responsible | [UP] | None |
| "Unassigned" | "Henry S. Kim" | Unassigned, Henry responsible | [UH] | None |
| "" (empty) | "" | Unknown/no DJ | [UP] | None |

---

## Execution Methods

### Terminal (with test mode)
```bash
osascript /Users/paulburchfield/Documents/projects/gig-db-to-calendar/gig_to_calendar.scpt --test
```

### Terminal (production)
```bash
osascript /Users/paulburchfield/Documents/projects/gig-db-to-calendar/gig_to_calendar.scpt
```

### Terminal (skip conflict check)
```bash
osascript /Users/paulburchfield/Documents/projects/gig-db-to-calendar/gig_to_calendar.scpt --force
```

### Stream Deck (production workflow)
- Stream Deck button triggers a Keyboard Maestro macro
- Macro title: "Gig DB → Calendar"
- Macro action: Execute Shell Script
- Command: `osascript /Users/paulburchfield/Documents/projects/gig-db-to-calendar/gig_to_calendar.scpt`

### Direct Python (for testing with JSON files)
```bash
cd /Users/paulburchfield/Documents/projects/gig-db-to-calendar
python3 gig_to_calendar.py sample_booking.json --test
```

**Note:** Direct Python execution bypasses the conflict check entirely, since that logic lives in the AppleScript. Use direct Python only for testing event creation logic (title formatting, time conversion, etc.).

---

## Input Formats

The Python script accepts two JSON formats:

### FM Format (from Safari/AppleScript)
```json
{
  "FMeventDate": "02/21/2026",
  "FMstartTime": "4:00",
  "FMendTime": "10:00",
  "FMclient": "Catherine MacDougall and Jacob Asmuth",
  "FMvenue": "Kohl Mansion (FOG OK)",
  "FMvenueAddress": "2750 Adeline Drive***Burlingame, CA 94010",
  "FMDJ1": "Paul Burchfield",
  "FMDJ2": "",
  "FMsound": "Standard Speakers",
  "FMcersound": "1",
  "MailCoordinator": "Jutta Lammerts <jutta@daylikenoother.com>"
}
```

### Clean Format (for manual testing)
```json
{
  "event_date": "2026-02-21",
  "client_name": "Catherine MacDougall and Jacob Asmuth",
  "assigned_dj": "Paul Burchfield",
  "venue_name": "Kohl Mansion (FOG OK)",
  "venue_street": "2750 Adeline Drive",
  "venue_city_state_zip": "Burlingame, CA 94010",
  "setup_time": "4:00",
  "clear_time": "10:00",
  "planner_name": "Jutta Lammerts",
  "has_ceremony_sound": true,
  "sound_type": "Standard Speakers"
}
```

The script auto-detects which format is being used by checking for the presence of `FMclient`.

---

## Known FMsound Values

From observed data:

| Value | Arrival Category |
|-------|-----------------|
| "Standard Speakers" | Standard (90 or 120 based on ceremony) |
| "Standard + Sub" | Standard |
| "Quad Speakers" | Quad (always 120 min) |
| "Quad + Side + Sub" | Quad (always 120 min) |
| "Corporate Setup" | Standard |
| "No Main Sound" | Reduced (60 or 90 based on ceremony) |

---

## Development Decisions & Notes

### Why AppleScript + Python (not pure Python)?
AppleScript is the most reliable way to create calendar events in Apple Calendar.app without extra auth complexity. Python handles the data transformation and business logic. The AppleScript extracts data from Safari via JavaScript execution, writes a temp JSON file, and calls the Python script.

### Why not a FileMaker API endpoint?
Henry (who built the FileMaker system) pointed out that the booking data is already available as JavaScript variables in the page source. This meant zero work on the FileMaker/PHP side — the AppleScript just reads what's already there.

### Why conflict check lives in AppleScript (not Python)?
The conflict check queries Apple Calendar, which is most naturally done via AppleScript. Keeping it in the AppleScript means the check happens *before* Python is called — if the user cancels, no temp file is written and no Python process runs. This also means direct Python testing (for title/time logic) isn't blocked by the conflict check.

The trade-off is that the DJ initials mapping is duplicated in both files. If a new DJ is added, both must be updated.

### Calendar `whose` clause for date filtering
The AppleScript uses `every event whose start date ≥ dayStart and start date < dayEnd` to query events on a specific date. This is efficient (Calendar.app filters server-side) but has known quirks with recurring events and multi-day spans. Since DJ gig events are neither recurring nor multi-day, this approach works well.

### Calendar invite gotcha
During testing, we discovered that if you create an event, delete it, and decline the invite, attempting to recreate the same event may fail silently. Using unique client names for each test avoids this issue.

### FMcersound empty string
When FMcersound is empty (""), the script treats it as "0" (no ceremony sound). This is handled by the default in `booking_data.get('FMcersound', '0')`.

### The "and" heuristic for couple detection
Splitting on " and " works because:
- Couples are entered as "FirstName LastName and FirstName LastName"
- Corporate/non-couple events like "Bird Family Seder" or "HCF Volunteer Summit" don't contain " and " between two full names
- Edge case check: both sides must have 2+ words to be treated as a couple, preventing false matches on things like "Tom and Jerry"

---

## Future Development Ideas

- **Batch processing:** Currently handles one event at a time. Could be extended to process multiple new bookings.
- **Update existing events:** When a DJ is assigned to a previously unassigned event, update the calendar event title and add the invitee.
- **Notification improvements:** Currently shows a macOS notification on success. Could include more detail or error specifics.
- **Availability matrix sync:** After creating the calendar event, automatically update the Google Sheets availability matrix.
- **Git version control:** Not currently tracked. Could be added if the tool grows in complexity.

---

*Last updated: February 2026*
