"""
Post-Booking Nurture Email Scheduler (Standalone)

Normally, nurture scheduling runs automatically as part of gig_booking_manager.py.
This standalone script is for:
  - Backfilling existing bookings that were created before the nurture system
  - Manual scheduling if the booking manager's nurture step was skipped
  - Testing schedule calculations with --dry-run

Usage:
    python3 nurture_scheduler.py booking.json
    python3 nurture_scheduler.py booking.json --dry-run
    python3 nurture_scheduler.py booking.json --email "maria@gmail.com" --email "jose@gmail.com"
    python3 nurture_scheduler.py booking.json --credentials PATH
"""

import argparse
import json
import os
import sys
from datetime import datetime

from nurture_config import (
    DEFAULT_CREDENTIALS_PATH,
    SHORT_BOOKER_MONTHS,
    EMAIL_SCHEDULE,
    calculate_send_dates,
    determine_sender,
    get_recipients,
    init_nurture_sheet,
    check_duplicate,
    col_index,
)


def parse_booking_for_nurture(booking_path, email_args=None):
    """Parse a booking JSON file and extract fields needed for nurture scheduling.

    Supports both FM format and clean format booking JSONs.
    Returns a dict with: couple_name, email1, email2, venue, event_date, dj_name
    """
    with open(booking_path, 'r') as f:
        data = json.load(f)

    # Detect format
    if 'FMclient' in data or 'FMeventDate' in data:
        # FM format
        couple_name = data.get('FMclient', '').strip()
        venue = data.get('FMvenue', '').strip()
        event_date_str = data.get('FMeventDate', '').strip()
        dj_name = data.get('FMDJ1', '').strip()
        email1 = data.get('FMemail1', '').strip()
        email2 = data.get('FMemail2', '').strip()
        event_type = data.get('FMeventType', '').strip()
    else:
        # Clean format
        couple_name = data.get('client_name', data.get('client', '')).strip()
        venue = data.get('venue_name', data.get('venue', '')).strip()
        event_date_str = data.get('event_date', '').strip()
        dj_name = data.get('assigned_dj', data.get('dj', '')).strip()
        email1 = data.get('email1', '').strip()
        email2 = data.get('email2', '').strip()
        event_type = data.get('event_type', '').strip()

    # CLI email overrides
    if email_args:
        if len(email_args) >= 1:
            email1 = email_args[0]
        if len(email_args) >= 2:
            email2 = email_args[1]

    # Parse event date - try common formats
    event_date = None
    for fmt in ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%m-%d-%Y'):
        try:
            event_date = datetime.strptime(event_date_str, fmt)
            break
        except ValueError:
            continue

    if not event_date:
        print(f"  ERROR: Could not parse event date: '{event_date_str}'")
        sys.exit(1)

    return {
        'couple_name': couple_name,
        'email1': email1,
        'email2': email2,
        'venue': venue,
        'event_date': event_date,
        'dj_name': dj_name,
        'event_type': event_type,
    }


def build_nurture_rows(booking, scheduled_emails):
    """Build the row data for the Nurture Tracker sheet.

    Returns a list of lists, each representing one row.
    """
    recipients = get_recipients(booking['email1'], booking['email2'])
    email_str = ", ".join(recipients) if recipients else ""
    sender = determine_sender(booking['dj_name'])
    event_date_str = booking['event_date'].strftime('%m/%d/%Y')
    booking_date_str = datetime.now().strftime('%m/%d/%Y')

    rows = []
    for email in scheduled_emails:
        row = [
            booking['couple_name'],                     # Couple Name
            email_str,                                  # Email
            booking['venue'],                           # Venue
            event_date_str,                             # Event Date
            booking_date_str,                           # Booking Date
            email['num'],                               # Email #
            email['topic'],                             # Email Topic
            email['send_date'].strftime('%m/%d/%Y'),    # Scheduled Send
            'pending',                                  # Status
            '',                                         # Sent Date
            sender,                                     # Sender
            booking['dj_name'] if booking['dj_name'] else '',  # DJ Name
            '',                                         # Notes
        ]
        rows.append(row)

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Schedule nurture emails for a newly booked couple."
    )
    parser.add_argument("booking_file", help="Path to the booking JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be scheduled without writing to the sheet")
    parser.add_argument("--email", action="append", dest="emails",
                        help="Email address for the couple (can be specified twice)")
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS_PATH,
                        help="Path to Google credentials JSON")

    args = parser.parse_args()

    # Parse booking
    print(f"\n{'=' * 60}")
    print(f"  NURTURE EMAIL SCHEDULER")
    print(f"{'=' * 60}\n")

    booking = parse_booking_for_nurture(args.booking_file, args.emails)

    print(f"  Couple:     {booking['couple_name']}")
    print(f"  Venue:      {booking['venue']}")
    print(f"  Event Date: {booking['event_date'].strftime('%B %d, %Y')}")
    print(f"  DJ:         {booking['dj_name'] or 'Unassigned'}")

    recipients = get_recipients(booking['email1'], booking['email2'])
    if recipients:
        print(f"  Email(s):   {', '.join(recipients)}")
    else:
        print(f"  ⚠️  No email addresses provided. Rows will be created without email.")

    print()

    # Check event type
    event_type = booking.get('event_type', '').lower()
    if event_type and event_type != 'wedding':
        print(f"  ℹ️  Event type is '{booking.get('event_type', '')}', not Wedding. Skipping.")
        print()
        return

    # Calculate lead time
    booking_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    lead_days = (booking['event_date'] - booking_date).days
    lead_months = lead_days / 30.44

    print(f"  Lead time:  {lead_days} days ({lead_months:.1f} months)")

    if lead_days < SHORT_BOOKER_MONTHS * 30:
        print(f"  ℹ️  Under {SHORT_BOOKER_MONTHS} months out. No nurture emails scheduled.")
        print()
        return

    # Calculate schedule
    scheduled = calculate_send_dates(booking_date, booking['event_date'])

    if not scheduled:
        print(f"  ℹ️  No emails qualify for this booking timeline.")
        print()
        return

    # Display schedule
    print(f"\n  Scheduled {len(scheduled)} of {len(EMAIL_SCHEDULE)} emails:\n")
    for email in scheduled:
        anchor_label = "after booking" if email['anchor'] == 'booking' else "before event"
        print(f"    #{email['num']}  {email['send_date'].strftime('%b %d, %Y')} (Tue)  "
              f"{email['topic']}")

    skipped = len(EMAIL_SCHEDULE) - len(scheduled)
    if skipped > 0:
        print(f"\n  ℹ️  {skipped} email(s) skipped (overlap, hard stop, or past due)")

    print()

    # Build rows
    rows = build_nurture_rows(booking, scheduled)

    if args.dry_run:
        print(f"  [DRY RUN] Would write {len(rows)} rows to Nurture Tracker sheet")
        print()
        return

    # Write to sheet
    print(f"  Writing to Nurture Tracker sheet...")

    try:
        worksheet = init_nurture_sheet(args.credentials)
    except Exception as e:
        print(f"  ERROR: Could not connect to Nurture Tracker sheet: {e}")
        sys.exit(1)

    # Check for duplicates
    event_date_str = booking['event_date'].strftime('%m/%d/%Y')
    if check_duplicate(worksheet, booking['couple_name'], event_date_str):
        print(f"  ⚠️  Nurture rows already exist for {booking['couple_name']} on "
              f"{event_date_str}. Skipping to avoid duplicates.")
        print(f"      Use --force to override (not yet implemented).")
        print()
        return

    try:
        worksheet.append_rows(rows, value_input_option='USER_ENTERED')
        print(f"  ✓ {len(rows)} rows written to Nurture Tracker")
    except Exception as e:
        print(f"  ERROR: Failed to write rows: {e}")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
