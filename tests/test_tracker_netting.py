#!/usr/bin/env python3
"""
Tests for net_tracker_rows (dj_core): collapsing Inquiry Tracker rows that
describe one event into the rows that still stand.

A booking and its cancellation are two form rows on the same (Event Date,
Venue) key: a Booked row, then a Canceled row entered later (Paul logs the
cancel date in both Inquiry Date and Decision Date on that row). The dashboard
and booking_history already net them; this is the shared rule for the
checker tools and the 2027 assignment script.
"""

import unittest

import dj_core


def _row(ts, event_date, venue, resolution, **extra):
    d = {"Timestamp": ts, "Event Date": event_date,
         "Venue (if known)": venue, "Resolution": resolution}
    d.update(extra)
    return d


class TestNetTrackerRows(unittest.TestCase):
    def test_booked_then_later_canceled_nets_to_the_canceled_row(self):
        rows = [_row("2/20/2026 9:01:48", "6/17/2027", "Nestldown", "Booked"),
                _row("11/3/2026 9:41:13", "6/17/2027", "Nestldown", "Canceled")]
        out = dj_core.net_tracker_rows(rows)
        self.assertEqual(list(out), [("6/17/2027", "nestldown")])
        self.assertEqual([r["Resolution"] for r in out[("6/17/2027", "nestldown")]], ["Canceled"])

    def test_canceled_before_the_booking_does_not_cancel_it(self):
        rows = [_row("2/1/2026 10:00:00", "9/5/2026", "Nestldown", "Booked"),
                _row("1/1/2026 10:00:00", "9/5/2026", "Nestldown", "Canceled")]
        out = dj_core.net_tracker_rows(rows)
        self.assertEqual([r["Resolution"] for r in out[("9/5/2026", "nestldown")]], ["Booked"])

    def test_rebooking_after_a_cancel_stands_as_booked(self):
        rows = [_row("1/1/2026 10:00:00", "9/5/2026", "Nestldown", "Booked"),
                _row("2/1/2026 10:00:00", "9/5/2026", "Nestldown", "Canceled"),
                _row("3/1/2026 10:00:00", "9/5/2026", "Nestldown", "Booked", Note="second couple")]
        out = dj_core.net_tracker_rows(rows)
        kept = out[("9/5/2026", "nestldown")]
        self.assertEqual([r["Resolution"] for r in kept], ["Booked"])
        self.assertEqual(kept[0]["Note"], "second couple")

    def test_two_live_bookings_on_one_key_both_stand(self):
        rows = [_row("1/1/2026 10:00:00", "9/5/2026", "Allied Arts Guild", "Booked"),
                _row("1/2/2026 10:00:00", "9/5/2026", "Allied Arts Guild", "Booked")]
        out = dj_core.net_tracker_rows(rows)
        self.assertEqual(len(out[("9/5/2026", "allied arts guild")]), 2)

    def test_non_booked_rows_keep_only_the_newest(self):
        rows = [_row("1/1/2026 10:00:00", "9/5/2026", "Nestldown", "Cold"),
                _row("2/1/2026 10:00:00", "9/5/2026", "Nestldown", "Didn't Book")]
        out = dj_core.net_tracker_rows(rows)
        self.assertEqual([r["Resolution"] for r in out[("9/5/2026", "nestldown")]], ["Didn't Book"])

    def test_venue_casing_and_whitespace_share_a_key(self):
        rows = [_row("1/1/2026 10:00:00", "9/5/2026", "el Prado ", "Booked"),
                _row("2/1/2026 10:00:00", "9/5/2026", " el PRADO", "Canceled")]
        out = dj_core.net_tracker_rows(rows)
        self.assertEqual(list(out), [("9/5/2026", "el prado")])
        self.assertEqual(out[("9/5/2026", "el prado")][0]["Resolution"], "Canceled")

    def test_different_venues_on_one_date_stay_separate(self):
        rows = [_row("1/1/2026 10:00:00", "9/5/2026", "Nestldown", "Booked"),
                _row("1/2/2026 10:00:00", "9/5/2026", "Kohl Mansion", "Didn't Book")]
        out = dj_core.net_tracker_rows(rows)
        self.assertEqual(len(out), 2)

    def test_canceled_row_without_a_timestamp_does_not_count(self):
        rows = [_row("1/1/2026 10:00:00", "9/5/2026", "Nestldown", "Booked"),
                _row("", "9/5/2026", "Nestldown", "Canceled")]
        out = dj_core.net_tracker_rows(rows)
        self.assertEqual([r["Resolution"] for r in out[("9/5/2026", "nestldown")]], ["Booked"])


if __name__ == "__main__":
    unittest.main()
