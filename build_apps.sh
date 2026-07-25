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

  APP="dist/DJ Availability $YEAR.app"
  # app_icon.icns carries a com.apple.provenance xattr that macOS re-pins;
  # it breaks PyInstaller's built-in ad-hoc signing ("detritus not allowed").
  # Strip xattrs and re-sign, then verify. Retry loop: this repo lives under
  # Documents (iCloud-synced), and the file provider re-tags freshly written
  # files for up to ~a minute after the build, so early strip+sign attempts
  # can fail ("detritus not allowed") until the sync sweep settles.
  SIGNED=0
  for ATTEMPT in $(seq 1 12); do
    xattr -cr "$APP"
    if codesign -s - --force --all-architectures --timestamp --deep "$APP"; then
      SIGNED=1
      break
    fi
    echo "codesign attempt $ATTEMPT failed (xattrs re-pinned mid-sign); retrying in 5s..."
    sleep 5
  done
  [ "$SIGNED" = 1 ] || { echo "ERROR: codesign failed after 12 attempts: $APP" >&2; exit 1; }
  codesign -v "$APP"

  mv "$APP" release/
done

rm -rf build dist ./*.spec
echo "Done. Apps in release/:"
ls -d release/*.app
