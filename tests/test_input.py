from __future__ import annotations

import unittest

from dctl.errors import DctlError
from dctl.platform.linux.input import ydotool_key_args, ydotool_scroll_args


class InputTests(unittest.TestCase):
    def test_ydotool_key_args_for_combo(self) -> None:
        args = ydotool_key_args("ctrl+shift+t")
        self.assertEqual(args, ["29:1", "42:1", "20:1", "20:0", "42:0", "29:0"])

    def test_ydotool_key_args_for_function_key(self) -> None:
        args = ydotool_key_args("alt+f4")
        self.assertEqual(args, ["56:1", "62:1", "62:0", "56:0"])


class InputScrollTests(unittest.TestCase):
    def test_ydotool_scroll_args_down(self) -> None:
        args = ydotool_scroll_args("down", 3)
        self.assertIn("click", args)
        self.assertIn("0xC5", args)
        self.assertIn("--repeat", args)
        self.assertIn("3", args)

    def test_ydotool_scroll_args_up(self) -> None:
        args = ydotool_scroll_args("up", 1)
        self.assertIn("0xC4", args)

    def test_ydotool_scroll_args_invalid_direction(self) -> None:
        with self.assertRaises(DctlError):
            ydotool_scroll_args("diagonal")


if __name__ == "__main__":
    unittest.main()
