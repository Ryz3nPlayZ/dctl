from __future__ import annotations

import unittest

from dctl.adapters.browser_cdp import parse_key_combo


class BrowserAdapterTests(unittest.TestCase):
    def test_parse_key_combo_for_modifiers(self) -> None:
        spec = parse_key_combo("ctrl+shift+a")
        self.assertEqual(spec.modifiers, 10)
        self.assertEqual(spec.key, "a")
        self.assertEqual(spec.code, "KeyA")
        self.assertEqual(spec.key_code, 65)
        self.assertIsNone(spec.text)

    def test_parse_key_combo_for_named_key(self) -> None:
        spec = parse_key_combo("Enter")
        self.assertEqual(spec.key, "Enter")
        self.assertEqual(spec.code, "Enter")
        self.assertEqual(spec.key_code, 13)


if __name__ == "__main__":
    unittest.main()
