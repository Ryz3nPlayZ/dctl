from __future__ import annotations

import json
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dctl.adapters.browser_cdp import (
    _discover_browser_processes,
    _discover_browser_processes_macos,
    _discover_browser_processes_windows_tasklist,
    _parse_debug_port,
    _pid_for_debug_port,
    act,
    actions,
    attach,
    click_action,
    discover,
    evaluate,
    parse_key_combo,
    resolve_target,
    selector_audit,
    session_info,
    snapshot,
    start_browser,
    stop_browser,
    tabs,
    text,
    type_text,
    wait_selector,
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

    def test_snapshot_includes_quality_diagnostics(self) -> None:
        fake_payload = {
            "title": "Example",
            "url": "https://example.com",
            "readyState": "complete",
            "visibleText": "tiny",
            "textLength": 4,
            "truncated": False,
            "frameCount": 0,
            "headings": [],
            "landmarks": [],
            "interactions": [],
            "contentBlocks": [],
            "latex": [],
        }
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": fake_payload}},
        ):
            payload = snapshot("active", min_text=20)
        quality = payload["result"]["quality"]
        codes = {issue["code"] for issue in quality["issues"]}
        self.assertIn("TOO_LITTLE_CONTENT", codes)
        self.assertFalse(quality["ok"])

    def test_snapshot_strict_fails_loudly_on_quality_issues(self) -> None:
        fake_payload = {
            "title": "Example",
            "url": "https://example.com",
            "readyState": "complete",
            "visibleText": "short",
            "textLength": 5,
            "truncated": False,
            "frameCount": 0,
            "headings": [],
            "landmarks": [],
            "interactions": [],
            "contentBlocks": [],
            "latex": [],
        }
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": fake_payload}},
        ):
            with self.assertRaises(DctlError) as ctx:
                snapshot("active", strict=True, min_text=50)
        self.assertEqual(ctx.exception.code, "BACKEND_FAILURE")
        self.assertIn("quality", ctx.exception.details)

    def test_snapshot_reports_unparseable_latex(self) -> None:
        fake_payload = {
            "title": "Math",
            "url": "https://example.com/math",
            "readyState": "complete",
            "visibleText": "x",
            "textLength": 1,
            "truncated": False,
            "frameCount": 0,
            "headings": [{"tag": "h1", "level": 1, "text": "Math"}],
            "landmarks": [{"tag": "main", "role": "main", "label": None}],
            "interactions": [{"tag": "button", "role": None, "type": None, "label": "Run", "disabled": False}],
            "contentBlocks": [{"tag": "p", "text": "content"}],
            "latex": [{"format": "katex", "source": None, "renderedText": None}],
        }
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": fake_payload}},
        ):
            payload = snapshot("active", min_text=0)
        codes = {issue["code"] for issue in payload["result"]["quality"]["issues"]}
        self.assertIn("LATEX_UNPARSEABLE", codes)

    def test_snapshot_accepts_parseable_latex_payloads(self) -> None:
        fake_payload = {
            "title": "Math",
            "url": "https://example.com/math",
            "readyState": "complete",
            "visibleText": "Equation",
            "textLength": 8,
            "truncated": False,
            "frameCount": 0,
            "headings": [{"tag": "h1", "level": 1, "text": "Math"}],
            "landmarks": [{"tag": "main", "role": "main", "label": None}],
            "interactions": [{"tag": "button", "role": None, "type": None, "label": "Run", "disabled": False}],
            "contentBlocks": [{"tag": "p", "text": "Equation"}],
            "latex": [{"format": "katex", "source": "x^2+y^2=z^2", "renderedText": "x2 + y2 = z2"}],
        }
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": fake_payload}},
        ):
            payload = snapshot("active", min_text=0)
        codes = {issue["code"] for issue in payload["result"]["quality"]["issues"]}
        self.assertNotIn("LATEX_UNPARSEABLE", codes)

    def test_snapshot_rejects_invalid_thresholds(self) -> None:
        with self.assertRaises(DctlError) as ctx:
            snapshot("active", min_text=50, max_text=10)
        self.assertEqual(ctx.exception.code, "INVALID_SELECTOR")

    def test_snapshot_treats_visual_surfaces_as_content(self) -> None:
        fake_payload = {
            "title": "Graph",
            "url": "https://example.com/graph",
            "readyState": "complete",
            "visibleText": "",
            "textLength": 0,
            "truncated": False,
            "frameCount": 0,
            "headings": [],
            "landmarks": [],
            "interactions": [],
            "contentBlocks": [],
            "latex": [],
            "visuals": [{"kind": "svg", "tag": "svg", "label": "Line chart"}],
        }
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": fake_payload}},
        ):
            payload = snapshot("active", min_text=50)
        quality = payload["result"]["quality"]
        codes = {issue["code"] for issue in quality["issues"]}
        self.assertNotIn("EMPTY_SURFACE", codes)
        self.assertNotIn("TOO_LITTLE_CONTENT", codes)
        self.assertEqual(quality["metrics"]["visuals"], 1)

    def test_snapshot_reports_category_truncation(self) -> None:
        fake_payload = {
            "title": "Dense page",
            "url": "https://example.com/dense",
            "readyState": "complete",
            "visibleText": "hello world",
            "textLength": 11,
            "truncated": False,
            "frameCount": 0,
            "headings": [{"tag": "h1", "level": 1, "text": "Title"}],
            "landmarks": [{"tag": "main", "role": "main", "label": None}],
            "interactions": [{"tag": "button", "role": None, "type": None, "label": "Go", "disabled": False}],
            "contentBlocks": [{"tag": "p", "text": "Body"}],
            "latex": [],
            "extractionStats": {
                "headings": {"totalVisible": 220, "returned": 120, "truncated": True},
                "landmarks": {"totalVisible": 1, "returned": 1, "truncated": False},
                "interactions": {"totalVisible": 1, "returned": 1, "truncated": False},
                "contentBlocks": {"totalVisible": 1, "returned": 1, "truncated": False},
                "latex": {"totalVisible": 0, "returned": 0, "truncated": False},
            },
        }
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": fake_payload}},
        ):
            payload = snapshot("active", min_text=0)
        codes = {issue["code"] for issue in payload["result"]["quality"]["issues"]}
        self.assertIn("CATEGORY_TRUNCATION", codes)

    def test_batch_reuses_resolved_target_across_operations(self) -> None:
        from dctl.adapters import browser_cdp as module

        operations = '[{"op":"text"},{"op":"selection"}]'
        target = {"id": "page-1", "type": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:9333/devtools/page/1"}
        with patch("dctl.adapters.browser_cdp.normalize_endpoint", return_value="http://127.0.0.1:9333") as normalize_patch, patch(
            "dctl.adapters.browser_cdp.resolve_target",
            return_value=target,
        ) as resolve_patch, patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": {"text": "ok"}}},
        ):
            payload = module.batch("active", operations)
        self.assertEqual(normalize_patch.call_count, 1)
        self.assertEqual(resolve_patch.call_count, 1)
        self.assertEqual(payload["endpoint"], "http://127.0.0.1:9333")
        self.assertEqual(len(payload["results"]), 2)

    def test_parse_debug_port_from_cmdline(self) -> None:
        self.assertEqual(_parse_debug_port("/usr/bin/google-chrome\0--remote-debugging-port=9333\0"), 9333)
        self.assertIsNone(_parse_debug_port("/usr/bin/google-chrome\0--profile-directory=Default\0"))

    def test_selector_resolution_requires_unique_dom_match(self) -> None:
        from dctl.adapters import browser_cdp as module

        class FakeSession:
            async def call(self, method: str, params: dict[str, object] | None = None):
                if method == "DOM.getDocument":
                    return {"root": {"nodeId": 1}}
                if method == "DOM.querySelectorAll":
                    return {"nodeIds": [10, 20]}
                raise AssertionError(f"unexpected method {method}")

        def fake_run(_target: dict[str, object], operation):
            return asyncio.run(operation(FakeSession()))

        with patch("dctl.adapters.browser_cdp._run_in_target_session", side_effect=fake_run):
            with self.assertRaises(DctlError) as ctx:
                module._node_id_for_selector({"type": "page"}, ".dup")
        self.assertEqual(ctx.exception.code, "MULTIPLE_MATCHES")

    def test_type_text_fails_on_ambiguous_selector(self) -> None:
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._send_command",
            return_value={},
        ), patch(
            "dctl.adapters.browser_cdp._node_id_for_selector",
            side_effect=DctlError("MULTIPLE_MATCHES", "ambiguous selector"),
        ):
            with self.assertRaises(DctlError) as ctx:
                type_text("active", "hello", selector=".dup")
        self.assertEqual(ctx.exception.code, "MULTIPLE_MATCHES")

    def test_text_strict_selector_fails_on_ambiguous_selector(self) -> None:
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._node_id_for_selector",
            side_effect=DctlError("MULTIPLE_MATCHES", "ambiguous selector"),
        ):
            with self.assertRaises(DctlError) as ctx:
                text("active", selector=".dup", strict_selector=True)
        self.assertEqual(ctx.exception.code, "MULTIPLE_MATCHES")

    def test_wait_selector_strict_fails_on_ambiguous_selector(self) -> None:
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": {"__error": "multiple", "count": 3}}},
        ):
            with self.assertRaises(DctlError) as ctx:
                wait_selector("active", ".dup", strict_selector=True)
        self.assertEqual(ctx.exception.code, "MULTIPLE_MATCHES")

    def test_selector_audit_returns_read_only_match_diagnostics(self) -> None:
        fake_payload = {
            "selector": ".item",
            "matchCount": 3,
            "visibleCount": 2,
            "disabledCount": 1,
            "editableCount": 0,
            "unique": False,
            "samples": [{"tag": "button", "label": "Run"}],
            "samplesTruncated": True,
            "sampleLimit": 1,
        }
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9333", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": fake_payload}},
        ):
            result = selector_audit("active", ".item", sample_limit=1)
        self.assertEqual(result["result"]["matchCount"], 3)
        self.assertFalse(result["result"]["unique"])

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

    def test_discover_browser_processes_macos(self) -> None:
        fake_ps_output = (
            "USER   PID %CPU %MEM   VSZ   RSS TTY   STAT START   TIME COMMAND\n"
            "user  1234  2.0  1.0 500000 50000  ??  Ss   10:00  0:01 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --remote-debugging-port=9222\n"
            "user  5678  0.5  0.3 100000 10000   ??  S    10:01  0:00 /usr/bin/python3 script.py\n"
        )
        with patch("dctl.adapters.browser_cdp.subprocess.check_output", return_value=fake_ps_output):
            result = _discover_browser_processes_macos()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pid"], 1234)
        self.assertEqual(result[0]["app"], "chrome")
        self.assertEqual(result[0]["debug_port"], 9222)

    def test_discover_browser_processes_macos_no_browsers(self) -> None:
        fake_ps_output = (
            "USER   PID %CPU %MEM   VSZ   RSS TTY   STAT START   TIME COMMAND\n"
            "user  9999  0.5  0.3 100000 10000   ??  S    10:01  0:00 /usr/bin/python3 script.py\n"
        )
        with patch("dctl.adapters.browser_cdp.subprocess.check_output", return_value=fake_ps_output):
            result = _discover_browser_processes_macos()
        self.assertEqual(len(result), 0)

    def test_discover_browser_processes_windows_tasklist(self) -> None:
        fake_output = (
            '"chrome.exe","1234","Console","1","50,000 K"\n'
            '"python.exe","5678","Console","1","10,000 K"\n'
            '"brave.exe","9012","Console","1","40,000 K"\n'
        )
        with patch("dctl.adapters.browser_cdp.subprocess.check_output", return_value=fake_output):
            result = _discover_browser_processes_windows_tasklist()
        self.assertEqual(len(result), 2)
        pids = {r["pid"] for r in result}
        self.assertIn(1234, pids)
        self.assertIn(9012, pids)

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

    def test_active_target_selector_fails_when_ambiguous(self) -> None:
        targets = [
            {"id": "page-1", "type": "page", "title": "One", "url": "https://one.example"},
            {"id": "page-2", "type": "page", "title": "Two", "url": "https://two.example"},
        ]
        with patch("dctl.adapters.browser_cdp._fetch_json", return_value=targets):
            with self.assertRaises(DctlError) as ctx:
                resolve_target("active", endpoint="http://127.0.0.1:9222")
        self.assertEqual(ctx.exception.code, "MULTIPLE_MATCHES")

    def test_active_target_selector_prefers_session_active_target(self) -> None:
        targets = [
            {"id": "page-1", "type": "page", "title": "One", "url": "https://one.example"},
            {"id": "page-2", "type": "page", "title": "Two", "url": "https://two.example"},
        ]
        with patch("dctl.adapters.browser_cdp._fetch_json", return_value=targets), patch(
            "dctl.adapters.browser_cdp._session_active_target_id", return_value="page-2"
        ):
            result = resolve_target("active", endpoint="http://127.0.0.1:9222", session_name="work")
        self.assertEqual(result["id"], "page-2")

    def test_tabs_include_preferred_target_and_scores(self) -> None:
        listed = {
            "endpoint": "http://127.0.0.1:9222",
            "items": [
                {"id": "utility", "type": "page", "title": "Omnibox Popup", "url": "chrome://new-tab-page/"},
                {"id": "work", "type": "page", "title": "Work", "url": "https://app.example.com"},
            ],
        }
        with patch("dctl.adapters.browser_cdp.list_targets", return_value=listed), patch(
            "dctl.adapters.browser_cdp._session_active_target_id", return_value="work"
        ):
            payload = tabs(session_name="agent-main")
        self.assertEqual(payload["recommendedTargetId"], "work")
        self.assertEqual(payload["preferredTargetId"], "work")
        self.assertTrue(payload["items"][0]["isPreferred"])
        self.assertGreater(payload["items"][0]["targetScore"], payload["items"][1]["targetScore"])

    def test_evaluate_supports_return_by_value_flag(self) -> None:
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9222", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._send_command",
            return_value={},
        ), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": {"ok": True}}},
        ) as eval_patch:
            payload = evaluate("active", "(() => ({ ok: true }))()", return_by_value=True)
        self.assertTrue(payload["meta"]["returnByValue"])
        self.assertTrue(eval_patch.call_args.kwargs["return_by_value"])

    def test_actions_returns_extracted_payload(self) -> None:
        fake_payload = {
            "query": "submit",
            "role": "button",
            "totalVisible": 3,
            "returned": 1,
            "sampleLimit": 50,
            "truncated": False,
            "items": [{"actionId": 0, "label": "Submit", "role": "button"}],
        }
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9222", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": fake_payload}},
        ):
            payload = actions("active", query="submit", role="button")
        self.assertEqual(payload["result"]["returned"], 1)
        self.assertEqual(payload["result"]["items"][0]["actionId"], 0)

    def test_click_action_fails_loudly_when_action_missing(self) -> None:
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=("http://127.0.0.1:9222", {"type": "page"})), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": {"__error": "ACTION_NOT_FOUND", "actionId": 9, "available": 2, "sample": []}}},
        ):
            with self.assertRaises(DctlError) as ctx:
                click_action("active", 9)
        self.assertEqual(ctx.exception.code, "ELEMENT_NOT_FOUND")
        self.assertIn("available", ctx.exception.details)

    def test_act_composite_resolves_single_action_and_snapshots(self) -> None:
        from dctl.adapters import browser_cdp as module

        prepared = ("http://127.0.0.1:9222", {"id": "page-1", "type": "page"})
        with patch("dctl.adapters.browser_cdp._prepare_page_target", return_value=prepared), patch(
            "dctl.adapters.browser_cdp.actions",
            return_value={"endpoint": prepared[0], "target": prepared[1], "result": {"items": [{"actionId": 4, "label": "Submit"}]}},
        ) as actions_patch, patch(
            "dctl.adapters.browser_cdp.click_action",
            return_value={"endpoint": prepared[0], "target": prepared[1], "result": {"actionId": 4, "clicked": True}},
        ) as click_patch, patch(
            "dctl.adapters.browser_cdp.snapshot",
            return_value={"endpoint": prepared[0], "target": prepared[1], "result": {"quality": {"ok": True}}},
        ) as snapshot_patch:
            payload = act("active", query="submit", snapshot_after=True)

        self.assertEqual(payload["actionId"], 4)
        self.assertIn("timingsMs", payload)
        self.assertIn("total", payload["timingsMs"])
        actions_patch.assert_called_once()
        click_patch.assert_called_once()
        snapshot_patch.assert_called_once()

    def test_batch_reports_timing_metrics(self) -> None:
        from dctl.adapters import browser_cdp as module

        operations = '[{"op":"text"},{"op":"selection"}]'
        target = {"id": "page-1", "type": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:9333/devtools/page/1"}
        with patch("dctl.adapters.browser_cdp.normalize_endpoint", return_value="http://127.0.0.1:9333"), patch(
            "dctl.adapters.browser_cdp.resolve_target",
            return_value=target,
        ), patch(
            "dctl.adapters.browser_cdp._runtime_evaluate",
            return_value={"result": {"value": {"text": "ok"}}},
        ):
            payload = module.batch("active", operations)

        self.assertIn("timingsMs", payload)
        self.assertIn("total", payload["timingsMs"])
        self.assertEqual(len(payload["timingsMs"]["operations"]), 2)

    def test_batch_supports_act_operation(self) -> None:
        from dctl.adapters import browser_cdp as module

        operations = '[{"op":"act","query":"submit","snapshot":true}]'
        target = {"id": "page-1", "type": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:9333/devtools/page/1"}
        with patch("dctl.adapters.browser_cdp.normalize_endpoint", return_value="http://127.0.0.1:9333"), patch(
            "dctl.adapters.browser_cdp.resolve_target",
            return_value=target,
        ), patch(
            "dctl.adapters.browser_cdp.act",
            return_value={"endpoint": "http://127.0.0.1:9333", "target": target, "actionId": 0, "steps": {}, "timingsMs": {"total": 1.0}},
        ) as act_patch:
            payload = module.batch("active", operations)
        act_patch.assert_called_once()
        self.assertEqual(payload["results"][0]["actionId"], 0)

    def test_start_browser_with_managed_session_persists_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            class FakeProcess:
                pid = 4242
                returncode = 0
                args = []
                stdin = None
                stdout = None
                stderr = None
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def kill(self): pass
                def poll(self): return self.returncode
                def communicate(self, *a, **kw): return (b"", b"")
                def wait(self, **kw): return self.returncode

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
