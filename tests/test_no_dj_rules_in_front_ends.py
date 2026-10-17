#!/usr/bin/env python3
"""
Availability rules live in dj_core (check_dj_availability, dj_status and
dj_range_bucket). A front end that tests a DJ's name is re-deriving a
rule, which is how the Streamlit app ended up with its own copy of the
Stephanie rule in 2026. This test fails the moment that creeps back.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT_ENDS = ["check_dj.py", "check_dj_gui.py", "dj_app.py"]
DJ_NAMES = "Henry|Woody|Paul|Stefano|Felipe|Stephanie"
RULE = re.compile(rf'\b(dj_name|label|dj)\s*==\s*["\']({DJ_NAMES})["\']')


class TestNoDJRulesInFrontEnds(unittest.TestCase):

    def test_front_ends_do_not_branch_on_dj_name(self):
        hits = []
        for name in FRONT_ENDS:
            for n, line in enumerate(ROOT.joinpath(name).read_text().splitlines(), 1):
                if RULE.search(line):
                    hits.append(f"{name}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "DJ-name rule outside dj_core:\n" + "\n".join(hits))

    def test_regex_catches_a_real_branch(self):
        self.assertTrue(RULE.search('elif label == "Stephanie":'))
        self.assertTrue(RULE.search("if dj_name == 'Stefano' and not clean_value:"))


if __name__ == "__main__":
    unittest.main()
