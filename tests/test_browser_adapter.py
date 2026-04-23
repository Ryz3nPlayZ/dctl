from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dctl.adapters.browser_cdp import (
    _discover_browser_processes,
    _parse_debug_port,
    _pid_for_debug_port,
    attach,
    discover,
    parse_key_combo,
    session_info,
    start_browser,
    stop_browser,
)
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

    def test_enter_key_uses_paragraph_separator_command(self) -> None:
        from dctl.adapters import browser_cdp as module

        calls: list[tuple[str, dict[str, object] | None]] = []

        def fake_send(target: dict[str, object], method: str, params: dict[str, object] | None = None):
            calls.append((method, params))
            if method == "Page.bringToFront":
                return {}
            return {}

        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._send_command", side_effect=fake_send
        ):
            module.press_key("active", "enter")

        self.assertEqual(calls[0][0], "Page.bringToFront")
        self.assertEqual(calls[1][0], "Input.dispatchKeyEvent")
        self.assertEqual(calls[1][1]["commands"], ["insertParagraphSeparator"])

    def test_caret_positions_input_selection(self) -> None:
        from dctl.adapters import browser_cdp as module

        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": {"kind": "input", "selectionStart": 2, "selectionEnd": 5, "valueLength": 10}}},
        ):
            result = module.caret("active", selector="#box", start=2, end=5)
        self.assertEqual(result["selector"], "#box")
        self.assertEqual(result["result"]["kind"], "input")

    def test_caret_positions_contenteditable_selection(self) -> None:
        from dctl.adapters import browser_cdp as module

        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": {"kind": "contenteditable", "selection": "abc", "textLength": 10}}},
        ):
            result = module.caret("active", selector="#editor", start=1, end=3)
        self.assertEqual(result["selector"], "#editor")
        self.assertEqual(result["result"]["kind"], "contenteditable")

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
            self.assertEqual(_pid_for_debug_port(9333, proc_root=tmpdir), 1001)

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

    def test_start_browser_with_managed_session_persists_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            class FakeProcess:
                pid = 4242

            with (
                patch.dict("os.environ", {"DCTL_BROWSER_HOME": tmpdir}),
                patch("dctl.adapters.browser_cdp.resolve_browser_executable", return_value="/usr/bin/google-chrome"),
                patch("dctl.adapters.browser_cdp._find_free_port", return_value=9444),
                patch("dctl.adapters.browser_cdp.subprocess.Popen", return_value=FakeProcess()),
                patch("dctl.adapters.browser_cdp._fetch_json", return_value={"Browser": "Chrome/123"}),
            ):
                payload = start_browser(app="chrome", session_name="Agent Main", url="https://example.com")

            self.assertEqual(payload["session"], "agent-main")
            self.assertTrue(payload["managed"])
            self.assertFalse(payload["existing_session"])
            self.assertEqual(payload["port"], 9444)
            self.assertTrue(payload["user_data_dir"].endswith("/profiles/agent-main"))
            metadata_path = Path(tmpdir) / "sessions" / "agent-main.json"
            self.assertTrue(metadata_path.exists())
            record = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(record["pid"], 4242)
            self.assertEqual(record["port"], 9444)
            self.assertEqual(record["name"], "agent-main")

    def test_attach_named_session_uses_saved_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = Path(tmpdir) / "sessions"
            session_path.mkdir(parents=True, exist_ok=True)
            (session_path / "agent-main.json").write_text(
                json.dumps(
                    {
                        "name": "agent-main",
                        "pid": 4242,
                        "port": 9444,
                        "user_data_dir": str(Path(tmpdir) / "profiles" / "agent-main"),
                    }
                ),
                encoding="utf-8",
            )

            def fake_fetch(url: str, method: str = "GET"):
                if url == "http://127.0.0.1:9444/json/version":
                    return {"Browser": "Chrome/123"}
                if url == "http://127.0.0.1:9444/json/list":
                    return [{"id": "page-1", "type": "page", "title": "Inbox", "url": "https://mail.google.com"}]
                raise DctlError("BACKEND_FAILURE", f"unexpected {url}")

            with patch.dict("os.environ", {"DCTL_BROWSER_HOME": tmpdir}), patch(
                "dctl.adapters.browser_cdp._fetch_json", side_effect=fake_fetch
            ):
                payload = attach(session_name="agent-main")

            self.assertEqual(payload["endpoint"], "http://127.0.0.1:9444")
            self.assertEqual(payload["version"]["session"], "agent-main")
            self.assertEqual(payload["tabs"][0]["title"], "Inbox")

    def test_stop_browser_for_managed_session_preserves_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "profiles" / "agent-main"
            profile_dir.mkdir(parents=True, exist_ok=True)
            (profile_dir / "Cookies").write_text("keep", encoding="utf-8")
            session_path = Path(tmpdir) / "sessions"
            session_path.mkdir(parents=True, exist_ok=True)
            (session_path / "agent-main.json").write_text(
                json.dumps(
                    {
                        "name": "agent-main",
                        "pid": 4242,
                        "port": 9444,
                        "user_data_dir": str(profile_dir),
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"DCTL_BROWSER_HOME": tmpdir}), patch(
                "dctl.adapters.browser_cdp.os.kill", return_value=None
            ):
                payload = stop_browser(session_name="agent-main")
                info = session_info("agent-main")

            self.assertEqual(payload["session"], "agent-main")
            self.assertTrue(profile_dir.exists())
            self.assertFalse(payload["user_data_dir_removed"])
            self.assertIsNone(info["pid"])
            self.assertFalse(info["reachable"])


if __name__ == "__main__":
    unittest.main()
