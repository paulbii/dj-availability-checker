"""
DJ Availability Checker - GUI Interface (PyWebView)
Drop this file alongside dj_core.py and run it directly.
Requires: pip install pywebview
"""

import webview
import json
import threading
from datetime import datetime, timedelta
import calendar

# Import core functionality (same as check_dj.py)
from dj_core import (
    init_google_sheets_from_file,
    get_date_availability_data,
    get_venue_inquiries_for_date,
    get_nearby_bookings_for_dj,
    check_dj_availability,
    is_weekend,
    get_cache_info,
    clear_gig_cache,
    get_fully_booked_dates,
    get_bulk_availability_data,
    auto_clear_stale_cache,
    KNOWN_CELL_VALUES,
    get_gig_database_bookings,
)


# ── HTML/CSS/JS for the GUI ─────────────────────────────────────────────────

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #1a1a2e;
    --surface: #16213e;
    --surface2: #1c2a4a;
    --border: #2a3a5c;
    --text: #e0e0e0;
    --text-dim: #8892a4;
    --accent: #4fc3f7;
    --red: #ff5555;
    --green: #55ff55;
    --yellow: #ffff55;
    --blue: #5555ff;
    --cyan: #55ffff;
    --orange: #ffaa00;
  }

  body {
    font-family: 'DM Sans', -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Top Bar ── */
  .topbar {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 14px 24px;
    display: flex;
    align-items: center;
    gap: 16px;
    -webkit-app-region: drag;
    flex-shrink: 0;
  }
  .topbar h1 {
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: var(--accent);
  }
  .topbar .year-badge {
    background: var(--accent);
    color: var(--bg);
    font-size: 12px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 4px;
    letter-spacing: 0.5px;
  }
  .topbar .status {
    margin-left: auto;
    font-size: 12px;
    color: var(--text-dim);
    -webkit-app-region: no-drag;
  }
  .topbar .status.connected { color: var(--green); }
  .topbar .status.error { color: var(--red); }

  /* ── Main Layout ── */
  .main {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* ── Sidebar ── */
  .sidebar {
    width: 240px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    padding: 16px 0;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }
  .sidebar .section-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-dim);
    padding: 8px 20px 6px;
  }
  .sidebar button {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 10px 20px;
    background: none;
    border: none;
    color: var(--text-dim);
    font-family: inherit;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s;
    border-left: 3px solid transparent;
  }
  .sidebar button:hover {
    background: var(--surface2);
    color: var(--text);
  }
  .sidebar button.active {
    background: var(--surface2);
    color: var(--accent);
    border-left-color: var(--accent);
  }
  .sidebar button .icon {
    font-size: 16px;
    width: 22px;
    text-align: center;
    flex-shrink: 0;
  }
  .sidebar .spacer { flex: 1; }
  .sidebar .cache-info {
    padding: 12px 20px;
    font-size: 11px;
    color: var(--text-dim);
    border-top: 1px solid var(--border);
  }

  /* ── Content Area ── */
  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Input Panel ── */
  .input-panel {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 20px 28px;
    flex-shrink: 0;
  }
  .input-panel h2 {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 14px;
  }
  .input-row {
    display: flex;
    gap: 12px;
    align-items: flex-end;
    flex-wrap: wrap;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .field label {
    font-size: 11px;
    font-weight: 500;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .field input, .field select {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    padding: 8px 12px;
    border-radius: 6px;
    outline: none;
    transition: border-color 0.15s;
    width: 140px;
  }
  .field select { width: 160px; cursor: pointer; }
  .field input:focus, .field select:focus {
    border-color: var(--accent);
  }
  .field input::placeholder { color: var(--text-dim); opacity: 0.5; }

  .btn {
    background: var(--accent);
    color: var(--bg);
    border: none;
    font-family: inherit;
    font-size: 13px;
    font-weight: 600;
    padding: 9px 20px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
  .btn.secondary {
    background: var(--surface2);
    color: var(--text);
    border: 1px solid var(--border);
  }

  /* ── Results Panel ── */
  .results {
    flex: 1;
    overflow-y: auto;
    padding: 20px 28px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    line-height: 1.7;
  }
  .results::-webkit-scrollbar { width: 8px; }
  .results::-webkit-scrollbar-track { background: transparent; }
  .results::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  .results .line { white-space: pre-wrap; }
  .results .line.red { color: var(--red); }
  .results .line.green { color: var(--green); }
  .results .line.yellow { color: var(--yellow); }
  .results .line.blue { color: var(--blue); }
  .results .line.cyan { color: var(--cyan); }
  .results .line.dim { color: var(--text-dim); }
  .results .line.heading {
    color: var(--accent);
    font-weight: 600;
    font-size: 14px;
  }
  .results .line.separator {
    color: var(--border);
    user-select: none;
  }
  .results .line.warn { color: var(--orange); }
  .results .line.section-gap {
    height: 12px;
  }
  .results .section-divider {
    border-top: 1px solid var(--border);
    margin: 14px 0;
  }

  .results .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-dim);
    gap: 8px;
  }
  .results .empty-state .icon { font-size: 32px; opacity: 0.4; }
  .results .empty-state p { font-family: 'DM Sans', sans-serif; font-size: 14px; }

  .loading {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--accent);
    padding: 20px 0;
  }
  .loading .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Panel visibility ── */
  .panel { display: none; }
  .panel.active { display: block; }
</style>
</head>
<body>

<!-- Top Bar -->
<div class="topbar">
  <h1>DJ AVAILABILITY CHECKER</h1>
  <span class="year-badge" id="yearBadge">2026</span>
  <span class="status" id="statusText">Connecting…</span>
</div>

<div class="main">

  <!-- Sidebar -->
  <div class="sidebar">
    <div class="section-label">Queries</div>
    <button class="active" onclick="switchPanel('single')" id="nav-single">
      <span class="icon">📅</span> Check Date
    </button>
    <button onclick="switchPanel('range')" id="nav-range">
      <span class="icon">📊</span> Date Range
    </button>
    <button onclick="switchPanel('minspots')" id="nav-minspots">
      <span class="icon">🔍</span> Min. Availability
    </button>
    <button onclick="switchPanel('djquery')" id="nav-djquery">
      <span class="icon">🎧</span> DJ Availability
    </button>
    <button onclick="switchPanel('booked')" id="nav-booked">
      <span class="icon">🚫</span> Fully Booked
    </button>
    <div class="spacer"></div>
    <div class="cache-info" id="cacheInfo"></div>
  </div>

  <!-- Content -->
  <div class="content">

    <!-- ── Input Panels ── -->
    <div class="input-panel">

      <!-- Single Date -->
      <div class="panel active" id="panel-single">
        <h2>Check Specific Date</h2>
        <div class="input-row">
          <div class="field">
            <label>Date (MM-DD)</label>
            <input type="text" id="singleDate" placeholder="07-05"
                   maxlength="5" onkeydown="if(event.key==='Enter') runSingle()">
          </div>
          <button class="btn" onclick="runSingle()" id="btnSingle">Check</button>
        </div>
      </div>

      <!-- Date Range -->
      <div class="panel" id="panel-range">
        <h2>Query Date Range</h2>
        <div class="input-row">
          <div class="field">
            <label>Start (MM-DD)</label>
            <input type="text" id="rangeStart" placeholder="06-01" maxlength="5">
          </div>
          <div class="field">
            <label>End (MM-DD)</label>
            <input type="text" id="rangeEnd" placeholder="09-30" maxlength="5">
          </div>
          <div class="field">
            <label>Day Filter</label>
            <select id="rangeFilter">
              <option value="">All Days</option>
              <option value="Saturday">Saturday</option>
              <option value="Sunday">Sunday</option>
              <option value="Weekend">Weekend</option>
              <option value="Weekday">Weekday</option>
            </select>
          </div>
          <button class="btn" onclick="runRange()">Search</button>
        </div>
      </div>

      <!-- Min Availability -->
      <div class="panel" id="panel-minspots">
        <h2>Find Dates with Minimum Availability</h2>
        <div class="input-row">
          <div class="field">
            <label>Start (MM-DD)</label>
            <input type="text" id="minStart" placeholder="06-01" maxlength="5">
          </div>
          <div class="field">
            <label>End (MM-DD)</label>
            <input type="text" id="minEnd" placeholder="09-30" maxlength="5">
          </div>
          <div class="field">
            <label>Min Spots</label>
            <input type="number" id="minSpots" value="1" min="0" style="width:80px;">
          </div>
          <div class="field">
            <label>Day Filter</label>
            <select id="minFilter">
              <option value="">All Days</option>
              <option value="Saturday">Saturday</option>
              <option value="Sunday">Sunday</option>
              <option value="Weekend">Weekend</option>
              <option value="Weekday">Weekday</option>
            </select>
          </div>
          <button class="btn" onclick="runMinSpots()">Search</button>
        </div>
      </div>

      <!-- DJ Query -->
      <div class="panel" id="panel-djquery">
        <h2>Check DJ Availability in Range</h2>
        <div class="input-row">
          <div class="field">
            <label>DJ Name</label>
            <select id="djName">
              <option>Henry</option>
              <option>Woody</option>
              <option>Paul</option>
              <option>Stefano</option>
              <option>Felipe</option>
            </select>
          </div>
          <div class="field">
            <label>Start (MM-DD)</label>
            <input type="text" id="djStart" placeholder="06-01" maxlength="5">
          </div>
          <div class="field">
            <label>End (MM-DD)</label>
            <input type="text" id="djEnd" placeholder="09-30" maxlength="5">
          </div>
          <button class="btn" onclick="runDjQuery()">Search</button>
        </div>
      </div>

      <!-- Fully Booked -->
      <div class="panel" id="panel-booked">
        <h2>List Fully Booked Dates</h2>
        <div class="input-row">
          <div class="field">
            <label>Start (MM-DD)</label>
            <input type="text" id="bookedStart" placeholder="01-01" maxlength="5" value="01-01">
          </div>
          <div class="field">
            <label>End (MM-DD)</label>
            <input type="text" id="bookedEnd" placeholder="12-31" maxlength="5" value="12-31">
          </div>
          <button class="btn" onclick="runBooked()">Search</button>
        </div>
      </div>

    </div>

    <!-- Results -->
    <div class="results" id="results">
      <div class="empty-state">
        <div class="icon">🎛️</div>
        <p>Select an option and enter a date to get started</p>
      </div>
    </div>

  </div>
</div>

<script>
  // ── Panel switching ──
  function switchPanel(name) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.sidebar button').forEach(b => b.classList.remove('active'));
    document.getElementById('panel-' + name).classList.add('active');
    document.getElementById('nav-' + name).classList.add('active');
  }

  // ── Show loading state ──
  function showLoading(msg) {
    document.getElementById('results').innerHTML =
      '<div class="loading"><div class="spinner"></div><span>' + msg + '</span></div>';
  }

  // ── Render result lines ──
  function renderLines(lines) {
    const el = document.getElementById('results');
    el.innerHTML = lines.map(l => {
      if (l.cls === 'divider') return '<div class="section-divider"></div>';
      const cls = l.cls ? ' ' + l.cls : '';
      return '<div class="line' + cls + '">' + escapeHtml(l.text) + '</div>';
    }).join('');
    el.scrollTop = 0;
  }

  function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── API calls to Python backend ──
  async function runSingle() {
    const date = document.getElementById('singleDate').value.trim();
    if (!date) return;
    showLoading('Checking ' + date + '…');
    const result = await pywebview.api.check_single_date(date);
    renderLines(result);
  }

  async function runRange() {
    const start = document.getElementById('rangeStart').value.trim();
    const end = document.getElementById('rangeEnd').value.trim();
    const filter = document.getElementById('rangeFilter').value;
    if (!start || !end) return;
    showLoading('Querying ' + start + ' to ' + end + '…');
    const result = await pywebview.api.check_date_range(start, end, filter, null);
    renderLines(result);
  }

  async function runMinSpots() {
    const start = document.getElementById('minStart').value.trim();
    const end = document.getElementById('minEnd').value.trim();
    const spots = parseInt(document.getElementById('minSpots').value) || 1;
    const filter = document.getElementById('minFilter').value;
    if (!start || !end) return;
    showLoading('Searching for dates with ' + spots + '+ spots…');
    const result = await pywebview.api.check_date_range(start, end, filter, spots);
    renderLines(result);
  }

  async function runDjQuery() {
    const dj = document.getElementById('djName').value;
    const start = document.getElementById('djStart').value.trim();
    const end = document.getElementById('djEnd').value.trim();
    if (!start || !end) return;
    showLoading('Checking ' + dj + ' availability…');
    const result = await pywebview.api.check_dj_range(dj, start, end);
    renderLines(result);
  }

  async function runBooked() {
    const start = document.getElementById('bookedStart').value.trim();
    const end = document.getElementById('bookedEnd').value.trim();
    showLoading('Scanning for fully booked dates…');
    const result = await pywebview.api.check_fully_booked(start, end);
    renderLines(result);
  }

  // ── Init: set year badge, check connection ──
  async function init() {
    try {
      const info = await pywebview.api.get_info();
      document.getElementById('yearBadge').textContent = info.year;
      document.getElementById('statusText').textContent = '● Connected';
      document.getElementById('statusText').className = 'status connected';

      // Add Stephanie for 2027+
      if (parseInt(info.year) >= 2027) {
        const sel = document.getElementById('djName');
        const opt = document.createElement('option');
        opt.text = 'Stephanie';
        sel.add(opt);
      }
    } catch(e) {
      document.getElementById('statusText').textContent = '● Connection error';
      document.getElementById('statusText').className = 'status error';
    }
  }

  // Wait for pywebview API to be ready
  window.addEventListener('pywebviewready', init);
</script>

</body>
</html>
"""


# ── Python Backend (exposed to JS via pywebview) ────────────────────────────

class Api:
    """Backend API exposed to the webview JavaScript."""

    def __init__(self, year):
        self.year = year
        self.sheet_name = year
        self.service = None
        self.spreadsheet = None
        self.spreadsheet_id = None
        self.client = None
        self._init_sheets()

    def _init_sheets(self):
        """Initialize Google Sheets connection."""
        try:
            self.service, self.spreadsheet, self.spreadsheet_id, self.client = (
                init_google_sheets_from_file()
            )
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")

    def get_info(self):
        return {"year": self.year}

    # ── Helpers to convert colorama-style output to classified lines ──

    def _classify_line(self, text):
        """Determine CSS class for a line based on content patterns."""
        t = text.strip()
        if not t:
            return {"text": "", "cls": ""}
        if t.startswith("=") or t.startswith("-"):
            return {"text": t, "cls": "separator"}

        lower = t.lower()

        # Headings / labels
        if any(t.startswith(h) for h in [
            "Year:", "Date:", "AVAILABILITY SUMMARY",
            "AVAILABILITY QUERY RESULTS", "DJ AVAILABILITY QUERY",
            "FULLY BOOKED DATES", "DJ:", "Date range:", "Filter:", "Total",
            "Minimum spots:"
        ]):
            return {"text": t, "cls": "heading"}

        # Status colors
        if "booked" in lower and (":" in t):
            return {"text": t, "cls": "red"}
        if "reserved" in lower:
            return {"text": t, "cls": "red"}
        if "stanford" in lower:
            return {"text": t, "cls": "red"}
        if "available" in lower and ("spot" in lower or "booking" in lower or "for booking" in lower):
            return {"text": t, "cls": "green"}
        if "- available" in lower:
            return {"text": t, "cls": "green"}
        if "Available to Book:" in t:
            return {"text": t, "cls": "green"}
        if "backup" in lower:
            return {"text": t, "cls": "blue"}
        if "Available to Backup:" in t:
            return {"text": t, "cls": "cyan"}
        if "[maybe]" in lower:
            return {"text": t, "cls": "yellow"}
        if "⚠" in t or "unknown" in lower:
            return {"text": t, "cls": "warn"}
        if "TIP:" in t or "INQUIRIES" in t:
            return {"text": t, "cls": "yellow"}
        if "ℹ" in t or "cache" in lower:
            return {"text": t, "cls": "cyan"}
        if "Confirmed bookings:" in t or "Available spots:" in t:
            return {"text": t, "cls": "heading"}
        if "AVAILABLE FOR BOOKING" in t:
            return {"text": t, "cls": "green"}
        if "BOOKED (" in t:
            return {"text": t, "cls": "red"}
        if "BACKUP (" in t:
            return {"text": t, "cls": "blue"}
        if lower.startswith("no ") or lower.startswith("none"):
            return {"text": t, "cls": "dim"}
        if "not available" in lower:
            return {"text": t, "cls": "dim"}

        # Range results with spot counts
        if "spot(s) available" in lower:
            # Try to color by count
            if "0 spot" in t:
                return {"text": t, "cls": "red"}
            elif "1 spot" in t:
                return {"text": t, "cls": "yellow"}
            else:
                return {"text": t, "cls": "green"}

        # Fully booked dates section
        if "Found " in t and "fully booked" in lower:
            return {"text": t, "cls": "red"}

        return {"text": t, "cls": ""}

    def _strip_ansi(self, text):
        """Remove ANSI color codes from text."""
        import re
        return re.sub(r'\x1b\[[0-9;]*m', '', text)

    def _process_output(self, raw_text):
        """Convert raw terminal output (with ANSI codes) to classified lines."""
        clean = self._strip_ansi(raw_text)
        return [self._classify_line(line) for line in clean.split("\n")]

    # ── Exposed API Methods ──

    def check_single_date(self, month_day):
        try:
            data = get_date_availability_data(
                self.sheet_name, month_day,
                self.service, self.spreadsheet, self.spreadsheet_id
            )

            if data is None:
                return [{"text": "An unexpected error occurred.", "cls": "red"}]
            if isinstance(data, dict) and 'error' in data:
                if data['error'] == 'invalid_format':
                    return [{"text": "Invalid date format. Use MM-DD (e.g., 07-05).", "cls": "red"}]
                elif data['error'] == 'not_found':
                    return [{"text": f"No entry found for {data['formatted_date']} in the {self.sheet_name} sheet.", "cls": "yellow"}]
                elif data['error'] == 'worksheet_not_found':
                    return [{"text": f"The {self.sheet_name} worksheet was not found.", "cls": "red"}]
                return [{"text": "An error occurred.", "cls": "red"}]

            # Build output lines (replicating check_availability logic)
            date_obj = data['date_obj']
            selected_data = data['selected_data']
            availability = data['availability']
            gig_bookings = data.get('gig_bookings', {'assigned': {}, 'unassigned': []})
            assigned_bookings = gig_bookings.get('assigned', {})
            unassigned_bookings = gig_bookings.get('unassigned', [])

            venue_info = get_venue_inquiries_for_date(selected_data['Date'], self.client)

            year_int = int(self.sheet_name)
            lines = []
            lines.append({"text": f"Year: {self.sheet_name}", "cls": "heading"})
            lines.append({"text": f"Date: {selected_data['Date']}", "cls": "heading"})
            lines.append({"text": "", "cls": "divider"})

            for label, value in selected_data.items():
                if label == "Date":
                    continue

                if label == "TBA":
                    if unassigned_bookings:
                        venues = [b.get('venue', 'Unknown') for b in unassigned_bookings]
                        lines.append({"text": f"{label}: BOOKED ({', '.join(venues)})", "cls": "red"})
                    elif value and ("booked" in str(value).lower() or "aag" in str(value).lower()):
                        lines.append({"text": f"{label}: {value}", "cls": "red"})
                    else:
                        lines.append({"text": f"{label}: {value}", "cls": ""})

                elif label == "AAG":
                    vl = str(value).lower()
                    if "reserved" in vl:
                        lines.append({"text": f"{label}: {value}", "cls": "red"})
                    else:
                        lines.append({"text": f"{label}: {value}", "cls": ""})

                elif label == "Stephanie":
                    steph_booking = assigned_bookings.get("Stephanie")
                    clean_value = value.replace(" (BOLD)", "").strip() if value else ""
                    clean_lower = clean_value.lower()
                    vl = str(value).lower()

                    if steph_booking:
                        venue = steph_booking.get('venue', '')
                        t = f"{label}: BOOKED ({venue})"
                        if clean_lower != "booked":
                            if clean_value:
                                t += f'  ⚠️  matrix shows "{clean_value}"'
                            else:
                                t += "  ⚠️  matrix is blank"
                        lines.append({"text": t, "cls": "red"})
                    elif "booked" in vl or "aag" in vl:
                        lines.append({"text": f"{label}: {value}", "cls": "red"})
                    elif "reserved" in vl:
                        lines.append({"text": f"{label}: {value}", "cls": "red"})
                    elif "backup" in vl:
                        lines.append({"text": f"{label}: {value}", "cls": "blue"})
                    elif year_int >= 2027:
                        is_bold = "(BOLD)" in value if value else False
                        cv = value.replace(" (BOLD)", "") if value else ""
                        can_book, can_backup = check_dj_availability(label, cv, date_obj, is_bold, self.sheet_name, warn=False)
                        nearby = []
                        if can_book and not steph_booking:
                            nearby = get_nearby_bookings_for_dj(label, date_obj, self.sheet_name, self.service, self.spreadsheet, self.spreadsheet_id)
                        lines.append(self._format_dj_line(label, value, date_obj, can_book, can_backup, nearby, steph_booking))
                    elif not value or value.strip() == "":
                        lines.append({"text": f"{label}: not available ({self.sheet_name})", "cls": "dim"})
                    elif clean_value and clean_lower not in KNOWN_CELL_VALUES:
                        lines.append({"text": f"{label}: {clean_value} ⚠️  unknown status — treating as unavailable", "cls": "warn"})
                    else:
                        lines.append({"text": f"{label}: {value}", "cls": ""})

                else:
                    # Standard DJ
                    dj_gig_booking = assigned_bookings.get(label)
                    is_bold = "(BOLD)" in value if value else False
                    clean_value = value.replace(" (BOLD)", "") if value else ""
                    can_book, can_backup = check_dj_availability(label, clean_value, date_obj, is_bold, self.sheet_name, warn=False)
                    nearby = []
                    if can_book and not dj_gig_booking:
                        nearby = get_nearby_bookings_for_dj(label, date_obj, self.sheet_name, self.service, self.spreadsheet, self.spreadsheet_id)
                    lines.append(self._format_dj_line(label, value, date_obj, can_book, can_backup, nearby, dj_gig_booking))

            # Summary
            lines.append({"text": "", "cls": "divider"})
            lines.append({"text": "AVAILABILITY SUMMARY:", "cls": "heading"})
            lines.append({"text": f"Confirmed bookings: {availability['booked_count']}", "cls": ""})

            if availability.get('aag_reserved', False):
                lines.append({"text": "AAG Spot Reserved: 1", "cls": "yellow"})

            avail = availability['available_spots']
            has_uncertain = "Stefano" in selected_data and (not selected_data["Stefano"] or selected_data["Stefano"].strip() == "")
            spots_text = f"Available spots: {avail}"
            if has_uncertain:
                spots_text += "*"
            if avail <= 2 and avail > 0 and availability['available_booking']:
                spots_text += f" ({', '.join(availability['available_booking'])})"
            cls = "green" if avail >= 2 else ("yellow" if avail == 1 else "red")
            lines.append({"text": spots_text, "cls": cls})
            if has_uncertain:
                lines.append({"text": "* Availability depends on Stefano's confirmation", "cls": "yellow"})

            if venue_info and venue_info.get('not_booked'):
                lines.append({"text": "", "cls": "divider"})
                lines.append({"text": f"INQUIRIES (not booked): {', '.join(venue_info['not_booked'])}", "cls": "yellow"})

            cache_info = get_cache_info()
            if cache_info:
                lines.append({"text": "", "cls": "divider"})
                age = cache_info['age_minutes']
                if age == 0 or cache_info['cache_time'] == 'Just now':
                    lines.append({"text": "ℹ Gig database: Fresh data (just fetched)", "cls": "cyan"})
                else:
                    lines.append({"text": f"ℹ Gig database: Cached from {cache_info['cache_time']} ({age} min ago)", "cls": "cyan"})
            return lines

        except Exception as e:
            return [{"text": f"Error: {str(e)}", "cls": "red"}]

    def _format_dj_line(self, dj_name, value, date_obj, is_bookable, is_backup, nearby_bookings=None, gig_booking=None):
        """Format a DJ status as a classified line dict."""
        clean_value = value.replace(" (BOLD)", "").strip() if value else ""
        clean_lower = clean_value.lower()

        if gig_booking:
            venue = gig_booking.get('venue', '')
            t = f"{dj_name}: BOOKED ({venue})"
            if clean_lower != "booked":
                if clean_value:
                    t += f'  ⚠️  matrix shows "{clean_value}"'
                else:
                    t += "  ⚠️  matrix is blank"
            return {"text": t, "cls": "red"}

        if dj_name == "Stefano" and (not value or value.strip() == ""):
            return {"text": f"{dj_name}: [MAYBE]", "cls": "yellow"}

        value_lower = value.lower() if value else ""
        if value and "booked" in value_lower:
            return {"text": f"{dj_name}: {value}", "cls": "red"}
        if value and value_lower == "stanford":
            return {"text": f"{dj_name}: STANFORD", "cls": "red"}
        if value and "reserved" in value_lower:
            return {"text": f"{dj_name}: RESERVED", "cls": "red"}
        if value and "backup" in value_lower:
            return {"text": f"{dj_name}: {value}", "cls": "blue"}

        if dj_name == "Felipe" and self.year in ["2026", "2027"] and (not value or value.strip() == ""):
            return {"text": f"{dj_name}: [BLANK] - can backup", "cls": "blue"}

        if value and value_lower == "last":
            return {"text": f"{dj_name}: {value} - available (low priority)", "cls": "green"}

        if clean_value and clean_lower not in KNOWN_CELL_VALUES:
            return {"text": f"{dj_name}: {clean_value} ⚠️  unknown status — treating as unavailable", "cls": "warn"}

        nearby_text = ""
        if nearby_bookings and len(nearby_bookings) > 0:
            nearby_text = f" (booked: {', '.join(nearby_bookings)})"

        if is_bookable:
            return {"text": f"{dj_name}: {value} - available{nearby_text}", "cls": "green"}
        if is_backup:
            return {"text": f"{dj_name}: {value} - can backup", "cls": "blue"}

        return {"text": f"{dj_name}: {value}", "cls": ""}

    def check_date_range(self, start_str, end_str, day_filter, min_spots):
        """Query date range - mirrors query_date_range()."""
        try:
            start_date, end_date = self._parse_dates(start_str, end_str)
            if not start_date:
                return [{"text": "Invalid date format. Use MM-DD.", "cls": "red"}]
            if start_date > end_date:
                return [{"text": "Start date must be before end date.", "cls": "red"}]

            all_data = get_bulk_availability_data(
                self.sheet_name, self.service, self.spreadsheet, self.spreadsheet_id,
                start_date, end_date
            )
            if all_data is None:
                return [{"text": f"Error fetching data from {self.sheet_name} sheet.", "cls": "red"}]

            day_filter = day_filter or None
            results = []
            for date_info in all_data:
                date_obj = date_info['date_obj']
                day_name = calendar.day_name[date_obj.weekday()]
                include = True
                if day_filter:
                    df = day_filter.lower()
                    if df == "weekend":
                        include = date_obj.weekday() >= 5
                    elif df == "weekday":
                        include = date_obj.weekday() < 5
                    else:
                        include = day_name.lower() == df

                if include:
                    avail = date_info['availability']['available_spots']
                    if min_spots is None or avail >= min_spots:
                        available_djs = list(date_info['availability']['available_booking'])
                        sv = date_info['selected_data'].get('Stefano', '')
                        sc = str(sv).replace(" (BOLD)", "").strip() if sv else ""
                        if not sc and 'Stefano' not in available_djs:
                            available_djs.append('Stefano [MAYBE]')
                        results.append({
                            'date': date_info['date'],
                            'spots': avail,
                            'djs': available_djs
                        })

            lines = []
            lines.append({"text": f"AVAILABILITY QUERY RESULTS - {self.sheet_name}", "cls": "heading"})
            lines.append({"text": f"Date range: {start_str} to {end_str}", "cls": "heading"})
            if day_filter:
                lines.append({"text": f"Filter: {day_filter}", "cls": "heading"})
            if min_spots is not None:
                lines.append({"text": f"Minimum spots: {min_spots}", "cls": "heading"})
            lines.append({"text": f"Total matching dates: {len(results)}", "cls": "heading"})
            lines.append({"text": "", "cls": "divider"})

            if not results:
                lines.append({"text": "No dates found matching criteria.", "cls": "dim"})
            else:
                for r in results:
                    dj_list = f" ({', '.join(r['djs'])})" if r['djs'] else ""
                    cls = "green" if r['spots'] >= 2 else ("yellow" if r['spots'] == 1 else "red")
                    lines.append({"text": f"{r['date']}: {r['spots']} spot(s) available{dj_list}", "cls": cls})

            return lines

        except Exception as e:
            return [{"text": f"Error: {str(e)}", "cls": "red"}]

    def check_dj_range(self, dj_name, start_str, end_str):
        """Check a specific DJ's availability - mirrors query_dj_availability()."""
        try:
            auto_clear_stale_cache(60)
            start_date, end_date = self._parse_dates(start_str, end_str)
            if not start_date:
                return [{"text": "Invalid date format. Use MM-DD.", "cls": "red"}]
            if start_date > end_date:
                return [{"text": "Start date must be before end date.", "cls": "red"}]

            all_data = get_bulk_availability_data(
                self.sheet_name, self.service, self.spreadsheet, self.spreadsheet_id,
                start_date, end_date
            )
            if all_data is None:
                return [{"text": f"Error fetching data from {self.sheet_name} sheet.", "cls": "red"}]

            available_dates = []
            booked_dates = []
            backup_dates = []
            booked_date_infos = []

            for date_info in all_data:
                if dj_name not in date_info['selected_data']:
                    continue
                value = date_info['selected_data'][dj_name]
                is_bold = date_info['bold_status'].get(dj_name, False)
                clean_value = str(value).replace(" (BOLD)", "") if value else ""
                vl = clean_value.lower()

                if "booked" in vl or vl == "stanford" or vl == "reserved":
                    booked_date_infos.append(date_info)
                elif "backup" in vl:
                    backup_dates.append(date_info['date'])
                else:
                    if dj_name == "Stefano" and (not clean_value or clean_value == ""):
                        available_dates.append(f"{date_info['date']} [MAYBE]")
                    else:
                        can_book, can_backup = check_dj_availability(
                            dj_name, clean_value, date_info['date_obj'], is_bold, self.sheet_name, warn=False
                        )
                        if can_book:
                            available_dates.append(date_info['date'])

            # Look up venues for booked dates
            for date_info in booked_date_infos:
                month_day = date_info['date_obj'].strftime("%m-%d")
                gig_bookings = get_gig_database_bookings(self.sheet_name, month_day)
                assigned = gig_bookings.get('assigned', {})
                if dj_name in assigned:
                    venue = assigned[dj_name].get('venue', '')
                    booked_dates.append(f"{date_info['date']} ({venue})" if venue else date_info['date'])
                else:
                    booked_dates.append(date_info['date'])

            lines = []
            lines.append({"text": f"DJ AVAILABILITY QUERY - {self.sheet_name}", "cls": "heading"})
            lines.append({"text": f"DJ: {dj_name}", "cls": "heading"})
            lines.append({"text": f"Date range: {start_str} to {end_str}", "cls": "heading"})
            lines.append({"text": "", "cls": "divider"})

            lines.append({"text": f"AVAILABLE FOR BOOKING ({len(available_dates)} dates):", "cls": "green"})
            for d in available_dates:
                lines.append({"text": f"  {d}", "cls": "green"})
            if not available_dates:
                lines.append({"text": "  None", "cls": "dim"})

            lines.append({"text": "", "cls": "divider"})
            lines.append({"text": f"BOOKED ({len(booked_dates)} dates):", "cls": "red"})
            for d in booked_dates:
                lines.append({"text": f"  {d}", "cls": "red"})
            if not booked_dates:
                lines.append({"text": "  None", "cls": "dim"})

            lines.append({"text": "", "cls": "divider"})
            lines.append({"text": f"BACKUP ({len(backup_dates)} dates):", "cls": "blue"})
            for d in backup_dates:
                lines.append({"text": f"  {d}", "cls": "blue"})
            if not backup_dates:
                lines.append({"text": "  None", "cls": "dim"})

            return lines

        except Exception as e:
            return [{"text": f"Error: {str(e)}", "cls": "red"}]

    def check_fully_booked(self, start_str, end_str):
        """List fully booked dates - mirrors show_fully_booked_dates()."""
        try:
            start_date, end_date = self._parse_dates(start_str, end_str)
            if not start_date:
                return [{"text": "Invalid date format. Use MM-DD.", "cls": "red"}]
            if start_date > end_date:
                return [{"text": "Start date must be before end date.", "cls": "red"}]

            fully_booked = get_fully_booked_dates(
                self.sheet_name, self.service, self.spreadsheet, self.spreadsheet_id,
                start_date, end_date
            )
            if fully_booked is None:
                return [{"text": f"Error fetching data from {self.sheet_name} sheet.", "cls": "red"}]

            lines = []
            lines.append({"text": f"FULLY BOOKED DATES - {self.sheet_name}", "cls": "heading"})
            lines.append({"text": f"Date range: {start_str} to {end_str}", "cls": "heading"})
            lines.append({"text": "", "cls": "divider"})

            if not fully_booked:
                lines.append({"text": "No fully booked dates found in this range!", "cls": "green"})
            else:
                lines.append({"text": f"Found {len(fully_booked)} fully booked date(s):", "cls": "red"})
                for booking in fully_booked:
                    lines.append({"text": "", "cls": "divider"})
                    lines.append({"text": booking['date'], "cls": "red"})
                    if booking.get('booked_djs'):
                        lines.append({"text": f"  Booked: {', '.join(booking['booked_djs'])}", "cls": "red"})
                    tba = booking['availability']['tba_bookings']
                    if tba > 0:
                        lines.append({"text": f"  TBA Bookings: {tba}", "cls": "red"})
                    if booking.get('aag_status'):
                        aag = booking['aag_status']
                        cls = "red" if 'reserved' in aag.lower() else ""
                        lines.append({"text": f"  AAG: {aag}", "cls": cls})
                    if booking.get('backup_assigned'):
                        lines.append({"text": f"  Backup Assigned: {', '.join(booking['backup_assigned'])}", "cls": "blue"})
                    if booking.get('available_to_book'):
                        lines.append({"text": f"  Available to Book: {', '.join(booking['available_to_book'])}", "cls": "green"})
                    if not booking.get('backup_assigned') and booking.get('available_to_backup'):
                        lines.append({"text": f"  Available to Backup: {', '.join(booking['available_to_backup'])}", "cls": "cyan"})

            if fully_booked:
                lines.append({"text": "", "cls": "divider"})
                lines.append({"text": "TIP: Review your open inquiries for these dates to notify couples.", "cls": "yellow"})
                lines.append({"text": "     [MAYBE] = Stefano blank cell - may be available if asked.", "cls": "yellow"})
            return lines

        except Exception as e:
            return [{"text": f"Error: {str(e)}", "cls": "red"}]

    def _parse_dates(self, start_str, end_str):
        try:
            s = datetime.strptime(f"{self.year}-{start_str}", "%Y-%m-%d")
            e = datetime.strptime(f"{self.year}-{end_str}", "%Y-%m-%d")
            return s, e
        except ValueError:
            return None, None


# ── Entry Point ──────────────────────────────────────────────────────────────

def main(year="2026"):
    api = Api(year)
    window = webview.create_window(
        f"DJ Availability — {year}",
        html=HTML,
        js_api=api,
        width=960,
        height=700,
        min_size=(800, 500),
    )
    webview.start()


if __name__ == "__main__":
    main("2026")
