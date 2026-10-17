#!/bin/bash
# One command to ship a change to every availability tool.
#   ./release.sh "commit message"
#
# 1. runs the test suite
# 2. freezes both DJ Availability apps (build_apps.sh) and installs them
#    into /Applications, replacing the old bundles
# 3. commits whatever is STAGED (stage with git add first; nothing is
#    staged for you) and pushes, which redeploys the Streamlit Cloud app
# Without a message, steps 1-2 run and the commit/push is skipped.
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-}"

# The apps are built from the working tree but the commit takes the index;
# the pre-commit check compares the two. Refuse to run with them apart.
if ! git diff --quiet -- dj_core.py check_dj_gui.py; then
  echo "dj_core.py or check_dj_gui.py has unstaged edits. git add them (or revert) first." >&2
  exit 1
fi

echo "== tests"
.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED)" | tee /tmp/release-tests.txt
grep -q "^OK" /tmp/release-tests.txt

echo "== build"
./build_apps.sh

echo "== install"
for YEAR in 2026 2027; do
  SRC="release/DJ Availability $YEAR.app"
  DST="/Applications/DJ Availability $YEAR.app"
  if pgrep -f "$DST/Contents/MacOS" >/dev/null; then
    echo "Quit 'DJ Availability $YEAR' first (it is running), then re-run." >&2
    exit 1
  fi
  rm -rf "$DST"
  ditto "$SRC" "$DST"
  codesign -v "$DST"
  echo "installed: $DST ($(cat "$DST/Contents/Resources/source-stamp.txt"))"
done

if [ -z "$MSG" ]; then
  echo "== no commit message given; skipping commit and push"
  exit 0
fi

if git diff --cached --quiet; then
  echo "== nothing staged; skipping commit and push (git add the files first)"
  exit 0
fi

echo "== commit"
git commit -m "$MSG

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"

echo "== push"
git push
echo "Done. Streamlit Cloud redeploys from main within a few minutes."
