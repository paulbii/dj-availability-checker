#!/bin/bash
# Pre-commit check: if dj_core.py or check_dj_gui.py is staged, the
# installed DJ Availability apps must already contain exactly the staged
# sources. Otherwise a rule change reaches GitHub with the desktop apps
# behind it, which is what happened on 2026-10-17.
#   SKIP_FROZEN_CHECK=1 git commit ...   # machines without the apps (Henry)
set -euo pipefail
cd "$(dirname "$0")/.."

[ "${SKIP_FROZEN_CHECK:-}" = "1" ] && exit 0

if ! git diff --cached --name-only | grep -qxE "dj_core\.py|check_dj_gui\.py"; then
  exit 0
fi

WANT="$(scripts/source_stamp.sh --staged)"
for YEAR in 2026 2027; do
  STAMP_FILE="/Applications/DJ Availability $YEAR.app/Contents/Resources/source-stamp.txt"
  HAVE="$(cat "$STAMP_FILE" 2>/dev/null || echo missing)"
  if [ "$HAVE" != "$WANT" ]; then
    cat >&2 <<EOF
Frozen app is stale: DJ Availability $YEAR has $HAVE, staged sources are $WANT.
Run ./release.sh "message" (tests, build, install, commit, push) instead of
git commit. Bypass on a machine without the apps: SKIP_FROZEN_CHECK=1.
EOF
    exit 1
  fi
done
