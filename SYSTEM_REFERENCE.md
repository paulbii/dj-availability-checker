# Big Fun DJ — Availability Checker System Reference

> **Purpose:** Complete technical and business reference for the DJ availability checker system. Use this document as context when building new tools, debugging, or onboarding anyone (human or AI) to work with this codebase.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture & Data Flow](#architecture--data-flow)
3. [Data Sources](#data-sources)
4. [Code Structure](#code-structure)
5. [DJ Availability Rules](#dj-availability-rules)
6. [Availability Calculation](#availability-calculation)
7. [API Reference](#api-reference)
8. [Google Sheets Structure](#google-sheets-structure)
9. [Business Process Context](#business-process-context)
10. [Edge Cases & Gotchas](#edge-cases--gotchas)
11. [Performance & Caching](#performance--caching)
12. [Deployment](#deployment)

---

## System Overview

The DJ Availability Checker helps Paul manage booking operations for Big Fun DJ, a wedding and event DJ service. It answers the core question: **"For a given date, who is available and how many spots are open?"**

There are two interfaces:

- **Terminal app** (`check_2026.py`, `check_2027.py`) — Paul's primary daily tool. Left running in a terminal window. Supports single-date lookups, date range queries, DJ-specific queries, and fully-booked-date reports.
- **Streamlit web app** (`dj_app.py`) — Deployed on Streamlit Cloud for team access. Provides the same core functionality with a browser-based UI.

Both interfaces share business logic through `dj_core.py`.

---

## Architecture & Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Google Sheets   │     │  FileMaker Pro    │     │  Google Sheets      │
│  Availability    │     │  Gig Database     │     │  "Didn't Book"      │
│  Matrix          │     │  (bigfundj.com)   │     │  Inquiries Tracker  │
│                  │     │                   │     │                     │
│  - DJ status     │     │  - Confirmed gigs │     │  - Lead tracking    │
│  - Bold/plain    │     │  - Venues         │     │  - Resolution       │
│  - AAG holds     │     │  - Client names   │     │  - Venue names      │
│  - TBA bookings  │     │  - Assigned DJs   │     │                     │
└────────┬─────────┘     └────────┬──────────┘     └──────────┬──────────┘
         │                        │                            │
         │  Google Sheets API     │  HTTP JSON API             │  Google Sheets API
         │  (2 calls: values +    │  (1 call per date or       │  (1 call: all records)
         │   formatting)          │   1 call for ±3 days)      │
         │                        │                            │
         └────────────┬───────────┴────────────┬───────────────┘
                      │                        │
                      ▼                        ▼
              ┌───────────────┐      ┌──────────────────┐
              │  dj_core.py   │      │  check_2026.py   │
              │  (shared      │◄─────│  check_2027.py   │
              │   logic)      │      │  dj_app.py       │
              └───────────────┘      └──────────────────┘
```

**For a single-date lookup (Option 1), the system:**

1. Fetches the row from Google Sheets (values + bold formatting) — 2 API calls
2. Applies DJ availability rules to determine who can book/backup
3. Queries FileMaker gig database for confirmed booking details — 1 API call
4. Queries FileMaker MD endpoint for nearby bookings (±3 days) — 1 API call
5. Queries inquiries spreadsheet for lead history on that date — 1 API call

**For range queries (Options 2-5), the system:**

1. Bulk-fetches the entire date range from Google Sheets — 2 API calls total
2. Processes all dates locally in memory
3. Only queries FileMaker for specific needs (e.g., venue names for booked dates)

---

## Data Sources

### 1. Availability Matrix (Google Sheets)

The primary source of truth for DJ scheduling.

- **Spreadsheet ID:** `1lXwHECkQJy7h87L5oKbo0hDTpalDgKFTbBQJ4pIerFo`
- **Tabs:** One per year (`2025`, `2026`, `2027`)
- **Structure:** Each row is a date, columns are DJs + TBA + AAG
- **Updated by:** Paul manually
- **Authentication:** Service account via `your-credentials.json`

**Key detail:** Cell formatting (bold vs. plain) matters for some rules (specifically Woody's OUT status). The system must fetch both values AND formatting data, which requires the Google Sheets API v4 service (not just gspread).

### 2. Gig Database (FileMaker Pro)

The confirmed booking database — shows what's actually contracted.

- **Base URL:** `https://database.bigfundj.com/bigfunadmin/`
- **Single-day endpoint:** `availabilityjson.php?date=M/D/YYYY`
- **Multi-day endpoint:** `availabilityMDjson.php?date=M/D/YYYY` (returns ±3 days)
- **Authentication:** None required (internal network)
- **Maintained by:** Henry (built the FileMaker system and PHP endpoints)

### 3. Inquiries Tracker (Google Sheets — "Didn't Book")

Tracks all inbound leads and their outcomes.

- **Spreadsheet ID:** `1ng-OytB9LJ8Fmfazju4cfFJRRa6bqfRIZA8GYEWhJRs`
- **Sheet name:** `Form Responses 1`
- **Key columns:** Event Date, Venue (if known), Resolution, Decision Date
- **Resolution values:** `Booked`, `Didn't Book`, `We turn down`, `Ghosted`, etc.
- **Used for:** Showing inquiry history when checking a specific date

---

## Code Structure

```
dj-availability-checker/
├── dj_core.py          # Shared business logic (ALL rules live here)
│   ├── init_google_sheets_from_file()    # Auth & connection
│   ├── check_dj_availability()           # Core rule engine
│   ├── analyze_availability()            # Aggregate availability for a date
│   ├── get_date_availability_data()      # Single-date lookup
│   ├── get_bulk_availability_data()      # Range lookup (2 API calls)
│   ├── get_fully_booked_dates()          # Filter for zero-availability dates
│   ├── get_gig_database_bookings()       # FileMaker single-day query
│   ├── get_gig_database_bookings_multiday()  # FileMaker ±3 days query
│   ├── get_nearby_bookings_for_dj()      # DJ's nearby bookings
│   ├── get_venue_inquiries_for_date()    # Lead history lookup
│   └── auto_clear_stale_cache()          # Cache management
│
├── check_2026.py       # Terminal interface for 2026
│   ├── Option 1: Check specific date
│   ├── Option 2: Query date range
│   ├── Option 3: Find dates with minimum availability
│   ├── Option 4: Check DJ availability in range
│   ├── Option 5: List fully booked dates
│   └── Option 6: Exit
│
├── check_2027.py       # Terminal interface for 2027 (same structure)
├── dj_app.py           # Streamlit web interface
│
├── booking_comparator.py  # Cross-checks 3 booking systems for discrepancies
│   ├── Reads gig database from text file (raw or reformatted format)
│   ├── Pulls availability matrix LIVE from Google Sheets
│   ├── Pulls master calendar LIVE via icalBuddy (macOS)
│   ├── Compares bookings + backup DJs across all three
│   └── Saves report to "MM-DD-YYYY - Systems crosscheck.txt"
│
├── confirmation_forwarder.py  # Forwards booking confirmations via MailMaven
│   ├── Reads new-booking JSON from gig database
│   ├── Creates forward drafts to DJ and/or office
│   ├── Handles DJ email (consult month, template text)
│   └── Handles office email (client name, CC addresses)
│
├── test_confirmation_forwarder.py  # 62 tests for confirmation_forwarder
├── gig_db.txt             # Gig database export for booking_comparator
│
├── your-credentials.json   # Google service account credentials
├── .streamlit/
│   └── secrets.toml    # Credentials for Streamlit (local & cloud)
├── requirements.txt
├── docs/
│   └── FULLY_BOOKED_FEATURE.md
└── README.md
```

**Key principle:** All business rules live in `dj_core.py`. The year-specific scripts (`check_2026.py`, etc.) handle UI/display only. If a rule changes, you change it in one place.

---

## Booking Comparator (`booking_comparator.py`)

Cross-checks three booking systems to surface discrepancies that need manual attention.

### Data Sources

| System | Source | How It's Read |
|---|---|---|
| Gig Database | Text file export from FileMaker | You paste/export to `gig_db.txt` |
| Availability Matrix | Google Sheets | Pulled live via API (uses `dj_core.py`) |
| Master Calendar | macOS Calendar (Gigs) | Pulled live via `icalBuddy` |

### Usage

```
python3 booking_comparator.py --year 2026
python3 booking_comparator.py --year 2026 --no-calendar
python3 booking_comparator.py --year 2026 --output custom_name.txt
```

The report automatically saves to `MM-DD-YYYY - Systems crosscheck.txt` and also prints to the console.

### Gig Database Text File Format

The script accepts the raw FileMaker export format:

```
>	01-03-26 Sat  H	3:00	10:00		--C-A--	Client Name	Venue
```

Or the reformatted format:

```
01-03-26 — H — Client Name — Venue
```

### What It Checks

**Booking discrepancies:** Dates where the DJ lists don't match across systems. Categories include missing from matrix, missing from gig DB, DJ assignment mismatches, and missing from calendar.

**Backup DJ discrepancies:** Compares backup assignments between the matrix and calendar.

### Special Handling

- **RESERVED** entries in the matrix are skipped (held but not booked)
- **"Hold to DJ"** calendar events are skipped (the calendar equivalent of RESERVED)
- **Dual-DJ calendar events** like `[WM/HK]` are split into separate entries
- **BACKUP DJ** calendar events are tracked separately from bookings
- **TBA/Unassigned** bookings are normalized to "TBA" across all systems
- DJ codes: S=Stefano, SD=Stephanie, P=Paul, H=Henry, W=Woody, F=Felipe, FS=Felipe

### Prerequisites

- `icalBuddy` installed (`brew install ical-buddy`) — only needed for calendar comparison
- `your-credentials.json` for Google Sheets API access
- Calendar named "Gigs" in macOS Calendar with events prefixed by DJ initials in brackets (e.g., `[PB] Client Name`)

---

## Confirmation Forwarder (`confirmation_forwarder.py`)

Automates forwarding booking confirmation emails to DJs and/or the office via MailMaven (macOS mail client).

### Usage

Run from the dj-availability-checker folder after selecting a confirmation email in MailMaven:

```
python3 confirmation_forwarder.py
```

The script reads the booking JSON from the gig database, determines who to email, builds the appropriate template text, and creates forward drafts in MailMaven via AppleScript.

### What It Does

1. Reads the new-booking JSON (from FileMaker webhook or file)
2. Determines the assigned DJ and whether to send a DJ email, office email, or both
3. For the **DJ email**: includes consult month reminder, template greeting, and relevant booking details
4. For the **office email**: includes client name and CCs Henry and Woody when applicable
5. Creates forward drafts in MailMaven using AppleScript (Tab navigation to body, clipboard paste for template text)

### Special Handling

- Skips DJ email when DJ is "Unknown" or "Unassigned"
- Uses "next [Month]" phrasing when the consult month is in a future year
- Always includes client name in office email (handles double-booking edge case)
- CC addresses are entered via keystroke + Enter (not set value) to ensure they stick

---

## DJ Availability Rules

### General Cell Values

| Cell Value | Meaning |
|---|---|
| `BOOKED` | DJ is booked for an event |
| `BACKUP` | DJ is assigned as backup |
| `OUT` | Not available (exceptions below) |
| `MAXED` | Hit booking limit, not available |
| `RESERVED` | Spot held (typically AAG events) |
| `STANFORD` | DJ is booked for a Stanford event (treated as booked) |
| `OK` | Available (Felipe-specific) |
| `OK TO BACKUP` | Can be backup only |
| `DAD` | Felipe-specific — backup only |
| `[blank]` | Depends on DJ and year (see below) |

**Bold formatting matters** — specifically for Woody's OUT status.

### DJ-Specific Rules

#### Henry
| Day Type | Cell Value | Can Book | Can Backup |
|---|---|---|---|
| Weekend | blank | ✅ | ✅ |
| Weekend | OUT | ❌ | ❌ |
| Weekday | blank | ❌ | ✅ |
| Weekday | OUT | ❌ | ❌ |

**Why:** Henry has a day job; weekends only for events.

#### Woody
| Day Type | Cell Value | Bold? | Can Book | Can Backup |
|---|---|---|---|---|
| Any | blank | — | ✅ | ✅ |
| Weekend | OUT | No | ❌ | ✅ |
| Weekend | OUT | **Yes** | ❌ | ❌ |
| Weekday | OUT | Any | ❌ | ❌ |

**Why:** Woody prefers weekdays but helps on weekends. Bold OUT = hard commitment (family event, travel). Plain OUT = preference, can still backup if needed.

#### Paul
Standard rules. Blank = available. OUT = unavailable.

#### Stefano
| Cell Value | Can Book | Can Backup | Display |
|---|---|---|---|
| blank | ❌ | ❌ | `[MAYBE]` |
| BOOKED | ❌ | ❌ | — |
| OUT | ❌ | ❌ | — |

**Why:** Stefano prefers a maximum of two events per month. Blank doesn't mean available — it means he hasn't been asked. The system shows `[MAYBE]` so Paul knows to check with him directly. Stefano's blank cells do NOT count toward available spots automatically.

#### Felipe

**2025:** Standard rules. Blank = available.

**2026 & 2027:**
| Cell Value | Can Book | Can Backup |
|---|---|---|
| blank | ❌ | ✅ |
| OK | ✅ | ✅ |
| DAD | ❌ | ✅ |
| OK TO BACKUP | ❌ | ✅ |
| OUT | ❌ | ❌ |
| MAXED | ❌ | ❌ |

**Why:** Felipe transitioned to backup-only role in 2026. He's available for events only when explicitly marked "OK."

#### Stephanie

**2025:** Standard rules. Blank = available.

**2026:**
| Cell Value | Can Book | Can Backup |
|---|---|---|
| blank | ❌ | ❌ |
| RESERVED | ❌ | ❌ |
| BOOKED | ❌ | ❌ |

**Why:** In 2026, Stephanie only works explicitly assigned events (primarily AAG overflow). Not part of the regular rotation.

**2027:**
| Day Type | Cell Value | Can Book | Can Backup |
|---|---|---|---|
| Weekend | blank | ✅ | ✅ |
| Weekday | blank | ❌ | ❌ |
| Any | OUT | ❌ | ❌ |
| Any | RESERVED | ❌ | ❌ |

**Why:** Starting 2027, Stephanie joins as a regular weekend DJ but only works weekends.

### Backup Assignment Rules

1. **Every booked date needs a backup assigned.**
2. Preferred backup hierarchy:
   - Woody (weekends) — **unpaid**
   - Stefano — **paid**
   - Felipe — **paid**
3. The system shows "Available to Backup" only when no backup is already assigned (reduces noise).

---

## Availability Calculation

```
Available Spots = (DJs available for booking)
                  - (TBA unassigned bookings)
                  - (AAG RESERVED holds)
```

A date is **fully booked** when `Available Spots == 0`.

### TBA Column

Tracks unassigned bookings that consume spots:

| TBA Value | Spots Consumed |
|---|---|
| `BOOKED` | 1 |
| `BOOKED x 2` | 2 |
| `BOOKED x N` | N |
| `AAG` | 1 |
| `BOOKED, AAG` | 2 (comma-separated) |

### AAG Column (2026+)

| AAG Value | Effect |
|---|---|
| `RESERVED` | Reduces available spots by 1 |
| blank | No effect |

---

## API Reference

### FileMaker — Single Day

```
GET https://database.bigfundj.com/bigfunadmin/availabilityjson.php?date=2/24/2026
```

**Response:**
```json
[
  {
    "event_date": "2026-02-24",
    "venue_name": "Kohl Mansion",
    "client_name": "HCF Volunteer Summit",
    "assigned_dj": "Woody Miraglia"
  }
]
```

Returns bookings for that specific date only. Empty array `[]` if no bookings.

### FileMaker — Multi-Day (±3 days)

```
GET https://database.bigfundj.com/bigfunadmin/availabilityMDjson.php?date=2/24/2026
```

**Response:** Same format, but returns bookings from 2/21/2026 through 2/27/2026 inclusive.

```json
[
  {
    "event_date": "2026-02-21",
    "venue_name": "Kohl Mansion",
    "client_name": "Catherine MacDougall and Jacob Asmuth",
    "assigned_dj": "Paul Burchfield"
  },
  {
    "event_date": "2026-02-21",
    "venue_name": "Allied Arts Guild",
    "client_name": "Michael Yu and Li Sun",
    "assigned_dj": "Henry S. Kim"
  },
  {
    "event_date": "2026-02-24",
    "venue_name": "Kohl Mansion",
    "client_name": "HCF Volunteer Summit",
    "assigned_dj": "Woody Miraglia"
  }
]
```

**Date format in responses:** `YYYY-MM-DD`
**Date format in request URL:** `M/D/YYYY` (no leading zeros)

### DJ Name Mapping

The FileMaker API returns full names. The system maps to short names:

| API Value (first name) | Short Name |
|---|---|
| `henry` | Henry |
| `paul` | Paul |
| `stefano` | Stefano |
| `woody` | Woody |
| `felipe` | Felipe |
| `stephanie` | Stephanie |

If `assigned_dj` is `"Unassigned"`, the booking goes into the unassigned/TBA list.

### Google Sheets API

**Authentication:** OAuth2 service account with scopes:
- `spreadsheets.google.com/feeds`
- `googleapis.com/auth/spreadsheets`
- `googleapis.com/auth/drive.file`
- `googleapis.com/auth/drive`

**Rate limit:** 60 requests per minute. The bulk fetch approach (2 calls for an entire year) avoids this.

---

## Google Sheets Structure

### Availability Matrix

Each year tab has this general layout:

| Row | A (Date) | B | C | D (Henry) | E (Woody) | F (Paul) | G (Stefano) | H | I (TBA) | ... |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Sat 1/3 | | | | | BOOKED | | | | |
| 2 | Sun 1/4 | | | | OUT | | | | | |
| ... | | | | | | | | | | |

Columns B and C exist but aren't used by the checker. The specific column assignments vary by year (see column mappings below).

### Column Mappings

**2025:** A=Date, D=Henry, E=Woody, F=Paul, G=Stefano, H=Felipe, I=TBA, K=Stephanie

**2026:** A=Date, D=Henry, E=Woody, F=Paul, G=Stefano, H=Felipe, I=TBA, K=Stephanie, L=AAG

**2027:** A=Date, D=Henry, E=Woody, F=Paul, G=Stefano, H=Stephanie, I=TBA, J=AAG, L=Felipe

Note: In 2027, Stephanie moves to column H (Felipe's old spot) and Felipe moves to column L, reflecting the team restructure.

### Inquiries Tracker ("Didn't Book" Sheet)

| Column | Content |
|---|---|
| Event Date | Date of the event (various formats: `m/d/yyyy`, `mm/dd/yyyy`) |
| Venue (if known) | Venue name |
| Resolution | `Booked`, `Didn't Book`, `We turn down`, `Ghosted`, etc. |
| Decision Date | When the outcome was determined |

The system groups by venue and uses the most recent decision date when duplicates exist.

---

## Business Process Context

### Capacity Model

Big Fun DJ operates at roughly **2.0–2.2 events per peak Saturday**. The theoretical maximum is limited by the number of DJs available on any given date.

### Pricing

- **Peak season** (April–October Saturdays): $1,999–$2,299
- **Off-peak:** $1,399–$1,599
- **Overtime:** $125 per 30-minute increment beyond 4-hour base
- Plus equipment add-ons

### Lead Flow

1. Inquiry comes in (form, email, phone call)
2. Paul checks availability using this tool
3. Sales call happens
4. Booking confirmed → FileMaker + Availability Matrix updated
5. If date is full → couple is turned away or waitlisted

### Why Three Systems?

- **Availability Matrix (Google Sheets):** Quick visual overview, handles nuanced statuses (OUT, MAYBE, bold formatting) that FileMaker can't easily represent. Paul updates this as the single scheduling view.
- **Gig Database (FileMaker):** Contract-level detail — client names, venues, financial records. Source of truth for confirmed bookings.
- **Inquiries Tracker:** Separate from bookings. Tracks the funnel — who inquired, what happened, conversion data.

The availability checker bridges all three to give Paul a complete picture for any date.

### Allied Arts Guild (AAG)

Starting in 2027, Big Fun DJ has an exclusive arrangement with Allied Arts Guild. Saturdays are held with `RESERVED` status in the availability matrix. Stephanie primarily handles AAG overflow events.

---

## Edge Cases & Gotchas

### Bold vs. Plain Text

The Google Sheets API returns formatting separately from values. You must use the v4 API (`service.spreadsheets().get(includeGridData=True)`) to get bold status. The simpler gspread `.get()` only returns values.

Bold is detected via `effectiveFormat.textFormat.bold` or `textFormatRuns` (for partially bold cells). If a cell has `textFormatRuns`, the first run's bold status is used.

### Stefano Blank ≠ Available

This is the most common source of confusion. For every other DJ, blank = available. For Stefano, blank = unknown/maybe. The system handles this with a `[MAYBE]` qualifier and does NOT count Stefano toward available spots.

### TBA Bookings Consume Spots

When TBA shows `BOOKED`, it means a booking exists but no DJ has been assigned yet. This reduces available spots because one of the available DJs will need to be assigned to it.

### Year Boundary Dates

The nearby bookings check (±3 days) skips dates outside the current year. If you check January 1, it won't look at December 29–31 of the previous year.

### Date Formats Vary

- **Availability Matrix dates:** `"Sat 1/3"` format (day-of-week + M/D)
- **FileMaker request URL:** `M/D/YYYY` (no leading zeros)
- **FileMaker response dates:** `YYYY-MM-DD`
- **Inquiries sheet dates:** Various (`m/d/yyyy`, `mm/dd/yyyy`, `m/d/yy`)
- **Internal code format:** `MM-DD` for most functions

### Google Sheets Range Notation

When using `sheet.get()` via gspread, do NOT prefix with sheet name (e.g., use `"A1:L50"` not `"2026!A1:L50"`). When using the Sheets API v4 directly, you DO need the sheet name prefix.

### Cache Staleness

The gig database cache auto-clears after 60 minutes. Since Paul leaves the terminal script running all day, this prevents showing stale booking data. The cache timestamp is displayed in output (e.g., "Cached from 3:40 PM (12 min ago)").

Google Sheets data is never cached in the terminal version — it's fetched fresh each query.

### Rate Limits

Google Sheets API: 60 requests/minute. The bulk fetch approach (`get_bulk_availability_data()`) fetches an entire year in 2 calls. Before this optimization, range queries could make 60–120 calls and hit the limit.

---

## Performance & Caching

### Gig Database Cache

- Uses Python's `@lru_cache` with hour-based cache keys
- Auto-clears after 60 minutes via `auto_clear_stale_cache()`
- Can be manually cleared via `clear_gig_cache()`
- Cache info displayed in output for transparency

### Bulk Fetch (Range Queries)

For options 2–5, `get_bulk_availability_data()` fetches the entire date range in 2 API calls:

1. `sheet.get(range)` — all cell values
2. `service.spreadsheets().get(includeGridData=True)` — all formatting

All date processing happens locally. This replaced per-date fetching that was hitting rate limits.

### Multi-Day Endpoint

Henry's `availabilityMDjson.php` endpoint returns ±3 days in a single call, replacing 6 parallel calls to `availabilityjson.php`. This reduces FileMaker server load significantly.

---

## Deployment

### Terminal (Local)

```bash
cd ~/Documents/projects/dj-availability-checker
python check_2026.py
```

Requires: `your-credentials.json` in project root.

### Streamlit Cloud

Deployed from GitHub. Secrets stored in Streamlit Cloud dashboard (same values as `your-credentials.json` but in TOML format).

### Streamlit Local

```bash
streamlit run dj_app.py
```

Requires: `.streamlit/secrets.toml` (generated from `your-credentials.json`).

### Mac App Launcher

An Automator application that launches the Streamlit app locally and opens the browser:

```bash
cd /Users/paulburchfield/Documents/projects/dj-availability-checker
streamlit run dj_app.py &
sleep 2
open http://localhost:8501
```

---

*Last updated: January 2026*
