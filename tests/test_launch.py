from __future__ import annotations

import unittest

from dctl.platform.linux.launch import _augment_for_accessibility


class LaunchTests(unittest.TestCase):
    def test_chromium_like_launch_gets_accessibility_flag(self) -> None:
        entry = {"id": "code", "name": "Visual Studio Code"}
        cmd, env = _augment_for_accessibility(entry, ["/usr/bin/code", "--new-window"])
        self.assertIn("--force-renderer-accessibility", cmd)
        self.assertEqual(env["ACCESSIBILITY_ENABLED"], "1")

    def test_generic_launch_still_gets_accessibility_env(self) -> None:
        entry = {"id": "kitty", "name": "kitty"}
        cmd, env = _augment_for_accessibility(entry, ["kitty"])
        self.assertEqual(cmd, ["kitty"])
        self.assertEqual(env["ACCESSIBILITY_ENABLED"], "1")


if __name__ == "__main__":
    unittest.main()
