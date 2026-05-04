"""
Wedding Fair Date Check — single-input availability lookup.

One window, one date field. Type 9-15-26 or 5-31-27 (slashes/dots also work),
hit Enter, get a big AVAILABLE / NOT AVAILABLE answer plus a slot count.

Run: python wedding_fair_check.py
"""

import re
import calendar
import webview

from dj_core import (
    init_google_sheets_from_file,
    get_date_availability_data,
    COLUMNS_2026,
    COLUMNS_2027,
)


SUPPORTED_YEARS = {"2026", "2027"}
NON_DJ_COLUMNS = {"Date", "TBA", "AAG"}


def _named_dj_count(sheet_name):
    cols = COLUMNS_2026 if sheet_name == "2026" else COLUMNS_2027
    return sum(1 for label in cols.values() if label not in NON_DJ_COLUMNS)


def parse_date(raw):
    """Parse a lenient date string into (sheet_name, month_day).

    Accepts M-D-YY, M/D/YY, M.D.YY, with 2- or 4-digit year. Raises ValueError
    with a user-friendly message if it can't make sense of the input.
    """
    parts = re.split(r"[-/.\s]+", (raw or "").strip())
    if len(parts) != 3:
        raise ValueError("Couldn't read that date. Try 9-15-26.")

    m_str, d_str, y_str = parts
    try:
        month = int(m_str)
        day = int(d_str)
        year_int = int(y_str)
    except ValueError:
        raise ValueError("Couldn't read that date. Try 9-15-26.")

    if len(y_str) == 2:
        year_int += 2000
    year = str(year_int)

    if year not in SUPPORTED_YEARS:
        raise ValueError(f"No matrix for {year} yet.")

    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("Couldn't read that date. Try 9-15-26.")

    return year, f"{month:02d}-{day:02d}"


class Api:
    def __init__(self):
        self.service = None
        self.spreadsheet = None
        self.spreadsheet_id = None
        self._init_sheets()

    def _init_sheets(self):
        try:
            self.service, self.spreadsheet, self.spreadsheet_id, _ = (
                init_google_sheets_from_file()
            )
        except Exception as e:
            print(f"Sheets init failed: {e}")

    def check(self, raw):
        try:
            sheet_name, month_day = parse_date(raw)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        if self.service is None:
            return {"ok": False, "error": "Can't reach Google Sheets. Check internet."}

        try:
            data = get_date_availability_data(
                sheet_name, month_day, self.service, self.spreadsheet, self.spreadsheet_id
            )
        except Exception as e:
            return {"ok": False, "error": f"Lookup failed: {e}"}

        if "error" in data:
            err = data["error"]
            if err == "invalid_format":
                return {"ok": False, "error": "Couldn't read that date. Try 9-15-26."}
            if err == "not_found":
                return {"ok": False, "error": f"No row for {data.get('formatted_date', raw)} in matrix."}
            if err == "worksheet_not_found":
                return {"ok": False, "error": f"No matrix tab for {sheet_name}."}
            return {"ok": False, "error": f"Lookup error: {err}"}

        date_obj = data["date_obj"]
        availability = data["availability"]

        if sheet_name == "2027":
            # 2027 has a 2-event cap. AAG=RESERVED counts toward the cap.
            booked_count = availability.get("booked_count", 0)
            if availability.get("aag_reserved"):
                booked_count += 1
            spots = max(0, 2 - booked_count)
            sub = f"{spots} of 2 spots open"
        else:
            spots = availability["available_spots"]
            total = _named_dj_count(sheet_name)
            sub = f"{spots} of {total} DJs open"

        stefano_cell = (
            str(data["selected_data"].get("Stefano", ""))
            .replace(" (BOLD)", "")
            .strip()
        )
        stefano_maybe = (
            sheet_name == "2026"
            and date_obj.weekday() == 5  # Saturday
            and spots == 0
            and not stefano_cell
        )

        if spots > 0:
            status = "available"
        elif stefano_maybe:
            status = "maybe"
        else:
            status = "unavailable"

        return {
            "ok": True,
            "status": status,
            "sub": sub,
            "date_long": f"{calendar.day_name[date_obj.weekday()]}, "
                          f"{calendar.month_name[date_obj.month]} {date_obj.day}, {date_obj.year}",
        }


HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>BIG FUN — Date Check</title>
<style>
  :root {
    --bg: #0e1116;
    --panel: #161b22;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --green: #3fb950;
    --red: #f85149;
    --border: #30363d;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 28px 24px;
  }
  .title {
    align-self: flex-start;
    color: var(--muted);
    font-size: 13px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 18px;
  }
  .input-wrap {
    width: 100%;
    max-width: 560px;
  }
  input#date {
    width: 100%;
    background: var(--panel);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 22px 24px;
    font-size: 32px;
    font-weight: 500;
    letter-spacing: 0.02em;
    outline: none;
    text-align: center;
  }
  input#date:focus {
    border-color: var(--accent);
  }
  input#date::placeholder {
    color: #4d5560;
    font-weight: 400;
  }
  .result {
    width: 100%;
    max-width: 560px;
    margin-top: 32px;
    text-align: center;
    min-height: 200px;
  }
  .date-line {
    color: var(--muted);
    font-size: 18px;
    margin-bottom: 16px;
  }
  .banner {
    display: inline-block;
    padding: 24px 56px;
    border-radius: 14px;
    font-size: 48px;
    font-weight: 700;
    letter-spacing: 0.04em;
  }
  .banner.green {
    background: rgba(63, 185, 80, 0.15);
    color: var(--green);
    border: 2px solid rgba(63, 185, 80, 0.5);
  }
  .banner.red {
    background: rgba(248, 81, 73, 0.15);
    color: var(--red);
    border: 2px solid rgba(248, 81, 73, 0.5);
  }
  .banner.amber {
    background: rgba(210, 153, 34, 0.15);
    color: #e3b341;
    border: 2px solid rgba(210, 153, 34, 0.5);
  }
  .sub {
    margin-top: 16px;
    font-size: 18px;
    color: var(--muted);
  }
  .error {
    margin-top: 24px;
    color: var(--red);
    font-size: 18px;
  }
  .hint {
    margin-top: 18px;
    color: var(--muted);
    font-size: 13px;
  }
</style>
</head>
<body>
  <div class="title">BIG FUN — Date Check</div>
  <div class="input-wrap">
    <input id="date" type="text" autofocus autocomplete="off"
           placeholder="9-15-26  or  5-31-27" />
    <div class="hint">Type a date and press Enter</div>
  </div>
  <div class="result" id="result"></div>

<script>
  const input = document.getElementById('date');
  const result = document.getElementById('result');

  function clearResult() {
    while (result.firstChild) result.removeChild(result.firstChild);
  }

  function makeDiv(cls, text) {
    const el = document.createElement('div');
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  }

  function showError(msg) {
    clearResult();
    result.appendChild(makeDiv('error', msg));
  }

  function showResult(r) {
    clearResult();
    result.appendChild(makeDiv('date-line', r.date_long));

    let cls, word, sub;
    if (r.status === 'available') {
      cls = 'green'; word = 'AVAILABLE';
      sub = r.sub;
    } else if (r.status === 'maybe') {
      cls = 'amber'; word = 'MAYBE';
      sub = 'Stefano not yet confirmed for this date';
    } else {
      cls = 'red'; word = 'NOT AVAILABLE';
      sub = r.sub;
    }

    result.appendChild(makeDiv('banner ' + cls, word));
    result.appendChild(makeDiv('sub', sub));
  }

  async function lookup() {
    const raw = input.value.trim();
    if (!raw) { clearResult(); return; }
    try {
      const r = await pywebview.api.check(raw);
      if (r.ok) showResult(r);
      else showError(r.error);
    } catch (e) {
      showError('Lookup failed: ' + e);
    }
  }

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); lookup(); }
  });
  input.addEventListener('input', clearResult);
</script>
</body>
</html>
"""


def main():
    api = Api()
    webview.create_window(
        "BIG FUN — Date Check",
        html=HTML,
        js_api=api,
        width=720,
        height=560,
        min_size=(640, 480),
    )
    webview.start()


if __name__ == "__main__":
    main()
