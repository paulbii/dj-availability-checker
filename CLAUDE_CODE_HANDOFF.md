# Claude Code Handoff — DJ Availability Checker

**Author:** Paul Burchfield (paulbii@gmail.com)
**Project:** Big Fun DJ — Availability Checker & Booking Automation
**Date:** March 2026
**Repo:** `paulbii/dj-availability-checker`

---

## 1. What We've Built

Everything below was built or significantly iterated on across our conversations. The system manages DJ scheduling for Big Fun DJ (~225 events/year) across three data sources: a Google Sheets availability matrix, a FileMaker Pro gig database, and a Google Sheets inquiry tracker.

### Availability Checker (daily-use tool)

| Artifact | Form | What It Does |
|----------|------|--------------|
| `check_dj.py` | Python script | Terminal-based availability checker with 7 menu options: single date, date range, min. availability, DJ-specific query, fully booked dates, turned-away inquiries, exit. Shared module called by year-specific wrappers. |
| `check_2026.py` / `check_2027.py` | Python wrappers | One-liners that call `check_dj.main("2026")` or `main("2027")`. |
| `check_dj_gui.py` | Python + PyWebView | Desktop GUI version with sidebar navigation, same functionality as terminal. |
| `check_2026_gui.py` / `check_2027_gui.py` | Python wrappers | GUI year wrappers. |
| `dj_app.py` | Streamlit app | Web version at `https://dj-availability-checker.streamlit.app`. 6 tabs matching terminal options. Exists mainly for the company owners to use. |
| `dj_core.py` | Python module | Shared business logic: DJ rules, column mappings, Google Sheets/FileMaker connections, availability calculations. Every other script imports from here. |

**Features added in our sessions:**

- **Clipboard copy**: When checking a date (Option 1 or Option 6), the date is automatically copied to clipboard in MM-DD-YY format with leading zeros. Works in terminal and GUI versions via `pbcopy`.
- **Turned-away inquiry lookup** (Option 6): Searches the Inquiry Tracker for resolution = "Full" on a given date. Results are color-coded by recency tier: green/REACH OUT (within 4 weeks), yellow/MAYBE (5–10 weeks), gray/STALE (older than 10 weeks). Each entry shows venue, inquiry date with relative age label (e.g., "2 weeks ago"), and decision date. Sorted most-recent-first. Added to all three versions (terminal, GUI, Streamlit).

### Gig Booking Manager (booking automation)

| Artifact | Form | What It Does |
|----------|------|--------------|
| `gig_booking_manager.py` | Python script | Three-phase booking automation: validate matrix → write BOOKED + assign backup → create calendar events + open Google Form. |
| `gig_booking_manager.scpt` | AppleScript | Extracts booking data from FileMaker in Safari, writes JSON to `/tmp/gig_booking.json`, calls the Python script. Triggered via Stream Deck. |

**Features added in our sessions:**

- **Venue context in backup dialog**: When the backup assigner prompts you to pick a DJ, it now shows the DJ name and venue for each booking on that date (fetched from gig DB JSON). Helps with geography-based decisions.
- **One booking per line in dialog**: Each booked event gets its own line in the AppleScript dialog instead of being crammed together.
- **Cancel-to-stop**: The AppleScript Cancel button now stops the entire script (returns "STOP"), while Skip moves to the next date. The prompt says "Cancel = stop script" so it's clear.

### Cancel Booking (new, built from scratch)

| Artifact | Form | What It Does |
|----------|------|--------------|
| `cancel_booking.py` | Python script | 5-step cancellation: parse booking → connect to matrix → validate BOOKED/RESERVED → restore default cell value + optionally remove backup → delete calendar events + open Google Form with "Canceled" status. |
| `cancel_booking.scpt` | AppleScript | Same Safari-extraction pattern as booking manager, calls `cancel_booking.py`. For Stream Deck. |

**Key design decisions:**

- Default cell values are computed by DJ + day of week (not formula restoration, since BOOKED already overwrote formulas): Woody=OUT on weekends, Stefano=OUT except Saturdays, Felipe=OUT on weekdays, others=blank.
- Backup DJ removal prompts via AppleScript dialog: "Keep Backup" / "Remove Backup".
- Calendar event deletion filters out BACKUP DJ and Hold events to avoid accidental deletion.
- Uses the same `parse_booking_data()` and `SheetsClient` from gig_booking_manager.py — no separate mock client.
- Inquiry Tracker convention for cancellations: same date for Inquiry Date and Decision Date (today), matching the "full at inquiry" pattern.

### Backup Tools

| Artifact | Form | What It Does |
|----------|------|--------------|
| `backup_assigner.py` | Python script | Scans matrix for future dates with bookings but no backup DJ. Shows AppleScript dialog per date with venue context. |
| `backup_stats.py` | Python script | Counts backup assignments per DJ for a given year. |

### Other Tools (pre-existing, not heavily modified in our sessions)

| Artifact | Form | What It Does |
|----------|------|--------------|
| `booking_comparator.py` | Python script | Cross-checks Gig Database, Availability Matrix, and Master Calendar for discrepancies. |
| `confirmation_forwarder.py` | Python script | Creates MailMaven email forward drafts for office and DJ after booking confirmation. |
| `dashboard.py` | Streamlit app | Operations dashboard with booking metrics and lead tracking. |

### Infrastructure

| Artifact | Form | What It Does |
|----------|------|--------------|
| `.github/workflows/keep-alive.yml` | GitHub Actions | Pings Streamlit app every 5 minutes to prevent sleep. Also monitored by UptimeRobot (Paul's existing account). |

### Documentation

| Artifact | Form | What It Does |
|----------|------|--------------|
| `DJ_SYSTEM_REFERENCE.md` | Markdown | Complete system reference covering all tools, configurations, rules, and file inventory. |
| `PROJECT_CONTEXT.md` | Markdown | Business context, DJ roster, system architecture, data sources, edge cases. |
| `SYSTEM_REFERENCE.md` | Markdown | Deep dive on availability checker architecture. |
| `COWORK_INTRO.md` | Markdown | Quick-start guide for AI assistants. |

---

## 2. How Paul Likes to Work

### Communication Style

- **Direct and efficient.** Doesn't want long explanations of what I'm about to do — just do it. "do it" or "yes" means proceed immediately.
- **Shows me output and asks "how does that look?"** — expects me to eyeball it and flag issues. Screenshot-driven feedback loop.
- **Corrects course quickly.** If something is wrong, he'll paste the terminal output or a screenshot and say "this isn't right" or "look at the differences." Expects me to diagnose from the evidence.
- **Asks good follow-up questions.** After a feature works, he immediately thinks about edge cases or related improvements (e.g., "does this work for both 2026 and 2027?", "what about when the date is not found?").

### Development Preferences

- **Test with real data.** Prefers testing with actual gig database records over synthetic samples. Asked "is there a way to run it in test mode with an actual gig database record?" rather than using sample JSONs.
- **`--dry-run` first, always.** Validates before committing to real writes.
- **All three versions stay in sync.** Terminal, GUI, and Streamlit versions should have feature parity. When one gets an upgrade, all should get it.
- **Practical over perfect.** Doesn't ask for exhaustive test suites or over-engineered solutions. Prefers working code that solves the immediate problem, with `--dry-run` as the safety net.
- **Commits after features are tested.** Doesn't commit speculatively — waits until the output looks right.
- **AppleScript for macOS automation.** Uses Stream Deck with `osascript` commands to trigger workflows. Expects the same pattern for new tools.

### UI/Output Preferences

- **Clean, readable terminal output.** Likes structured multi-step output with clear section headers (e.g., `[1/5] Parsing booking data...`).
- **Color-coded information.** Green for good/available, red for booked/unavailable, yellow for warnings/maybe, cyan for informational.
- **One item per line.** Pushed back when two bookings appeared on one line in a dialog — "let's show one line per event."
- **Actionable labels.** Preferred "REACH OUT" / "MAYBE" / "STALE" over raw dates — wants to know what to *do* at a glance.
- **Relative time labels.** "2 weeks ago" is more useful than just "2/28/2026."

### Where He Pushes Back

- **Cluttered UI.** Wants clean separation of information.
- **Missing context for decisions.** Added venue info to backup dialogs because he was keeping the calendar open separately to check geography.
- **Ambiguous button behavior.** Pointed out that Cancel and Skip did the same thing — wanted Cancel to truly stop the script.
- **Things that don't work on first try.** Will paste error output and expect a fix, not a re-explanation.

---

## 3. What's Unfinished

### Needs Testing

- **`cancel_booking.py` live run.** Tested with `--dry-run` successfully. Has not been run without the flag on a real cancellation yet. First real cancellation will be the true test.

### Cleanup

- **`system_overview.js`** is sitting in the project directory (couldn't delete it from Cowork). Run `rm system_overview.js` locally.
- **`DJ_Availability_Checker_System_Reference.docx`** was generated but the markdown version (`DJ_SYSTEM_REFERENCE.md`) supersedes it. Can delete the docx if not needed.
- **Crosscheck text files** (`02-15-2026 - Systems crosscheck.txt`, etc.) and `Smart Calendar Time Blocker - Project Brief.docx` are untracked in the repo. Decide if they should be committed or gitignored.

### Potential Improvements

- **Auto-run turned-away lookup after cancellation.** cancel_booking.py opens the Google Form at the end, but doesn't automatically check for turned-away inquiries on the newly-freed date. Could add a step that runs the lookup and displays results in terminal.
- **Keep-alive reliability.** GitHub Actions cron every 5 minutes isn't guaranteed to be precise. UptimeRobot is the more reliable mechanism. If the app still sleeps, consider a dedicated cron service.
- **Streamlit redeployment.** After pushing changes, Streamlit Cloud sometimes needs a manual reboot (Manage app → Reboot) to pick up changes.

---

## 4. Key Context About Paul & Big Fun DJ

### The Person

- Paul is the owner/operator of Big Fun DJ and one of the performing DJs.
- He runs the entire availability and booking pipeline himself — no admin staff for this.
- His daily workflow: check availability for incoming inquiries, make sales calls, confirm bookings, assign backup DJs, reconcile systems periodically.
- He's technical enough to run Python scripts, use Stream Deck, understand JSON, and debug terminal output. Not a developer by trade.
- Uses a MacBook Pro with miniconda Python, macOS Calendar, MailMaven, Safari for FileMaker access.
- His two bosses (company owners) use the Streamlit web version — they don't touch the terminal tools.

### The Business

- ~225 events per year, peak season April–October (Saturdays at $1,999–$2,299).
- 6 DJs with very different availability rules (see DJ_SYSTEM_REFERENCE.md Section 7).
- Three independent systems that must stay in sync: Google Sheets matrix, FileMaker gig database, macOS Calendar.
- Data accuracy is the top priority. Realistic projections over optimistic ones.
- Cancellations happen a few times a year — infrequent but the process should be smooth.
- Allied Arts Guild (AAG) exclusive arrangement starting 2027 adds complexity.

### Technical Environment

- **Python:** miniconda at `/Users/paulburchfield/miniconda3/bin/python3`
- **Project:** `~/Documents/projects/dj-availability-checker/`
- **GitHub:** `paulbii/dj-availability-checker` (main branch, auto-deploys Streamlit)
- **Credentials:** `your-credentials.json` (Google service account, gitignored)
- **Stream Deck:** Two buttons — Book Event and Cancel Booking — both run `osascript` commands
- **Git lock files:** Occasionally stale `.git/index.lock` and `.git/HEAD.lock` appear (likely from Cowork's sandboxed writes). Fix with `rm -f .git/index.lock .git/HEAD.lock` before committing.

---

## 5. Artifacts — Current Versions

The full codebase lives in the GitHub repo. The key files that were created or significantly modified in our sessions are:

### New Files (created from scratch)

- `cancel_booking.py` — Full cancellation workflow
- `cancel_booking.scpt` — AppleScript trigger for Stream Deck
- `backup_stats.py` — Backup assignment counts
- `DJ_SYSTEM_REFERENCE.md` — Complete system reference
- `CLAUDE_CODE_HANDOFF.md` — This document

### Significantly Modified Files

- `dj_core.py` — Added `get_full_inquiries_for_date()` with recency tiers, dash/slash date parsing
- `check_dj.py` — Added Option 6 (turned-away inquiries), bumped Exit to 7, clipboard copy on date check
- `check_dj_gui.py` — Added Turned Away panel, clipboard copy, inquiry tier coloring
- `dj_app.py` — Complete rewrite for feature parity (all 6 tabs), added Turned Away tab with tier coloring
- `backup_assigner.py` — Added venue context from gig DB, one-per-line booking display, Cancel-to-stop
- `gig_booking_manager.py` — Added booking context to backup dialog, Cancel returns STOP
- `.github/workflows/keep-alive.yml` — Changed from every 10 hours to every 5 minutes

### Reference Documents (pre-existing, read but not heavily modified)

- `PROJECT_CONTEXT.md` — Business context and architecture
- `SYSTEM_REFERENCE.md` — Technical deep dive
- `COWORK_INTRO.md` — AI assistant quick-start
- `DASHBOARD_REFERENCE.md` — Dashboard metrics and dedup logic

All code is in the repo. To get the current versions, clone `paulbii/dj-availability-checker` at HEAD.
