"""
Post-Booking Nurture Email Sender

Run manually on Tuesdays. Reads the Nurture Tracker Google Sheet, finds
emails due today (or past due), merges templates with couple data, sends
via SMTP, and marks rows as sent.

Usage:
    python3 nurture_sender.py
    python3 nurture_sender.py --dry-run
    python3 nurture_sender.py --date 2026-04-14
    python3 nurture_sender.py --credentials PATH
"""

import argparse
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText

from nurture_config import (
    DEFAULT_CREDENTIALS_PATH,
    SMTP_CREDENTIALS_PATH,
    EMAIL_SCHEDULE,
    TEMPLATES_DIR,
    NURTURE_COLUMNS,
    init_nurture_sheet,
    col_index,
)


def load_smtp_credentials(path=None):
    """Load SMTP credentials from JSON file.

    Expected format:
    {
        "host": "smtp.ipage.com",
        "port": 465,
        "username": "paul@bigfundj.com",
        "password": "..."
    }

    One login is used for all sending. The From header is set per-email
    based on the assigned DJ (paul@ for Paul's couples, info@ for others).
    """
    creds_path = path or SMTP_CREDENTIALS_PATH
    if not os.path.exists(creds_path):
        print(f"  ERROR: SMTP credentials not found at {creds_path}")
        sys.exit(1)

    with open(creds_path, 'r') as f:
        return json.load(f)


def load_template(template_filename):
    """Load and parse a template file.

    Returns (subject, body) tuple.
    Template format:
        Subject: The subject line
        ---
        Body text with {{merge_fields}}
    """
    template_path = os.path.join(TEMPLATES_DIR, template_filename)

    if not os.path.exists(template_path):
        print(f"  ⚠️  Template not found: {template_path}")
        return None, None

    with open(template_path, 'r') as f:
        content = f.read()

    parts = content.split('---', 1)
    if len(parts) != 2:
        print(f"  ⚠️  Template missing --- separator: {template_filename}")
        return None, None

    header = parts[0].strip()
    body = parts[1].strip()

    subject = ""
    for line in header.split('\n'):
        if line.startswith('Subject:'):
            subject = line[len('Subject:'):].strip()
            break

    return subject, body


def merge_template(body, couple_name, venue, dj_name=""):
    """Replace merge fields in template body with actual values."""
    merged = body.replace('{{couple_names}}', couple_name)
    merged = merged.replace('{{venue}}', venue if venue else 'your venue')
    merged = merged.replace('{{dj_name}}', dj_name if dj_name else '')
    return merged


def send_email(sender, recipients, subject, body, smtp_creds, dry_run=False):
    """Send a plain-text email via SMTP.

    Uses a single SMTP login (from smtp_creds) and sets the From header
    to the sender address (paul@ or info@).

    Returns True on success, False on failure.
    """
    if dry_run:
        print(f"    [DRY RUN] Would send:")
        print(f"      From:    {sender}")
        print(f"      To:      {', '.join(recipients)}")
        print(f"      Subject: {subject}")
        preview = body.split('\n')[:3]
        for line in preview:
            print(f"      > {line}")
        print(f"      ... ({len(body.split(chr(10)))} lines total)")
        return True

    host = smtp_creds['host']
    port = smtp_creds.get('port', 465)
    username = smtp_creds['username']
    password = smtp_creds['password']

    msg = MIMEText(body, 'plain')
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)
            server.starttls()

        server.login(username, password)
        server.sendmail(sender, recipients, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"    ERROR: SMTP send failed: {e}")
        return False


def get_email_config(email_num):
    """Look up the template filename and subject for a given email number."""
    for email in EMAIL_SCHEDULE:
        if email['num'] == email_num:
            return email['template'], email['subject']
    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Send due nurture emails and update the tracker sheet."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be sent without actually sending")
    parser.add_argument("--preview", action="store_true",
                        help="Show full merged emails before sending, with option to proceed")
    parser.add_argument("--date",
                        help="Override today's date (YYYY-MM-DD format, for testing)")
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS_PATH,
                        help="Path to Google credentials JSON")
    parser.add_argument("--smtp-credentials", default=SMTP_CREDENTIALS_PATH,
                        help="Path to SMTP credentials JSON")

    args = parser.parse_args()

    # Determine "today"
    if args.date:
        try:
            today = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            print(f"  ERROR: Invalid date format: {args.date} (expected YYYY-MM-DD)")
            sys.exit(1)
    else:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"\n{'=' * 60}")
    print(f"  NURTURE EMAIL SENDER")
    print(f"{'=' * 60}")
    print(f"\n  Date: {today.strftime('%A, %B %d, %Y')}")

    if today.weekday() != 1 and not args.date:
        print(f"  ℹ️  Today is not Tuesday. Run with --date to override.\n")

    # Load SMTP credentials (skip in dry-run)
    smtp_creds = None
    if not args.dry_run:
        smtp_creds = load_smtp_credentials(args.smtp_credentials)

    # Connect to sheet
    print(f"  Connecting to Nurture Tracker...")
    try:
        worksheet = init_nurture_sheet(args.credentials)
    except Exception as e:
        print(f"  ERROR: Could not connect to Nurture Tracker: {e}")
        sys.exit(1)

    # Read all rows
    all_rows = worksheet.get_all_values()
    if len(all_rows) <= 1:
        print(f"  ℹ️  No data rows in the sheet.\n")
        return

    header = all_rows[0]
    data_rows = all_rows[1:]

    # Find due rows
    status_col = col_index("Status") - 1
    send_date_col = col_index("Scheduled Send") - 1
    due_rows = []

    for i, row in enumerate(data_rows):
        if row[status_col].strip().lower() != 'pending':
            continue

        send_date_str = row[send_date_col].strip()
        try:
            send_date = datetime.strptime(send_date_str, '%m/%d/%Y')
        except ValueError:
            continue

        if send_date <= today:
            due_rows.append((i + 2, row))  # +2 for 1-indexed + header row

    if not due_rows:
        print(f"  ℹ️  No emails due today.\n")
        return

    print(f"  Found {len(due_rows)} email(s) due.\n")

    # Process each due row
    sent_count = 0
    error_count = 0
    preview_queue = []
    couple_name_col = col_index("Couple Name") - 1
    email_col = col_index("Email") - 1
    venue_col = col_index("Venue") - 1
    email_num_col = col_index("Email #") - 1
    topic_col = col_index("Email Topic") - 1
    sender_col = col_index("Sender") - 1
    dj_name_col = col_index("DJ Name") - 1
    sent_date_col = col_index("Sent Date") - 1

    for sheet_row, row in due_rows:
        couple_name = row[couple_name_col]
        email_str = row[email_col]
        venue = row[venue_col]
        email_num = int(row[email_num_col])
        topic = row[topic_col]
        sender = row[sender_col]
        dj_name = row[dj_name_col]

        print(f"  #{email_num} {topic}")
        print(f"    Couple: {couple_name}")

        # Get recipients
        recipients = [e.strip() for e in email_str.split(',') if e.strip()]
        if not recipients:
            print(f"    ⚠️  No email address. Skipping.")
            error_count += 1
            continue

        # Load template
        template_file, config_subject = get_email_config(email_num)
        if not template_file:
            print(f"    ⚠️  No template defined for email #{email_num}. Skipping.")
            error_count += 1
            continue

        _, body = load_template(template_file)
        if not body:
            error_count += 1
            continue

        # Merge body and subject
        body = merge_template(body, couple_name, venue, dj_name)
        subject = config_subject.replace('{{venue}}', venue if venue else 'your venue')

        # Preview mode: show full email and collect for batch send
        if args.preview:
            print(f"    From:    {sender}")
            print(f"    To:      {', '.join(recipients)}")
            print(f"    Subject: {subject}")
            print(f"    {'─' * 50}")
            for line in body.split('\n'):
                print(f"    {line}")
            print(f"    {'─' * 50}")
            print()
            preview_queue.append({
                'sheet_row': sheet_row,
                'sender': sender,
                'recipients': recipients,
                'subject': subject,
                'body': body,
                'couple_name': couple_name,
                'email_num': email_num,
            })
            continue

        # Send
        success = send_email(sender, recipients, subject, body, smtp_creds,
                             dry_run=args.dry_run)

        if success:
            sent_count += 1
            # Update sheet
            if not args.dry_run:
                try:
                    worksheet.update_cell(sheet_row, col_index("Status"), 'sent')
                    worksheet.update_cell(sheet_row, col_index("Sent Date"),
                                          today.strftime('%m/%d/%Y'))
                    print(f"    ✓ Sent and marked in sheet")
                except Exception as e:
                    print(f"    ⚠️  Sent but failed to update sheet: {e}")
            else:
                print(f"    [DRY RUN] Would mark as sent")
        else:
            error_count += 1

        print()

    # Preview mode: prompt to send
    if args.preview and preview_queue:
        print(f"{'=' * 60}")
        print(f"  {len(preview_queue)} email(s) ready to send.")
        print(f"{'=' * 60}")
        answer = input("\n  Send all? (yes/no): ").strip().lower()

        if answer in ('yes', 'y'):
            if not smtp_creds:
                smtp_creds = load_smtp_credentials(args.smtp_credentials)

            for item in preview_queue:
                success = send_email(
                    item['sender'], item['recipients'],
                    item['subject'], item['body'], smtp_creds
                )
                if success:
                    sent_count += 1
                    try:
                        worksheet.update_cell(item['sheet_row'], col_index("Status"), 'sent')
                        worksheet.update_cell(item['sheet_row'], col_index("Sent Date"),
                                              today.strftime('%m/%d/%Y'))
                        print(f"  ✓ #{item['email_num']} {item['couple_name']}")
                    except Exception as e:
                        print(f"  ⚠️  #{item['email_num']} {item['couple_name']}: sent but sheet update failed ({e})")
                else:
                    error_count += 1
            print()
        else:
            print("\n  Canceled. No emails sent.\n")
            return

    # Summary
    print(f"{'=' * 60}")
    print(f"  Summary: {sent_count} sent, {error_count} error(s)")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
