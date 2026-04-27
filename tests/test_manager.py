from __future__ import annotations

import unittest

from dctl.platform.manager import _filter_tree_items


class ManagerTreeFilterTests(unittest.TestCase):
    def test_filter_tree_items_keeps_matching_branch(self) -> None:
        tree = [
            {
                "name": "Firefox",
                "window": {"title": "Firefox", "id": "window:Firefox"},
                "children": [
                    {
                        "name": "Preferences",
                        "window": {"title": "Preferences", "id": "window:Preferences"},
                        "children": [
                            {
                                "name": "Save",
                                "window": {"title": "Preferences", "id": "window:Preferences"},
                                "children": [],
                            }
                        ],
                    },
                    {"name": "Downloads", "children": []},
                ],
            },
            {"name": "Terminal", "window": {"title": "Terminal", "id": "window:Terminal"}, "children": []},
        ]

        filtered = _filter_tree_items(tree, "Preferences")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "Firefox")
        self.assertEqual(len(filtered[0]["children"]), 1)
        self.assertEqual(filtered[0]["children"][0]["name"], "Preferences")

    def test_filter_tree_items_matches_window_metadata(self) -> None:
        tree = [
            {
                "name": "LibreOffice",
                "window": {"title": "Untitled 1 - LibreOffice Writer", "id": "window:Untitled 1"},
                "children": [],
            }
        ]

        filtered = _filter_tree_items(tree, "LibreOffice Writer")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "LibreOffice")


if __name__ == "__main__":
    unittest.main()