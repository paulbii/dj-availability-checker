# DJ Availability Checker — Complete System Reference

**Big Fun DJ | Last Updated: March 2026 | Paul Burchfield**

---

## 1. System Overview

The DJ Availability Checker is a booking and availability management system for Big Fun DJ, handling approximately 225 events annually. It bridges three independent data sources and provides multiple interfaces for checking availability, managing bookings, and tracking leads.

### Data Sources

| System | Details | Purpose |
|--------|---------|---------|
| **Availability Matrix** | Google Sheets `1lXwHECkQJy7h87L5oKbo0hDTpalDgKFTbBQJ4pIerFo` — Tabs: 2025, 2026, 2027 | DJ scheduling status, bold/plain OUT formatting, TBA bookings, AAG holds |
| **Gig Database** | FileMaker Pro via JSON API at `https://database.bigfundj.com/bigfunadmin/` — Single-day + multi-day endpoints | Contract-level details: client names, venues, financial records, confirmed bookings |
| **Inquiry Tracker** | Google Sheets `1ng-OytB9LJ8Fmfazju4cfFJRRa6bqfRIZA8GYEWhJRs` — Tab: Form Responses 1 | Lead tracking: who inquired, outcome (Booked, Full, Ghosted, etc.), conversion data |

---

## 2. Availability Checker (check_2026 / check_2027)

The primary tool used daily to check DJ availability. Available in three interfaces: terminal, desktop GUI, and web (Streamlit).

### Terminal Version

**Files:** `check_dj.py`, `check_2026.py`, `check_2027.py`
**Launch:** `python3 check_2026.py` or `python3 check_2027.py`
**Dependencies:** colorama, gspread, Google Sheets API, FileMaker JSON endpoints

#### Menu Options

| # | Option | Description |
|---|--------|-------------|
| 1 | Check specific date | Single date lookup with DJ statuses, venue info, nearby bookings, inquiry history. Copies date to clipboard in MM-DD-YY format. |
| 2 | Query date range | Bulk availability across a date range with optional day-of-week filter (Saturday/Sunday/Weekend/Weekday). |
| 3 | Find dates with min. availability | Find dates with N or more available spots in a range. |
| 4 | Check DJ availability in range | Show a specific DJ's status across a date range. |
| 5 | List fully booked dates | Find all dates with zero availability in a range. |
| 6 | Turned-away inquiries | Search inquiry tracker for leads turned away (resolution = Full) on a date. Color-coded by recency: green (REACH OUT, within 4 weeks), yellow (MAYBE, 5–10 weeks), gray (STALE, older). |
| 7 | Exit | |

### Desktop GUI Version

**Files:** `check_dj_gui.py`, `check_2026_gui.py`, `check_2027_gui.py`
**Launch:** `python3 check_2026_gui.py` or `python3 check_2027_gui.py`
**Dependencies:** pywebview (in addition to terminal deps)

Same functionality as terminal version in a desktop window with sidebar navigation. Panels: Single Date, Date Range, Min. Availability, DJ Availability, Fully Booked, Turned Away.

### Streamlit Web Version

**File:** `dj_app.py`
**URL:** `https://dj-availability-checker.streamlit.app`
**Launch locally:** `streamlit run dj_app.py`
**Auth:** Streamlit secrets (`gcp_service_account` in `secrets.toml` / Cloud dashboard)

Browser-based version for team access (primarily for company owners). Same 6 tabs as terminal options. Uses `init_google_sheets_from_dict()` with Streamlit secrets instead of local credentials file. Keep-alive via GitHub Actions cron (every 5 min) + UptimeRobot.

---

## 3. Gig Booking Manager

Automates availability matrix and calendar updates when a new booking is confirmed in FileMaker.

**Files:** `gig_booking_manager.py`, `gig_booking_manager.scpt`
**Trigger:** Stream Deck button runs `dj-checker-button gig_booking_manager.scpt` (see Stream Deck Buttons)
**Flags:** `--dry-run` (validate only) | `--test` (calendar invites to paul@bigfundj.com) | `--credentials PATH`

### Workflow

1. AppleScript extracts booking data from FileMaker page open in Safari via JavaScript, writes JSON to `/tmp/gig_booking.json`.
2. Python script runs in three phases: **Validate** (check matrix cell + calendar conflicts) → **Update Matrix** (write BOOKED, optionally assign backup via AppleScript dialog) → **Create Calendar Events** (primary + backup).
3. Opens Google Form pre-filled with booking metadata (event date, venue, decision date = today, status = Booked).

### Input Format (FileMaker JSON)

| Field | Description |
|-------|-------------|
| `FMeventDate` | Event date (MM/DD/YYYY) |
| `FMstartTime` / `FMendTime` | Start/end times (24-hour format) |
| `FMclient` | Client name |
| `FMvenue` | Venue name |
| `FMvenueAddress` | Street\*\*\*unused\*\*\*City, State ZIP (splits on \*\*\*) |
| `FMDJ1` / `FMDJ2` | Primary DJ full name / Secondary DJ (for unassigned bookings) |
| `FMsound` | Sound package type (Ceremony or Standard Speakers) |
| `FMcersound` | Has ceremony sound: 1 = true, 0 = false |
| `MailCoordinator` | Planner/coordinator name |

Also supports clean test format (`event_date` as YYYY-MM-DD, `assigned_dj` as first name, etc.). Auto-detected by presence of `FMclient` field.

### Calendar Events

Booking events are titled `[DJ_INITIALS] Client Name` (e.g., `[PB] Smith Wedding`). Backup events are titled `[WD] BACKUP DJ` or `[WD] PAID BACKUP DJ`. Created in the **Gigs** calendar on macOS.

### Backup DJ Assignment

After writing BOOKED to the matrix, the script checks if a backup is needed and shows an AppleScript dialog listing eligible DJs with venue context. Skip moves to next step. Cancel stops the script. Selecting a DJ writes BACKUP to their cell and creates a backup calendar event.

---

## 3b. Assign DJ

Moves a booking that Paul has just assigned in FileMaker from TBA to the DJ in the other two systems. Built 2026-11-01 for the 2027 assignment round; `assign_dj.py` plus `tests/test_assign_dj.py` (33 tests).

**Files:** `assign_dj.py`, `assign_dj.scpt` (source `assign_dj.applescript`)
**Trigger:** Stream Deck button runs `dj-checker-button assign_dj.scpt` with the FileMaker record open in Safari
**Flags:** `--dry-run` (validate against the live matrix and calendar, write nothing) | `--test` (real writes, calendar invite to paul@bigfundj.com) | `--credentials PATH`

### Workflow

1. **By hand in FileMaker first:** DJ1 set to the DJ, DJ2 cleared, a dated line in the notes, record saved. (Mirrors how a new booking is entered before Book Event.)
2. Press the button. The AppleScript is the booking manager's with different paths: it writes `/tmp/gig_assign.json` and calls `assign_dj.py`, logging to `/tmp/bigfun-assign-dj.log`.
3. **Validate:** DJ1 is set; the date row exists; the TBA cell holds a BOOKED; the Gigs calendar has a `[U?]` event whose title contains the client name (`[UP]`, `[UH]`, `[UW]`: U plus the booker's initial). The DJ's own cell must not hold `BACKUP` (alone or `DAD, BACKUP`): the date's backup is never rewritten to BOOKED by a script (Paul 2026-11-01); move the backup first. Both or neither: nothing is written unless both checks pass, and each failure names what it saw. A second press on a finished assignment is a no-op.
4. **Matrix:** TBA steps down one (`BOOKED x 2` -> `BOOKED` -> blank, `AAG` kept). The DJ's cell becomes `BOOKED` whatever it held (an OK in anyone's cell is overwritten, Paul 2026-11-01), or `BOOKED x 2` if they already have one that day.
5. **Calendar:** the bracket in the title becomes the DJ's initials, the rest of the title (Setup, planner) is untouched, and the DJ's BIG FUN address is added as an attendee, which sends the invite. The event is found and changed through Calendar.app by uid, the same AppleScript path Book Event uses, because CalDAV writes cannot carry attendees.
6. **Backup:** Book Event skips its backup dialog for an unassigned booking, so a TBA event never had one. The same dialog runs here after the assignment: candidates from the year's backup-eligible list minus the DJ just assigned, filtered by the Book Event `can_backup` rules (Woody's bold-OUT check included); a date that already has a backup is reported, not changed. A pick gets the calendar conflict check, then `BACKUP` in the Matrix (`DAD` and the other default markers replaced, anything else kept with `, BACKUP` appended), then the all-day `[XX] BACKUP DJ` / `PAID BACKUP DJ` event with the invite (`--test` sends it to Paul). Skip, Cancel, a conflict, or an unreadable calendar leaves the assignment in place with no backup; if the Matrix write succeeds and the event fails, the dialog says to create the event by hand. A dry run lists the candidates and shows no dialog.

7. **Paul only:** the booking email folder on love2tap, `BIG FUN/2027/MM-DD-YY: First and First (planner)`, through Book Event's `create_email_folder`. The log and the final dialog say whether it was created, already existed, or has to be made by hand; a folder failure never undoes the assignment.

Not done here: the couple's reply and the DJ handoff email. A joint unassigned bracket (`[UP/SB]`) is refused, not guessed.

### Sample

`sample_bookings/sample_assign_dj.json` is a clean-format record for a dry run; change the date, DJ and client to a real unassigned booking.

---

## 4. Cancel Booking

Reverses a booking: clears the matrix, deletes calendar events, optionally removes backup, logs to Google Form.

**Files:** `cancel_booking.py`, `cancel_booking.scpt`
**Trigger:** Stream Deck button runs `dj-checker-button cancel_booking.scpt` (see Stream Deck Buttons)
**Flags:** `--dry-run` | `--test` | `--credentials PATH`

**Calendar.app may be closed.** All three buttons edit the calendar through `calendar_app.py`, which launches Calendar.app hidden and waits for it to load. Nothing to do before pressing a button.

### 5-Step Process

1. Parse booking data (same JSON format as gig_booking_manager)
2. Connect to availability matrix
3. Validate DJ is marked BOOKED, RESERVED, or WEDFAIRE on that date
4. Update matrix: restore DJ's default cell value, optionally remove backup DJ
5. Clean up calendar: delete booking event and optionally backup event, open Google Form with Canceled status

### Default Cell Values

When clearing a BOOKED cell, the script restores the DJ's default value based on their name and day of week (since writing BOOKED overwrote any formula that was there):

| DJ | Weekdays (Mon–Fri) | Weekends (Sat–Sun) |
|----|--------------------|--------------------|
| Woody | (blank) | OUT |
| Stefano | OUT | Saturday: (blank), Sunday: OUT |
| Felipe | OUT | (blank) |
| Henry, Paul, Stephanie | (blank) | (blank) |

### Inquiry Tracker Convention

For cancellations, set the Inquiry Date and Decision Date to the same value (today). This mirrors the convention used when a date is full at initial contact — no decision period to track. The distinction is clear from the Resolution field: Full vs. Canceled.

A cancellation is therefore two rows on the same (Event Date, Venue) key: the original Booked row and a later Canceled row. Readers pair them with `dj_core.net_tracker_rows()`: each Canceled row timestamped after the earliest Booked row cancels one Booked row (newest Booked rows kept, so a re-booking after a cancel still stands); when every booking is cancelled the newest Canceled row stands. `get_venue_inquiries_for_date()` and the 2027 assignment script (`~/EA/projects/dj-capacity-2027/assign_2027.py`) read the tracker through it; the dashboard's `dedupe_inquiries()` applies the same rule in pandas. Added 2026-11-03.

---

## 5. Backup DJ Tools

### Backup Assigner

**File:** `backup_assigner.py`
**Launch:** `python3 backup_assigner.py --year 2026`
**Flags:** `--year` (required) | `--dry-run`

Scans the matrix for future dates with bookings but no backup DJ assigned. For each, shows an AppleScript dialog with eligible DJs and venue context (fetched from gig database JSON endpoint). Cancel button stops the entire operation. Skip moves to next date. Selecting a DJ writes BACKUP and creates a calendar event.

### Backup Stats

**File:** `backup_stats.py`
**Launch:** `python3 backup_stats.py --year 2026`

Counts how many times each DJ is assigned as BACKUP in the availability matrix for a given year. Shows summary with counts and specific dates.

---

## 6. Other Tools

### Booking Comparator

**File:** `booking_comparator.py`
**Launch:** `python3 booking_comparator.py --year 2026 [--no-calendar] [--output report.txt] [--accepted accepted.txt]`

Cross-checks three systems (Gig Database, Availability Matrix, Master Calendar) to identify discrepancies. Reads the calendar over CalDAV (`calendar_read.py`). Outputs a text report file. `--accepted` names a hand-written list of discrepancies to list but not count (format in the file header and in `parse_accepted`; Paul's copy lives at `~/EA/loops/systems-crosscheck/accepted.txt`). Calendar backups by people with no Matrix column (Alan Do, `[AD]`) are listed, not compared.

### Confirmation Forwarder

**File:** `confirmation_forwarder.py`
**Launch:** `python3 confirmation_forwarder.py /tmp/gig_booking.json`

After booking confirmation is sent to a couple, creates pre-filled forward drafts in MailMaven for the office (confirmations@bigfundj.com, CC: Henry & Woody) and the assigned DJ.

### Potential Availability Triage

**File:** `potential_availability.py`
**Launch:** `python3 potential_availability.py`

Read-only triage of open inquiries. Reads every thread in the IMAP folder `BIG FUN/Sales/Potential` (love2tap, on Fastmail), pulls the event date and venue from each subject line, checks each date against the availability matrix, and prints + saves a sorted report. Saves a markdown copy to `~/Downloads/YYYY-MM-DD-potential-availability.md`.

Subject parsing: primary format `(DOW MM-DD-YY Venue) ...` yields date + venue; a loose-date fallback (e.g. `8/7/2026`) catches corporate subjects with no venue; subjects with no parseable date are listed separately for manual check. Each resolved date reports spots open / FULL, DJs free to book, DJs free for backup, and booked/TBA/AAG counts. Dates not seeded in the matrix (matrix is seeded Fri-Mon, other dates added as needed) are flagged "not seeded in matrix." Loads each year's tab in a single API call. Uses the Keychain IMAP app password (`bigfun-imap` / `paul`, IMAP-only access, read-only here) and `your-credentials.json`.

---

## 7. Core Module (dj_core.py)

Shared business logic imported by all other scripts. Single source of truth for DJ rules, column mappings, availability logic, and API connections.

### Key Constants

| Constant | Value/Purpose |
|----------|---------------|
| `COLUMNS_2026` | D=Henry, E=Woody, F=Paul, G=Stefano, H=Felipe, I=TBA, K=Stephanie, L=AAG |
| `COLUMNS_2027` | D=Henry, E=Woody, F=Paul, G=Stefano, H=Stephanie, I=TBA, J=AAG, L=Felipe |
| `KNOWN_CELL_VALUES` | booked, backup, out, maxed, reserved, stanford, ok, ok to backup, dad, last, aag |
| `BACKUP_ELIGIBLE_DJS` | DJs who can be assigned as backup |
| `PAID_BACKUP_DJS` / `UNPAID_BACKUP_DJS` | Determines calendar event title: PAID BACKUP DJ vs BACKUP DJ |

### Key Functions

| Function | Purpose |
|----------|---------|
| `init_google_sheets_from_file()` | Auth with local credentials JSON |
| `init_google_sheets_from_dict()` | Auth with Streamlit secrets dict |
| `check_dj_availability()` | Core rule engine for a single DJ on a date |
| `get_date_availability_data()` | Single-date lookup (values + formatting) |
| `get_bulk_availability_data()` | Range lookup (2 API calls for all data) |
| `get_fully_booked_dates()` | Filter for zero-availability dates |
| `get_gig_database_bookings()` | FileMaker single-day query |
| `get_gig_database_bookings_multiday()` | FileMaker ±3 days query |
| `get_venue_inquiries_for_date()` | All inquiry history for a date |
| `net_tracker_rows()` | Pairs a Booked row with its later Canceled row (see Inquiry Tracker Convention) |
| `get_full_inquiries_for_date()` | Turned-away (Full) inquiries with recency tiers |
| `get_nearby_bookings_for_dj()` | DJ's bookings within ±3 days |
| `auto_clear_stale_cache()` | Clears gig DB cache after 60 minutes |

### Known Matrix Cell Values

| Value | Meaning | Counts as Booked? |
|-------|---------|-------------------|
| BOOKED | Confirmed paid event | Yes |
| WEDFAIRE | Wedding fair or expo (not a paid event, but equipment is deployed and entered in Gig DB) | Yes |
| BACKUP | Assigned as backup DJ for another DJ's event | No (backup slot) |
| RESERVED | Date held/reserved (e.g., Stephanie) | Yes |
| STANFORD | Stanford event (treated as booked) | Yes |
| AAG | Allied Arts Guild event | Yes |
| OUT | Unavailable (bold vs plain matters for some DJs) | No |
| MAXED | Hit scheduling cap (e.g., Stefano 2/month) | No |
| OK | Available (Felipe-specific, also general) | No |
| OK TO BACKUP | Available for backup only (Felipe-specific) | No |
| DAD | Personal/family (Felipe-specific, available for backup) | No |
| LAST | Available but assign last | No |
| (blank) | Meaning varies by DJ and day of week | No |

### DJ Availability Rules

Each DJ has unique rules for determining availability based on cell value, bold formatting, and day of week:

| DJ | Available to Book | Available to Backup |
|----|-------------------|---------------------|
| **Paul** | Blank = yes, OUT = no | Blank = yes |
| **Henry** | Weekend blank = yes, Weekday blank = no (day job) | Any blank = yes |
| **Woody** | Blank = yes, Weekend OUT (plain) = no | Blank = yes, Weekend OUT (plain) = yes, Weekend OUT (bold) = no, Weekday OUT = no |
| **Stefano** | Max 2/month. Blank = MAYBE (not counted) | Blank = MAYBE |
| **Felipe** | OK = yes, Blank/DAD/OK TO BACKUP = no | Blank/OK/DAD/OK TO BACKUP = yes |
| **Stephanie** | 2026 and 2027: explicit only (OK = yes, blank = no, any day). Paul 2026-10-17: out for 2027 except dates she has said yes to. | Same: OK = yes, blank = no |

---

## 8. Deployment & Configuration

### Local Setup

1. Clone the repository from GitHub (`paulbii/dj-availability-checker`).
2. Install Python dependencies: `pip install gspread oauth2client colorama pywebview streamlit requests`
3. Place `your-credentials.json` (Google service account) in the project directory. This file grants access to the Availability Matrix and Inquiry Tracker spreadsheets only.
4. For Streamlit local dev, create `.streamlit/secrets.toml` with `[gcp_service_account]` section containing the same credentials.

### Streamlit Cloud

Auto-deploys from the main branch on GitHub. Secrets are configured in the Streamlit Cloud dashboard under the app's settings. The keep-alive workflow (`.github/workflows/keep-alive.yml`) pings the app every 5 minutes via GitHub Actions cron. UptimeRobot also monitors the URL as a more reliable backup.

### Shipping an availability-rule change

Rules live in `dj_core.py` only (`check_dj_availability` for yes/no, `dj_status` for wording and color, `dj_range_bucket` for the per-DJ range query). The three front ends paint `DJStatus` and `tests/test_no_dj_rules_in_front_ends.py` fails if one of them branches on a DJ name again.

The desktop apps are frozen PyInstaller bundles and do not see source edits. Each carries `Contents/Resources/source-stamp.txt`, a hash of `dj_core.py` + `check_dj_gui.py` (`scripts/source_stamp.sh`). The pre-commit hook (`scripts/check_frozen_apps.sh`) refuses a commit that stages either file unless the installed apps already carry that hash.

So the one path is: edit, `git add` by name, `./release.sh "message"`. It runs the tests, rebuilds and installs both apps, commits, and pushes (Streamlit Cloud redeploys from `main`). On a machine without the apps: `SKIP_FROZEN_CHECK=1 git commit`.

### Stream Deck Buttons

| Button | Command (Run Shell Command) |
|--------|---------|
| Book Event | `/Users/paulburchfield/bin/dj-checker-button gig_booking_manager.scpt` |
| Cancel Booking | `/Users/paulburchfield/bin/dj-checker-button cancel_booking.scpt` |
| Assign DJ | `/Users/paulburchfield/bin/dj-checker-button assign_dj.scpt` |
| Stefano Enforcer | `/Users/paulburchfield/bin/dj-checker-button stefano_maxed_enforcer.scpt` |
| Nestldown Roster | `/Users/paulburchfield/bin/dj-checker-button run_nestldown_roster.scpt` |
| Potential Availability | `/Users/paulburchfield/bin/dj-checker-button potential_availability.scpt` |
| DJ Assignments page | `/Users/paulburchfield/bin/dj-checker-button publish_assignments_page.scpt` (rebuilds and uploads bigfundj.com/CLIENTS/assignments/2027/; the Python lives in `~/EA/projects/dj-capacity-2027`) |

**Why a launcher (2026-09-19).** This repo is under `~/Documents`, which iCloud evicts, sometimes within minutes. Stream Deck starts processes with iCloud downloading turned off, so an evicted file fails instead of downloading: `script error -36` for a `.scpt`, `[Errno 11] Resource deadlock avoided` for a `.py`. `~/bin/dj-checker-button` sits outside iCloud, turns downloading on, then runs `osascript <script>`; everything it spawns inherits the setting. Running a `.scpt` straight from Stream Deck (Run AppleScript, or `osascript ...` as a shell command) skips that and will fail whenever the file has gone cold. From Terminal, plain `osascript <script>` is fine.

**The venv is outside iCloud for the same reason**, at `~/.local/share/dj-availability-checker/venv`; `.venv` in the repo is a symlink to it, so every `.venv/bin/python` path still works. macOS never downloads an evicted binary on exec, so a venv inside iCloud cannot be made reliable. To rebuild: create the venv at that path, reinstall, keep the symlink.

The Book Event, Cancel Booking and Assign DJ AppleScripts accept `--dry-run` and `--test` flags as arguments.

### Key File Paths

| Item | Path |
|------|------|
| Project directory | `~/Documents/projects/dj-availability-checker/` |
| Credentials | `~/Documents/projects/dj-availability-checker/your-credentials.json` |
| Python binary | `/Users/paulburchfield/miniconda3/bin/python3` |
| Venv | `~/.local/share/dj-availability-checker/venv` (repo `.venv` is a symlink) |
| Temp booking JSON | `/tmp/gig_booking.json` |
| Temp assignment JSON | `/tmp/gig_assign.json` (Assign DJ) |
| Sample bookings | `sample_bookings/` directory (test JSON files) |

---

## 9. Date Format Reference

| Context | Format | Example |
|---------|--------|---------|
| Matrix dates (cell A column) | Day M/D | Sat 1/3 |
| FileMaker request URL | M/D/YYYY | 1/3/2026 |
| FileMaker response | YYYY-MM-DD | 2026-01-03 |
| Inquiry tracker dates | Various: m/d/yyyy, m/d/yy | 1/3/2026 or 1/3/26 |
| Clipboard copy | MM-DD-YY | 01-03-26 |
| Calendar event titles | [INITIALS] Client Name | [PB] Smith Wedding |
| User input (check scripts) | MM-DD or M-DD | 07-11 or 7-11 |

---

## 10. Complete File Inventory

| File | Purpose |
|------|---------|
| **dj_core.py** | Shared business logic, rules, API connections |
| **check_dj.py** | Terminal availability checker (shared module) |
| check_2026.py / check_2027.py | Year-specific terminal wrappers |
| **check_dj_gui.py** | PyWebView desktop GUI checker |
| check_2026_gui.py / check_2027_gui.py | Year-specific GUI wrappers |
| **dj_app.py** | Streamlit web interface |
| **gig_booking_manager.py** | Booking automation (matrix + calendar + form) |
| gig_booking_manager.scpt | AppleScript trigger for booking manager |
| **cancel_booking.py** | Booking cancellation (reverse of booking manager) |
| cancel_booking.scpt | AppleScript trigger for cancellation |
| calendar_read.py | CalDAV reads: day listings as (uid, title) |
| **calendar_app.py** | Calendar.app writes for the buttons: launch guard, delete / retitle / create by `event id` |
| test_calendar_app.py | Tests for calendar_app |
| **assign_dj.py** | Move a TBA booking to the DJ Paul set in FileMaker (matrix + calendar) |
| assign_dj.scpt / assign_dj.applescript | AppleScript trigger for Assign DJ, and its source |
| **backup_assigner.py** | Bulk backup DJ assignment with venue context |
| backup_stats.py | Backup assignment counts per DJ per year |
| **booking_comparator.py** | Cross-system discrepancy checker |
| confirmation_forwarder.py | Email forward drafts via MailMaven |
| **potential_availability.py** | Triage availability for open inquiries (Sales/Potential folder) |
| potential_availability.scpt | AppleScript trigger for potential availability triage |
| your-credentials.json | Google service account credentials (gitignored) |
| sample_bookings/ | Test JSON files for dry-run testing |
