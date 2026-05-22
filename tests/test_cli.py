from __future__ import annotations

import unittest

from dctl.cli import build_parser, dispatch
from dctl.errors import DctlError


class _DummyManager:
    def capabilities(self):  # pragma: no cover - not used in these tests
        return {}


class CliTests(unittest.TestCase):
    def test_browser_snapshot_parser_includes_quality_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "browser",
                "snapshot",
                "active",
                "--text-limit",
                "5000",
                "--max-items",
                "50",
                "--min-text",
                "100",
                "--max-text",
                "15000",
                "--strict",
            ]
        )
        self.assertEqual(args.text_limit, 5000)
        self.assertEqual(args.max_items, 50)
        self.assertEqual(args.min_text, 100)
        self.assertEqual(args.max_text, 15000)
        self.assertTrue(args.strict)

    def test_browser_parser_includes_selector_and_strict_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "browser",
                "selector",
                "active",
                ".item",
                "--sample-limit",
                "15",
                "--session",
                "work",
            ]
        )
        self.assertEqual(args.browser_command, "selector")
        self.assertEqual(args.selector, ".item")
        self.assertEqual(args.sample_limit, 15)
        self.assertEqual(args.session, "work")

        args_text = parser.parse_args(["browser", "text", "active", "--selector", ".x", "--strict-selector"])
        self.assertTrue(args_text.strict_selector)

        args_wait = parser.parse_args(["browser", "wait-selector", "active", ".x", "--strict-selector"])
        self.assertTrue(args_wait.strict_selector)

    def test_browser_parser_includes_tabs_and_eval_quality_flags(self) -> None:
        parser = build_parser()
        args_tabs = parser.parse_args(
            ["browser", "tabs", "--url-contains", "albert.io", "--title-contains", "Algebra", "--include-non-pages"]
        )
        self.assertEqual(args_tabs.url_contains, "albert.io")
        self.assertEqual(args_tabs.title_contains, "Algebra")
        self.assertTrue(args_tabs.include_non_pages)

        args_eval = parser.parse_args(["browser", "eval", "active", "1+1", "--return-by-value"])
        self.assertTrue(args_eval.return_by_value)

    def test_browser_parser_includes_actions_commands(self) -> None:
        parser = build_parser()
        args_actions = parser.parse_args(
            ["browser", "actions", "active", "--query", "submit", "--role", "button", "--sample-limit", "25"]
        )
        self.assertEqual(args_actions.browser_command, "actions")
        self.assertEqual(args_actions.query, "submit")
        self.assertEqual(args_actions.role, "button")
        self.assertEqual(args_actions.sample_limit, 25)

        args_click_action = parser.parse_args(["browser", "click-action", "active", "3", "--query", "next"])
        self.assertEqual(args_click_action.browser_command, "click-action")
        self.assertEqual(args_click_action.action_id, 3)
        self.assertEqual(args_click_action.query, "next")

        args_act = parser.parse_args(
            [
                "browser",
                "act",
                "active",
                "--query",
                "submit",
                "--role",
                "button",
                "--wait-selector",
                ".result",
                "--snapshot",
                "--snapshot-strict",
            ]
        )
        self.assertEqual(args_act.browser_command, "act")
        self.assertEqual(args_act.query, "submit")
        self.assertEqual(args_act.role, "button")
        self.assertEqual(args_act.wait_selector, ".result")
        self.assertTrue(args_act.snapshot)
        self.assertTrue(args_act.snapshot_strict)

    def test_libreoffice_command_fails_with_missing_uno_dependency(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["libreoffice", "docs"])
        with self.assertRaises(DctlError) as ctx:
            dispatch(args, _DummyManager())
        self.assertEqual(ctx.exception.code, "DEPENDENCY_MISSING")
        self.assertIn("uno", ctx.exception.message.lower())

    def test_click_parser_accepts_button_and_double(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["click", "@100,200", "--button", "right", "--double"])
        self.assertEqual(args.button, "right")
        self.assertTrue(args.double)
        self.assertEqual(args.selector, "@100,200")

    def test_click_parser_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["click", "@100,200"])
        self.assertEqual(args.button, "left")
        self.assertFalse(args.double)

    def test_clipboard_read_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["clipboard", "read"])
        self.assertEqual(args.clipboard_command, "read")

    def test_clipboard_write_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["clipboard", "write", "hello world"])
        self.assertEqual(args.clipboard_command, "write")
        self.assertEqual(args.text, "hello world")


if __name__ == "__main__":
    unittest.main()
