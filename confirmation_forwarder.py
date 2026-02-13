#!/usr/bin/env python3
"""
Confirmation Email Forwarder
=============================
After the gig booking manager updates the matrix and calendar, and you've
sent the confirmation email to the couple and moved it to the "Booked"
folder, this script creates two pre-filled forward drafts in MailMaven:

  1. Office forward  → confirmations@bigfundj.com (CC: Henry, Woody)
  2. DJ forward       → assigned DJ's email (only if a DJ is assigned)

Both drafts open for review before sending.

Prerequisites:
  - The confirmation email should be selected in MailMaven (in the Booked folder)
  - MailMaven must be running

The script uses Opt+Cmd+F to trigger MailMaven's native forward, which
includes the original message automatically. Then it fills in the
recipients and prepends the template text via System Events.

MailMaven compose window field order:
  Field 1 = To, Field 2 = CC, Field 3 = BCC, Field 4 = Subject
  Body = AXWebArea inside scroll area 1 of group 1 of group 2

Usage:
  python3 confirmation_forwarder.py /tmp/gig_booking.json
  python3 confirmation_forwarder.py sample_bookings/sample_regular_booking.json
"""

import json
import sys
import os
import subprocess
from datetime import datetime, timedelta

# Import DJ data from shared core
from dj_core import DJ_EMAILS, DJ_NAME_MAP, get_dj_short_name


# =============================================================================
# CONFIGURATION
# =============================================================================

OFFICE_TO = "confirmations@bigfundj.com"
OFFICE_CC = ["henry@bigfundj.com", "woody@bigfundj.com"]

OFFICE_TEMPLATE = """\
This event has booked. Please send confirmation documents to {client_name}.

Thanks.

Paul

"""

DJ_TEMPLATE = """\
Hi {dj_name},

New event for you.
{notes_section}
Please send a "hello" email.

Then no further action is needed until {consult_month}.

Thanks.

Paul

"""


# =============================================================================
# HELPERS
# =============================================================================

def parse_booking_json(json_path):
    """Parse booking JSON (supports both FM and clean formats)."""
    with open(json_path, 'r') as f:
        raw = json.load(f)

    if "FMeventDate" in raw:
        return {
            "event_date": raw.get("FMeventDate", ""),
            "client_name": raw.get("FMclient", ""),
            "venue_name": raw.get("FMvenue", ""),
            "assigned_dj": get_dj_short_name(raw.get("FMDJ1", "")),
            "secondary_dj": get_dj_short_name(raw.get("FMDJ2", "")),
        }
    else:
        dj_name = raw.get("assigned_dj", "")
        return {
            "event_date": raw.get("event_date", ""),
            "client_name": raw.get("client_name", ""),
            "venue_name": raw.get("venue_name", ""),
            "assigned_dj": get_dj_short_name(dj_name) if dj_name else "",
            "secondary_dj": raw.get("secondary_dj", ""),
        }


def calculate_consult_month(event_date_str):
    """Calculate consultation month (~5 weeks before event date)."""
    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d")
    except ValueError:
        for fmt in ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"]:
            try:
                event_date = datetime.strptime(event_date_str, fmt)
                break
            except ValueError:
                continue
        else:
            return "TBD"

    consult_date = event_date - timedelta(weeks=5)
    month_name = consult_date.strftime("%B")

    # If the consult month is in a future year, prefix with "next"
    now = datetime.now()
    if consult_date.year > now.year:
        return f"next {month_name}"
    return month_name


def escape_for_applescript(text):
    """Escape text for use inside AppleScript double-quoted strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def run_applescript(script):
    """Execute AppleScript and return (success, stdout, stderr)."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=60
    )
    return result.returncode == 0, result.stdout.strip(), result.stderr.strip()


def create_forward_draft(to_addr, cc_addrs, prepend_text):
    """
    Create a forward draft in MailMaven using native forward (Opt+Cmd+F),
    then fill in recipients and prepend template text to the body.

    The currently selected message in MailMaven will be forwarded.

    MailMaven compose field order:
      Field 1 = To, Field 2 = CC, Field 3 = BCC, Field 4 = Subject
      Body = AXWebArea inside scroll area 1 of group 1 of group 2
    """

    escaped_to = escape_for_applescript(to_addr)
    escaped_prepend = escape_for_applescript(prepend_text)

    # Build CC lines: Tab from To to CC, then type each address + Enter
    cc_lines = ""
    if cc_addrs:
        # Tab from To field to CC field
        cc_lines = "keystroke tab\n            delay 0.2\n"
        for addr in cc_addrs:
            escaped_addr = escape_for_applescript(addr)
            cc_lines += f'            keystroke "{escaped_addr}"\n'
            cc_lines += '            delay 0.2\n'
            cc_lines += '            keystroke return\n'
            cc_lines += '            delay 0.2\n'

    script = f"""
    tell application "MailMaven"
        activate
    end tell

    delay 0.3

    -- Trigger native forward (includes original message automatically)
    tell application "System Events"
        tell process "MailMaven"
            keystroke "f" using {{option down, command down}}
        end tell
    end tell

    delay 1

    tell application "System Events"
        tell process "MailMaven"
            set frontWin to front window

            -- Fill in To field
            click text field 1 of frontWin
            delay 0.1
            set value of text field 1 of frontWin to "{escaped_to}"
            delay 0.2

            -- Fill in CC field: click it, type each address + Enter to confirm
            {cc_lines}

            -- Tab from To field to body
            -- 8 tabs from To when no CC, 7 tabs when CC was filled (already tabbed once)
            click text field 1 of frontWin
            delay 0.1
            repeat {"7" if cc_addrs else "8"} times
                keystroke tab
                delay 0.1
            end repeat
            delay 0.3

            -- Now cursor should be in the body area
            -- Move to the very top of the body
            key code 126 using command down -- Cmd+Up = go to top
            delay 0.2

            -- Use clipboard to paste the template text
            set the clipboard to "{escaped_prepend}"
            delay 0.1
            keystroke "v" using command down -- Cmd+V = paste
            delay 0.3

            -- Move cursor back to top so Paul can review
            key code 126 using command down -- Cmd+Up = go to top
        end tell
    end tell
    """
    return script


# =============================================================================
# MAIN
# =============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 confirmation_forwarder.py <booking_json_path>")
        print("       python3 confirmation_forwarder.py /tmp/gig_booking.json")
        sys.exit(1)

    json_path = sys.argv[1]
    if not os.path.exists(json_path):
        print(f"Error: File not found: {json_path}")
        sys.exit(1)

    # Parse booking data
    booking = parse_booking_json(json_path)
    dj_name = booking["assigned_dj"]
    client = booking["client_name"]
    venue = booking["venue_name"]
    event_date = booking["event_date"]

    print(f"\n{'='*50}")
    print(f"CONFIRMATION FORWARDER")
    print(f"{'='*50}")
    print(f"Client: {client}")
    print(f"Venue:  {venue}")
    print(f"Date:   {event_date}")
    print(f"DJ:     {dj_name or 'Unassigned'}")

    # Build DJ email info
    dj_email = None
    dj_body = None
    if dj_name and dj_name not in ("Unknown", "Unassigned"):
        dj_email = DJ_EMAILS.get(dj_name)
        consult_month = calculate_consult_month(event_date)
        notes_section = ""
        dj_body = DJ_TEMPLATE.format(
            dj_name=dj_name,
            notes_section=notes_section,
            consult_month=consult_month,
        )
        print(f"Consult month: {consult_month}")
        print(f"DJ email: {dj_email}")

    print(f"{'='*50}")
    print(f"\nMake sure the confirmation email is selected in MailMaven.")
    input("Press Enter when ready...")

    # --- Office forward ---
    print("\nCreating office forward draft...")
    office_script = create_forward_draft(
        to_addr=OFFICE_TO,
        cc_addrs=OFFICE_CC,
        prepend_text=OFFICE_TEMPLATE.format(client_name=client),
    )

    success, _, stderr = run_applescript(office_script)
    if success:
        print("✓ Office draft opened")
    else:
        print(f"✗ Office draft failed: {stderr}")
        sys.exit(1)

    # Pause before creating second forward — need to reselect the original message
    if dj_email and dj_body:
        print("\nSwitch back to the Booked folder and reselect the confirmation email.")
        input("Press Enter when ready for the DJ forward...")

        print("Creating DJ forward draft...")
        dj_script = create_forward_draft(
            to_addr=dj_email,
            cc_addrs=[],
            prepend_text=dj_body,
        )

        success, _, stderr = run_applescript(dj_script)
        if success:
            print("✓ DJ draft opened")
        else:
            print(f"✗ DJ draft failed: {stderr}")
    elif not dj_name or dj_name in ("Unknown", "Unassigned"):
        print("\nNo DJ assigned — skipping DJ forward")

    print("\nDone. Review drafts and send when ready.")


if __name__ == "__main__":
    main()
