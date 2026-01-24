# DJ Availability Checker - 2027 Updates Summary

## Overview
All files have been updated to support 2027 with new DJs, column layouts, and business rules.

---

## Key Changes for 2027

### 1. New Column Layout (2027 ONLY)
```
A: Date
D: Henry
E: Woody
F: Paul
G: Stefano
H: Stephanie (de Jesus) ← NEW REGULAR DJ
I: TBA
J: AAG (Allied Arts Guild) ← NEW COLUMN
L: Felipe
```

**Note:** 2025/2026 keep their existing column layout with Stephanie in column K

---

### 2. Stephanie de Jesus Rules
- **Full name:** Stephanie de Jesus
- **Initials:** SD
- **Availability:** Weekends only (Saturday + Sunday)
- **Weekday + blank cell:** NOT available (cannot book or backup)
- **Weekend + blank cell:** Available for booking AND backup
- **Behavior:** Inverse of Henry (Henry = weekday backup only, Stephanie = weekend only)

### 3. AAG (Allied Arts Guild) Column Rules
- **Purpose:** Track reserved spots for exclusive venue relationship
- **"RESERVED" status:** Holds one Saturday spot for AAG
  - Reduces available spots by 1
  - Displayed in **RED** (treated as a booked event)
- **When AAG books:**
  1. Assign "BOOKED" to appropriate DJ or TBA column
  2. Clear "RESERVED" from AAG cell for that date

### 4. Felipe Rules (2026 & 2027)
- **Default (blank cell):** Backup only
- **"OK":** Can be booked AND backup (special exception)
- **"DAD" or "OK to backup":** Backup only
- **"OUT" or "MAXED":** Not available
- **Any other status:** Defaults to backup only

---

## Color Coding Reference

When using `check_2027.py`, output is color-coded for quick visual scanning:

**Red (Booked/Unavailable):**
- BOOKED events
- AAG: RESERVED (held spot)
- DJs with gig database bookings (shows venue name)

**Blue (Backup):**
- BACKUP assignments
- DJs available for backup only
- Felipe blank cells (backup-only default)

**Green (Available):**
- DJs available for booking
- Includes nearby bookings info when applicable

**Yellow (Uncertain/Info):**
- Stefano with blank cell [MAYBE]
- AAG summary line ("AAG Spot Reserved: 1")
- Venue inquiries that didn't book

**White/Default:**
- OUT, MAXED, other unavailable statuses
- Stephanie on weekdays (not available)

---

## Updated Files

### 1. dj_core.py (Core Logic Module)
**New Features:**
- Year-specific column mappings (`COLUMNS_2025_2026` vs `COLUMNS_2027`)
- `get_columns_for_year()` function to return correct columns
- Stephanie weekend-only logic in `check_dj_availability()`
- AAG "RESERVED" handling in `analyze_availability()`
- Felipe 2026/2027 rules (backup-only by default)
- Dynamic range notation based on year (A:K for 2025/2026, A:L for 2027)

**Key Functions Updated:**
- `check_dj_availability()` - Added Stephanie weekday check
- `analyze_availability()` - Added AAG reserved spot tracking
- `get_date_availability_data()` - Year-aware column selection

### 2. check_2027.py (Terminal Interface)
**Features:**
- Terminal-based availability checking for 2027
- Color-coded output:
  - Red = Booked/AAG
  - Blue = Backup
  - Green = Available (blank)
  - Yellow/Orange = Other statuses
  - Magenta = TBA bookings
- AAG RESERVED spot display
- Interactive date entry (MM-DD format)

### 3. dj_app.py (Streamlit Web Interface)
**New Features:**
- Year selector dropdown (2025, 2026, 2027)
- Year-specific column handling
- AAG column display with RESERVED highlighting
- Stephanie status formatting
- Enhanced availability summary with AAG reserved info

---

## Business Logic Summary

### Available Spots Calculation
```
Available Spots = DJs available for booking
                - TBA bookings (need assignment)
                - AAG RESERVED spots (if applicable)
                - Must keep 1 for backup
```

### DJ-Specific Rules

#### Henry
- Weekdays: Blank cell = backup only (cannot book)
- Weekends: Normal availability rules

#### Woody
- Plain "OUT" on weekends = Can backup (unpaid)
- BOLD "OUT" on weekends = Cannot backup or book
- "OUT" on weekdays = Cannot backup or book

#### Stefano
- Blank cell = NOT available (must be explicitly marked)
- "OK" = Available for booking and backup
- Two events per month limit (tracked manually)

#### Stephanie (2027+)
- **Weekdays:** Blank = NOT available
- **Weekends:** Blank = Available for booking AND backup
- Think of her as "inverse Henry"

#### Felipe (2026+)
- Backup-only by default (blank cell = backup available)
- "OK" = Special exception, can be booked
- "DAD" = Backup only
- No events accepted in 2026/2027

#### Paul
- Standard rules apply
- Blank = Available for booking and backup

---

## Testing Recommendations

### 1. Test 2027 Stephanie Rules
```python
# Test weekday with blank cell
python check_2027.py
# Enter: 01-06 (Monday)
# Stephanie should show: NOT available

# Test weekend with blank cell  
python check_2027.py
# Enter: 01-04 (Saturday)
# Stephanie should show: BLANK - available
```

### 2. Test AAG RESERVED
```python
# Find a date with AAG RESERVED
python check_2027.py
# Available spots should be reduced by 1
# Summary should show "AAG Spot Reserved: 1"
```

### 3. Test Felipe 2027
```python
# Test blank cell
python check_2027.py
# Felipe blank = backup only (not "not available")

# Test "OK" status
# Felipe with "OK" = can be booked
```

### 4. Test Year Transitions
- Check 2025/2026 still work (Stephanie in column K)
- Check 2027 uses new columns (Stephanie in H, AAG in J, Felipe in L)

---

## Deployment Steps

### Local Testing
1. **Terminal version:**
   ```bash
   python check_2027.py
   ```

2. **Web version (local):**
   ```bash
   streamlit run dj_app.py
   ```

### GitHub Deployment
```bash
# Navigate to your repo
cd ~/path/to/your-repo

# Copy updated files
cp /path/to/dj_core.py .
cp /path/to/check_2027.py .
cp /path/to/dj_app.py .

# Commit and push
git add dj_core.py check_2027.py dj_app.py
git commit -m "Add 2027 support with Stephanie and AAG columns"
git push
```

### Streamlit Cloud
- Push to GitHub will auto-deploy to Streamlit Cloud
- Check deployment status in Streamlit Cloud dashboard
- Test year selector shows 2025, 2026, and 2027

---

## Backward Compatibility

✅ **2025 and 2026 continue to work exactly as before**
- Same column layout (A, D, E, F, G, H, I, K)
- Same business rules
- No breaking changes

✅ **2027 introduces new features without affecting old years**
- New column layout only for 2027 sheet
- New DJs and rules only apply to 2027

---

## Future Considerations

### Stephanie Capacity Rules (TBD)
- Maximum events per month (like Stefano's 2-per-month)
- Saturday-only vs. Saturday+Sunday availability
- Update logic when finalized

### AAG Workflow
- Consider adding AAG booking count tracking
- May want separate AAG analytics later

### Column Layout Standardization
- If 2028+ continues with 2027 layout, create "2027+" group
- Avoid year-by-year column definitions if layout stabilizes

---

## Questions or Issues?

If you encounter any issues:
1. Check Google Sheet tab name matches year (e.g., "2027")
2. Verify column layout in sheet matches expected layout
3. Test with known dates that have data
4. Check credentials file/secrets are configured correctly

For AAG questions:
- RESERVED should be in column J only
- When AAG books, manually update both AAG and DJ/TBA columns
- RESERVED count is boolean (present = 1 spot, absent = 0 spots)
