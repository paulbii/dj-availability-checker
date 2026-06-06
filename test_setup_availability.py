#!/usr/bin/env python3
"""
Tests for the SETUP role distinction in the availability tools (dj_core).

A setup is a soft hold: the PRIMARY (DJ1, arranged site access) is committed,
but a HELPER (DJ2 on a 2-person setup) could be pulled for a paying event.
Both are marked SETUP in the matrix, so the role comes from the gig db
(assigned_dj = primary, assigned_roadie_or_dj2 = helper).
"""

import unittest

from dj_core import (
    ingest_gig_booking,
    setup_status_text,
    PALETTE,
    hex_to_ansi256,
    term_color,
    html_color,
)


class TestPalette(unittest.TestCase):
    def test_hex_to_ansi256_in_range_and_distinct(self):
        # Every palette color maps to a valid 256-color index.
        for name, hexv in PALETTE.items():
            self.assertTrue(16 <= hex_to_ansi256(hexv) <= 255, name)
        # A gray maps into the grayscale ramp (232-255).
        self.assertTrue(232 <= hex_to_ansi256("#808080") <= 255)
        # Distinct hues get distinct codes.
        self.assertNotEqual(hex_to_ansi256(PALETTE["red"]),
                            hex_to_ansi256(PALETTE["green"]))
        self.assertNotEqual(hex_to_ansi256(PALETTE["amber"]),
                            hex_to_ansi256(PALETTE["violet"]))

    def test_term_color_toggle(self):
        self.assertEqual(term_color("amber", enabled=False), "")
        self.assertTrue(term_color("amber").startswith("\033[38;5;"))
        self.assertEqual(term_color("not_a_color"), "")

    def test_html_color(self):
        self.assertEqual(
            html_color("gold", "INQUIRIES"),
            f'<span style="color:{PALETTE["gold"]}">INQUIRIES</span>',
        )


class TestIngestGigBooking(unittest.TestCase):
    def _ingest(self, record):
        assigned, unassigned = {}, []
        ingest_gig_booking(assigned, unassigned, record)
        return assigned, unassigned

    def test_setup_tags_primary_and_helper(self):
        assigned, _ = self._ingest({
            "assigned_dj": "Woody Miraglia",
            "assigned_roadie_or_dj2": "Paul Burchfield",
            "venue_name": "Sobrato",
            "client_name": "Sobrato Setup",
            "event_type": "Setup",
        })
        self.assertEqual(assigned["Woody"]["role"], "primary")
        self.assertTrue(assigned["Woody"]["is_setup"])
        self.assertEqual(assigned["Paul"]["role"], "helper")
        self.assertTrue(assigned["Paul"]["is_setup"])

    def test_setup_helper_roadie_is_skipped(self):
        assigned, _ = self._ingest({
            "assigned_dj": "Woody Miraglia",
            "assigned_roadie_or_dj2": "Ryan Roadie",
            "venue_name": "Sobrato",
            "event_type": "Setup",
        })
        self.assertIn("Woody", assigned)
        self.assertEqual(len(assigned), 1)  # roadie not added

    def test_non_setup_has_no_role_and_no_helper_injected(self):
        # 1/25-style real co-DJ event: DJ2 is a co-DJ, but for a non-setup we
        # leave the behavior unchanged (no role tags, DJ2 not injected here).
        assigned, _ = self._ingest({
            "assigned_dj": "Woody Miraglia",
            "assigned_roadie_or_dj2": "Henry S. Kim",
            "venue_name": "Fogarty",
            "event_type": "Other",
        })
        self.assertIn("Woody", assigned)
        self.assertNotIn("role", assigned["Woody"])
        self.assertNotIn("is_setup", assigned["Woody"])
        self.assertNotIn("Henry", assigned)

    def test_unassigned_goes_to_unassigned_list(self):
        assigned, unassigned = self._ingest({
            "assigned_dj": "Unassigned",
            "venue_name": "Kohl Mansion",
            "client_name": "TBA Client",
            "event_type": "Wedding",
        })
        self.assertEqual(assigned, {})
        self.assertEqual(len(unassigned), 1)
        self.assertEqual(unassigned[0]["venue"], "Kohl Mansion")


class TestSetupStatusText(unittest.TestCase):
    def test_primary(self):
        text = setup_status_text({"is_setup": True, "role": "primary",
                                  "venue": "Sobrato"})
        self.assertEqual(text, "SETUP (Sobrato) — primary, committed")

    def test_helper(self):
        text = setup_status_text({"is_setup": True, "role": "helper",
                                  "venue": "Sobrato"})
        self.assertEqual(
            text, "SETUP (Sobrato) — helper, could take a paying event (review)")

    def test_no_venue(self):
        text = setup_status_text({"is_setup": True, "role": "primary",
                                  "venue": ""})
        self.assertEqual(text, "SETUP — primary, committed")

    def test_non_setup_returns_none(self):
        self.assertIsNone(setup_status_text({"venue": "Nestldown"}))
        self.assertIsNone(setup_status_text(None))


if __name__ == "__main__":
    unittest.main()
