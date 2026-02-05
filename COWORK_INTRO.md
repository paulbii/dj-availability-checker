This is the DJ Availability Checker project for Big Fun DJ, a wedding and event DJ company.

**Before doing anything, read these docs in order:**
1. PROJECT_CONTEXT.md — Business rules, DJ roster, system architecture, and how everything connects
2. SYSTEM_REFERENCE.md — Deep dive on the availability checker
3. DASHBOARD_REFERENCE.md — Dashboard metrics and deduplication rules

**Critical rules:**
- All business logic lives in dj_core.py — change rules there, not in UI files
- Stefano blank ≠ available (shows [MAYBE], never auto-counted)
- Felipe is backup-only in 2026+ unless cell shows "OK"
- Woody's bold OUT vs plain OUT matters for backup eligibility
- Unknown cell values should warn and be treated as unavailable

**The workflow:**
1. **When an inquiry comes in** → Use check_2026.py or check_2027.py to check availability
2. **Once an event books** → Use gig_booking_manager.py to update all systems

**The codebase:**
- check_2026.py / check_2027.py — Terminal availability checkers for inquiries (calls check_dj.py)
- check_dj.py — Shared core logic for terminal checker (year-agnostic)
- dj_app.py — Streamlit web interface for availability checking
- gig_booking_manager.py — Automates matrix + calendar updates after booking
- dashboard.py — Operations dashboard
- dj_core.py — Core business logic (all rules live here)

When making changes, check existing logic in dj_core.py first. Use --dry-run for testing booking manager changes.
