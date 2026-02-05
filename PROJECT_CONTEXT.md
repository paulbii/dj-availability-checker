# Big Fun DJ — Project Context

> **Purpose:** Comprehensive context for AI assistants working on this codebase. Contains business rules, system architecture, DJ roster, and operational knowledge.

---

## Table of Contents

1. [Business Overview](#business-overview)
2. [System Architecture](#system-architecture)
3. [DJ Roster & Rules](#dj-roster--rules)
4. [Data Sources](#data-sources)
5. [Key Files](#key-files)
6. [Credentials & Secrets](#credentials--secrets)
7. [Common Workflows](#common-workflows)
8. [Skills](#skills)
9. [Related Documentation](#related-documentation)

---

## Business Overview

**Big Fun DJ** is a wedding and event DJ company handling approximately 225 events annually. The business operates at roughly 2.0–2.2 events per peak Saturday.

### Pricing
- **Peak season** (April–October Saturdays): $1,999–$2,299
- **Off-peak:** $1,399–$1,599
- **Overtime:** $125 per 30-minute increment beyond 4-hour base

### Key Venues
Premium venues include Thomas Fogarty, Nestldown, and Kohl Mansion. Allied Arts Guild (AAG) has an exclusive arrangement starting 2027.

### Business Priorities
- Data accuracy is paramount — realistic projections over optimistic scenarios
- Multiple validation points to prevent booking conflicts
- Gig database is the single source of truth for confirmed bookings
- Availability matrix is the single source of truth for DJ scheduling

---

## System Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Availability       │     │  FileMaker Pro      │     │  Inquiry Tracker    │
│  Matrix (Sheets)    │     │  Gig Database       │     │  (Sheets)           │
│                     │     │                     │     │                     │
│  - DJ status        │     │  - Confirmed gigs   │     │  - Lead tracking    │
│  - Bold/plain OUT   │     │  - Venues/clients   │     │  - Resolutions      │
│  - AAG holds        │     │  - Assigned DJs     │     │  - Conversion data  │
│  - TBA bookings     │     │  - Event times      │     │                     │
└─────────┬───────────┘     └─────────┬───────────┘     └─────────┬───────────┘
          │                           │                           │
          └───────────────┬───────────┴───────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │      dj_core.py       │
              │   (shared logic)      │
              └───────────┬───────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
    ┌───────────┐   ┌───────────┐   ┌───────────┐
    │ check_dj  │   │  dj_app   │   │ dashboard │
    │ (terminal)│   │(Streamlit)│   │(Streamlit)│
    └───────────┘   └───────────┘   └───────────┘
```

### Tools

| Tool | Interface | Purpose |
|------|-----------|---------|
| Availability Checker | Terminal (`check_dj.py`) | Paul's daily lookup tool |
| Availability Checker | Streamlit (`dj_app.py`) | Team access via browser |
| Gig Booking Manager | Terminal/Stream Deck | Automates matrix + calendar after booking |
| Operations Dashboard | Streamlit (`dashboard.py`) | Read-only status board |

---

## DJ Roster & Rules

### Current Team (2026)

| DJ | Role | Availability Pattern |
|----|------|---------------------|
| **Paul** | Owner | Standard (blank = available, OUT = unavailable) |
| **Henry** | Weekend DJ | Weekends only for events; weekdays = backup only |
| **Woody** | Flexible | Prefers weekdays; plain OUT on weekend = can backup; **bold OUT** = fully unavailable |
| **Stefano** | Limited | Max 2 events/month; blank = MAYBE (must check); never auto-counted as available |
| **Felipe** | Backup-only (2026+) | Transitioned from regular DJ; blank = backup only; "OK" = can book |
| **Stephanie** | AAG overflow (2026) | Only works explicitly assigned events in 2026 |

### 2027 Changes

- **Stephanie** joins as regular weekend-only DJ (blank on weekend = available)
- **Felipe** remains backup-only
- **AAG column** added for Allied Arts Guild holds

### Availability Matrix Cell Values

| Value | Meaning |
|-------|---------|
| `BOOKED` | DJ has an event |
| `BACKUP` | DJ is assigned as backup |
| `OUT` | Not available (see bold rules for Woody) |
| `MAXED` | Hit booking limit |
| `RESERVED` | Spot held (typically AAG or specific DJ request) |
| `STANFORD` | Stanford event booking |
| `OK` | Felipe: available for events |
| `OK TO BACKUP` | Can backup only |
| `DAD` | Felipe: parenting duty, backup only |
| `LAST` | Available but low priority |
| `[blank]` | Depends on DJ and year (see rules above) |

### Backup Rules

1. Every booked date needs a backup assigned
2. Preferred hierarchy: Woody (unpaid) → Stefano (paid) → Felipe (paid)
3. Check for calendar conflicts before assigning

### Bold Formatting

**Bold matters only for Woody's OUT status:**
- Plain OUT on weekend = can backup
- **Bold OUT** = completely unavailable (family event, travel)

---

## Data Sources

### Availability Matrix (Google Sheets)
- **ID:** `1lXwHECkQJy7h87L5oKbo0hDTpalDgKFTbBQJ4pIerFo`
- **Tabs:** `2025`, `2026`, `2027`
- **Updated by:** Paul manually

### Gig Database (FileMaker Pro)
- **Base URL:** `https://database.bigfundj.com/bigfunadmin/`
- **Single-day:** `availabilityjson.php?date=M/D/YYYY`
- **Multi-day:** `availabilityMDjson.php?date=M/D/YYYY` (±3 days)
- **Maintained by:** Henry

### Inquiry Tracker (Google Sheets)
- **ID:** `1ng-OytB9LJ8Fmfazju4cfFJRRa6bqfRIZA8GYEWhJRs`
- **Tab used:** `Master View`
- **Resolution values:** `Booked`, `Didn't Book`, `We turn down`, `Cold`, `Ghosted`, `Canceled`

### Booking Snapshots (Google Sheets)
- **ID:** `1JV5S1hbtYcXhVoeqsYVw_nhUvRoOlSBt5BYZ0ffxFkU`
- **Used for:** YoY booking pace comparison

---

## Key Files

### Core Logic
- `dj_core.py` — All business rules, shared by all interfaces

### Terminal Tools
- `check_dj.py` — Main availability checker (runs as `check_2026.py`, `check_2027.py`)
- `gig_booking_manager.py` — Automates matrix updates + calendar creation

### Streamlit Apps
- `dj_app.py` — Availability checker web interface
- `dashboard.py` — Operations dashboard

### AppleScript
- `gig_booking_manager.scpt` — Extracts data from Safari, calls Python script

### Configuration
- `your-credentials.json` — Google service account (DO NOT COMMIT)
- `.streamlit/secrets.toml` — Streamlit secrets (DO NOT COMMIT)

---

## Credentials & Secrets

All credentials live in the project folder but are gitignored:

| File | Purpose |
|------|---------|
| `your-credentials.json` | Google Sheets API service account |
| `.streamlit/secrets.toml` | Streamlit Cloud secrets (local dev) |

Streamlit Cloud has secrets configured in the dashboard settings.

FileMaker URL is stored in `.streamlit/secrets.toml` under `[filemaker]`.

---

## Common Workflows

### Check Availability (Paul's Daily Use)
```bash
python check_2026.py
# or
python check_2027.py
```
Options: single date, date range, DJ-specific query, fully booked dates

### Book an Event (Stream Deck)
1. Open booking in Safari (FileMaker web)
2. Press Stream Deck button → runs `gig_booking_manager.scpt`
3. Script extracts data, validates, writes to matrix, creates calendar event
4. Backup dialog appears if applicable

### Deploy Streamlit Apps
Both apps deploy automatically from GitHub to Streamlit Cloud.

### Run Dashboard Locally
```bash
streamlit run dashboard.py
```

---

## Skills

### booking-parser
**Location:** `/mnt/skills/user/booking-parser/SKILL.md`

**Description:** Parse DJ booking records from database format (descending order with tabs) to simplified format (ascending order with dashes). Use when user uploads booking data that needs to be reformatted for cross-checking with calendar or spreadsheet systems.

### booking-comparator
**Location:** `/mnt/skills/user/booking-comparator/SKILL.md`

**Description:** Compare DJ booking records across three systems (Gig Database, Availability Matrix, Master Calendar) to identify discrepancies. Use when user uploads booking data from multiple systems that needs cross-checking for synchronization issues, missing events, or DJ assignment mismatches.

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| `SYSTEM_REFERENCE.md` | Deep dive on availability checker architecture |
| `GIG_TO_CALENDAR_REFERENCE.md` | Calendar automation logic and field mappings |
| `DASHBOARD_REFERENCE.md` | Dashboard dedup rules and metrics definitions |

---

## Edge Cases & Gotchas

### Stefano Blank ≠ Available
For every other DJ, blank = available. For Stefano, blank = unknown/maybe. The system shows `[MAYBE]` and does NOT count him toward available spots.

### Bold Detection
Requires Google Sheets API v4 with `includeGridData=True`. Plain gspread `.get()` only returns values, not formatting.

### TBA Bookings Consume Spots
`TBA = BOOKED` means an unassigned booking exists. One available DJ will need to cover it.

### Date Formats Vary
- Matrix: `"Sat 1/3"` (day-of-week + M/D)
- FileMaker request: `M/D/YYYY`
- FileMaker response: `YYYY-MM-DD`
- Inquiry tracker: Various (`m/d/yyyy`, `mm/dd/yyyy`, `m/d/yy`)

### Unknown Matrix Values
Unknown cell values (typos, etc.) trigger warnings and are treated as unavailable. Known values: `booked`, `backup`, `out`, `maxed`, `reserved`, `stanford`, `ok`, `ok to backup`, `dad`, `last`, `aag`

### Deduplication in Dashboard
Same venue + same event date can have multiple rows. Logic:
- Multiple Booked = separate clients, keep all
- Canceled after Booked = reduces count by 1
- Cold → Booked = keep Booked only

---

## Development Patterns

### Local Testing → GitHub Deploy
Paul's workflow: test locally, commit to GitHub, Streamlit Cloud auto-deploys.

### Dry Run Mode
Both `gig_booking_manager.py` and availability tools support `--dry-run` for validation without writes.

### Test Mode
`--test` flag routes calendar invites to paul@bigfundj.com instead of actual DJs.

### Caching
- Gig database: LRU cache, auto-clears after 60 minutes
- Google Sheets: Fresh fetch on terminal, 1-hour TTL on Streamlit
- Dashboard: 1-hour TTL, manual refresh available

---

*Last updated: February 2026*
