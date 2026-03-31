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
**Trigger:** Stream Deck button runs `osascript gig_booking_manager.scpt`
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

## 4. Cancel Booking

Reverses a booking: clears the matrix, deletes calendar events, optionally removes backup, logs to Google Form.

**Files:** `cancel_booking.py`, `cancel_booking.scpt`
**Trigger:** Stream Deck button runs `osascript cancel_booking.scpt`
**Flags:** `--dry-run` | `--test` | `--credentials PATH`

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
**Launch:** `python3 booking_comparator.py --year 2026 [--no-calendar] [--output report.txt]`

Cross-checks three systems (Gig Database, Availability Matrix, Master Calendar) to identify discrepancies. Uses icalBuddy for macOS calendar access. Outputs a text report file.

### Confirmation Forwarder

**File:** `confirmation_forwarder.py`
**Launch:** `python3 confirmation_forwarder.py /tmp/gig_booking.json`

After booking confirmation is sent to a couple, creates pre-filled forward drafts in MailMaven for the office (confirmations@bigfundj.com, CC: Henry & Woody) and the assigned DJ.

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
| **Stephanie** | 2026: explicit only. 2027+: weekend blank = yes | Per year rules |

---

## 8. Deployment & Configuration

### Local Setup

1. Clone the repository from GitHub (`paulbii/dj-availability-checker`).
2. Install Python dependencies: `pip install gspread oauth2client colorama pywebview streamlit requests`
3. Place `your-credentials.json` (Google service account) in the project directory. This file grants access to the Availability Matrix and Inquiry Tracker spreadsheets only.
4. For Streamlit local dev, create `.streamlit/secrets.toml` with `[gcp_service_account]` section containing the same credentials.

### Streamlit Cloud

Auto-deploys from the main branch on GitHub. Secrets are configured in the Streamlit Cloud dashboard under the app's settings. The keep-alive workflow (`.github/workflows/keep-alive.yml`) pings the app every 5 minutes via GitHub Actions cron. UptimeRobot also monitors the URL as a more reliable backup.

### Stream Deck Buttons

| Button | Command |
|--------|---------|
| Book Event | `osascript ~/Documents/projects/dj-availability-checker/gig_booking_manager.scpt` |
| Cancel Booking | `osascript ~/Documents/projects/dj-availability-checker/cancel_booking.scpt` |

Both AppleScripts accept `--dry-run` and `--test` flags as arguments.

### Key File Paths

| Item | Path |
|------|------|
| Project directory | `~/Documents/projects/dj-availability-checker/` |
| Credentials | `~/Documents/projects/dj-availability-checker/your-credentials.json` |
| Python binary | `/Users/paulburchfield/miniconda3/bin/python3` |
| Temp booking JSON | `/tmp/gig_booking.json` |
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
| **backup_assigner.py** | Bulk backup DJ assignment with venue context |
| backup_stats.py | Backup assignment counts per DJ per year |
| **booking_comparator.py** | Cross-system discrepancy checker |
| confirmation_forwarder.py | Email forward drafts via MailMaven |
| your-credentials.json | Google service account credentials (gitignored) |
| sample_bookings/ | Test JSON files for dry-run testing |
