# Freeze DJ Availability GUI Apps (PyInstaller) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two Automator wrapper apps (`DJ Availability 2026.app` / `DJ Availability 2027.app`) with self-contained PyInstaller `.app` bundles that have a real icon, no Automator spinning-gear, and no dependency on the project folder path or venv.

**Architecture:** The existing pywebview GUI (`check_dj_gui.py` + `dj_core.py`) is frozen as-is. One small addition to `dj_core.py`: `init_google_sheets_auto()`, which loads the Google service-account JSON from the macOS Keychain (service `bigfun-google-service-account`, account `paul`) and falls back to `your-credentials.json` in the CWD. This removes the frozen app's only local-file dependency while leaving every other tool (terminal, Streamlit, booking manager) untouched. Credentials are never baked into the bundle.

**Tech Stack:** Python 3.13 (miniconda, non-framework — this is why PyInstaller, not py2app), PyInstaller ≥6.10, pywebview 6.2.1, keyring.

**Working directory for all commands:** `/Users/paulburchfield/Documents/projects/dj-availability-checker`

**Key facts the executor needs:**
- The Automator apps run `check_20XX_gui.py` via a shell action; that's the whole wrapper. The gear in the menu bar is the Automator applet stub staying resident.
- `check_2027_gui.py` is a 5-line launcher: `from check_dj_gui import main; main("2027")`. It is a perfect PyInstaller entry script; do NOT create new entry scripts.
- `check_dj_gui.py` calls `init_google_sheets_from_file()` exactly once (line ~645) with its default relative path `your-credentials.json` — the only reason the Automator command `cd`s to the project dir first.
- `init_google_sheets_from_dict()` already exists in `dj_core.py` and returns the same 4-tuple as `init_google_sheets_from_file()`.
- `dj_core.py` does NOT import `json` at top level; import it inside the new helper.
- `your-credentials.json` is gitignored (verified). The repo is on public GitHub — never commit the JSON or the icns of anything containing secrets.
- `tests/` exists but is empty (no established test patterns). Use stdlib `unittest`.
- Secrets standard (EA repo, `references/secrets-management.md`): Keychain via `keyring`, service names `bigfun-*`, account `paul`. Plaintext copies of secrets in new locations are forbidden.
- `app_icon.png` (512×512) exists at project root.
- Out of scope: `DJ Availability Checker.app` (a third Automator app that launches the Streamlit web app — different animal, note it to Paul as an optional follow-up).

---

### Task 1: Keychain credential + `init_google_sheets_auto()`

**Files:**
- Modify: `dj_core.py` (add one function after `init_google_sheets_from_dict`, ~line 670)
- Modify: `check_dj_gui.py:16` (import) and `check_dj_gui.py:645` (call site)
- Test: `tests/test_init_google_sheets_auto.py` (new)

- [ ] **Step 0: Install keyring into the venv (it's in requirements.txt but was never installed)**

```bash
.venv/bin/pip install "keyring>=25.7.0"
.venv/bin/python -c "import keyring; print('keyring OK:', keyring.__version__)"
```

Expected: `keyring OK: <version>`. **Must be installed in `.venv`, not conda base** — PyInstaller bundles only what's importable from the build venv; if keyring is missing there, the frozen app's `try/except` silently falls back to the file path and fails with an unhelpful "Error connecting to Google Sheets."

- [ ] **Step 1: Store the service-account JSON in the Keychain**

```bash
.venv/bin/python - <<'EOF'
import keyring, pathlib
blob = pathlib.Path("your-credentials.json").read_text()
keyring.set_password("bigfun-google-service-account", "paul", blob)
back = keyring.get_password("bigfun-google-service-account", "paul")
assert back == blob
print(f"Stored OK ({len(back)} chars)")
EOF
```

Expected: `Stored OK (2417 chars)`. (Do NOT delete `your-credentials.json` — the terminal/Streamlit tools still use it as fallback.)

- [ ] **Step 2: Write the failing test**

Create `tests/test_init_google_sheets_auto.py`:

```python
"""Tests for dj_core.init_google_sheets_auto (Keychain-first credential loading)."""
import json
import unittest
from unittest import mock

import dj_core


class TestInitGoogleSheetsAuto(unittest.TestCase):
    def test_uses_keychain_blob_when_present(self):
        blob = json.dumps({"type": "service_account"})
        with mock.patch("keyring.get_password", return_value=blob), \
             mock.patch.object(dj_core, "init_google_sheets_from_dict",
                               return_value="DICT") as from_dict, \
             mock.patch.object(dj_core, "init_google_sheets_from_file",
                               return_value="FILE") as from_file:
            result = dj_core.init_google_sheets_auto()
        from_dict.assert_called_once_with({"type": "service_account"})
        from_file.assert_not_called()
        self.assertEqual(result, "DICT")

    def test_falls_back_to_file_when_keychain_empty(self):
        with mock.patch("keyring.get_password", return_value=None), \
             mock.patch.object(dj_core, "init_google_sheets_from_file",
                               return_value="FILE") as from_file:
            result = dj_core.init_google_sheets_auto()
        from_file.assert_called_once_with()
        self.assertEqual(result, "FILE")

    def test_falls_back_to_file_when_keyring_errors(self):
        with mock.patch("keyring.get_password", side_effect=RuntimeError("no backend")), \
             mock.patch.object(dj_core, "init_google_sheets_from_file",
                               return_value="FILE"):
            self.assertEqual(dj_core.init_google_sheets_auto(), "FILE")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test — verify it fails**

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```

Expected: 3 errors, `AttributeError: module 'dj_core' has no attribute 'init_google_sheets_auto'`. (If you instead see `ModuleNotFoundError: keyring`, Step 0 was skipped — go back.)

- [ ] **Step 4: Implement the helper**

In `dj_core.py`, directly after `init_google_sheets_from_dict()`:

```python
def init_google_sheets_auto():
    """Initialize Google Sheets from the best available credential source.

    Tries the macOS Keychain first (service 'bigfun-google-service-account',
    account 'paul') so frozen .app bundles work from any directory, then
    falls back to your-credentials.json in the working directory (terminal
    and Streamlit tools are unaffected).
    """
    import json
    try:
        import keyring
        blob = keyring.get_password("bigfun-google-service-account", "paul")
    except Exception:
        blob = None
    if blob:
        return init_google_sheets_from_dict(json.loads(blob))
    return init_google_sheets_from_file()
```

- [ ] **Step 5: Run the test — verify it passes**

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```

Expected: `OK` (3 tests).

- [ ] **Step 6: Wire the GUI to the new helper**

In `check_dj_gui.py`: add `init_google_sheets_auto` to the `from dj_core import (...)` block (line ~16), and change the single call site (line ~645) from `init_google_sheets_from_file()` to `init_google_sheets_auto()`. Keep `init_google_sheets_from_file` in the import list only if it is still referenced elsewhere (it isn't — grep to confirm, then remove it from the import).

- [ ] **Step 7: Verify the GUI still works from source (now via Keychain)**

```bash
.venv/bin/python check_2027_gui.py
```

Expected: window opens ("DJ Availability — 2027"); run one date check (e.g. `06-19`) and confirm results render. A Keychain access prompt may appear — click **Always Allow**. Close the window.

- [ ] **Step 8: Commit**

```bash
git add dj_core.py check_dj_gui.py tests/test_init_google_sheets_auto.py
git commit -m "feat: Keychain-first Google credentials (init_google_sheets_auto) for frozen GUI apps"
```

---

### Task 2: App icon (.icns)

**Files:**
- Create: `app_icon.icns` (generated from existing `app_icon.png`, 512×512)

- [ ] **Step 1: Generate the iconset and icns**

```bash
rm -rf /tmp/app_icon.iconset && mkdir /tmp/app_icon.iconset
for s in 16 32 64 128 256; do
  sips -z $s $s app_icon.png --out /tmp/app_icon.iconset/icon_${s}x${s}.png >/dev/null
  d=$((s*2))
  sips -z $d $d app_icon.png --out /tmp/app_icon.iconset/icon_${s}x${s}@2x.png >/dev/null
done
sips -z 512 512 app_icon.png --out /tmp/app_icon.iconset/icon_512x512.png >/dev/null
iconutil -c icns /tmp/app_icon.iconset -o app_icon.icns
ls -la app_icon.icns
```

Expected: `app_icon.icns` exists, non-zero size. (No 1024px source; omitting `icon_512x512@2x` is fine.)

- [ ] **Step 2: Commit**

```bash
git add app_icon.icns
git commit -m "build: generate app_icon.icns from app_icon.png"
```

---

### Task 3: PyInstaller build of the 2027 app + smoke test

**Files:**
- Modify: `.gitignore` (add `release/` and `*.spec`)

- [ ] **Step 1: Install PyInstaller into the venv**

```bash
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller --version
```

Expected: version ≥ 6.10 prints. (`pyinstaller-hooks-contrib` comes with it and covers pywebview, keyring, and googleapiclient.)

- [ ] **Step 2: Build the 2027 app**

```bash
.venv/bin/pyinstaller --noconfirm --clean --windowed \
  --name "DJ Availability 2027" \
  --icon app_icon.icns \
  --osx-bundle-identifier "com.bigfundj.dj-availability-2027" \
  check_2027_gui.py
```

Expected: ends with `Building BUNDLE ... completed successfully.` Output at `dist/DJ Availability 2027.app`.

- [ ] **Step 3: Smoke test from Terminal first (visible tracebacks)**

Launch from a neutral CWD so a silent file-fallback to `your-credentials.json` can't mask a broken Keychain path:

```bash
cd /tmp && "/Users/paulburchfield/Documents/projects/dj-availability-checker/dist/DJ Availability 2027.app/Contents/MacOS/DJ Availability 2027"; cd -
```

Expected: window opens; run a real date check and confirm DJ statuses render; Keychain prompt on first access — **Always Allow**. Ctrl-C after closing the window.

Troubleshooting if it crashes on startup:
- `ModuleNotFoundError` for a Google package → rebuild adding `--collect-data googleapiclient --collect-submodules googleapiclient`.
- keyring backend error → rebuild adding `--collect-submodules keyring.backends`.
- Blank window / WebKit issue → rebuild adding `--collect-all webview`.

- [ ] **Step 4: Smoke test as a real app launch**

```bash
open "dist/DJ Availability 2027.app"
```

Expected: app launches from Finder context, proper icon in Dock, **no spinning gear in the menu bar**, date check works.

- [ ] **Step 5: Ignore build artifacts**

Add to `.gitignore` (a `dist/`/`build/` pair already exists under the Python section — add these under it):

```
release/
*.spec
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore
git commit -m "build: ignore PyInstaller artifacts"
```

---

### Task 4: `build_apps.sh` — one command builds both year apps

> **SUPERSEDED NOTE (2026-07-25, execution):** the script below is the pre-amendment version. The shipped `build_apps.sh` at the project root additionally strips xattrs and ad-hoc re-signs each bundle in a bounded retry loop — `app_icon.icns` carries a `com.apple.provenance` xattr, and the iCloud file provider (repo lives under Documents) re-pins xattrs for up to ~a minute after a build, which breaks PyInstaller's built-in codesign ("detritus not allowed"). **`build_apps.sh` is the source of truth; don't re-execute the script below from this doc.**

**Files:**
- Create: `build_apps.sh`

- [ ] **Step 1: Write the build script**

```bash
#!/bin/bash
# Build self-contained .app bundles for the DJ Availability GUI apps.
# Output: release/DJ Availability <year>.app
#
# Re-run this (then the install step in docs/plans/2026-07-25-freeze-gui-apps-pyinstaller.md)
# whenever check_dj_gui.py or dj_core.py changes — the frozen apps do NOT
# pick up source edits on their own.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf release build dist && mkdir release

for YEAR in 2026 2027; do
  .venv/bin/pyinstaller --noconfirm --clean --windowed \
    --name "DJ Availability $YEAR" \
    --icon app_icon.icns \
    --osx-bundle-identifier "com.bigfundj.dj-availability-$YEAR" \
    "check_${YEAR}_gui.py"
  mv "dist/DJ Availability $YEAR.app" release/
done

rm -rf build dist ./*.spec
echo "Done. Apps in release/:"
ls -d release/*.app
```

(If Task 3 needed extra `--collect-*` flags, include the same flags here.)

- [ ] **Step 2: Make it executable and run it**

```bash
chmod +x build_apps.sh && ./build_apps.sh
```

Expected: `release/DJ Availability 2026.app` and `release/DJ Availability 2027.app` both listed.

- [ ] **Step 3: Spot-check the 2026 app**

```bash
open "release/DJ Availability 2026.app"
```

Expected: window titled "DJ Availability — 2026", date check works. (Fresh adhoc signature → one new Keychain prompt per app; **Always Allow**.)

- [ ] **Step 4: Commit**

```bash
git add build_apps.sh
git commit -m "build: build_apps.sh freezes both GUI year apps with PyInstaller"
```

---

### Task 5: Install to /Applications and verify

**⚠️ Replacing apps in /Applications is the outward-facing step — confirm with Paul before executing this task.**

- [ ] **Step 1: Archive the old Automator apps (don't delete)**

```bash
mkdir -p archive/automator-apps
mv "/Applications/DJ Availability 2026.app" archive/automator-apps/
mv "/Applications/DJ Availability 2027.app" archive/automator-apps/
```

- [ ] **Step 2: Install the new apps**

```bash
ditto "release/DJ Availability 2026.app" "/Applications/DJ Availability 2026.app"
ditto "release/DJ Availability 2027.app" "/Applications/DJ Availability 2027.app"
```

Same names and paths as before, so Spotlight, Dock pins, and any StreamDeck launch buttons keep working.

- [ ] **Step 3: Final verification checklist (Paul, hands-on)**

- `open "/Applications/DJ Availability 2027.app"` → window opens.
- Menu bar: **no spinning gear** while the app runs.
- Dock: proper name + custom icon (not a generic Python/Automator icon).
- Run one real date check; result matches a run of `.venv/bin/python check_2027.py` option 1 for the same date.
- Quit the app; verify no orphan process: `pgrep -fl "DJ Availability"` → nothing.
- Repeat window-open check for the 2026 app.

- [ ] **Step 4: Commit the archive note**

```bash
git add -A archive/automator-apps 2>/dev/null || true
git commit -m "chore: retire Automator wrapper apps, replaced by PyInstaller bundles" --allow-empty
```

(The `.app` bundles may be too noisy for git; if so, leave them untracked — the folder keeps them safe locally, which is the point.)

---

## Post-install notes (surface to Paul at the end)

1. **Rebuild rule:** the frozen apps snapshot the code. After any edit to `dj_core.py` / `check_dj_gui.py`: `./build_apps.sh`, then re-run Task 5 Steps 1–2 (the mv of old versions can just be `rm -rf` of the previous frozen copies at that point — they're reproducible).
2. **Keychain prompts:** each rebuild produces a new adhoc code signature, so macOS asks once per app for Keychain access again. Always Allow and move on.
3. **Out of scope, optional follow-up:** `DJ Availability Checker.app` (the Streamlit launcher) is still an Automator applet with the same spinning-gear behavior. Different fix (it launches a server + browser); do later if the gear bothers you there too.
4. **Terminal + Streamlit tools are unchanged** — still run from live source with the JSON file. Only the two GUI apps read Keychain first.
