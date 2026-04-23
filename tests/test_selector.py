from __future__ import annotations

import unittest

from dctl.locator import build_locator
from dctl.selector import match_selector, parse_selector


class SelectorTests(unittest.TestCase):
    def test_parse_and_match_basic_selector(self) -> None:
        selector = parse_selector('app:"Firefox" AND role:button AND name~:"save"')
        element = {
            "app": {"name": "Firefox"},
            "window": {"title": "Preferences"},
            "role": "button",
            "name": "Save Changes",
            "text": "",
            "value": None,
            "state": ["enabled", "visible"],
            "path": "/window[0]/button[1]",
            "bounds": {"x": 10, "y": 10, "width": 50, "height": 20},
        }
        self.assertTrue(match_selector(element, selector))

    def test_coordinate_selector(self) -> None:
        selector = parse_selector("@100,200")
        element = {
            "app": {"name": "Firefox"},
            "window": {"title": "Preferences"},
            "role": "button",
            "name": "Save",
            "text": "",
            "value": None,
            "state": ["enabled"],
            "path": "/window[0]/button[1]",
            "bounds": {"x": 90, "y": 190, "width": 30, "height": 30},
        }
        self.assertTrue(match_selector(element, selector))

    def test_locator_format(self) -> None:
        locator = build_locator(app_name="Firefox", window_title="Preferences", path="/window[0]/button[1]")
        self.assertEqual(locator, 'app:"Firefox" AND window:"Preferences" AND path:/window[0]/button[1]')


if __name__ == "__main__":
    unittest.main()
