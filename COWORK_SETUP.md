# Cowork Initial Prompt — DJ Availability Checker

Use this as your initial instruction when starting a Cowork session:

---

## Suggested Prompt

```
You are helping me develop and maintain the DJ Availability Checker system for Big Fun DJ, a wedding/event DJ company.

**Start by reading these files in order:**
1. PROJECT_CONTEXT.md — Business rules, DJ roster, system architecture
2. SYSTEM_REFERENCE.md — Availability checker deep dive
3. GIG_TO_CALENDAR_REFERENCE.md — Calendar automation logic
4. DASHBOARD_REFERENCE.md — Dashboard dedup rules

**Key things to know:**
- dj_core.py contains ALL business logic — change rules there, not in UI files
- Stefano blank ≠ available (shows [MAYBE], doesn't count toward spots)
- Felipe is backup-only in 2026+ unless marked "OK"
- Woody's bold OUT vs plain OUT matters (bold = fully unavailable)
- The gig database (FileMaker) is source of truth for confirmed bookings
- The availability matrix (Google Sheets) is source of truth for DJ scheduling

**When I ask you to make changes:**
1. Read the relevant reference doc first
2. Check dj_core.py for existing logic before adding new code
3. Run tests if available
4. Use --dry-run mode when testing booking manager changes

**Current DJ roster (2026):**
- Paul (owner, standard rules)
- Henry (weekends only for events)
- Woody (prefers weekdays, bold OUT = unavailable, plain OUT on weekend = can backup)
- Stefano (max 2/month, blank = MAYBE)
- Felipe (backup-only, blank = can backup, OK = can book)
- Stephanie (AAG overflow only in 2026, joins as weekend DJ in 2027)

The repo is connected to this Cowork session. The main folder is dj-availability-checker.
```

---

## Files to Ensure Are in the Repo

Before starting Cowork, confirm these are committed:

**Reference Docs:**
- [ ] PROJECT_CONTEXT.md
- [ ] SYSTEM_REFERENCE.md
- [ ] GIG_TO_CALENDAR_REFERENCE.md
- [ ] DASHBOARD_REFERENCE.md

**Core Code:**
- [ ] dj_core.py
- [ ] check_dj.py
- [ ] gig_booking_manager.py
- [ ] dj_app.py
- [ ] dashboard.py

**Skills:**
- [ ] booking-parser.skill (or SKILL.md in a skills folder)

**Config (gitignored but noted):**
- your-credentials.json
- .streamlit/secrets.toml

---

## Notes

- Cowork doesn't have access to this chat's memory, so the PROJECT_CONTEXT.md serves as the "brain dump"
- If you make significant changes in Cowork, consider updating the reference docs
- The skills files help Cowork understand specific parsing/comparison tasks
