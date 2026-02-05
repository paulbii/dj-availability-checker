# Review Findings

## Finding 1 (gig_booking_manager.py:261)
**[P2] Possible case-mismatch in known cell guard**

`value` is uppercased, but the guard checks `value.lower()` against `KNOWN_CELL_VALUES`. If `KNOWN_CELL_VALUES` is uppercase, valid values will be rejected as unknown. Consider normalizing both sides to the same case.

## Finding 2 (gig_booking_manager.py:468)
**[P1] Incorrect A1 range for columns > Z**

`is_cell_bold` only supports A–Z and defaults to `A` for columns > 26, so the wrong cell is queried when a DJ column is AA/AB/etc. That can flip backup eligibility (e.g., Woody OUT bold). Consider an A1 conversion that handles multi-letter columns (e.g., 27 -> AA).

## Finding 3 (gig_booking_manager.py:360)
**[P2] Stephanie weekend rule not applied in spot count**

`calculate_spots_remaining` adds Stephanie as available when blank in 2027+, but doesn’t check weekend (comment notes it). This can overcount remaining spots on weekdays and affect backup prompts.
