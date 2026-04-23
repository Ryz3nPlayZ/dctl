from __future__ import annotations

import unittest

from dctl.platform.linux.input import ydotool_key_args


class InputTests(unittest.TestCase):
    def test_ydotool_key_args_for_combo(self) -> None:
        args = ydotool_key_args("ctrl+shift+t")
        self.assertEqual(args, ["29:1", "42:1", "20:1", "20:0", "42:0", "29:0"])

    def test_ydotool_key_args_for_function_key(self) -> None:
        args = ydotool_key_args("alt+f4")
        self.assertEqual(args, ["56:1", "62:1", "62:0", "56:0"])


if __name__ == "__main__":
    unittest.main()
