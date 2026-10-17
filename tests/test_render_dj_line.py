#!/usr/bin/env python3
"""check_dj.render_dj_line paints a DJStatus for the terminal. Color is
forced off for the test, since check_dj decides at import from whether
stdout is a TTY."""

import unittest

import check_dj
from dj_core import DJStatus


class TestRenderDJLine(unittest.TestCase):

    def setUp(self):
        self._fore, self._style = check_dj.Fore, check_dj.Style
        check_dj.Fore = check_dj._Fore(False)
        check_dj.Style = check_dj._Style(False)

    def tearDown(self):
        check_dj.Fore, check_dj.Style = self._fore, self._style

    def test_text_is_prefixed_with_name(self):
        line = check_dj.render_dj_line("Henry", DJStatus("available", "green", True, True))
        self.assertEqual(line, "Henry: available")

    def test_warning_is_appended(self):
        line = check_dj.render_dj_line("Paul", DJStatus("BOOKED (Nestldown)", "red", False, False, "matrix is blank"))
        self.assertEqual(line, "Paul: BOOKED (Nestldown)  ⚠️  matrix is blank")

    def test_every_kind_has_a_color(self):
        for kind in ("red", "green", "blue", "yellow", "amber", "violet", "dim", "warn"):
            check_dj.render_dj_line("Paul", DJStatus("x", kind, False, False))


if __name__ == "__main__":
    unittest.main()
