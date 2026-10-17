#!/bin/bash
# Print a short hash of the sources frozen into the DJ Availability apps.
#   scripts/source_stamp.sh           # working tree
#   scripts/source_stamp.sh --staged  # git index (what a commit would contain)
# Used by build_apps.sh (writes it into each bundle) and
# scripts/check_frozen_apps.sh (compares it in the pre-commit hook).
set -euo pipefail
cd "$(dirname "$0")/.."
FILES="dj_core.py check_dj_gui.py"
for f in $FILES; do
  if [ "${1:-}" = "--staged" ]; then git show ":$f"; else cat "$f"; fi
done | shasum -a 256 | cut -c1-16
