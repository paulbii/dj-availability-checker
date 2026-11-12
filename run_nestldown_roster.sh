#!/bin/zsh
# Wrapper for the Nestldown roster launchd job (com.bigfundj.nestldown-roster).
# Runs the generator and, if it exits non-zero, pushes a flagged Apple Reminder
# so a silent crash is visible. A wrapper (not a try/except inside the script) is
# used on purpose: the failure mode that started this was an ImportError at the
# top of nestldown_roster.py, which in-script error handling can't catch.

PY=/Users/paulburchfield/miniconda3/bin/python3
SCRIPT=/Users/paulburchfield/Documents/projects/dj-availability-checker/nestldown_roster.py
REMCTL=/Users/paulburchfield/.local/bin/remctl
SENTINEL=$HOME/.nestldown-roster-alert-sent

# Run the generator, capturing output so we can quote the tail in the alert.
OUT=$("$PY" "$SCRIPT" 2>&1)
STATUS=$?
print -r -- "$OUT"

if [ $STATUS -eq 0 ]; then
  # Success: clear the sentinel so the next failure alerts fresh.
  rm -f "$SENTINEL"
  exit 0
fi

# Failure. Alert once per outage (sentinel present = already alerted, still down).
if [ ! -f "$SENTINEL" ]; then
  TAIL=$(print -r -- "$OUT" | tail -n 3 | tr '\n' ' ')
  TITLE="Nestldown roster page stopped updating (exit $STATUS)"
  NOTE="The nightly auto-update crashed, so the live page is frozen. Last log: ${TAIL} | Fix: run run_nestldown_roster.sh in dj-availability-checker, then check /tmp/nestldown-roster.log"
  # remctl often cannot see the BIG FUN list ("list not found"); the reminders CLI can.
  # The sentinel is written only when an alert really went out, so a failed alert
  # is tried again on the next run instead of going quiet.
  if "$REMCTL" add "$TITLE" -l "BIG FUN" -n "$NOTE" -f 2>&1 \
     || /opt/homebrew/bin/reminders add "BIG FUN" "$TITLE" --priority high --notes "$NOTE" 2>&1; then
    touch "$SENTINEL"
  fi
fi

exit $STATUS
