#!/usr/bin/env python3
"""
Assign DJ
=========
Moves a booking that Paul has just assigned in FileMaker from TBA to the DJ in
the other two systems: the Availability Matrix and the Gigs calendar.

Paul's half, done by hand in FileMaker first: DJ1 set to the DJ, DJ2 cleared,
a dated line added to the notes, record saved. Then this button:

  Phase 1 (Validate):  DJ1 is set; the date row exists; the TBA cell holds a
                       BOOKED; the calendar has a [U?] event for this client;
                       the DJ is not already the date's backup (a BACKUP cell is
                       never rewritten to BOOKED, Paul 2026-11-01).
                       Both systems or neither, so nothing is written unless
                       both checks pass. A second press is a no-op.
  Phase 2 (Matrix):    TBA steps down one (BOOKED x 2 -> BOOKED -> blank, AAG
                       kept); the DJ's cell becomes BOOKED whatever it held
                       (an OK in anyone's cell is overwritten, Paul 2026-11-01),
                       or BOOKED x 2 if they already have one that day.
  Phase 3 (Calendar):  The [U?] bracket in the title becomes the DJ's initials,
                       the rest of the title is untouched, and the DJ's BIG FUN
                       address is added as an attendee, which sends the invite.
  Phase 4 (Backup):    Book Event skips its backup dialog for an unassigned
                       booking, so a TBA event never had one. The same dialog
                       runs here: candidates by the matrix rules, calendar
                       conflict check, BACKUP in the matrix, all-day BACKUP DJ
                       event with the invite. Skip or Cancel leaves the
                       assignment in place. A date that already has a backup
                       is reported, not changed.

  Phase 5 (Paul only): the booking email folder on love2tap, BIG FUN/<year>/
                       <MM-DD-YY: names>, through Book Event's function. The
                       log says whether it was really created.

No Google Form, no nurture emails: the two emails (couple reply, DJ handoff)
stay by hand.

Usage:
  python3 assign_dj.py /tmp/gig_assign.json            # production
  python3 assign_dj.py /tmp/gig_assign.json --dry-run  # validate, write nothing
  python3 assign_dj.py /tmp/gig_assign.json --test     # real writes, invite to paul@
"""

import argparse
import os
import re
import sys

import calendar_read
from calendar_app import CalendarApp
from dj_core import BACKUP_ELIGIBLE_DJS, COLUMN_MAPS, DJ_EMAILS, get_dj_initials
from gig_booking_manager import (
    CALENDAR_NAME,
    DEFAULT_CREDENTIALS_PATH,
    MockSheetsClient,
    SheetsClient,
    calculate_spots_remaining,
    can_backup,
    check_calendar_conflicts,
    check_existing_backup,
    create_allday_backup_event,
    create_email_folder,
    increment_booked,
    parse_booking_data,
    show_backup_dialog,
    show_notification,
    show_warning_dialog,
    split_backup_hits,
)

TEST_INVITEE = "paul@bigfundj.com"
LOG_PATH = "/tmp/bigfun-assign-dj.log"

# "[UP] Client", "[UH] Client (planner)": U plus the booker's initial, nothing else
# in the bracket. "[UP/SB] ..." (a joint unassigned setup) deliberately does not match.
_UNASSIGNED_RE = re.compile(r"^\[U[A-Z]\]\s")


# =============================================================================
# PURE PIECES
# =============================================================================

def is_backup_cell(current_value):
    """True when the cell holds BACKUP, alone or compound ('DAD, BACKUP')."""
    return "BACKUP" in [p.strip().upper() for p in (current_value or "").split(",")]


# Default availability markers a backup write replaces outright; anything else
# ('DAD-DUTY') is kept and BACKUP appended. Same set as Book Event.
_BACKUP_REPLACES = {"", "OUT", "OK", "DAD", "STANFORD", "LAST", "OK TO BACKUP", "BACKUP"}


def backup_cell_value(current_value):
    v = (current_value or "").strip()
    if v.upper() in _BACKUP_REPLACES:
        return "BACKUP"
    return f"{v}, BACKUP"


def backup_candidates(row_data, assigned_dj, year, date_obj, col_map, bold_lookup):
    """
    (dj, note) pairs for the backup dialog: the year's eligible DJs, minus the
    one just assigned, filtered through can_backup. bold_lookup(dj) answers the
    Woody plain-vs-bold OUT question and is only called for that case.
    """
    out = []
    for cand in BACKUP_ELIGIBLE_DJS.get(year, BACKUP_ELIGIBLE_DJS[2026]):
        if cand == assigned_dj or cand not in col_map:
            continue
        cell = row_data.get(cand, "") or ""
        bold = False
        if cand == "Woody" and cell.strip().upper() == "OUT":
            bold = bool(bold_lookup(cand))
        ok, note = can_backup(cand, cell, bold, date_obj, year)
        if ok:
            out.append((cand, note))
    return out


def decrement_tba(current_value):
    """
    Step the TBA cell down one booking.
    'BOOKED' -> '', 'BOOKED x 2' -> 'BOOKED', 'BOOKED x 3' -> 'BOOKED x 2',
    'BOOKED, AAG' -> 'AAG', 'BOOKED x 2, AAG' -> 'BOOKED, AAG'.
    Raises ValueError when there is no BOOKED to move.
    """
    parts = [p.strip() for p in (current_value or "").split(",") if p.strip()]
    aag_parts = [p for p in parts if p.upper() == "AAG"]
    booked_parts = [p for p in parts if p.upper() != "AAG"]
    if len(booked_parts) != 1:
        raise ValueError(f"TBA cell has no BOOKED to move: '{current_value}'")
    bp = booked_parts[0].upper()
    if bp == "BOOKED":
        new_booked = ""
    elif bp.startswith("BOOKED X "):
        try:
            n = int(bp.replace("BOOKED X ", ""))
        except ValueError:
            raise ValueError(f"TBA cell is not a count I understand: '{current_value}'")
        new_booked = "BOOKED" if n - 1 == 1 else f"BOOKED x {n - 1}"
    else:
        raise ValueError(f"TBA cell has no BOOKED to move: '{current_value}'")
    return ", ".join(p for p in [new_booked] + aag_parts if p)


def assigned_cell_value(current_value):
    """
    The DJ's cell after assignment. BOOKED replaces anything that is not already
    a booking (blank, OK, RESERVED, OUT...); an existing BOOKED increments.
    """
    if (current_value or "").strip().upper().startswith("BOOKED"):
        return increment_booked(current_value)
    return "BOOKED"


def is_unassigned_title(title):
    return bool(_UNASSIGNED_RE.match((title or "").strip()))


def retitle(title, new_bracket):
    """'[UP] Client (planner)' -> '[HK] Client (planner)'. Only an unassigned title."""
    title = title.strip()
    if not is_unassigned_title(title):
        raise ValueError(f"Not an unassigned calendar title: '{title}'")
    return new_bracket + title[title.index("]") + 1:]


def pick_unassigned_event(listing, client_display):
    """
    From [(uid, summary), ...] on the date, the one [U?] event for this client.
    None when there is none. ValueError when more than one matches.
    """
    want = client_display.strip().lower()
    hits = [(uid, t) for uid, t in listing if is_unassigned_title(t) and want in t.lower()]
    if len(hits) > 1:
        raise ValueError("More than one unassigned event matches "
                         f"'{client_display}': " + "; ".join(t for _, t in hits))
    return hits[0] if hits else None


def find_assigned_event(listing, bracket, client_display):
    want = client_display.strip().lower()
    for uid, t in listing:
        if t.strip().startswith(bracket) and want in t.lower():
            return uid, t
    return None


# =============================================================================
# CALENDAR: read over CalDAV, edit in Calendar.app by `event id` through
# calendar_app.CalendarApp (the only path that carries attendees; it also
# launches Calendar.app when closed). A `whose` clause walks the whole Gigs
# calendar: 30s for a day listing, and `first event whose uid is` ran 1m54s and
# then failed on a valid uid (measured 2026-11-02).
# =============================================================================


# =============================================================================
# THE FLOW
# =============================================================================

def assign(booking, sheets, app=None, fetch_day=calendar_read.fetch_day_events,
           dry_run=False, test_mode=False,
           log=print, warn=None, notify=None,
           choose_backup=show_backup_dialog, conflicts=check_calendar_conflicts,
           make_backup_event=create_allday_backup_event,
           make_email_folder=create_email_folder):
    """
    Returns True when the booking is now on the DJ in both systems (or already
    was), False when it halted with a message. Raises on unexpected errors.
    `warn` and `notify` are the user-facing dialogs; None means print only.
    """
    def halt(msg):
        log(f"HALTED: {msg}")
        if warn:
            warn(msg)
        return False

    dj = booking["dj_short_name"]
    bracket = booking["dj_initials_bracket"]
    client = booking["client_display"]
    date_obj = booking["date"]
    year = booking["year"]
    log(f"{booking['date_display']} {client} at {booking['venue_name']} -> {dj} {bracket}")

    # ---- Phase 1: validate --------------------------------------------------
    if booking["is_unassigned"]:
        return halt("DJ1 is still Unassigned in FileMaker. Set the DJ, save the record, then press again.")
    col_map = COLUMN_MAPS.get(year)
    if not col_map:
        return halt(f"No column mapping defined for year {year}.")
    if dj not in col_map:
        return halt(f"{dj} does not have a column in the {year} matrix.")

    sheets.init()
    row_num = sheets.find_date_row(date_obj, year)
    if row_num is None:
        return halt(f"{booking['date_display']} has no row in the {year} matrix. "
                    "An unassigned booking always has one; check the sheet.")
    row_data = sheets.get_row_data(row_num, year)
    tba_value = row_data.get("TBA", "") or ""
    dj_value = row_data.get(dj, "") or ""
    log(f"Matrix row {row_num}: TBA='{tba_value}', {dj}='{dj_value}'")
    if is_backup_cell(dj_value):
        return halt(f"{dj} is the backup on {booking['date_display']} (matrix cell '{dj_value}'). "
                    "A BACKUP cell is never changed to BOOKED by this button. Nothing was written. "
                    f"Move the backup to another DJ first, then press again.")

    # CalendarReadError propagates: nothing has been written yet, and main()
    # turns it into the error dialog. It never reads as "nothing on the calendar".
    listing = fetch_day(CALENDAR_NAME, date_obj.date())
    try:
        target = pick_unassigned_event(listing, client)
    except ValueError as e:
        return halt(str(e))
    tba_has_booking = "BOOKED" in tba_value.upper()

    if target is None and not tba_has_booking:
        done = find_assigned_event(listing, bracket, client)
        if done:
            log(f"Already assigned: '{done[1]}' and TBA is '{tba_value}'. Nothing to do.")
            if notify:
                notify("Already assigned", f"{done[1]} is on {dj} in both systems.")
            return True
        return halt(f"Nothing to move for {client} on {booking['date_display']}: TBA is "
                    f"'{tba_value}' and the calendar has no [U?] event for them.\n\n"
                    "Calendar that day: " + ("; ".join(t for _, t in listing) or "nothing"))
    if target is None:
        return halt(f"TBA shows '{tba_value}' but the calendar has no unassigned event for "
                    f"{client} on {booking['date_display']}.\n\nCalendar that day: "
                    + ("; ".join(t for _, t in listing) or "nothing")
                    + "\n\nNothing was written. Fix the calendar title, then press again.")
    if not tba_has_booking:
        return halt(f"The calendar has '{target[1]}' but TBA is '{tba_value}' on "
                    f"{booking['date_display']}. Nothing was written. Run the crosscheck.")

    uid, old_title = target
    new_tba = decrement_tba(tba_value)
    new_cell = assigned_cell_value(dj_value)
    new_title = retitle(old_title, bracket)
    invitee = TEST_INVITEE if test_mode else DJ_EMAILS[dj]
    log(f"Plan: TBA '{tba_value}' -> '{new_tba}'; {dj} '{dj_value}' -> '{new_cell}'; "
        f"'{old_title}' -> '{new_title}' + invite {invitee}")

    existing_backup = check_existing_backup(row_data)
    candidates = backup_candidates(
        row_data, dj, year, date_obj, col_map,
        bold_lookup=lambda cand: sheets.is_cell_bold(year, row_num, col_map[cand]))
    if existing_backup:
        log(f"Backup already assigned: {existing_backup}")
    else:
        log("Backup candidates: " + (", ".join(
            c + (f" ({n})" if n else "") for c, n in candidates) or "none"))

    if dry_run:
        log("[DRY RUN] No writes, no backup dialog.")
        return True

    # ---- Phase 2: matrix ----------------------------------------------------
    sheets.write_cell(row_num, col_map["TBA"], new_tba, year)
    sheets.write_cell(row_num, col_map[dj], new_cell, year)
    log(f"Matrix: TBA -> '{new_tba}', {dj} -> '{new_cell}'")

    # ---- Phase 3: calendar --------------------------------------------------
    app = app or CalendarApp()
    try:
        app.retitle_and_invite(uid, new_title, invitee)
    except Exception as e:
        return halt(f"Matrix is updated but the calendar change failed:\n\n{e}\n\n"
                    f"Retitle '{old_title}' to '{new_title}' and invite {invitee} by hand, "
                    "or the crosscheck will show the gap.")
    log(f"Calendar: '{new_title}', invited {invitee}")

    # ---- Phase 4: backup ----------------------------------------------------
    # The assignment above stands whatever happens here.
    after = dict(row_data, TBA=new_tba, **{dj: new_cell})
    spots = calculate_spots_remaining(after, year, date_obj)
    context = f"{booking['venue_name']} -> {dj}"
    choice = choose_backup(booking["date_display"], spots, candidates, existing_backup, context)
    backup_line = ""
    if existing_backup:
        backup_line = f"backup already {existing_backup}"
    elif choice == "STOP":
        log("Backup: cancelled")
        backup_line = "no backup (cancelled)"
    elif not choice:
        log("Backup: skipped")
        backup_line = "no backup (skipped)"
    else:
        backup_line = _assign_backup(choice, booking, sheets, row_num, col_map, after,
                                     test_mode, log, warn, conflicts, make_backup_event)

    # ---- Phase 5: Paul's email folder ---------------------------------------
    # create_email_folder swallows its own errors and returns None, so the
    # return value is the only truth about whether the folder exists.
    folder_line = ""
    if dj == "Paul":
        try:
            created = make_email_folder(booking, dry_run=False)
        except Exception as e:
            created = None
            log(f"Email folder: not created ({e})")
        if created:
            log(f"Email folder: created '{created}'")
            folder_line = f"\nemail folder {created}"
        else:
            log("Email folder: not created, make it by hand")
            folder_line = "\nemail folder NOT created"

    if notify:
        notify("DJ assigned", f"{new_title}\nMatrix TBA -> {dj}, invite sent to {invitee}\n{backup_line}{folder_line}")
    return True


def _assign_backup(backup_dj, booking, sheets, row_num, col_map, row_data,
                   test_mode, log, warn, conflicts, make_backup_event):
    """Conflict check, matrix BACKUP, all-day calendar event. Returns a one-line summary."""
    year = booking["year"]
    date_obj = booking["date"]
    bracket = f"[{get_dj_initials(backup_dj)}]"
    try:
        clash = conflicts(date_obj, bracket)
    except Exception as e:
        msg = (f"Calendar check failed for backup {bracket} on {booking['date_display']}:\n\n{e}\n\n"
               "Backup NOT assigned (not checked, so not written). The DJ assignment is intact.")
        log(f"Backup: calendar check failed for {backup_dj}: {e}")
        if warn:
            warn(msg)
        return "no backup (calendar check failed)"
    # A hand-made "[WM] BACKUP" alone means the backup is already on the calendar:
    # just fill in the Matrix.
    already_backup, clash = split_backup_hits(clash)
    if clash:
        msg = (f"Calendar conflict for backup {bracket} on {booking['date_display']}:\n\n"
               + "\n".join(clash) + "\n\nBackup NOT assigned. The DJ assignment is intact.")
        log(f"Backup: calendar conflict for {backup_dj}: {clash}")
        if warn:
            warn(msg)
        return "no backup (calendar conflict)"

    new_val = backup_cell_value(row_data.get(backup_dj, ""))
    sheets.write_cell(row_num, col_map[backup_dj], new_val, year)
    log(f"Matrix: {backup_dj} -> '{new_val}'")
    if already_backup:
        log(f"Calendar: backup already on the calendar ({already_backup[0]}), no new event")
        return f"backup {backup_dj} (calendar event already there)"
    try:
        title = make_backup_event(date_obj, backup_dj, test_mode)
    except Exception as e:
        msg = (f"Matrix shows {backup_dj} as BACKUP but the calendar event failed:\n\n{e}\n\n"
               f"Create the all-day '{bracket} BACKUP DJ' event by hand, or the crosscheck will show the gap.")
        log(f"Backup: calendar event failed for {backup_dj}, create by hand: {e}")
        if warn:
            warn(msg)
        return f"backup {backup_dj} (matrix only, calendar by hand)"
    log(f"Calendar: created '{title}'")
    return f"backup {backup_dj}"


def main():
    parser = argparse.ArgumentParser(description="Assign DJ: move a TBA booking to the DJ in the matrix and calendar")
    parser.add_argument("json_path", help="Booking JSON from the FileMaker page (FM or clean format)")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, write nothing")
    parser.add_argument("--test", action="store_true", help="Real writes, but the calendar invite goes to paul@")
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS_PATH)
    args = parser.parse_args()

    if not os.path.exists(args.json_path):
        print(f"Error: File not found: {args.json_path}")
        sys.exit(1)

    lines = []

    def log(msg):
        print(msg)
        lines.append(msg)

    log("Python started")
    booking = parse_booking_data(args.json_path)
    # The dry run reads the live matrix too: assign() exits before any write,
    # so the validation it reports is against the real row, not a mock.
    sheets = SheetsClient(args.credentials) if os.path.exists(args.credentials) else MockSheetsClient()
    try:
        assign(booking, sheets, dry_run=args.dry_run, test_mode=args.test, log=log,
               warn=None if args.dry_run else show_warning_dialog,
               notify=None if args.dry_run else show_notification)
        sys.exit(0)
    except Exception as e:
        log(f"ERROR: {e}")
        if not args.dry_run:
            show_warning_dialog(f"Assign DJ error:\n\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
