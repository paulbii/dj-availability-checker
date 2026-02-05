# Changelog

All notable changes to the DJ Availability Checker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]
<!-- Features in development go here -->

## [2026-02-05] - Gig Booking Manager Enhancements

### Added

#### Auto-Create Missing Date Rows
- **What:** Automatically creates new date rows in availability matrix when booking dates that don't exist
- **How:** Inserts rows chronologically with proper formula templates (columns B, C, E, G, H)
- **Benefit:** No need to manually add future dates to the availability sheets
- **Supports:** Both 2026 and 2027 sheets
- **Testing:** Use `--dry-run` flag to preview row creation before actual execution
- **Note:** 2027 sheet required conversion from dynamic array formula to static date values for compatibility

#### Multiple Bookings Per DJ Per Date
- **What:** Support for booking the same DJ multiple times on the same date
- **Safety:** Validates matrix and calendar counts match before proceeding; aborts if mismatch detected
- **UX:** Shows confirmation dialog with existing event details before adding additional bookings
- **Display:** Smart incrementing in matrix: `BOOKED` → `BOOKED x 2` → `BOOKED x 3`
- **Limit:** No arbitrary limit on number of bookings per DJ per date
- **Benefit:** Handles New Year's Eve and other multi-event scenarios

#### Nestldown Venue Special Calendar Timing
- **What:** Extended calendar blocks for Nestldown full events
- **Rules:**
  - 6-hour events → 9-hour calendar block (1:40 before event start, 1:20 after event end)
  - 7-hour events → 10-hour calendar block (1:40 before event start, 1:20 after event end)
  - Short events (3-hour minimonies) → Normal timing rules apply
- **Benefit:** Accounts for Nestldown's extensive setup/teardown requirements
- **Detection:** Case-insensitive venue name matching

### Changed
- **Dry-run mode:** Now reads real availability matrix and calendar data (true simulation instead of mock data)
- **2027 Sheet Structure:** Converted column A from `=FILTER(SEQUENCE(...))` dynamic array formula to static date values for row insertion compatibility

### Fixed
- Dry-run mode correctly handles non-existent rows (placeholder row 999) without attempting to read from invalid sheet ranges

### Testing
- Added comprehensive test samples in `sample_bookings/` directory
  - `sample_new_date_12_17_26.json` - Test auto-create for 2026
  - `sample_new_date_07_22_27.json` - Test auto-create for 2027
  - `sample_second_booking_same_day.json` - Test multiple bookings
  - `sample_nestldown_minimony.json` - Test Nestldown minimony timing
- Use `--test` flag to redirect calendar invites to paul@bigfundj.com during testing

---

## Previous Development

See [git log](https://github.com/paulbii/dj-availability-checker/commits/main) for historical changes prior to changelog creation.
