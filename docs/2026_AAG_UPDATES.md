# 2026 Updates - AAG Column & Stephanie Logic

## Summary
Updated all files to handle AAG (Allied Arts Guild) column in 2026 and properly handle Stephanie's 2026-specific availability rules.

---

## What Changed

### 1. Column Layout - 2026 Gets AAG Column

**2025:**
- No AAG column
- Stephanie in column K

**2026:** ← NEW
- AAG column added in column L
- Stephanie remains in column K
- Felipe remains in column H

**2027:**
- AAG column in column J
- Stephanie moves to column H
- Felipe moves to column L

### 2. Stephanie 2026 vs 2027 Logic

**Stephanie in 2026:**
- Blank cell = **NOT available** (only works when explicitly assigned)
- BOOKED = Booked for event
- RESERVED = Reserved for AAG event
- BACKUP = Assigned as backup
- OUT/other statuses = Standard rules

**Stephanie in 2027:**
- Blank cell + weekend = **Available**
- Blank cell + weekday = **NOT available**
- BOOKED/RESERVED/BACKUP = Same as 2026

### 3. AAG RESERVED Logic

**AAG Column:**
- RESERVED = Holding 1 spot for AAG (unassigned)
- Blank = No AAG hold on this date

**Stephanie Column:**
- RESERVED = Stephanie assigned to AAG event

**Important:** RESERVED appears in **either** AAG **or** Stephanie, never both:
- `AAG: RESERVED` → Holding spot, no DJ assigned yet
- `Stephanie: RESERVED` → Stephanie assigned to take the AAG spot

**Both reduce available spots by 1** (but it's the same 1 spot, not 2 separate spots)

### 4. Booking Flow Example

**Initial state (holding spot):**
```
AAG: RESERVED
Stephanie: (blank)
```

**Stephanie assigned:**
```
AAG: (blank)
Stephanie: RESERVED
```

**Fully booked:**
```
AAG: (blank)
Stephanie: BOOKED
```

---

## Files Updated

### 1. `dj_core.py`

**Column Definitions:**
```python
COLUMNS_2025 = {...}  # Original without AAG

COLUMNS_2026 = {      # NEW
    ...
    "L": "AAG"
}

COLUMNS_2027 = {...}  # AAG in column J
```

**Availability Logic:**
```python
# Stephanie 2026 - only available when explicitly assigned
if dj_name == "Stephanie" and year == "2026":
    if not value:
        return False, False  # Not available

# Handle RESERVED status
if value_lower == "reserved":
    return False, False  # Treated as booked
```

**Counting Logic:**
```python
# AAG RESERVED sets flag (reduces available spots)
if name == "AAG" and "reserved" in value_lower:
    aag_reserved = True

# Stephanie RESERVED counts as booking
if name == "Stephanie" and "reserved" in value_lower:
    booked_count += 1
```

### 2. `check_2026.py`

**AAG Column Display:**
```python
elif label == "AAG":
    value_lower = str(value).lower()
    if "reserved" in value_lower:
        response.append(f"{Fore.RED}{label}: {value}{Style.RESET_ALL}")
```

**Stephanie Display:**
```python
elif label == "Stephanie":
    if "reserved" in value_lower:
        response.append(f"{Fore.RED}{label}: {value}{Style.RESET_ALL}")
    elif not value or value.strip() == "":
        response.append(f"{label}: not available (2026)")
```

**Availability Summary:**
```python
# Show AAG RESERVED indicator
if availability.get('aag_reserved', False):
    response.append(f"{Fore.YELLOW}AAG Spot Reserved: 1{Style.RESET_ALL}")
```

### 3. `check_2027.py`

Already had AAG support, no changes needed (except consistency updates already made).

### 4. `dj_app.py` (Streamlit)

**AAG Column Display:**
```python
elif label == "AAG":
    value_lower = str(value).lower()
    if "reserved" in value_lower:
        formatted_value = f":red[{value}]"
```

**Stephanie Display:**
```python
# Stephanie 2026 handling
if dj_name == "Stephanie" and year == "2026":
    if not value or value.strip() == "":
        return "not available (2026)"

# RESERVED status handling
if value and "reserved" in value_lower:
    return f":red[{value}]"
```

**Availability Summary:**
```python
if avail.get('aag_reserved', False):
    st.warning("🏛️ **AAG Spot Reserved:** 1 spot held for Allied Arts Guild")
```

---

## Color Coding

**Red (Booked/Held):**
- BOOKED events
- AAG: RESERVED
- Stephanie: RESERVED
- Venue names from gig database

**Blue (Backup):**
- BACKUP assignments
- Felipe blank cells (backup-only)

**Green (Available):**
- Available DJs
- Nearby bookings info

**Yellow (Informational):**
- "AAG Spot Reserved: 1" (summary line)
- Stefano [MAYBE]
- Venue inquiries

**White/Default:**
- OUT, other unavailable statuses
- Stephanie blank in 2026

---

## Testing Checklist

Test these scenarios in 2026:

**AAG RESERVED scenarios:**
- [ ] Date with `AAG: RESERVED` shows in red
- [ ] Available spots reduced by 1
- [ ] Summary shows "AAG Spot Reserved: 1"

**Stephanie scenarios:**
- [ ] Stephanie blank cell shows "not available (2026)"
- [ ] `Stephanie: RESERVED` shows in red
- [ ] `Stephanie: RESERVED` reduces available spots by 1
- [ ] `Stephanie: BOOKED` shows in red
- [ ] `Stephanie: BACKUP` shows in blue

**Combined scenarios:**
- [ ] Only AAG or Stephanie has RESERVED, never both
- [ ] Available spots only reduced by 1 when either has RESERVED

**Workflow progression:**
```
1. AAG: RESERVED → spots - 1
2. Stephanie: RESERVED → spots - 1 (same spot as #1)
3. Stephanie: BOOKED → spots - 1 (finalized)
```

---

## Deployment

### Terminal Version
```bash
# Copy updated files
cp /path/to/dj_core.py ~/DJAutomation/
cp /path/to/check_2026.py ~/DJAutomation/

# Test it
python3 check_2026.py
# Enter a date with AAG RESERVED (like 05-09 or 05-30)
```

### Streamlit Version
```bash
# Update GitHub repo
cd ~/path/to/repo
cp /path/to/dj_core.py .
cp /path/to/dj_app.py .
git add dj_core.py dj_app.py
git commit -m "Add 2026 AAG support and fix Stephanie availability logic"
git push
```

Streamlit Cloud will auto-deploy in ~2 minutes.

---

## Key Business Rules Summary

### 2025
- No AAG tracking
- Stephanie: normal availability rules

### 2026
- AAG column tracks reserved spots
- Stephanie: only available when explicitly assigned (BOOKED/RESERVED/BACKUP)
- RESERVED can appear in AAG or Stephanie (mutually exclusive)

### 2027
- AAG column moved to position J
- Stephanie: weekend-only DJ, regular availability
- Felipe: backup-only default

---

## What Stays the Same

All other DJ rules remain unchanged:
- ✅ Henry weekday backup logic
- ✅ Woody weekend OUT backup logic
- ✅ Stefano blank = MAYBE
- ✅ Felipe 2026/2027 backup-only default
- ✅ TBA multiplier handling
- ✅ Gig database integration
- ✅ Venue inquiries tracking
- ✅ Nearby bookings display

---

## Questions & Clarifications

**Q: Can both AAG and Stephanie show RESERVED on the same date?**
A: No, they're mutually exclusive. Workflow is: AAG RESERVED → Stephanie RESERVED → Stephanie BOOKED

**Q: Does Stephanie RESERVED reduce spots by 1?**
A: Yes, same as AAG RESERVED (they represent the same held spot)

**Q: What if Stephanie is blank in 2026?**
A: She's not available that day (she only works when explicitly assigned)

**Q: What about 2027?**
A: In 2027, Stephanie becomes a regular weekend DJ with normal availability rules (blank on weekend = available)
