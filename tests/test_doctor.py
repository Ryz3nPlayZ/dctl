from __future__ import annotations

import unittest

from dctl.doctor import build_doctor_report
from dctl.errors import DctlError
from dctl.selector import parse_selector


class DoctorTests(unittest.TestCase):
    def test_linux_doctor_flags_missing_atspi_bus(self) -> None:
        report = build_doctor_report(
            {
                "platform": "linux",
                "commands": {"capabilities": True},
                "providers": {"capture": "grim", "input": "xdotool"},
                "warnings": [],
                "diagnostics": {
                    "checks": {"atspi_importable": True, "atspi_bus": False},
                    "helpers": {"xdg-open": "/usr/bin/xdg-open"},
                },
            }
        )
        issues = report["issues"]
        self.assertTrue(any(issue["area"] == "accessibility" for issue in issues))

    def test_invalid_selector_raises(self) -> None:
        with self.assertRaises(DctlError):
            parse_selector("near:\"save\"")


if __name__ == "__main__":
    unittest.main()
