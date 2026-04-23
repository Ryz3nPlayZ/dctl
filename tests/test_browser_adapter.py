from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dctl.adapters.browser_cdp import _discover_browser_processes, _parse_debug_port, attach, discover, parse_key_combo
from dctl.errors import DctlError


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

    def test_parse_debug_port_from_cmdline(self) -> None:
        self.assertEqual(_parse_debug_port("/usr/bin/google-chrome\0--remote-debugging-port=9333\0"), 9333)
        self.assertIsNone(_parse_debug_port("/usr/bin/google-chrome\0--profile-directory=Default\0"))

    def test_discover_browser_processes_from_fake_proc(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = Path(tmpdir)
            chrome = proc / "1001"
            chrome.mkdir()
            (chrome / "cmdline").write_bytes(
                b"/usr/bin/google-chrome-stable\0--remote-debugging-port=9333\0--profile-directory=Default\0"
            )
            irrelevant = proc / "1002"
            irrelevant.mkdir()
            (irrelevant / "cmdline").write_bytes(b"/usr/bin/python3\0script.py\0")

            items = _discover_browser_processes(proc_root=tmpdir)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["app"], "chrome")
            self.assertEqual(items[0]["debug_port"], 9333)

    def test_discover_attachable_existing_browser(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = Path(tmpdir)
            chrome = proc / "2001"
            chrome.mkdir()
            (chrome / "cmdline").write_bytes(
                b"/usr/bin/google-chrome-stable\0--remote-debugging-port=9333\0"
            )

            def fake_fetch(url: str, method: str = "GET"):
                if url == "http://127.0.0.1:9333/json/version":
                    return {"Browser": "Chrome/123"}
                if url == "http://127.0.0.1:9333/json/list":
                    return [
                        {"id": "page-1", "type": "page", "title": "Docs", "url": "https://docs.google.com"},
                        {"id": "worker-1", "type": "service_worker", "title": "Worker", "url": "chrome-extension://worker"},
                    ]
                raise DctlError("BACKEND_FAILURE", f"no endpoint for {url}")

            with patch("dctl.adapters.browser_cdp._fetch_json", side_effect=fake_fetch):
                payload = discover(proc_root=tmpdir)
                self.assertEqual(len(payload["attachable"]), 1)
                self.assertEqual(payload["attachable"][0]["page_count"], 1)
                attached = attach(proc_root=tmpdir)
                self.assertEqual(attached["endpoint"], "http://127.0.0.1:9333")
                self.assertEqual(len(attached["tabs"]), 1)
                self.assertEqual(attached["tabs"][0]["title"], "Docs")


if __name__ == "__main__":
    unittest.main()
