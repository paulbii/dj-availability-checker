const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
        ShadingType, PageNumber, PageBreak, LevelFormat } = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function headerCell(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: { fill: "2E4057", type: ShadingType.CLEAR },
    margins: cellMargins,
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 20 })] })]
  });
}

function cell(text, width, opts = {}) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR } : undefined,
    margins: cellMargins,
    children: [new Paragraph({ children: [new TextRun({ text, font: "Arial", size: 20, bold: opts.bold || false })] })]
  });
}

function multiLineCell(lines, width, opts = {}) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR } : undefined,
    margins: cellMargins,
    children: lines.map(l => new Paragraph({ children: [new TextRun({ text: l, font: "Arial", size: 20 })] }))
  });
}

function heading(text, level) {
  return new Paragraph({ heading: level, spacing: { before: 300, after: 150 },
    children: [new TextRun({ text, font: "Arial", bold: true })] });
}

function para(text, opts = {}) {
  return new Paragraph({ spacing: { after: 120 },
    children: [new TextRun({ text, font: "Arial", size: 22, ...opts })] });
}

function boldPara(label, value) {
  return new Paragraph({ spacing: { after: 80 },
    children: [
      new TextRun({ text: label, font: "Arial", size: 22, bold: true }),
      new TextRun({ text: value, font: "Arial", size: 22 })
    ]
  });
}

function codePara(text) {
  return new Paragraph({ spacing: { after: 80 },
    children: [new TextRun({ text, font: "JetBrains Mono", size: 18, color: "333333" })] });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: "2E4057" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "2E4057" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "4A6B8A" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ]
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [
    // ── TITLE PAGE ──
    {
      properties: {
        page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } }
      },
      children: [
        new Paragraph({ spacing: { before: 3000 } }),
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
          children: [new TextRun({ text: "DJ Availability Checker", font: "Arial", size: 52, bold: true, color: "2E4057" })] }),
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 },
          children: [new TextRun({ text: "Complete System Reference", font: "Arial", size: 32, color: "4A6B8A" })] }),
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
          children: [new TextRun({ text: "Big Fun DJ", font: "Arial", size: 24, color: "666666" })] }),
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
          children: [new TextRun({ text: "Last Updated: March 2026", font: "Arial", size: 22, color: "666666" })] }),
        new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "Paul Burchfield", font: "Arial", size: 22, color: "666666" })] }),
      ]
    },

    // ── MAIN CONTENT ──
    {
      properties: {
        page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } }
      },
      headers: {
        default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: "DJ Availability Checker \u2014 System Reference", font: "Arial", size: 16, color: "999999" })] })] })
      },
      footers: {
        default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "Page ", font: "Arial", size: 16, color: "999999" }),
                     new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "999999" })] })] })
      },
      children: [

        // ══════════════════════════════════════════
        // SECTION 1: SYSTEM OVERVIEW
        // ══════════════════════════════════════════
        heading("1. System Overview", HeadingLevel.HEADING_1),
        para("The DJ Availability Checker is a booking and availability management system for Big Fun DJ, handling approximately 225 events annually. It bridges three independent data sources and provides multiple interfaces for checking availability, managing bookings, and tracking leads."),

        heading("Data Sources", HeadingLevel.HEADING_2),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2200, 3800, 3360],
          rows: [
            new TableRow({ children: [headerCell("System", 2200), headerCell("Details", 3800), headerCell("Purpose", 3360)] }),
            new TableRow({ children: [
              cell("Availability Matrix", 2200, { bold: true }),
              multiLineCell(["Google Sheets", "ID: 1lXwHECkQJy7h87L5oKbo...FTbBQJ4pIerFo", "Tabs: 2025, 2026, 2027"], 3800),
              cell("DJ scheduling status, bold/plain OUT formatting, TBA bookings, AAG holds", 3360)
            ]}),
            new TableRow({ children: [
              cell("Gig Database", 2200, { bold: true }),
              multiLineCell(["FileMaker Pro via JSON API", "https://database.bigfundj.com/bigfunadmin/", "Single-day + multi-day endpoints"], 3800),
              cell("Contract-level details: client names, venues, financial records, confirmed bookings", 3360)
            ]}),
            new TableRow({ children: [
              cell("Inquiry Tracker", 2200, { bold: true }),
              multiLineCell(["Google Sheets", "ID: 1ng-OytB9LJ8Fmfaz...GYEWhJRs", "Tab: Form Responses 1"], 3800),
              cell("Lead tracking: who inquired, outcome (Booked, Full, Ghosted, etc.), conversion data", 3360)
            ]}),
          ]
        }),

        // ══════════════════════════════════════════
        // SECTION 2: AVAILABILITY CHECKER
        // ══════════════════════════════════════════
        new Paragraph({ children: [new PageBreak()] }),
        heading("2. Availability Checker (check_2026 / check_2027)", HeadingLevel.HEADING_1),
        para("The primary tool used daily to check DJ availability. Available in three interfaces: terminal, desktop GUI, and web (Streamlit)."),

        heading("Terminal Version", HeadingLevel.HEADING_2),
        boldPara("Files: ", "check_dj.py, check_2026.py, check_2027.py"),
        boldPara("Launch: ", "python3 check_2026.py  or  python3 check_2027.py"),
        boldPara("Dependencies: ", "colorama, gspread, Google Sheets API, FileMaker JSON endpoints"),
        para(""),
        heading("Menu Options", HeadingLevel.HEADING_3),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [800, 2800, 5760],
          rows: [
            new TableRow({ children: [headerCell("#", 800), headerCell("Option", 2800), headerCell("Description", 5760)] }),
            new TableRow({ children: [cell("1", 800), cell("Check specific date", 2800), cell("Single date lookup with DJ statuses, venue info, nearby bookings, inquiry history. Copies date to clipboard in MM-DD-YY format.", 5760)] }),
            new TableRow({ children: [cell("2", 800), cell("Query date range", 2800), cell("Bulk availability across a date range with optional day-of-week filter (Saturday/Sunday/Weekend/Weekday).", 5760)] }),
            new TableRow({ children: [cell("3", 800), cell("Find dates with min. availability", 2800), cell("Find dates with N or more available spots in a range.", 5760)] }),
            new TableRow({ children: [cell("4", 800), cell("Check DJ availability in range", 2800), cell("Show a specific DJ's status across a date range.", 5760)] }),
            new TableRow({ children: [cell("5", 800), cell("List fully booked dates", 2800), cell("Find all dates with zero availability in a range.", 5760)] }),
            new TableRow({ children: [cell("6", 800), cell("Turned-away inquiries", 2800), cell("Search inquiry tracker for leads turned away (resolution = Full) on a date. Color-coded by recency: green (REACH OUT, within 4 weeks), yellow (MAYBE, 5\u201310 weeks), gray (STALE, older).", 5760)] }),
            new TableRow({ children: [cell("7", 800), cell("Exit", 2800), cell("", 5760)] }),
          ]
        }),

        heading("Desktop GUI Version", HeadingLevel.HEADING_2),
        boldPara("Files: ", "check_dj_gui.py, check_2026_gui.py, check_2027_gui.py"),
        boldPara("Launch: ", "python3 check_2026_gui.py  or  python3 check_2027_gui.py"),
        boldPara("Dependencies: ", "pywebview (in addition to terminal deps)"),
        para("Same functionality as terminal version in a desktop window with sidebar navigation. Panels: Single Date, Date Range, Min. Availability, DJ Availability, Fully Booked, Turned Away."),

        heading("Streamlit Web Version", HeadingLevel.HEADING_2),
        boldPara("File: ", "dj_app.py"),
        boldPara("URL: ", "https://dj-availability-checker.streamlit.app"),
        boldPara("Launch locally: ", "streamlit run dj_app.py"),
        boldPara("Auth: ", "Streamlit secrets (gcp_service_account in secrets.toml / Cloud dashboard)"),
        para("Browser-based version for team access (primarily for company owners). Same 6 tabs as terminal options. Uses init_google_sheets_from_dict() with Streamlit secrets instead of local credentials file. Keep-alive via GitHub Actions cron (every 5 min) + UptimeRobot."),

        // ══════════════════════════════════════════
        // SECTION 3: GIG BOOKING MANAGER
        // ══════════════════════════════════════════
        new Paragraph({ children: [new PageBreak()] }),
        heading("3. Gig Booking Manager", HeadingLevel.HEADING_1),
        para("Automates availability matrix and calendar updates when a new booking is confirmed in FileMaker."),
        boldPara("Files: ", "gig_booking_manager.py, gig_booking_manager.scpt"),
        boldPara("Trigger: ", "Stream Deck button runs osascript gig_booking_manager.scpt"),
        boldPara("Flags: ", "--dry-run (validate only)  |  --test (calendar invites to paul@bigfundj.com)  |  --credentials PATH"),

        heading("Workflow", HeadingLevel.HEADING_2),
        para("1. AppleScript extracts booking data from FileMaker page open in Safari via JavaScript, writes JSON to /tmp/gig_booking.json."),
        para("2. Python script runs in three phases: Validate (check matrix cell + calendar conflicts) \u2192 Update Matrix (write BOOKED, optionally assign backup via AppleScript dialog) \u2192 Create Calendar Events (primary + backup)."),
        para("3. Opens Google Form pre-filled with booking metadata (event date, venue, decision date = today, status = Booked)."),

        heading("Input Format (FileMaker JSON)", HeadingLevel.HEADING_3),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2500, 6860],
          rows: [
            new TableRow({ children: [headerCell("Field", 2500), headerCell("Description", 6860)] }),
            new TableRow({ children: [cell("FMeventDate", 2500), cell("Event date (MM/DD/YYYY)", 6860)] }),
            new TableRow({ children: [cell("FMstartTime / FMendTime", 2500), cell("Start/end times (24-hour format)", 6860)] }),
            new TableRow({ children: [cell("FMclient", 2500), cell("Client name", 6860)] }),
            new TableRow({ children: [cell("FMvenue", 2500), cell("Venue name", 6860)] }),
            new TableRow({ children: [cell("FMvenueAddress", 2500), cell("Street***unused***City, State ZIP (splits on ***)", 6860)] }),
            new TableRow({ children: [cell("FMDJ1 / FMDJ2", 2500), cell("Primary DJ full name / Secondary DJ (for unassigned bookings)", 6860)] }),
            new TableRow({ children: [cell("FMsound", 2500), cell("Sound package type (Ceremony or Standard Speakers)", 6860)] }),
            new TableRow({ children: [cell("FMcersound", 2500), cell("Has ceremony sound: 1 = true, 0 = false", 6860)] }),
            new TableRow({ children: [cell("MailCoordinator", 2500), cell("Planner/coordinator name", 6860)] }),
          ]
        }),
        para("Also supports clean test format (event_date as YYYY-MM-DD, assigned_dj as first name, etc.). Auto-detected by presence of FMclient field."),

        heading("Calendar Events", HeadingLevel.HEADING_3),
        para("Booking events: titled [DJ_INITIALS] Client Name (e.g., [PB] Smith Wedding). Backup events: titled [WD] BACKUP DJ or [WD] PAID BACKUP DJ. Created in the Gigs calendar on macOS."),

        heading("Backup DJ Assignment", HeadingLevel.HEADING_3),
        para("After writing BOOKED to the matrix, the script checks if a backup is needed and shows an AppleScript dialog listing eligible DJs with venue context. Skip moves to next step. Cancel stops the script. Selecting a DJ writes BACKUP to their cell and creates a backup calendar event."),

        // ══════════════════════════════════════════
        // SECTION 4: CANCEL BOOKING
        // ══════════════════════════════════════════
        new Paragraph({ children: [new PageBreak()] }),
        heading("4. Cancel Booking", HeadingLevel.HEADING_1),
        para("Reverses a booking: clears the matrix, deletes calendar events, optionally removes backup, logs to Google Form."),
        boldPara("Files: ", "cancel_booking.py, cancel_booking.scpt"),
        boldPara("Trigger: ", "Stream Deck button runs osascript cancel_booking.scpt"),
        boldPara("Flags: ", "--dry-run  |  --test  |  --credentials PATH"),

        heading("5-Step Process", HeadingLevel.HEADING_2),
        para("1. Parse booking data (same JSON format as gig_booking_manager)"),
        para("2. Connect to availability matrix"),
        para("3. Validate DJ is marked BOOKED or RESERVED on that date"),
        para("4. Update matrix: restore DJ's default cell value, optionally remove backup DJ"),
        para("5. Clean up calendar: delete booking event and optionally backup event, open Google Form with Canceled status"),

        heading("Default Cell Values", HeadingLevel.HEADING_3),
        para("When clearing a BOOKED cell, the script restores the DJ's default value based on their name and day of week (since writing BOOKED overwrote any formula that was there):"),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2000, 3680, 3680],
          rows: [
            new TableRow({ children: [headerCell("DJ", 2000), headerCell("Weekdays (Mon\u2013Fri)", 3680), headerCell("Weekends (Sat\u2013Sun)", 3680)] }),
            new TableRow({ children: [cell("Woody", 2000), cell("(blank)", 3680), cell("OUT", 3680)] }),
            new TableRow({ children: [cell("Stefano", 2000), cell("OUT", 3680), cell("Saturday: (blank), Sunday: OUT", 3680)] }),
            new TableRow({ children: [cell("Felipe", 2000), cell("OUT", 3680), cell("(blank)", 3680)] }),
            new TableRow({ children: [cell("Henry, Paul, Stephanie", 2000), cell("(blank)", 3680), cell("(blank)", 3680)] }),
          ]
        }),

        heading("Inquiry Tracker Convention", HeadingLevel.HEADING_3),
        para("For cancellations, set the Inquiry Date and Decision Date to the same value (today). This mirrors the convention used when a date is full at initial contact \u2014 no decision period to track. The distinction is clear from the Resolution field: Full vs. Canceled."),

        // ══════════════════════════════════════════
        // SECTION 5: BACKUP TOOLS
        // ══════════════════════════════════════════
        new Paragraph({ children: [new PageBreak()] }),
        heading("5. Backup DJ Tools", HeadingLevel.HEADING_1),

        heading("Backup Assigner", HeadingLevel.HEADING_2),
        boldPara("File: ", "backup_assigner.py"),
        boldPara("Launch: ", "python3 backup_assigner.py --year 2026"),
        boldPara("Flags: ", "--year (required)  |  --dry-run"),
        para("Scans the matrix for future dates with bookings but no backup DJ assigned. For each, shows an AppleScript dialog with eligible DJs and venue context (fetched from gig database JSON endpoint). Cancel button stops the entire operation. Skip moves to next date. Selecting a DJ writes BACKUP and creates a calendar event."),

        heading("Backup Stats", HeadingLevel.HEADING_2),
        boldPara("File: ", "backup_stats.py"),
        boldPara("Launch: ", "python3 backup_stats.py --year 2026"),
        para("Counts how many times each DJ is assigned as BACKUP in the availability matrix for a given year. Shows summary with counts and specific dates."),

        // ══════════════════════════════════════════
        // SECTION 6: OTHER TOOLS
        // ══════════════════════════════════════════
        heading("6. Other Tools", HeadingLevel.HEADING_1),

        heading("Booking Comparator", HeadingLevel.HEADING_2),
        boldPara("File: ", "booking_comparator.py"),
        boldPara("Launch: ", "python3 booking_comparator.py --year 2026 [--no-calendar] [--output report.txt]"),
        para("Cross-checks three systems (Gig Database, Availability Matrix, Master Calendar) to identify discrepancies. Uses icalBuddy for macOS calendar access. Outputs a text report file."),

        heading("Confirmation Forwarder", HeadingLevel.HEADING_2),
        boldPara("File: ", "confirmation_forwarder.py"),
        boldPara("Launch: ", "python3 confirmation_forwarder.py /tmp/gig_booking.json"),
        para("After booking confirmation is sent to a couple, creates pre-filled forward drafts in MailMaven for the office (confirmations@bigfundj.com, CC: Henry & Woody) and the assigned DJ."),

        // ══════════════════════════════════════════
        // SECTION 7: CORE MODULE
        // ══════════════════════════════════════════
        new Paragraph({ children: [new PageBreak()] }),
        heading("7. Core Module (dj_core.py)", HeadingLevel.HEADING_1),
        para("Shared business logic imported by all other scripts. Single source of truth for DJ rules, column mappings, availability logic, and API connections."),

        heading("Key Constants", HeadingLevel.HEADING_2),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3500, 5860],
          rows: [
            new TableRow({ children: [headerCell("Constant", 3500), headerCell("Value/Purpose", 5860)] }),
            new TableRow({ children: [cell("COLUMNS_2026", 3500), cell("D=Henry, E=Woody, F=Paul, G=Stefano, H=Felipe, I=TBA, K=Stephanie, L=AAG", 5860)] }),
            new TableRow({ children: [cell("COLUMNS_2027", 3500), cell("D=Henry, E=Woody, F=Paul, G=Stefano, H=Stephanie, I=TBA, J=AAG, L=Felipe", 5860)] }),
            new TableRow({ children: [cell("KNOWN_CELL_VALUES", 3500), cell("booked, backup, out, maxed, reserved, stanford, ok, ok to backup, dad, last, aag", 5860)] }),
            new TableRow({ children: [cell("BACKUP_ELIGIBLE_DJS", 3500), cell("DJs who can be assigned as backup", 5860)] }),
            new TableRow({ children: [cell("PAID_BACKUP_DJS / UNPAID_BACKUP_DJS", 3500), cell("Determines calendar event title: PAID BACKUP DJ vs BACKUP DJ", 5860)] }),
          ]
        }),

        heading("Key Functions", HeadingLevel.HEADING_2),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [4200, 5160],
          rows: [
            new TableRow({ children: [headerCell("Function", 4200), headerCell("Purpose", 5160)] }),
            new TableRow({ children: [cell("init_google_sheets_from_file()", 4200), cell("Auth with local credentials JSON", 5160)] }),
            new TableRow({ children: [cell("init_google_sheets_from_dict()", 4200), cell("Auth with Streamlit secrets dict", 5160)] }),
            new TableRow({ children: [cell("check_dj_availability()", 4200), cell("Core rule engine for a single DJ on a date", 5160)] }),
            new TableRow({ children: [cell("get_date_availability_data()", 4200), cell("Single-date lookup (values + formatting)", 5160)] }),
            new TableRow({ children: [cell("get_bulk_availability_data()", 4200), cell("Range lookup (2 API calls for all data)", 5160)] }),
            new TableRow({ children: [cell("get_fully_booked_dates()", 4200), cell("Filter for zero-availability dates", 5160)] }),
            new TableRow({ children: [cell("get_gig_database_bookings()", 4200), cell("FileMaker single-day query", 5160)] }),
            new TableRow({ children: [cell("get_gig_database_bookings_multiday()", 4200), cell("FileMaker \u00B13 days query", 5160)] }),
            new TableRow({ children: [cell("get_venue_inquiries_for_date()", 4200), cell("All inquiry history for a date", 5160)] }),
            new TableRow({ children: [cell("get_full_inquiries_for_date()", 4200), cell("Turned-away (Full) inquiries with recency tiers", 5160)] }),
            new TableRow({ children: [cell("get_nearby_bookings_for_dj()", 4200), cell("DJ's bookings within \u00B13 days", 5160)] }),
            new TableRow({ children: [cell("auto_clear_stale_cache()", 4200), cell("Clears gig DB cache after 60 minutes", 5160)] }),
          ]
        }),

        heading("DJ Availability Rules", HeadingLevel.HEADING_2),
        para("Each DJ has unique rules for determining availability based on cell value, bold formatting, and day of week:"),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [1400, 4000, 3960],
          rows: [
            new TableRow({ children: [headerCell("DJ", 1400), headerCell("Available to Book", 4000), headerCell("Available to Backup", 3960)] }),
            new TableRow({ children: [cell("Paul", 1400), cell("Blank = yes, OUT = no", 4000), cell("Blank = yes", 3960)] }),
            new TableRow({ children: [cell("Henry", 1400), cell("Weekend blank = yes, Weekday blank = no (day job)", 4000), cell("Any blank = yes", 3960)] }),
            new TableRow({ children: [cell("Woody", 1400), cell("Blank = yes, Weekend OUT (plain) = no", 4000), cell("Blank = yes, Weekend OUT (plain) = yes, Weekend OUT (bold) = no, Weekday OUT = no", 3960)] }),
            new TableRow({ children: [cell("Stefano", 1400), cell("Max 2/month. Blank = MAYBE (not counted)", 4000), cell("Blank = MAYBE", 3960)] }),
            new TableRow({ children: [cell("Felipe", 1400), cell("OK = yes, Blank/DAD/OK TO BACKUP = no", 4000), cell("Blank/OK/DAD/OK TO BACKUP = yes", 3960)] }),
            new TableRow({ children: [cell("Stephanie", 1400), cell("2026: explicit only. 2027+: weekend blank = yes", 4000), cell("Per year rules", 3960)] }),
          ]
        }),

        // ══════════════════════════════════════════
        // SECTION 8: DEPLOYMENT & CONFIGURATION
        // ══════════════════════════════════════════
        new Paragraph({ children: [new PageBreak()] }),
        heading("8. Deployment & Configuration", HeadingLevel.HEADING_1),

        heading("Local Setup", HeadingLevel.HEADING_2),
        para("1. Clone the repository from GitHub (paulbii/dj-availability-checker)."),
        para("2. Install Python dependencies: pip install gspread oauth2client colorama pywebview streamlit requests"),
        para("3. Place your-credentials.json (Google service account) in the project directory. This file grants access to the Availability Matrix and Inquiry Tracker spreadsheets only."),
        para("4. For Streamlit local dev, create .streamlit/secrets.toml with [gcp_service_account] section containing the same credentials."),

        heading("Streamlit Cloud", HeadingLevel.HEADING_2),
        para("Auto-deploys from the main branch on GitHub. Secrets are configured in the Streamlit Cloud dashboard under the app's settings. The keep-alive workflow (.github/workflows/keep-alive.yml) pings the app every 5 minutes via GitHub Actions cron. UptimeRobot also monitors the URL as a more reliable backup."),

        heading("Stream Deck Buttons", HeadingLevel.HEADING_2),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2500, 6860],
          rows: [
            new TableRow({ children: [headerCell("Button", 2500), headerCell("Command", 6860)] }),
            new TableRow({ children: [cell("Book Event", 2500), cell("osascript ~/Documents/projects/dj-availability-checker/gig_booking_manager.scpt", 6860)] }),
            new TableRow({ children: [cell("Cancel Booking", 2500), cell("osascript ~/Documents/projects/dj-availability-checker/cancel_booking.scpt", 6860)] }),
          ]
        }),
        para("Both AppleScripts accept --dry-run and --test flags as arguments."),

        heading("Key File Paths", HeadingLevel.HEADING_2),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3000, 6360],
          rows: [
            new TableRow({ children: [headerCell("Item", 3000), headerCell("Path", 6360)] }),
            new TableRow({ children: [cell("Project directory", 3000), cell("~/Documents/projects/dj-availability-checker/", 6360)] }),
            new TableRow({ children: [cell("Credentials", 3000), cell("~/Documents/projects/dj-availability-checker/your-credentials.json", 6360)] }),
            new TableRow({ children: [cell("Python binary", 3000), cell("/Users/paulburchfield/miniconda3/bin/python3", 6360)] }),
            new TableRow({ children: [cell("Temp booking JSON", 3000), cell("/tmp/gig_booking.json", 6360)] }),
            new TableRow({ children: [cell("Sample bookings", 3000), cell("sample_bookings/ directory (test JSON files)", 6360)] }),
          ]
        }),

        // ══════════════════════════════════════════
        // SECTION 9: DATE FORMATS
        // ══════════════════════════════════════════
        heading("9. Date Format Reference", HeadingLevel.HEADING_1),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3000, 3180, 3180],
          rows: [
            new TableRow({ children: [headerCell("Context", 3000), headerCell("Format", 3180), headerCell("Example", 3180)] }),
            new TableRow({ children: [cell("Matrix dates (cell A column)", 3000), cell("Day M/D", 3180), cell("Sat 1/3", 3180)] }),
            new TableRow({ children: [cell("FileMaker request URL", 3000), cell("M/D/YYYY", 3180), cell("1/3/2026", 3180)] }),
            new TableRow({ children: [cell("FileMaker response", 3000), cell("YYYY-MM-DD", 3180), cell("2026-01-03", 3180)] }),
            new TableRow({ children: [cell("Inquiry tracker dates", 3000), cell("Various: m/d/yyyy, m/d/yy", 3180), cell("1/3/2026 or 1/3/26", 3180)] }),
            new TableRow({ children: [cell("Clipboard copy", 3000), cell("MM-DD-YY", 3180), cell("01-03-26", 3180)] }),
            new TableRow({ children: [cell("Calendar event titles", 3000), cell("[INITIALS] Client Name", 3180), cell("[PB] Smith Wedding", 3180)] }),
            new TableRow({ children: [cell("User input (check scripts)", 3000), cell("MM-DD or M-DD", 3180), cell("07-11 or 7-11", 3180)] }),
          ]
        }),

        // ══════════════════════════════════════════
        // SECTION 10: FILE INVENTORY
        // ══════════════════════════════════════════
        new Paragraph({ children: [new PageBreak()] }),
        heading("10. Complete File Inventory", HeadingLevel.HEADING_1),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3200, 6160],
          rows: [
            new TableRow({ children: [headerCell("File", 3200), headerCell("Purpose", 6160)] }),
            new TableRow({ children: [cell("dj_core.py", 3200, { bold: true }), cell("Shared business logic, rules, API connections", 6160)] }),
            new TableRow({ children: [cell("check_dj.py", 3200, { bold: true }), cell("Terminal availability checker (shared module)", 6160)] }),
            new TableRow({ children: [cell("check_2026.py / check_2027.py", 3200), cell("Year-specific terminal wrappers", 6160)] }),
            new TableRow({ children: [cell("check_dj_gui.py", 3200, { bold: true }), cell("PyWebView desktop GUI checker", 6160)] }),
            new TableRow({ children: [cell("check_2026_gui.py / check_2027_gui.py", 3200), cell("Year-specific GUI wrappers", 6160)] }),
            new TableRow({ children: [cell("dj_app.py", 3200, { bold: true }), cell("Streamlit web interface", 6160)] }),
            new TableRow({ children: [cell("gig_booking_manager.py", 3200, { bold: true }), cell("Booking automation (matrix + calendar + form)", 6160)] }),
            new TableRow({ children: [cell("gig_booking_manager.scpt", 3200), cell("AppleScript trigger for booking manager", 6160)] }),
            new TableRow({ children: [cell("cancel_booking.py", 3200, { bold: true }), cell("Booking cancellation (reverse of booking manager)", 6160)] }),
            new TableRow({ children: [cell("cancel_booking.scpt", 3200), cell("AppleScript trigger for cancellation", 6160)] }),
            new TableRow({ children: [cell("backup_assigner.py", 3200, { bold: true }), cell("Bulk backup DJ assignment with venue context", 6160)] }),
            new TableRow({ children: [cell("backup_stats.py", 3200), cell("Backup assignment counts per DJ per year", 6160)] }),
            new TableRow({ children: [cell("booking_comparator.py", 3200, { bold: true }), cell("Cross-system discrepancy checker", 6160)] }),
            new TableRow({ children: [cell("confirmation_forwarder.py", 3200), cell("Email forward drafts via MailMaven", 6160)] }),
            new TableRow({ children: [cell("your-credentials.json", 3200), cell("Google service account credentials (gitignored)", 6160)] }),
            new TableRow({ children: [cell("sample_bookings/", 3200), cell("Test JSON files for dry-run testing", 6160)] }),
          ]
        }),

      ]
    }
  ]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/sessions/magical-zen-lovelace/mnt/dj-availability-checker/DJ_Availability_Checker_System_Reference.docx", buffer);
  console.log("Document created successfully");
});
