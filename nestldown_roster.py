#!/usr/bin/env python3
"""
Nestldown DJ Roster Page Generator

Reads Nestldown events from the Gigs calendar via CalDAV, generates a styled
HTML roster page, and uploads it via FTP to bigfundj.com/CLIENTS/nestldown/.
"""

import argparse
import calendar as cal_module
import datetime
import ftplib
import io
import os
import re
from collections import defaultdict
from zoneinfo import ZoneInfo

import caldav
import keyring

from dj_core import DJ_INITIALS, DJ_EMAILS, DJ_PHONES, DJ_FULL_NAMES

TIMEZONE = ZoneInfo("America/Los_Angeles")
CALDAV_SERVICE = "bigfun-caldav"
VENUE_FILTER = "nestldown"
# Direct URL to the Gigs calendar (proven pattern from test_caldav_write.py)
GIGS_CALENDAR_URL = "https://caldav.love2tap.com/calendars/__uids__/65B490A6-6667-48BC-B9E4-1A638DAA787E/1187934A-6A2E-43A3-8355-74382DC82F47/"

FTP_SERVICE = "bigfun-ftp"
FTP_REMOTE_DIR = "/ROOTCLIENTS/nestldown"
FTP_FILENAME = "index.html"

# Reverse lookup: initials -> first name (for email/phone lookup)
# Exclude "Unknown" which maps to "UP" -- that's the unassigned fallback, not a real DJ
INITIALS_TO_NAME = {v: k for k, v in DJ_INITIALS.items() if k != "Unknown"}

# Non-booking event patterns to exclude
EXCLUDE_PATTERNS = ["backup dj", "hold to dj", "dad-duty"]


def is_booking_event(summary):
    """Return True if this calendar event is an actual booking (not backup, hold, etc.)."""
    summary_lower = summary.lower()
    return not any(pattern in summary_lower for pattern in EXCLUDE_PATTERNS)


def parse_event_summary(summary):
    """Parse a calendar event summary into roster data.

    Input format: '[XX] CoupleName' or '[XX] CoupleName (planner)'
    Returns dict with: couple, dj_name, email, phone
    Returns None if summary doesn't match expected format.
    """
    match = re.match(r"^\[([A-Z]{2})\]\s+(.+)$", summary)
    if not match:
        return None

    initials = match.group(1)
    couple = match.group(2).strip()

    # Strip (planner) suffix
    couple = re.sub(r"\s*\(planner\)\s*$", "", couple, flags=re.IGNORECASE)

    # Look up DJ by initials
    if initials in DJ_FULL_NAMES:
        first_name = INITIALS_TO_NAME.get(initials)
        return {
            "couple": couple,
            "dj_name": DJ_FULL_NAMES[initials],
            "email": DJ_EMAILS.get(first_name, "info@bigfundj.com"),
            "phone": DJ_PHONES.get(first_name, "1-800-924-4386"),
        }
    else:
        # Unknown initials = unassigned
        return {
            "couple": couple,
            "dj_name": "Unassigned",
            "email": "info@bigfundj.com",
            "phone": "1-800-924-4386",
        }


def fetch_nestldown_events():
    """Fetch all Nestldown events from the Gigs calendar for current year + next year.

    Returns list of dicts: {date, couple, dj_name, email, phone}
    Sorted chronologically.
    """
    url = keyring.get_password(CALDAV_SERVICE, "url")
    username = keyring.get_password(CALDAV_SERVICE, "username")
    password = keyring.get_password(CALDAV_SERVICE, "password")
    if not all([url, username, password]):
        raise RuntimeError("No CalDAV credentials found. Run setup_caldav.py first.")

    client = caldav.DAVClient(url=url, username=username, password=password)
    gigs_cal = caldav.Calendar(client=client, url=GIGS_CALENDAR_URL)

    # Query date range: Jan 1 current year through Dec 31 next year
    now = datetime.datetime.now(TIMEZONE)
    start = datetime.datetime(now.year, 1, 1, tzinfo=TIMEZONE)
    end = datetime.datetime(now.year + 2, 1, 1, tzinfo=TIMEZONE)

    events = gigs_cal.search(start=start, end=end, event=True, expand=True)

    roster = []
    skipped = 0

    for event in events:
        vevent = event.icalendar_component
        summary = str(vevent.get("summary", ""))
        location = str(vevent.get("location", ""))

        # Filter: Nestldown events only
        if VENUE_FILTER not in location.lower():
            continue

        # Filter: bookings only (exclude backups, holds, etc.)
        if not is_booking_event(summary):
            continue

        # Parse the summary
        parsed = parse_event_summary(summary)
        if parsed is None:
            skipped += 1
            print(f"  WARNING: Skipping malformed event: {summary}")
            continue

        # Extract date
        dtstart = vevent.get("dtstart")
        if dtstart is None:
            skipped += 1
            continue

        dt = dtstart.dt
        if isinstance(dt, datetime.datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TIMEZONE)
            else:
                dt = dt.astimezone(TIMEZONE)
            event_date = dt.date()
        elif isinstance(dt, datetime.date):
            event_date = dt
        else:
            skipped += 1
            continue

        parsed["date"] = event_date
        roster.append(parsed)

    if skipped:
        print(f"  Skipped {skipped} malformed or unparseable events")

    # Sort chronologically
    roster.sort(key=lambda e: e["date"])
    return roster


def generate_html(roster):
    """Generate a self-contained HTML page from the roster data.

    Args:
        roster: list of dicts with keys: date, couple, dj_name, email, phone
    Returns:
        Complete HTML string
    """
    today = datetime.date.today()

    # Group by year, then month
    by_year_month = defaultdict(lambda: defaultdict(list))
    for entry in roster:
        by_year_month[entry["date"].year][entry["date"].month].append(entry)

    def render_row(entry):
        date_str = entry["date"].strftime("%a, %B %-d")
        row_class = ""
        if entry["date"] < today:
            row_class = "past"
        elif entry["dj_name"] == "Unassigned":
            row_class = "unassigned"
        cls = f' class="{row_class}"' if row_class else ""

        return f"""            <tr{cls}>
              <td>{date_str}</td>
              <td>{entry['couple']}</td>
              <td>{entry['dj_name']}</td>
              <td>{entry['phone']}</td>
              <td>{entry['email']}</td>
            </tr>"""

    sections = []
    years = sorted(by_year_month.keys())
    for year in years:
        months = sorted(by_year_month[year].keys())
        month_sections = []
        for month in months:
            month_name = cal_module.month_name[month]
            rows = "\n".join(render_row(e) for e in by_year_month[year][month])
            month_sections.append(f"""
        <div class="month-section">
          <h3>{month_name} {year}</h3>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Couple</th>
                <th>DJ</th>
                <th>Phone</th>
                <th>Email</th>
              </tr>
            </thead>
            <tbody>
{rows}
            </tbody>
          </table>
        </div>""")

        sections.append(f"""
      <div class="year-section">
        <h2>{year}</h2>
        {"".join(month_sections)}
      </div>""")

    updated = datetime.datetime.now(TIMEZONE).strftime("%B %-d, %Y at %-I:%M %p %Z")

    if not roster:
        body_content = '<p class="no-events">No Nestldown events found for this period.</p>'
    else:
        body_content = "".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow">
  <link rel="icon" href="favicon.ico" type="image/x-icon">
  <title>BIG FUN Disc Jockeys &mdash; Nestldown Event Roster</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: 'Source Sans 3', sans-serif;
      background: #f8f6f3;
      color: #2c2c2c;
      line-height: 1.5;
      padding: 2rem 1rem;
    }}

    .container {{
      max-width: 960px;
      margin: 0 auto;
    }}

    header {{
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 2px solid #dd00aa;
    }}

    h1 {{
      font-family: 'Libre Baskerville', serif;
      font-size: 1.75rem;
      font-weight: 700;
      color: #1a1a1a;
      margin-bottom: 0.25rem;
    }}

    header p {{
      font-size: 0.95rem;
      color: #6b6158;
    }}

    h2 {{
      font-family: 'Libre Baskerville', serif;
      font-size: 1.35rem;
      color: #1a1a1a;
      margin-top: 2.5rem;
      margin-bottom: 0.5rem;
    }}

    h3 {{
      font-family: 'Source Sans 3', sans-serif;
      font-size: 1rem;
      font-weight: 600;
      color: #dd00aa;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 1.75rem;
      margin-bottom: 0.75rem;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 0.5rem;
    }}

    th {{
      text-align: left;
      font-size: 0.8rem;
      font-weight: 600;
      color: #6b6158;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid #d4c9b8;
    }}

    td {{
      padding: 0.6rem 0.75rem;
      font-size: 0.95rem;
      border-bottom: 1px solid #e8e2da;
    }}

    tr.past td {{
      opacity: 0.45;
    }}

    tr.unassigned td {{
      background: #fdf6ec;
    }}

    tr.unassigned td:nth-child(3) {{
      font-style: italic;
      color: #a08050;
    }}

    .no-events {{
      margin-top: 2rem;
      font-size: 1.05rem;
      color: #6b6158;
    }}

    footer {{
      margin-top: 3rem;
      padding-top: 1rem;
      border-top: 1px solid #d4c9b8;
      font-size: 0.8rem;
      color: #9a9088;
    }}

    @media (max-width: 640px) {{
      h1 {{ font-size: 1.3rem; }}
      td, th {{ padding: 0.4rem 0.5rem; font-size: 0.85rem; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>BIG FUN Disc Jockeys</h1>
      <p>Nestldown Event Roster</p>
    </header>
    {body_content}
    <footer>
      Last updated {updated}
    </footer>
  </div>
</body>
</html>"""


def setup_ftp_credentials():
    """One-time FTP credential setup. Store in macOS Keychain."""
    print("FTP Credential Setup for bigfundj.com")
    print("=" * 40)
    host = input("FTP host (e.g., bigfundj.com): ").strip()
    username = input("FTP username: ").strip()
    password = input("FTP password: ").strip()

    keyring.set_password(FTP_SERVICE, "host", host)
    keyring.set_password(FTP_SERVICE, "username", username)
    keyring.set_password(FTP_SERVICE, "password", password)
    print("Credentials saved to Keychain.")


def upload_html(html_content):
    """Upload HTML content to FTP server.

    Returns True on success, False on failure.
    """
    host = keyring.get_password(FTP_SERVICE, "host")
    username = keyring.get_password(FTP_SERVICE, "username")
    password = keyring.get_password(FTP_SERVICE, "password")
    if not all([host, username, password]):
        print("ERROR: No FTP credentials found. Run with --setup-ftp first.")
        return False

    try:
        ftp = ftplib.FTP(host)
        ftp.login(username, password)
        ftp.cwd(FTP_REMOTE_DIR)
        ftp.storbinary(f"STOR {FTP_FILENAME}", io.BytesIO(html_content.encode("utf-8")))
        ftp.quit()
        return True
    except Exception as e:
        print(f"ERROR: FTP upload failed: {e}")
        return False


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nestldown_roster.html")


def main():
    parser = argparse.ArgumentParser(
        description="Nestldown DJ Roster Page Generator"
    )
    parser.add_argument(
        "--setup-ftp", action="store_true",
        help="Set up FTP credentials in Keychain"
    )
    parser.add_argument(
        "--local-only", action="store_true",
        help="Generate HTML locally without uploading"
    )
    args = parser.parse_args()

    if args.setup_ftp:
        setup_ftp_credentials()
        return

    # Fetch events
    print("Fetching Nestldown events from Gigs calendar...")
    try:
        roster = fetch_nestldown_events()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return

    print(f"  Found {len(roster)} Nestldown events")

    # Generate HTML
    print("Generating HTML...")
    html = generate_html(roster)

    # Save locally
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved to {OUTPUT_FILE}")

    # Upload
    if not args.local_only:
        print("Uploading via FTP...")
        if upload_html(html):
            print("  Upload complete")
        else:
            print("  Upload failed. Local file available for inspection.")
    else:
        print("  Skipping upload (--local-only)")

    print("Done.")


if __name__ == "__main__":
    main()
