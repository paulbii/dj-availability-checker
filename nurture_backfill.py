"""
Post-Booking Nurture Email Backfill

One-time script to populate the Nurture Tracker with existing bookings.
Queries the multi-day API endpoint, filters to wedding couples assigned
to Paul or unassigned, and creates nurture schedule rows.

Usage:
    python3 nurture_backfill.py --dry-run
    python3 nurture_backfill.py
    python3 nurture_backfill.py --credentials PATH
"""

import argparse
import requests
import sys
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from nurture_config import (
    DEFAULT_CREDENTIALS_PATH,
    HARD_STOP_MONTHS,
    calculate_send_dates,
    determine_sender,
    get_recipients,
    init_nurture_sheet,
    check_duplicate,
)

GIG_DATABASE_MD_URL = 'https://database.bigfundj.com/bigfunadmin/availabilityMDjson.php'


def fetch_all_bookings(start_date, end_date):
    """Fetch all bookings from start_date to end_date using the multi-day endpoint.

    Steps through the date range in 7-day jumps. Each call returns ±3 days,
    so 7-day steps give complete coverage with no gaps.

    Returns a dict keyed by (event_date, venue_name, client_name) to deduplicate
    overlapping results from adjacent calls.
    """
    bookings = {}
    current = start_date
    call_count = 0

    while current <= end_date:
        date_str = f"{current.month}/{current.day}/{current.year}"
        url = f"{GIG_DATABASE_MD_URL}?date={date_str}"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                results = response.json()
                for booking in results:
                    key = (
                        booking.get('event_date', ''),
                        booking.get('venue_name', ''),
                        booking.get('client_name', ''),
                    )
                    if key not in bookings:
                        bookings[key] = booking
            call_count += 1
        except Exception as e:
            print(f"  ⚠️  API call failed for {date_str}: {e}")

        current += timedelta(days=7)

        # Brief pause every 10 calls to be polite to the server
        if call_count % 10 == 0:
            time.sleep(0.5)

    return bookings


def is_wedding(client_name):
    """Check if a booking is likely a wedding based on client name containing ' and '."""
    return ' and ' in client_name


def is_paul(assigned_dj):
    """Check if the DJ is Paul (soft launch filter -- Paul's couples only)."""
    dj_lower = assigned_dj.lower()
    first_name = dj_lower.split()[0] if dj_lower else ''
    return first_name == 'paul'


def main():
    parser = argparse.ArgumentParser(
        description="Backfill nurture emails for existing wedding bookings."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be added without writing to the sheet")
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS_PATH,
                        help="Path to Google credentials JSON")

    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  NURTURE EMAIL BACKFILL")
    print(f"{'=' * 60}\n")

    if args.dry_run:
        print("  MODE: DRY RUN (no writes)\n")

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    hard_stop_date = today + relativedelta(months=HARD_STOP_MONTHS)
    end_date = datetime(2027, 12, 31)

    print(f"  Date range: {hard_stop_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}")
    print(f"  Filters: weddings only, Paul's couples only\n")

    # Fetch all bookings
    print("  Fetching bookings from API...")
    all_bookings = fetch_all_bookings(hard_stop_date, end_date)
    print(f"  ✓ {len(all_bookings)} unique bookings found\n")

    # Filter
    eligible = []
    for key, booking in all_bookings.items():
        client_name = booking.get('client_name', '')
        assigned_dj = booking.get('assigned_dj', '')
        event_date_str = booking.get('event_date', '')

        if not is_wedding(client_name):
            continue

        if not is_paul(assigned_dj):
            continue

        try:
            event_date = datetime.strptime(event_date_str, '%Y-%m-%d')
        except ValueError:
            continue

        # Must be at least 2 months out
        if event_date < hard_stop_date:
            continue

        booking['event_date_obj'] = event_date
        eligible.append(booking)

    # Sort by event date
    eligible.sort(key=lambda b: b['event_date_obj'])

    print(f"  {len(eligible)} eligible wedding(s) for nurture emails:\n")

    if not eligible:
        print("  Nothing to backfill.\n")
        return

    for b in eligible:
        dj_short = b['assigned_dj'].split()[0] if b['assigned_dj'] else 'Unassigned'
        print(f"    {b['event_date']}  {b['client_name'][:40]:<40}  {dj_short:<12}  {b['venue_name'][:30]}")

    print()

    # Connect to sheet
    worksheet = None
    if not args.dry_run:
        print("  Connecting to Nurture Tracker...")
        try:
            worksheet = init_nurture_sheet(args.credentials)
            print("  ✓ Connected\n")
        except Exception as e:
            print(f"  ERROR: Could not connect: {e}")
            sys.exit(1)

    # Build and write rows
    total_rows = 0
    skipped_couples = 0
    duplicates = 0

    for booking in eligible:
        event_date = booking['event_date_obj']
        client_name = booking['client_name']
        venue = booking['venue_name']
        assigned_dj = booking['assigned_dj']
        email1 = booking.get('email1', '')
        email2 = booking.get('email2', '')

        dj_short = assigned_dj.split()[0] if assigned_dj else 'Unassigned'

        # Calculate schedule using today as the "booking date" for backfill
        scheduled = calculate_send_dates(today, event_date)

        if not scheduled:
            skipped_couples += 1
            continue

        # Build rows
        recipients = get_recipients(email1, email2)
        email_str = ", ".join(recipients) if recipients else ""
        sender = determine_sender(dj_short)
        event_date_str = event_date.strftime('%m/%d/%Y')
        booking_date_str = today.strftime('%m/%d/%Y')

        rows = []
        for email in scheduled:
            rows.append([
                client_name,
                email_str,
                venue,
                event_date_str,
                booking_date_str,
                email['num'],
                email['topic'],
                email['send_date'].strftime('%m/%d/%Y'),
                'pending',
                '',
                sender,
                dj_short if dj_short != 'Unassigned' else '',
                'Backfill',
            ])

        if args.dry_run:
            print(f"  {client_name}: {len(rows)} email(s)")
            for email in scheduled:
                print(f"    #{email['num']}  {email['send_date'].strftime('%b %d')}  {email['topic']}")
            total_rows += len(rows)
        else:
            # Check for duplicates
            if check_duplicate(worksheet, client_name, event_date_str):
                duplicates += 1
                continue

            try:
                worksheet.append_rows(rows, value_input_option='USER_ENTERED')
                total_rows += len(rows)
                print(f"  ✓ {client_name}: {len(rows)} email(s)")
            except Exception as e:
                print(f"  ⚠️  {client_name}: failed ({e})")

            # Brief pause between writes
            time.sleep(0.3)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  BACKFILL SUMMARY")
    print(f"{'=' * 60}")
    action = "Would add" if args.dry_run else "Added"
    print(f"  {action} {total_rows} nurture email row(s)")
    print(f"  {len(eligible) - skipped_couples - duplicates} couple(s) scheduled")
    if skipped_couples:
        print(f"  {skipped_couples} couple(s) skipped (no emails fit their timeline)")
    if duplicates:
        print(f"  {duplicates} couple(s) skipped (already in tracker)")
    print()


if __name__ == "__main__":
    main()
