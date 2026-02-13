#!/usr/bin/env python3
"""
Tests for confirmation_forwarder.py

Tests all the logic that doesn't require MailMaven:
  - JSON parsing (FM format and clean format)
  - Consult month calculation (including "next" year logic)
  - AppleScript escaping
  - Template formatting
  - AppleScript generation (addresses, CC handling, tab counts, body text)

Run:  python3 test_confirmation_forwarder.py
"""

import json
import os
import sys
import tempfile
import types
from datetime import datetime
from unittest.mock import MagicMock

# Mock out heavy dj_core dependencies before importing
# We only need DJ_EMAILS, DJ_NAME_MAP, and get_dj_short_name
for mod_name in [
    "gspread",
    "oauth2client", "oauth2client.service_account",
    "googleapiclient", "googleapiclient.discovery",
]:
    if mod_name not in sys.modules:
        mock = types.ModuleType(mod_name)
        if mod_name == "oauth2client.service_account":
            mock.ServiceAccountCredentials = MagicMock()
        if mod_name == "googleapiclient.discovery":
            mock.build = MagicMock()
        sys.modules[mod_name] = mock

# Import the functions we're testing
from confirmation_forwarder import (
    parse_booking_json,
    calculate_consult_month,
    escape_for_applescript,
    create_forward_draft,
    OFFICE_TEMPLATE,
    DJ_TEMPLATE,
    OFFICE_TO,
    OFFICE_CC,
)

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  \033[32m✓\033[0m {name}")
        passed += 1
    else:
        print(f"  \033[31m✗\033[0m {name}")
        if detail:
            print(f"    → {detail}")
        failed += 1


def make_temp_json(data):
    """Write a dict to a temp JSON file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f)
    return path


# =========================================================================
print("\n── parse_booking_json: Clean format ──")
# =========================================================================

path = make_temp_json({
    "event_date": "2026-07-20",
    "client_name": "Anderson & Martinez",
    "venue_name": "Mountain Winery",
    "assigned_dj": "Henry",
    "secondary_dj": "",
})
b = parse_booking_json(path)
os.unlink(path)

test("event_date", b["event_date"] == "2026-07-20", f"got {b['event_date']}")
test("client_name", b["client_name"] == "Anderson & Martinez", f"got {b['client_name']}")
test("venue_name", b["venue_name"] == "Mountain Winery", f"got {b['venue_name']}")
test("assigned_dj", b["assigned_dj"] == "Henry", f"got {b['assigned_dj']}")
test("secondary_dj empty", b["secondary_dj"] == "", f"got {b['secondary_dj']}")


# =========================================================================
print("\n── parse_booking_json: FM format ──")
# =========================================================================

path = make_temp_json({
    "FMeventDate": "2026-09-12",
    "FMclient": "Thompson Wedding",
    "FMvenue": "Nestldown",
    "FMDJ1": "Paul Burchfield",
    "FMDJ2": "",
})
b = parse_booking_json(path)
os.unlink(path)

test("FM event_date", b["event_date"] == "2026-09-12", f"got {b['event_date']}")
test("FM client_name", b["client_name"] == "Thompson Wedding", f"got {b['client_name']}")
test("FM venue_name", b["venue_name"] == "Nestldown", f"got {b['venue_name']}")
test("FM assigned_dj mapped", b["assigned_dj"] == "Paul", f"got {b['assigned_dj']}")


# =========================================================================
print("\n── parse_booking_json: Missing fields ──")
# =========================================================================

path = make_temp_json({"event_date": "2026-05-01"})
b = parse_booking_json(path)
os.unlink(path)

test("missing client_name → empty", b["client_name"] == "", f"got '{b['client_name']}'")
test("missing venue_name → empty", b["venue_name"] == "", f"got '{b['venue_name']}'")
test("missing assigned_dj → empty", b["assigned_dj"] == "", f"got '{b['assigned_dj']}'")


# =========================================================================
print("\n── parse_booking_json: Unassigned DJ ──")
# =========================================================================

path = make_temp_json({
    "event_date": "2026-08-15",
    "assigned_dj": "Unassigned",
    "client_name": "Williams Wedding",
    "venue_name": "Livermore Valley",
})
b = parse_booking_json(path)
os.unlink(path)

test("unassigned DJ stays 'Unassigned'", b["assigned_dj"] == "Unassigned", f"got '{b['assigned_dj']}'")


# =========================================================================
print("\n── calculate_consult_month ──")
# =========================================================================

# Standard: 5 weeks before 2026-07-20 → June 15 → June
test("July 2026 → June", calculate_consult_month("2026-07-20") == "June",
     f"got {calculate_consult_month('2026-07-20')}")

# September → ~August 7 → August
test("Sept 2026 → August", calculate_consult_month("2026-09-12") == "August",
     f"got {calculate_consult_month('2026-09-12')}")

# January event → 5 weeks back → late November/early December of prior year
result = calculate_consult_month("2026-01-15")
test("Jan 2026 → December (prior year, but same as current)", result == "December",
     f"got {result}")

# Event in March → ~late January/early February
result = calculate_consult_month("2026-03-01")
test("March 2026 → January", result == "January",
     f"got {result}")

# Bad date → TBD
test("invalid date → TBD", calculate_consult_month("not-a-date") == "TBD")

# Alternative date formats
test("MM/DD/YYYY format", calculate_consult_month("07/20/2026") == "June",
     f"got {calculate_consult_month('07/20/2026')}")

test("MM-DD-YYYY format", calculate_consult_month("07-20-2026") == "June",
     f"got {calculate_consult_month('07-20-2026')}")


# =========================================================================
print("\n── calculate_consult_month: 'next' year logic ──")
# =========================================================================

current_year = datetime.now().year

# Event next year → consult month should say "next [Month]"
next_year_date = f"{current_year + 1}-08-15"
result = calculate_consult_month(next_year_date)
test(f"event in {current_year + 1} → 'next July'", result == "next July",
     f"got '{result}'")

# Event in 2 years → still "next"
far_date = f"{current_year + 2}-03-01"
result = calculate_consult_month(far_date)
test(f"event in {current_year + 2} → 'next January'", result.startswith("next"),
     f"got '{result}'")

# Event this year → no "next"
this_year_date = f"{current_year}-09-15"
result = calculate_consult_month(this_year_date)
test(f"event in {current_year} → no 'next'", not result.startswith("next"),
     f"got '{result}'")

# Edge: event next year January, consult in December this year → no "next"
next_jan = f"{current_year + 1}-01-10"
result = calculate_consult_month(next_jan)
test(f"event Jan {current_year + 1}, consult Dec {current_year} → no 'next'",
     result == "December",
     f"got '{result}'")


# =========================================================================
print("\n── escape_for_applescript ──")
# =========================================================================

test("plain text unchanged", escape_for_applescript("hello") == "hello")
test("double quotes escaped", escape_for_applescript('say "hi"') == 'say \\"hi\\"')
test("backslash escaped", escape_for_applescript("path\\file") == "path\\\\file")
test("both quotes and backslash",
     escape_for_applescript('a\\b"c') == 'a\\\\b\\"c')
test("newlines preserved", escape_for_applescript("line1\nline2") == "line1\nline2")


# =========================================================================
print("\n── OFFICE_TEMPLATE formatting ──")
# =========================================================================

body = OFFICE_TEMPLATE.format(client_name="Anderson & Martinez")
test("contains client name", "Anderson & Martinez" in body,
     f"body: {repr(body[:80])}")
test("contains 'send confirmation documents to'",
     "send confirmation documents to Anderson & Martinez" in body)
test("contains Thanks", "Thanks." in body)
test("contains Paul", "Paul" in body)


# =========================================================================
print("\n── DJ_TEMPLATE formatting ──")
# =========================================================================

# With no notes
body = DJ_TEMPLATE.format(dj_name="Henry", notes_section="", consult_month="August")
test("contains DJ greeting", "Hi Henry," in body)
test("contains 'hello' email line", 'send a "hello" email' in body)
test("contains consult month", "until August." in body)
test("no double spaces from empty notes",
     "New event for you.\n\nPlease" in body)

# With "next" month
body = DJ_TEMPLATE.format(dj_name="Woody", notes_section="", consult_month="next August")
test("contains 'next August'", "until next August." in body)

# With notes
body = DJ_TEMPLATE.format(dj_name="Stefano", notes_section="\nBring extra speakers.",
                          consult_month="July")
test("notes appear in body", "Bring extra speakers." in body)


# =========================================================================
print("\n── create_forward_draft: Office email (with CC) ──")
# =========================================================================

office_body = OFFICE_TEMPLATE.format(client_name="Test Client")
script = create_forward_draft(
    to_addr=OFFICE_TO,
    cc_addrs=OFFICE_CC,
    prepend_text=office_body,
)

test("script contains To address",
     "confirmations@bigfundj.com" in script)
test("script contains Henry CC (keystroke)",
     'keystroke "henry@bigfundj.com"' in script)
test("script contains Woody CC (keystroke)",
     'keystroke "woody@bigfundj.com"' in script)
test("script uses 7 tabs (CC path)",
     "repeat 7 times" in script,
     f"script has: {'repeat 7' if 'repeat 7' in script else 'repeat 8'}")
test("script pastes with Cmd+V",
     'keystroke "v" using command down' in script)
test("script contains template text",
     "send confirmation documents to Test Client" in script)
test("script triggers forward shortcut",
     'keystroke "f" using {option down, command down}' in script)
test("script has keystroke return for CC confirmation",
     "keystroke return" in script)


# =========================================================================
print("\n── create_forward_draft: DJ email (no CC) ──")
# =========================================================================

dj_body = DJ_TEMPLATE.format(dj_name="Henry", notes_section="", consult_month="June")
script = create_forward_draft(
    to_addr="henry@bigfundj.com",
    cc_addrs=[],
    prepend_text=dj_body,
)

test("script contains DJ To address",
     "henry@bigfundj.com" in script)
test("script uses 8 tabs (no CC path)",
     "repeat 8 times" in script,
     f"script has: {'repeat 8' if 'repeat 8' in script else 'repeat 7'}")
test("no CC keystroke lines",
     'keystroke "woody@bigfundj.com"' not in script)
test("script contains DJ template text",
     "Hi Henry," in script)
test("script contains consult month",
     "until June." in script)


# =========================================================================
print("\n── create_forward_draft: special characters in client name ──")
# =========================================================================

office_body = OFFICE_TEMPLATE.format(client_name='O\'Brien & "DJ" Dave')
script = create_forward_draft(
    to_addr=OFFICE_TO,
    cc_addrs=[],
    prepend_text=office_body,
)

test("single quote passes through", "O'Brien" in script)
test("double quotes escaped for AppleScript", '\\"DJ\\"' in script)


# =========================================================================
print("\n── End-to-end: sample JSON files ──")
# =========================================================================

sample_dir = os.path.join(os.path.dirname(__file__), "sample_bookings")
if os.path.isdir(sample_dir):
    for fname in sorted(os.listdir(sample_dir)):
        if fname.endswith(".json"):
            path = os.path.join(sample_dir, fname)
            try:
                b = parse_booking_json(path)
                has_required = all(k in b for k in ["event_date", "client_name", "venue_name", "assigned_dj"])
                test(f"{fname} parses OK", has_required,
                     f"missing keys: {[k for k in ['event_date','client_name','venue_name','assigned_dj'] if k not in b]}")
            except Exception as e:
                test(f"{fname} parses OK", False, str(e))
else:
    print("  (sample_bookings directory not found, skipping)")


# =========================================================================
# SUMMARY
# =========================================================================
print(f"\n{'='*50}")
total = passed + failed
if failed == 0:
    print(f"\033[32m  All {total} tests passed ✓\033[0m")
else:
    print(f"\033[31m  {failed} of {total} tests failed\033[0m")
print(f"{'='*50}\n")

sys.exit(0 if failed == 0 else 1)
