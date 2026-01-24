# DJ Availability Checker

Automated system for checking DJ availability across multiple data sources for Big Fun DJ wedding entertainment business.

## Overview

This system integrates three data sources to provide comprehensive DJ availability checking:
- **Google Sheets** - Availability matrix with DJ schedules
- **FileMaker Pro** - Gig database with confirmed bookings and venue details
- **Google Sheets** - Venue inquiry tracking

## Features

✅ **Dual Interface**
- Terminal application for quick checks (`check_2026.py`, `check_2027.py`)
- Web application for team access (Streamlit app)

✅ **Performance Optimized**
- Parallel API requests for 18x speed improvement
- 1-hour caching for instant repeated queries
- Real-time gig database integration

✅ **Smart Business Logic**
- Year-specific DJ availability rules (2025, 2026, 2027)
- AAG (Allied Arts Guild) reservation tracking
- Nearby bookings display (±3 days)
- Venue inquiry tracking
- Backup DJ assignment rules

✅ **Data Visibility**
- Shows confirmed bookings with venue names
- Displays venue inquiries that didn't book
- Cache age indicators
- Manual refresh capability

## Quick Start

### Prerequisites

- Python 3.12+
- Google Sheets API credentials
- Access to FileMaker Pro gig database API

### Installation

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/dj-availability-checker.git
cd dj-availability-checker

# Install dependencies
pip install gspread oauth2client google-api-python-client colorama streamlit requests --break-system-packages

# Add your Google credentials
cp your-credentials.json ~/dj-availability-checker/

# Test terminal version
python3 check_2026.py
```

### Usage

**Terminal Interface:**
```bash
python3 check_2026.py
# Enter date in MM-DD format: 05-16

python3 check_2027.py
# Enter date in MM-DD format: 01-15
```

**Web Interface:**

Visit your deployed Streamlit app at: `https://your-app.streamlit.app`

## File Structure

```
dj-availability-checker/
├── README.md                    # This file
├── dj_core.py                   # Shared business logic
├── check_2026.py                # Terminal interface for 2026
├── check_2027.py                # Terminal interface for 2027
├── dj_app.py                    # Streamlit web application
├── your-credentials.json        # Google API credentials (not in git)
└── docs/                        # Detailed documentation
    ├── README.md
    ├── 2026_AAG_UPDATES.md
    ├── 2027_UPDATES_SUMMARY.md
    ├── CACHING_PERFORMANCE_IMPROVEMENTS.md
    └── STREAMLIT_UPDATE_GUIDE.md
```

## Business Rules Summary

### DJ Availability Logic

**Henry**
- Weekends only (regular gigs)
- Weekday blank = available for backup only

**Woody**
- Prefers weekdays for family commitments
- Weekend OUT (non-bold) = available for backup

**Paul**
- Available any day
- Handles approximately 35% of all events

**Stefano**
- Two events per month preference
- Blank cell = MAYBE (requires confirmation)
- Has significant unused capacity

**Felipe**
- 2026/2027: Transitioned to backup-only role
- Blank cell = available for backup only
- "OK" status = can be booked (special exception)

**Stephanie**
- 2026: Only available when explicitly assigned (BOOKED/RESERVED/BACKUP)
- 2027: Weekend-only DJ, blank weekend = available
- Handles overflow AAG events

### AAG (Allied Arts Guild) Tracking

- RESERVED status holds spot for AAG events
- Can appear in AAG column OR Stephanie column (mutually exclusive)
- Reduces available spots by 1
- Workflow: AAG RESERVED → Stephanie RESERVED → Stephanie BOOKED

### Pricing Tiers

- Off-peak: $1,399-$1,599
- Peak Saturdays (April-October): $1,999-$2,299

## Performance Metrics

| Metric | Value |
|--------|-------|
| Speed improvement (first query) | 18x faster |
| Speed improvement (cached) | 180x faster |
| API load reduction | 66% |
| Memory usage | ~60 KB (100 cached entries) |
| Cache duration | 1 hour |

## Documentation

For detailed implementation guides and technical documentation, see the [docs/](docs/) directory:

- [2026 AAG Updates](docs/2026_AAG_UPDATES.md) - AAG column and Stephanie logic
- [2027 Updates](docs/2027_UPDATES_SUMMARY.md) - Year-specific changes  
- [Performance Improvements](docs/CACHING_PERFORMANCE_IMPROVEMENTS.md) - Caching and parallel requests
- [Streamlit Deployment](docs/STREAMLIT_UPDATE_GUIDE.md) - Deployment workflow

## Key Venues

Premium venues with longer lead times (~6 weeks):
- Nestldown
- Thomas Fogarty Winery
- Hakone Gardens

## Technology Stack

- **Python 3.12+** - Core language
- **Google Sheets API** - Availability matrix and inquiry tracking
- **FileMaker Pro API** - Gig database integration
- **Streamlit** - Web interface
- **Colorama** - Terminal color output
- **ThreadPoolExecutor** - Parallel API requests
- **LRU Cache** - 1-hour response caching

## Development Workflow

```bash
# Make changes to code
vim dj_core.py

# Test locally
python3 check_2026.py

# Commit changes
git add .
git commit -m "Descriptive message"

# Push to GitHub (auto-deploys Streamlit)
git push
```

## Support & Maintenance

**Maintained by:** Paul Burchfield  
**Business:** Big Fun DJ  
**Created:** 2025-2026  
**License:** Private (Internal Use)

## Recent Updates

See [git log](https://github.com/YOUR_USERNAME/dj-availability-checker/commits/main) for full version history.

---

**Note:** This is an internal tool for Big Fun DJ business operations. Credentials and API access are required for operation.
