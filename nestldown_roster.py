#!/usr/bin/env python3
"""
Nestldown DJ Roster Page Generator

Reads Nestldown events from the Gigs calendar via CalDAV, generates a styled
HTML roster page, and uploads it via FTP to bigfundj.com/CLIENTS/nestldown/.
"""

import re
from dj_core import DJ_INITIALS, DJ_EMAILS, DJ_PHONES, DJ_FULL_NAMES

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
