"""
Generate a printable HTML report of dates BIG FUN is currently unavailable.

2026 and 2027, restricted to Fri/Sat/Sun, starting from today.
- 2026 rule: Stefano blank on Saturday = available (per Paul).
- 2027 rule: 2-event cap. Date is unavailable when
  (filled primary spots) + (1 if AAG=RESERVED) >= 2.

Run: python unavailable_report.py
Output: output/unavailable_<today>.html (auto-opens in browser)
"""

import os
import webbrowser
from datetime import datetime
from collections import defaultdict

from dj_core import (
    SPREADSHEET_ID,
    init_google_sheets_from_file,
    get_bulk_availability_data,
)


OPEN_VALUES = {"", "ok", "last"}


def clean(value):
    if not value:
        return ""
    return str(value).replace(" (BOLD)", "").strip().lower()


def is_open(value):
    """True if this cell means the DJ can still take a primary booking."""
    return clean(value) in OPEN_VALUES


def is_unavailable_2026(row):
    """A 2026 Fri/Sat/Sun date is unavailable when no primary DJ can take it.

    Primary pool by day:
      Fri: Paul
      Sat: Paul, Henry, Stefano (blank counts as available per Paul)
      Sun: Paul, Henry
    """
    data = row["selected_data"]
    date_obj = row["date_obj"]
    weekday = date_obj.weekday()  # Mon=0..Sun=6

    paul_open = is_open(data.get("Paul", ""))

    if weekday == 4:  # Friday
        return not paul_open

    if weekday == 5:  # Saturday
        henry_open = is_open(data.get("Henry", ""))
        stefano_open = is_open(data.get("Stefano", ""))  # blank counts as open
        return not (paul_open or henry_open or stefano_open)

    if weekday == 6:  # Sunday
        henry_open = is_open(data.get("Henry", ""))
        return not (paul_open or henry_open)

    return False


def is_unavailable_2027(row):
    """A 2027 Fri/Sat/Sun date is unavailable when actual bookings
    plus the AAG-RESERVED hold reach the 2-event cap.

    The cap is 2: one slot is held for AAG, one for tier-1 venues
    (Little Hills, Nestldown, Fogarty, etc.). Counting:
      - booked_count = real events (BOOKED, RESERVED on a DJ, WEDFAIRE,
        AAG-as-event, STANFORD). Does NOT include OUT or MAXED.
      - +1 if AAG column says RESERVED (the held AAG slot).
    """
    booked_count = row["availability"].get("booked_count", 0)
    if row.get("aag_reserved"):
        booked_count += 1
    return booked_count >= 2


def fetch(service, spreadsheet, year, start, end):
    return get_bulk_availability_data(
        year, service, spreadsheet, SPREADSHEET_ID,
        start_date=start, end_date=end,
    )


def collect_unavailable(rows, predicate):
    """Filter rows to Fri/Sat/Sun dates where predicate(row) is True."""
    out = []
    for row in rows or []:
        date_obj = row["date_obj"]
        if date_obj.weekday() not in (4, 5, 6):
            continue
        if predicate(row):
            out.append(date_obj)
    return out


def group_by_month(dates):
    """Group a list of date objects into {month_num: [date_obj, ...]}."""
    grouped = defaultdict(list)
    for d in sorted(dates):
        grouped[d.month].append(d)
    return grouped


MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def format_date_short(d):
    return f"{DAY_NAMES[d.weekday()]} {d.day}"


def render_year_block(title, subtitle, dates):
    grouped = group_by_month(dates)
    if not grouped:
        rows_html = '<div class="empty">No unavailable dates in this range.</div>'
    else:
        rows_html = ""
        for month_num in sorted(grouped):
            label = MONTH_NAMES[month_num]
            day_list = ", ".join(format_date_short(d) for d in grouped[month_num])
            rows_html += f'  <div class="row"><span class="month">{label}</span><span class="dates">{day_list}</span></div>\n'

    return f"""
<section class="year">
  <h2>{title}</h2>
  <div class="sub">{subtitle}</div>
{rows_html}</section>
""".strip()


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BIG FUN — Dates Unavailable</title>
<style>
@page {{ size: letter; margin: 0.5in; }}
body {{
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 11pt;
  color: #000;
  margin: 0;
  padding: 0;
}}
h1 {{
  font-size: 14pt;
  margin: 0 0 2pt 0;
}}
.gen {{
  font-size: 9pt;
  color: #444;
  margin-bottom: 12pt;
}}
.year {{
  margin-bottom: 14pt;
  page-break-inside: avoid;
}}
.year h2 {{
  font-size: 13pt;
  margin: 0;
  border-bottom: 1px solid #000;
  padding-bottom: 2pt;
}}
.sub {{
  font-size: 9pt;
  color: #444;
  margin: 2pt 0 6pt 0;
}}
.row {{
  display: flex;
  margin: 1pt 0;
  page-break-inside: avoid;
}}
.month {{
  flex: 0 0 48pt;
  font-weight: bold;
}}
.dates {{
  flex: 1;
}}
.empty {{
  font-style: italic;
  color: #555;
}}
.notes {{
  margin-top: 14pt;
  padding-top: 6pt;
  border-top: 1px solid #999;
  font-size: 9pt;
  color: #333;
}}
.notes ul {{
  margin: 4pt 0 0 14pt;
  padding: 0;
}}
</style>
</head>
<body>
<h1>BIG FUN — Dates Currently Unavailable</h1>
<div class="gen">Generated {generated}</div>
{year_2026}
{year_2027}
<div class="notes">
  <strong>Notes:</strong>
  <ul>
    <li>Restricted to Fri / Sat / Sun.</li>
    <li>2026: Stefano blank on Saturday counts as available.</li>
    <li>2027: 2-event cap. AAG hold + 1 booking = at cap.</li>
    <li>AAG holds may lapse to non-AAG inquiries within 6 months of the event.</li>
  </ul>
</div>
</body>
</html>
"""


def main():
    today = datetime.now()
    creds_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "your-credentials.json"
    )
    service, spreadsheet, _sid, _client = init_google_sheets_from_file(creds_path)

    start_2026 = max(today, datetime(2026, 1, 1))
    start_2027 = max(today, datetime(2027, 1, 1))

    print("Fetching 2026 matrix...")
    rows_2026 = fetch(service, spreadsheet, "2026",
                      start_2026, datetime(2026, 12, 31))
    print("Fetching 2027 matrix...")
    rows_2027 = fetch(service, spreadsheet, "2027",
                      start_2027, datetime(2027, 12, 31))

    unavail_2026 = collect_unavailable(rows_2026, is_unavailable_2026)
    unavail_2027 = collect_unavailable(rows_2027, is_unavailable_2027)

    block_2026 = render_year_block(
        "2026",
        f"{start_2026.strftime('%b %-d')} – Dec 31, Fri / Sat / Sun",
        unavail_2026,
    )
    block_2027 = render_year_block(
        "2027",
        f"{start_2027.strftime('%b %-d')} – Dec 31, Fri / Sat / Sun, 2-event cap applied",
        unavail_2027,
    )

    html_out = HTML_TEMPLATE.format(
        generated=today.strftime("%Y-%m-%d %H:%M"),
        year_2026=block_2026,
        year_2027=block_2027,
    )

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    filename = f"unavailable_{today.strftime('%Y-%m-%d')}.html"
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    print(
        f"2026: {len(unavail_2026)} unavailable dates  |  "
        f"2027: {len(unavail_2027)} unavailable dates  |  "
        f"Saved to {out_path}"
    )
    webbrowser.open(f"file://{out_path}")


if __name__ == "__main__":
    main()
