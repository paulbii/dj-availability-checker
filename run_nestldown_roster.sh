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
  "$REMCTL" add "Nestldown roster page stopped updating (exit $STATUS)" \
    -l "BIG FUN" \
    -n "The nightly auto-update crashed, so the live page is frozen. Last log: ${TAIL} | Fix: run run_nestldown_roster.sh in dj-availability-checker, then check /tmp/nestldown-roster.log" \
    -f 2>&1
  touch "$SENTINEL"
fi

exit $STATUS
