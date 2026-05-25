from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch


def _macos_env():
    # Build EnvironmentInfo without triggering platform/__init__.py
    detect = types.ModuleType("dctl.platform.detect")
    exec(open("dctl/platform/detect.py").read(), detect.__dict__)
    return detect.EnvironmentInfo(
        platform="darwin",
        session_type=None,
        desktop=None,
        display=None,
        wayland_display=None,
        helpers={"open": "/usr/bin/open", "screencapture": "/usr/sbin/screencapture"},
    )


class MacOsInputDecouplingTests(unittest.TestCase):
    @patch("importlib.util.find_spec")
    def test_input_available_without_accessibility(self, mock_find_spec) -> None:
        modules = {"ApplicationServices", "Quartz", "AppKit", "websockets", "docx", "openpyxl"}
        mock_find_spec.side_effect = lambda name: object() if name in modules else None

        import dctl.capabilities as caps_mod
        result = caps_mod.collect_capabilities(_macos_env())
        self.assertEqual(result["providers"]["input"], "quartz")
        self.assertTrue(result["commands"]["type"])
        self.assertTrue(result["commands"]["key"])
        self.assertTrue(result["commands"]["scroll"])
        self.assertTrue(result["commands"]["click"])
        self.assertTrue(result["commands"]["focus"])

    @patch("importlib.util.find_spec")
    def test_accessibility_gated_without_permission(self, mock_find_spec) -> None:
        modules = {"ApplicationServices", "Quartz", "AppKit", "websockets", "docx", "openpyxl"}
        mock_find_spec.side_effect = lambda name: object() if name in modules else None

        import dctl.capabilities as caps_mod
        result = caps_mod.collect_capabilities(_macos_env())
        self.assertIsNone(result["providers"]["accessibility"])
        self.assertFalse(result["commands"]["tree"])

    @patch("importlib.util.find_spec")
    def test_input_requires_quartz(self, mock_find_spec) -> None:
        modules = {"ApplicationServices", "AppKit", "websockets"}
        mock_find_spec.side_effect = lambda name: object() if name in modules else None

        import dctl.capabilities as caps_mod
        result = caps_mod.collect_capabilities(_macos_env())
        self.assertIsNone(result["providers"]["input"])
        self.assertFalse(result["commands"]["type"])
        self.assertFalse(result["commands"]["key"])


if __name__ == "__main__":
    unittest.main()
