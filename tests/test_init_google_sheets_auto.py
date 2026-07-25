"""Tests for dj_core.init_google_sheets_auto (Keychain-first credential loading)."""
import json
import unittest
from unittest import mock

import dj_core


class TestInitGoogleSheetsAuto(unittest.TestCase):
    def test_uses_keychain_blob_when_present(self):
        blob = json.dumps({"type": "service_account"})
        with mock.patch("keyring.get_password", return_value=blob), \
             mock.patch.object(dj_core, "init_google_sheets_from_dict",
                               return_value="DICT") as from_dict, \
             mock.patch.object(dj_core, "init_google_sheets_from_file",
                               return_value="FILE") as from_file:
            result = dj_core.init_google_sheets_auto()
        from_dict.assert_called_once_with({"type": "service_account"})
        from_file.assert_not_called()
        self.assertEqual(result, "DICT")

    def test_falls_back_to_file_when_keychain_empty(self):
        with mock.patch("keyring.get_password", return_value=None), \
             mock.patch.object(dj_core, "init_google_sheets_from_file",
                               return_value="FILE") as from_file:
            result = dj_core.init_google_sheets_auto()
        from_file.assert_called_once_with()
        self.assertEqual(result, "FILE")

    def test_falls_back_to_file_when_keyring_errors(self):
        with mock.patch("keyring.get_password", side_effect=RuntimeError("no backend")), \
             mock.patch.object(dj_core, "init_google_sheets_from_file",
                               return_value="FILE"):
            self.assertEqual(dj_core.init_google_sheets_auto(), "FILE")


if __name__ == "__main__":
    unittest.main()
