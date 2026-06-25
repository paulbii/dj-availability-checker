#!/usr/bin/env python3
"""
Potential-inquiry availability triage.

Reads every thread in the IMAP folder INBOX.BIG FUN.Sales.Potential (Paul's
love2tap account), pulls the event date and venue out of each subject line,
checks that date against the DJ availability matrix, and prints + saves a
sorted report of where we stand on each potential inquiry.

Subject formats handled:
  (SUN 06-27-27 Nestldown) BIG FUN Disc Jockeys   -> date + venue
  ...Corporate Event 8/7/2026                      -> loose date, no venue
  anything with no parseable date                  -> listed for manual check

Read-only. Never writes to the matrix, calendar, or email.

Usage:
    python3 potential_availability.py
"""

import os
import re
import json
import imaplib
import datetime
from email.header import decode_header, make_header

from colorama import Fore, Style, init as colorama_init

from dj_core import (
    init_google_sheets_from_file,
    analyze_availability,
    get_columns_for_year,
    get_column_indices,
)

colorama_init(autoreset=True)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAP_CREDENTIALS_PATH = os.path.join(SCRIPT_DIR, "imap_credentials.json")
POTENTIAL_FOLDER = "INBOX.BIG FUN.Sales.Potential"
DOWNLOADS_DIR = os.path.expanduser("~/Downloads")
SUPPORTED_YEARS = {"2025", "2026", "2027"}

# Primary subject pattern: "(DOW MM-DD-YY Venue)" -> date, venue
PRIMARY_RE = re.compile(
    r"\(\s*[A-Za-z]{3,4}\s+(\d{1,2}-\d{1,2}-\d{2})\s+(.+?)\)"
)
# Fallback: any loose date anywhere in the subject (M/D/YYYY, MM-DD-YY, etc.)
LOOSE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")


def clean_subject(raw):
    """Decode MIME subject and normalize whitespace (incl. nbsp)."""
    try:
        decoded = str(make_header(decode_header(raw)))
    except Exception:
        decoded = raw
    return decoded.replace("\xa0", " ").strip()


def fetch_subjects():
    """Return list of subject strings from the Potential folder (read-only)."""
    with open(IMAP_CREDENTIALS_PATH) as f:
        creds = json.load(f)
    imap = imaplib.IMAP4_SSL(creds["host"], creds.get("port", 993))
    imap.login(creds["username"], creds["password"])
    try:
        imap.select(f'"{POTENTIAL_FOLDER}"', readonly=True)
        _, data = imap.search(None, "ALL")
        ids = data[0].split()
        subjects = []
        for msg_id in ids:
            _, d = imap.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
            raw = d[0][1].decode(errors="replace")
            raw_subj = raw.split(":", 1)[1].strip() if ":" in raw else raw.strip()
            subjects.append(clean_subject(raw_subj))
        return subjects
    finally:
        imap.logout()


def parse_date_venue(subject):
    """
    Pull (date_obj, venue) from a subject.
    Returns (date_obj, venue) or (None, None) if no date found.
    Venue is "" when the date came from the loose fallback.
    """
    m = PRIMARY_RE.search(subject)
    if m:
        date_obj = _build_date(m.group(1).split("-"))
        if date_obj:
            return date_obj, m.group(2).strip()

    m = LOOSE_RE.search(subject)
    if m:
        date_obj = _build_date([m.group(1), m.group(2), m.group(3)])
        if date_obj:
            return date_obj, ""

    return None, None


def _build_date(parts):
    """parts = [month, day, year] as strings (year 2 or 4 digit)."""
    try:
        month, day, year = (int(p) for p in parts)
    except (ValueError, TypeError):
        return None
    if year < 100:
        year += 2000
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _cell_is_bold(cell):
    """Match dj_core's bold detection on a grid-data cell."""
    fmt = cell.get("effectiveFormat", {}).get("textFormat", {})
    if fmt.get("bold", False):
        return True
    return any(
        run.get("format", {}).get("bold", False)
        for run in cell.get("textFormatRuns", [])
    )


def load_year_grid(sheet_name, service, spreadsheet_id):
    """
    Read one year's matrix tab in a single API call and return a dict:
        formatted_date ("Mon 1/3") -> selected_data dict (with "(BOLD)" tags).
    Returns None if the worksheet doesn't exist.
    """
    column_indices = get_column_indices(get_columns_for_year(sheet_name))
    try:
        response = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=f"{sheet_name}!A:L",
            includeGridData=True,
        ).execute()
    except Exception:
        return None

    sheets = response.get("sheets", [])
    if not sheets or not sheets[0].get("data"):
        return None
    rows = sheets[0]["data"][0].get("rowData", [])

    grid = {}
    for row in rows:
        values = row.get("values", [])
        if not values:
            continue
        date_label = values[0].get("formattedValue", "").strip()
        if not date_label:
            continue
        selected = {}
        for label, index in column_indices.items():
            if index < len(values):
                cell = values[index]
                val = cell.get("formattedValue", "")
                if label != "Date" and _cell_is_bold(cell):
                    val = f"{val} (BOLD)"
                selected[label] = val
        grid[date_label] = selected
    return grid


def availability_for(date_obj, grids):
    """
    Return a result dict describing availability for date_obj, using the
    pre-loaded per-year grids. status: 'open' | 'full' | 'notfound' | 'notab'
    """
    sheet_name = str(date_obj.year)
    if sheet_name not in SUPPORTED_YEARS:
        return {"status": "notab", "note": f"no {sheet_name} matrix tab"}

    grid = grids.get(sheet_name)
    if grid is None:
        return {"status": "notab", "note": f"no {sheet_name} matrix tab"}

    formatted_date = f"{date_obj.strftime('%a')} {date_obj.month}/{date_obj.day}"
    selected = grid.get(formatted_date)
    if selected is None:
        return {"status": "notfound", "note": "not seeded in matrix — check manually"}

    a = analyze_availability(selected, date_obj, sheet_name)
    spots = a["available_spots"]
    return {
        "status": "open" if spots > 0 else "full",
        "spots": spots,
        "book": a["available_booking"],
        "backup": a["available_backup"],
        "booked": a["booked_count"],
        "tba": a["tba_bookings"],
        "aag": a["aag_reserved"],
    }


def build_report():
    subjects = fetch_subjects()
    service, spreadsheet, spreadsheet_id, _ = init_google_sheets_from_file(
        os.path.join(SCRIPT_DIR, "your-credentials.json")
    )

    parsed = []
    no_date = []
    for subject in subjects:
        date_obj, venue = parse_date_venue(subject)
        if date_obj is None:
            no_date.append(subject)
        else:
            parsed.append((date_obj, venue, subject))

    # Load each needed year's matrix once (one API call per year).
    grids = {}
    for year in sorted({str(d.year) for d, _, _ in parsed} & SUPPORTED_YEARS):
        grids[year] = load_year_grid(year, service, spreadsheet_id)

    dated = []
    for date_obj, venue, subject in parsed:
        result = availability_for(date_obj, grids)
        result["date_obj"] = date_obj
        result["venue"] = venue or "(venue not in subject)"
        result["subject"] = subject
        dated.append(result)

    dated.sort(key=lambda r: r["date_obj"])
    return dated, no_date


def _status_text(r, color=False):
    if r["status"] == "open":
        txt = f"{r['spots']} open"
        return f"{Fore.GREEN}✅ {txt}{Style.RESET_ALL}" if color else f"OPEN ({txt})"
    if r["status"] == "full":
        return f"{Fore.RED}❌ FULL{Style.RESET_ALL}" if color else "FULL"
    note = r.get("note", r["status"])
    return f"{Fore.YELLOW}{note}{Style.RESET_ALL}" if color else note


def _detail_text(r):
    """book / backup / counts suffix; only for dates that resolved in matrix."""
    if r["status"] not in ("open", "full"):
        return ""
    book = ", ".join(r["book"]) if r["book"] else "—"
    backup = ", ".join(r["backup"]) if r["backup"] else "—"
    aag = "yes" if r["aag"] else "no"
    return (
        f"book: {book}   backup: {backup}   "
        f"booked:{r['booked']} TBA:{r['tba']} AAG:{aag}"
    )


def print_terminal(dated, no_date):
    print()
    print(Style.BRIGHT + "POTENTIAL INQUIRIES — AVAILABILITY" + Style.RESET_ALL)
    print(Style.DIM + f"{len(dated)} dated, {len(no_date)} need manual check" + Style.RESET_ALL)
    print()
    for r in dated:
        date_str = r["date_obj"].strftime("%m-%d-%y")
        header = f"{Style.BRIGHT}{date_str}{Style.RESET_ALL}  {r['venue']}"
        print(f"{header}")
        print(f"    {_status_text(r, color=True)}   {_detail_text(r)}".rstrip())
    if no_date:
        print()
        print(Fore.YELLOW + Style.BRIGHT + "NO DATE IN SUBJECT — check manually:" + Style.RESET_ALL)
        for s in no_date:
            print(f"  • {s}")
    print()


def write_markdown(dated, no_date):
    today = datetime.date.today().isoformat()
    path = os.path.join(DOWNLOADS_DIR, f"{today}-potential-availability.md")
    lines = [
        "# Potential Inquiries — Availability",
        "",
        f"Generated {today} from `{POTENTIAL_FOLDER}`.",
        f"{len(dated)} dated inquiries, {len(no_date)} with no date in subject.",
        "",
        "| Date | Venue | Status | Free to book | Free for backup | Booked | TBA | AAG |",
        "|------|-------|--------|--------------|-----------------|--------|-----|-----|",
    ]
    for r in dated:
        date_str = r["date_obj"].strftime("%m-%d-%y")
        status = _status_text(r, color=False)
        if r["status"] in ("open", "full"):
            book = ", ".join(r["book"]) if r["book"] else "—"
            backup = ", ".join(r["backup"]) if r["backup"] else "—"
            aag = "yes" if r["aag"] else "no"
            lines.append(
                f"| {date_str} | {r['venue']} | {status} | {book} | {backup} "
                f"| {r['booked']} | {r['tba']} | {aag} |"
            )
        else:
            lines.append(
                f"| {date_str} | {r['venue']} | {status} | — | — | — | — | — |"
            )

    lines += ["", "## No date in subject — check manually", ""]
    if no_date:
        lines += [f"- {s}" for s in no_date]
    else:
        lines.append("_None._")
    lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def main():
    dated, no_date = build_report()
    print_terminal(dated, no_date)
    path = write_markdown(dated, no_date)
    print(Style.DIM + f"Saved: {path}" + Style.RESET_ALL)


if __name__ == "__main__":
    main()
