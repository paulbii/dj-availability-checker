#!/usr/bin/env python3
"""
Gig to Calendar - Creates Apple Calendar events from FileMaker JSON export
Usage: python3 gig_to_calendar.py booking.json
       python3 gig_to_calendar.py booking.json --test  (routes invites to paul@bigfundj.com)
"""

import json
import subprocess
import sys
import re
from datetime import datetime

# Import shared business logic from dj_core (single source of truth)
from dj_core import (
    DJ_INITIALS,
    DJ_EMAILS,
    get_dj_short_name,
    get_unassigned_initials,
    extract_client_first_names,
    calculate_arrival_offset,
    convert_times_to_24h,
)

CALENDAR_NAME = "Gigs"
TEST_EMAIL = "paul@bigfundj.com"


def check_calendar_conflicts(date_str, initials_bracket):
    """
    Check if any events on the given date contain the DJ initials in the title.
    Uses icalBuddy for fast calendar queries.
    Returns list of conflicting event titles, or empty list if clear.
    date_str: "YYYY-MM-DD" format
    """
    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/icalBuddy", "-ic", "Gigs,Unavailable",
             "-eep", "notes,url,location,attendees",
             "-b", "", "-nc",
             f"eventsFrom:{date_str}", f"to:{date_str}"],
            capture_output=True, text=True, timeout=10,
        )
        conflicts = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and initials_bracket in line:
                conflicts.append(line)
        return conflicts
    except FileNotFoundError:
        print("  WARNING: icalBuddy not installed (brew install ical-buddy)")
        return []
    except subprocess.TimeoutExpired:
        print("  WARNING: Calendar conflict check timed out")
        return []


def build_event_title(client, has_planner, dj_name, dj2_name=""):
    """Build event title with DJ initials and optional planner indicator."""
    names = extract_client_first_names(client)

    if dj_name == "Unassigned" and dj2_name:
        initials = get_unassigned_initials(dj2_name)
    else:
        initials = DJ_INITIALS.get(dj_name, "UP")

    title = f"[{initials}] {names}"
    if has_planner:
        title += " (planner)"
    return title


def clean_venue_name(venue_name):
    """Strip parenthetical notes from venue name."""
    # Remove anything in parentheses
    return re.sub(r'\s*\([^)]*\)', '', venue_name).strip()


def build_location(venue_name, venue_street, venue_city_state_zip):
    """Build full location string."""
    clean_name = clean_venue_name(venue_name)
    parts = [clean_name]
    
    if venue_street:
        parts.append(venue_street)
    if venue_city_state_zip:
        parts.append(venue_city_state_zip)
    
    return ", ".join(parts)


def convert_to_24hr(setup_time, clear_time, sound_type="", has_ceremony_sound=False):
    """
    Convert 12-hour times (no AM/PM) to 24-hour format with DJ arrival/departure offsets.
    Uses dj_core for core time conversion and arrival offset calculation.
    Applies departure offset (+1 hour) and midnight cap locally.
    """
    # Check for midnight in original time before conversion
    end_parts = clear_time.strip().split(":")
    original_end_is_midnight = (int(end_parts[0]) == 12 and
                                 (int(end_parts[1]) if len(end_parts) > 1 else 0) == 0)

    # Core conversion from dj_core
    (start_h, start_m), (end_h, end_m) = convert_times_to_24h(setup_time, clear_time)

    # Apply arrival offset (subtract from start)
    arrival_minutes = calculate_arrival_offset(sound_type, has_ceremony_sound)
    total_start_min = start_h * 60 + start_m - arrival_minutes
    start_h, start_m = total_start_min // 60, total_start_min % 60

    # Apply departure offset (+1 hour to end) unless original was midnight
    if not original_end_is_midnight:
        end_h += 1
        if end_h >= 24:
            end_h = 23
            end_m = 59

    return (start_h, start_m), (end_h, end_m)


def format_applescript_date(date_str, hour, minute):
    """
    Format date for AppleScript.
    Input date_str: "2026-06-20"
    Output: "June 20, 2026 4:00:00 PM" format
    """
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    
    # Determine AM/PM
    if hour >= 12:
        period = "PM"
        display_hour = hour - 12 if hour > 12 else 12
    else:
        period = "AM"
        display_hour = hour if hour > 0 else 12
    
    return f"{date_obj.strftime('%B')} {date_obj.day}, {date_obj.year} {display_hour}:{minute:02d}:00 {period}"


def create_calendar_event(title, start_date, end_date, location, dj_email=None):
    """Create calendar event using AppleScript. If dj_email is None, no invitee is added."""
    
    if dj_email:
        applescript = f'''
        tell application "Calendar"
            tell calendar "{CALENDAR_NAME}"
                set newEvent to make new event with properties {{summary:"{title}", start date:date "{start_date}", end date:date "{end_date}", location:"{location}"}}
                tell newEvent
                    make new attendee at end of attendees with properties {{email:"{dj_email}"}}
                end tell
            end tell
        end tell
        '''
    else:
        applescript = f'''
        tell application "Calendar"
            tell calendar "{CALENDAR_NAME}"
                make new event with properties {{summary:"{title}", start date:date "{start_date}", end date:date "{end_date}", location:"{location}"}}
            end tell
        end tell
        '''
    
    try:
        subprocess.run(['osascript', '-e', applescript], check=True, capture_output=True, text=True)
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr


def parse_venue_address(venue_address):
    """
    Parse FMvenueAddress which uses *** as delimiter.
    "2750 Adeline Drive***Burlingame, CA 94010" → ("2750 Adeline Drive", "Burlingame, CA 94010")
    """
    if not venue_address:
        return "", ""
    parts = venue_address.split("***")
    street = parts[0].strip() if len(parts) > 0 else ""
    city_state_zip = parts[1].strip() if len(parts) > 1 else ""
    return street, city_state_zip


def parse_coordinator(mail_coordinator):
    """
    Check if planner exists from MailCoordinator field.
    "Jutta Lammerts <jutta@daylikenoother.com>" → True
    "" → False
    """
    return bool(mail_coordinator and mail_coordinator.strip())


def parse_event_date(date_str):
    """
    Convert MM/DD/YYYY to YYYY-MM-DD.
    "02/21/2026" → "2026-02-21"
    """
    parts = date_str.split("/")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
    return date_str  # Return as-is if unexpected format


def process_booking(booking_data, test_mode=False):
    """Process a booking and create calendar event."""
    
    # Handle both FM field names (from page source) and clean field names (from JSON file)
    if 'FMclient' in booking_data:
        # FM field names from page source
        client = booking_data.get('FMclient', '')
        event_date = parse_event_date(booking_data.get('FMeventDate', ''))
        setup_time = booking_data.get('FMstartTime', '')
        clear_time = booking_data.get('FMendTime', '')
        venue_name = booking_data.get('FMvenue', '')
        venue_street, venue_city_state_zip = parse_venue_address(booking_data.get('FMvenueAddress', ''))
        assigned_dj = booking_data.get('FMDJ1', '')
        assigned_dj2 = booking_data.get('FMDJ2', '')
        has_planner = parse_coordinator(booking_data.get('MailCoordinator', ''))
        has_ceremony_sound = booking_data.get('FMcersound', '0') == '1'
        sound_type = booking_data.get('FMsound', '')
    else:
        # Clean field names (from manual JSON file)
        client = booking_data['client_name']
        event_date = booking_data['event_date']
        setup_time = booking_data['setup_time']
        clear_time = booking_data['clear_time']
        venue_name = booking_data['venue_name']
        venue_street = booking_data.get('venue_street', '')
        venue_city_state_zip = booking_data.get('venue_city_state_zip', '')
        assigned_dj = booking_data['assigned_dj']
        assigned_dj2 = booking_data.get('assigned_dj2', '')
        planner_name = booking_data.get('planner_name', '')
        has_planner = bool(planner_name and planner_name.strip())
        has_ceremony_sound = booking_data.get('has_ceremony_sound', False)
        sound_type = booking_data.get('sound_type', '')
    
    # Derive values
    dj = get_dj_short_name(assigned_dj)
    
    # Build event details
    title = build_event_title(client, has_planner, dj, assigned_dj2)
    location = build_location(venue_name, venue_street, venue_city_state_zip)
    
    # Use test email, real DJ email, or None for Unknown/Unassigned
    if dj in ("Unknown", "Unassigned"):
        dj_email = None
    elif test_mode:
        dj_email = TEST_EMAIL
    else:
        dj_email = DJ_EMAILS.get(dj)
    
    # Convert times (with DJ arrival/departure offsets)
    (start_h, start_m), (end_h, end_m) = convert_to_24hr(setup_time, clear_time, sound_type, has_ceremony_sound)
    
    start_date = format_applescript_date(event_date, start_h, start_m)
    end_date = format_applescript_date(event_date, end_h, end_m)
    
    # Display what we're creating
    print(f"\nCreating calendar event:")
    print(f"  Title:    {title}")
    print(f"  Start:    {start_date}")
    print(f"  End:      {end_date}")
    print(f"  Location: {location}")
    if dj_email:
        print(f"  DJ:       {dj} ({dj_email})")
    elif dj == "Unassigned":
        dj2_display = get_dj_short_name(assigned_dj2) if assigned_dj2 else "?"
        print(f"  DJ:       Unassigned ({dj2_display} responsible, no invitee)")
    else:
        print(f"  DJ:       Unassigned (no invitee)")
    if test_mode and dj not in ("Unknown", "Unassigned"):
        print(f"  [TEST MODE - invite redirected to {TEST_EMAIL}]")
    
    # Check for calendar conflicts before creating event
    if dj in ("Unknown", "Unassigned"):
        initials_bracket = f"[{get_unassigned_initials(assigned_dj2)}]" if dj == "Unassigned" and assigned_dj2 else "[UP]"
    else:
        initials_bracket = f"[{DJ_INITIALS.get(dj, 'UP')}]"

    conflicts = check_calendar_conflicts(event_date, initials_bracket)
    if conflicts:
        print(f"\n⚠️  CONFLICT DETECTED — existing event(s) with {initials_bracket} on this date:")
        for c in conflicts:
            print(f"     • {c}")
        print(f"\n  Skipping event creation to avoid duplicate.")
        return False

    # Create the event
    success, error = create_calendar_event(title, start_date, end_date, location, dj_email)
    
    if success:
        print(f"\n✓ Event created successfully in '{CALENDAR_NAME}' calendar")
    else:
        print(f"\n✗ Failed to create event: {error}")
    
    return success


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 gig_to_calendar.py booking.json")
        print("       python3 gig_to_calendar.py booking.json --test")
        sys.exit(1)
    
    json_file = sys.argv[1]
    test_mode = '--test' in sys.argv
    
    try:
        with open(json_file, 'r') as f:
            booking_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{json_file}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{json_file}': {e}")
        sys.exit(1)
    
    success = process_booking(booking_data, test_mode)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
