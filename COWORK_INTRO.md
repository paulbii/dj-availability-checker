This is the DJ Availability Checker project for Big Fun DJ, a wedding and event DJ company.

**Before doing anything, read these docs in order:**
1. PROJECT_CONTEXT.md — Business rules, DJ roster, system architecture, and how everything connects
2. SYSTEM_REFERENCE.md — Deep dive on the availability checker
3. GIG_TO_CALENDAR_REFERENCE.md — Calendar automation logic
4. DASHBOARD_REFERENCE.md — Dashboard metrics and deduplication rules

**Critical rules:**
- All business logic lives in dj_core.py — change rules there, not in UI files
- Stefano blank ≠ available (shows [MAYBE], never auto-counted)
- Felipe is backup-only in 2026+ unless cell shows "OK"
- Woody's bold OUT vs plain OUT matters for backup eligibility
- Unknown cell values should warn and be treated as unavailable

**The codebase:**
- check_dj.py — Terminal availability checker
- dj_app.py — Streamlit availability checker
- gig_booking_manager.py — Automates matrix + calendar after booking
- dashboard.py — Operations dashboard

When making changes, check existing logic in dj_core.py first. Use --dry-run for testing booking manager changes.
