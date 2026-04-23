from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

from dctl.adapters import browser_cdp, docx_files, libreoffice_uno, xlsx_files
from dctl.errors import DctlError, as_dctl_error
from dctl.output import emit_error, emit_success
from dctl.platform import DesktopManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dctl", description="Headless desktop control CLI for LLM agents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("capabilities")
    subparsers.add_parser("doctor")
    subparsers.add_parser("list-apps")
    subparsers.add_parser("list-windows")
    subparsers.add_parser("list-launchable")

    launch_parser = subparsers.add_parser("launch")
    launch_parser.add_argument("target")

    open_parser = subparsers.add_parser("open")
    open_parser.add_argument("target")

    tree_parser = subparsers.add_parser("tree")
    tree_parser.add_argument("--app")
    tree_parser.add_argument("--depth", type=int, default=5)

    element_parser = subparsers.add_parser("element")
    element_parser.add_argument("selector")

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("selector")

    describe_parser = subparsers.add_parser("describe")
    describe_parser.add_argument("x", type=int)
    describe_parser.add_argument("y", type=int)

    wait_parser = subparsers.add_parser("wait")
    wait_parser.add_argument("selector")
    wait_parser.add_argument("--timeout", type=float, default=10.0)
    wait_parser.add_argument("--interval", type=int, default=250)

    focus_parser = subparsers.add_parser("focus")
    focus_parser.add_argument("selector")

    click_parser = subparsers.add_parser("click")
    click_parser.add_argument("selector")

    type_parser = subparsers.add_parser("type")
    type_parser.add_argument("text")
    type_parser.add_argument("--into")

    key_parser = subparsers.add_parser("key")
    key_parser.add_argument("combo")

    scroll_parser = subparsers.add_parser("scroll")
    scroll_parser.add_argument("direction")
    scroll_parser.add_argument("--amount", type=int, default=1)

    screenshot_parser = subparsers.add_parser("screenshot")
    screenshot_parser.add_argument("--screen", type=int)
    screenshot_parser.add_argument("--window")
    screenshot_parser.add_argument("--region")
    screenshot_parser.add_argument("--output")
    screenshot_parser.add_argument("--base64", action="store_true")

    browser_parser = subparsers.add_parser("browser")
    browser_subparsers = browser_parser.add_subparsers(dest="browser_command", required=True)

    browser_start = browser_subparsers.add_parser("start")
    browser_start.add_argument("--app")
    browser_start.add_argument("--exec")
    browser_start.add_argument("--port", type=int)
    browser_start.add_argument("--url")
    browser_start.add_argument("--headless", action="store_true")

    browser_stop = browser_subparsers.add_parser("stop")
    browser_stop.add_argument("--pid", type=int, required=True)
    browser_stop.add_argument("--user-data-dir")

    browser_version = browser_subparsers.add_parser("version")
    browser_version.add_argument("--endpoint")
    browser_version.add_argument("--port", type=int)

    browser_targets = browser_subparsers.add_parser("targets")
    browser_targets.add_argument("--endpoint")
    browser_targets.add_argument("--port", type=int)

    browser_open = browser_subparsers.add_parser("open")
    browser_open.add_argument("url")
    browser_open.add_argument("--endpoint")
    browser_open.add_argument("--port", type=int)

    browser_activate = browser_subparsers.add_parser("activate")
    browser_activate.add_argument("target")
    browser_activate.add_argument("--endpoint")
    browser_activate.add_argument("--port", type=int)

    browser_close = browser_subparsers.add_parser("close")
    browser_close.add_argument("target")
    browser_close.add_argument("--endpoint")
    browser_close.add_argument("--port", type=int)

    browser_eval = browser_subparsers.add_parser("eval")
    browser_eval.add_argument("target")
    browser_eval.add_argument("expression")
    browser_eval.add_argument("--endpoint")
    browser_eval.add_argument("--port", type=int)
    browser_eval.add_argument("--no-await-promise", action="store_true")

    browser_dom = browser_subparsers.add_parser("dom")
    browser_dom.add_argument("target")
    browser_dom.add_argument("--selector")
    browser_dom.add_argument("--depth", type=int, default=3)
    browser_dom.add_argument("--no-pierce", action="store_true")
    browser_dom.add_argument("--endpoint")
    browser_dom.add_argument("--port", type=int)

    browser_ax = browser_subparsers.add_parser("ax")
    browser_ax.add_argument("target")
    browser_ax.add_argument("--selector")
    browser_ax.add_argument("--endpoint")
    browser_ax.add_argument("--port", type=int)

    browser_text = browser_subparsers.add_parser("text")
    browser_text.add_argument("target")
    browser_text.add_argument("--selector")
    browser_text.add_argument("--endpoint")
    browser_text.add_argument("--port", type=int)

    browser_selection = browser_subparsers.add_parser("selection")
    browser_selection.add_argument("target")
    browser_selection.add_argument("--endpoint")
    browser_selection.add_argument("--port", type=int)

    browser_click = browser_subparsers.add_parser("click")
    browser_click.add_argument("target")
    browser_click.add_argument("selector")
    browser_click.add_argument("--endpoint")
    browser_click.add_argument("--port", type=int)

    browser_type = browser_subparsers.add_parser("type")
    browser_type.add_argument("target")
    browser_type.add_argument("text")
    browser_type.add_argument("--selector")
    browser_type.add_argument("--clear", action="store_true")
    browser_type.add_argument("--endpoint")
    browser_type.add_argument("--port", type=int)

    browser_press = browser_subparsers.add_parser("press")
    browser_press.add_argument("target")
    browser_press.add_argument("combo")
    browser_press.add_argument("--endpoint")
    browser_press.add_argument("--port", type=int)

    browser_send = browser_subparsers.add_parser("send")
    browser_send.add_argument("target")
    browser_send.add_argument("method")
    browser_send.add_argument("--params")
    browser_send.add_argument("--endpoint")
    browser_send.add_argument("--port", type=int)

    libreoffice_parser = subparsers.add_parser("libreoffice")
    libreoffice_subparsers = libreoffice_parser.add_subparsers(dest="libreoffice_command", required=True)

    libreoffice_start = libreoffice_subparsers.add_parser("start")
    libreoffice_start.add_argument("--port", type=int)
    libreoffice_start.add_argument("--headless", action="store_true")
    libreoffice_start.add_argument("--exec")

    libreoffice_stop = libreoffice_subparsers.add_parser("stop")
    libreoffice_stop.add_argument("--pid", type=int, required=True)

    libreoffice_docs = libreoffice_subparsers.add_parser("docs")
    libreoffice_docs.add_argument("--port", type=int, default=2002)

    libreoffice_open = libreoffice_subparsers.add_parser("open")
    libreoffice_open.add_argument("path")
    libreoffice_open.add_argument("--port", type=int, default=2002)
    libreoffice_open.add_argument("--hidden", action="store_true")

    libreoffice_info = libreoffice_subparsers.add_parser("info")
    libreoffice_info.add_argument("document")
    libreoffice_info.add_argument("--port", type=int, default=2002)

    libreoffice_save = libreoffice_subparsers.add_parser("save")
    libreoffice_save.add_argument("document")
    libreoffice_save.add_argument("--port", type=int, default=2002)

    libreoffice_close = libreoffice_subparsers.add_parser("close")
    libreoffice_close.add_argument("document")
    libreoffice_close.add_argument("--port", type=int, default=2002)

    libreoffice_writer_text = libreoffice_subparsers.add_parser("writer-text")
    libreoffice_writer_text.add_argument("document")
    libreoffice_writer_text.add_argument("--port", type=int, default=2002)

    libreoffice_writer_paragraphs = libreoffice_subparsers.add_parser("writer-paragraphs")
    libreoffice_writer_paragraphs.add_argument("document")
    libreoffice_writer_paragraphs.add_argument("--port", type=int, default=2002)

    libreoffice_writer_append = libreoffice_subparsers.add_parser("writer-append")
    libreoffice_writer_append.add_argument("document")
    libreoffice_writer_append.add_argument("text")
    libreoffice_writer_append.add_argument("--port", type=int, default=2002)

    libreoffice_writer_set = libreoffice_subparsers.add_parser("writer-set-paragraph")
    libreoffice_writer_set.add_argument("document")
    libreoffice_writer_set.add_argument("index", type=int)
    libreoffice_writer_set.add_argument("text")
    libreoffice_writer_set.add_argument("--port", type=int, default=2002)

    libreoffice_calc_sheets = libreoffice_subparsers.add_parser("calc-sheets")
    libreoffice_calc_sheets.add_argument("document")
    libreoffice_calc_sheets.add_argument("--port", type=int, default=2002)

    libreoffice_calc_read = libreoffice_subparsers.add_parser("calc-read")
    libreoffice_calc_read.add_argument("document")
    libreoffice_calc_read.add_argument("sheet")
    libreoffice_calc_read.add_argument("range")
    libreoffice_calc_read.add_argument("--port", type=int, default=2002)

    libreoffice_calc_write_cell = libreoffice_subparsers.add_parser("calc-write-cell")
    libreoffice_calc_write_cell.add_argument("document")
    libreoffice_calc_write_cell.add_argument("sheet")
    libreoffice_calc_write_cell.add_argument("cell")
    libreoffice_calc_write_cell.add_argument("value")
    libreoffice_calc_write_cell.add_argument("--port", type=int, default=2002)
    libreoffice_calc_write_cell.add_argument("--json", action="store_true")

    libreoffice_calc_write_range = libreoffice_subparsers.add_parser("calc-write-range")
    libreoffice_calc_write_range.add_argument("document")
    libreoffice_calc_write_range.add_argument("sheet")
    libreoffice_calc_write_range.add_argument("range")
    libreoffice_calc_write_range.add_argument("rows_json")
    libreoffice_calc_write_range.add_argument("--port", type=int, default=2002)

    docx_parser = subparsers.add_parser("docx", aliases=["word"])
    docx_subparsers = docx_parser.add_subparsers(dest="docx_command", required=True)

    docx_inspect = docx_subparsers.add_parser("inspect")
    docx_inspect.add_argument("path")

    docx_read = docx_subparsers.add_parser("read")
    docx_read.add_argument("path")
    docx_read.add_argument("--include-empty", action="store_true")

    docx_paragraphs = docx_subparsers.add_parser("paragraphs")
    docx_paragraphs.add_argument("path")
    docx_paragraphs.add_argument("--skip-empty", action="store_true")

    docx_append = docx_subparsers.add_parser("append")
    docx_append.add_argument("path")
    docx_append.add_argument("text")
    docx_append.add_argument("--style")

    docx_insert = docx_subparsers.add_parser("insert-before")
    docx_insert.add_argument("path")
    docx_insert.add_argument("index", type=int)
    docx_insert.add_argument("text")
    docx_insert.add_argument("--style")

    docx_set = docx_subparsers.add_parser("set-paragraph")
    docx_set.add_argument("path")
    docx_set.add_argument("index", type=int)
    docx_set.add_argument("text")

    docx_replace = docx_subparsers.add_parser("replace")
    docx_replace.add_argument("path")
    docx_replace.add_argument("find")
    docx_replace.add_argument("replace")

    xlsx_parser = subparsers.add_parser("xlsx", aliases=["excel"])
    xlsx_subparsers = xlsx_parser.add_subparsers(dest="xlsx_command", required=True)

    xlsx_inspect = xlsx_subparsers.add_parser("inspect")
    xlsx_inspect.add_argument("path")

    xlsx_sheets = xlsx_subparsers.add_parser("sheets")
    xlsx_sheets.add_argument("path")

    xlsx_read = xlsx_subparsers.add_parser("read")
    xlsx_read.add_argument("path")
    xlsx_read.add_argument("sheet")
    xlsx_read.add_argument("range")

    xlsx_write_cell = xlsx_subparsers.add_parser("write-cell")
    xlsx_write_cell.add_argument("path")
    xlsx_write_cell.add_argument("sheet")
    xlsx_write_cell.add_argument("cell")
    xlsx_write_cell.add_argument("value")
    xlsx_write_cell.add_argument("--json", action="store_true")

    xlsx_write_range = xlsx_subparsers.add_parser("write-range")
    xlsx_write_range.add_argument("path")
    xlsx_write_range.add_argument("sheet")
    xlsx_write_range.add_argument("range")
    xlsx_write_range.add_argument("rows_json")

    return parser


def build_meta(manager: DesktopManager) -> dict[str, Any]:
    caps = manager.capabilities()
    return {
        "platform": caps["platform"],
        "session_type": caps["session_type"],
        "backend": caps["providers"],
        "warnings": caps.get("warnings", []),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def dispatch(args: argparse.Namespace, manager: DesktopManager) -> Any:
    command = args.command
    if command == "capabilities":
        return manager.capabilities()
    if command == "doctor":
        return manager.doctor()
    if command == "list-apps":
        return {"items": manager.list_apps()}
    if command == "list-windows":
        return {"items": manager.list_windows()}
    if command == "list-launchable":
        return {"items": manager.list_launchable()}
    if command == "launch":
        return manager.launch(args.target)
    if command == "open":
        return manager.open_target(args.target)
    if command == "tree":
        return manager.tree(app_name=args.app, depth=args.depth)
    if command == "element":
        return manager.element(args.selector)
    if command == "read":
        return manager.read(args.selector)
    if command == "describe":
        return manager.describe(args.x, args.y)
    if command == "wait":
        return manager.wait(args.selector, args.timeout, args.interval)
    if command == "focus":
        return manager.focus(args.selector)
    if command == "click":
        return manager.click(args.selector)
    if command == "type":
        return manager.type_text(args.text, args.into)
    if command == "key":
        return manager.press_key(args.combo)
    if command == "scroll":
        return manager.scroll(args.direction, args.amount)
    if command == "screenshot":
        return manager.screenshot(
            screen=args.screen,
            window=args.window,
            region=args.region,
            output_path=args.output,
            as_base64=args.base64,
        )
    if command == "browser":
        subcommand = args.browser_command
        if subcommand == "start":
            return browser_cdp.start_browser(app=args.app, executable=args.exec, port=args.port, url=args.url, headless=args.headless)
        if subcommand == "stop":
            return browser_cdp.stop_browser(args.pid, args.user_data_dir)
        if subcommand == "version":
            return browser_cdp.browser_version(endpoint=args.endpoint, port=args.port)
        if subcommand == "targets":
            return browser_cdp.list_targets(endpoint=args.endpoint, port=args.port)
        if subcommand == "open":
            return browser_cdp.open_target(args.url, endpoint=args.endpoint, port=args.port)
        if subcommand == "activate":
            return browser_cdp.activate_target(args.target, endpoint=args.endpoint, port=args.port)
        if subcommand == "close":
            return browser_cdp.close_target(args.target, endpoint=args.endpoint, port=args.port)
        if subcommand == "eval":
            return browser_cdp.evaluate(
                args.target,
                args.expression,
                endpoint=args.endpoint,
                port=args.port,
                await_promise=not args.no_await_promise,
            )
        if subcommand == "dom":
            return browser_cdp.dom(
                args.target,
                endpoint=args.endpoint,
                port=args.port,
                selector=args.selector,
                depth=args.depth,
                pierce=not args.no_pierce,
            )
        if subcommand == "ax":
            return browser_cdp.accessibility_tree(args.target, endpoint=args.endpoint, port=args.port, selector=args.selector)
        if subcommand == "text":
            return browser_cdp.text(args.target, endpoint=args.endpoint, port=args.port, selector=args.selector)
        if subcommand == "selection":
            return browser_cdp.selection(args.target, endpoint=args.endpoint, port=args.port)
        if subcommand == "click":
            return browser_cdp.click(args.target, args.selector, endpoint=args.endpoint, port=args.port)
        if subcommand == "type":
            return browser_cdp.type_text(
                args.target,
                args.text,
                endpoint=args.endpoint,
                port=args.port,
                selector=args.selector,
                clear=args.clear,
            )
        if subcommand == "press":
            return browser_cdp.press_key(args.target, args.combo, endpoint=args.endpoint, port=args.port)
        if subcommand == "send":
            return browser_cdp.send_command(args.target, args.method, args.params, endpoint=args.endpoint, port=args.port)
        raise DctlError("UNKNOWN", f"Unsupported browser command '{subcommand}'.")
    if command == "libreoffice":
        subcommand = args.libreoffice_command
        if subcommand == "start":
            return libreoffice_uno.start_office(port=args.port, headless=args.headless, executable=args.exec)
        if subcommand == "stop":
            return libreoffice_uno.stop_office(args.pid)
        if subcommand == "docs":
            return libreoffice_uno.list_documents(port=args.port)
        if subcommand == "open":
            return libreoffice_uno.open_document(args.path, port=args.port, hidden=args.hidden)
        if subcommand == "info":
            return libreoffice_uno.document_info(args.document, port=args.port)
        if subcommand == "save":
            return libreoffice_uno.save_document(args.document, port=args.port)
        if subcommand == "close":
            return libreoffice_uno.close_document(args.document, port=args.port)
        if subcommand == "writer-text":
            return libreoffice_uno.writer_text(args.document, port=args.port)
        if subcommand == "writer-paragraphs":
            return libreoffice_uno.writer_paragraphs(args.document, port=args.port)
        if subcommand == "writer-append":
            return libreoffice_uno.writer_append(args.document, args.text, port=args.port)
        if subcommand == "writer-set-paragraph":
            return libreoffice_uno.writer_set_paragraph(args.document, args.index, args.text, port=args.port)
        if subcommand == "calc-sheets":
            return libreoffice_uno.calc_sheets(args.document, port=args.port)
        if subcommand == "calc-read":
            return libreoffice_uno.calc_read(args.document, args.sheet, args.range, port=args.port)
        if subcommand == "calc-write-cell":
            return libreoffice_uno.calc_write_cell(
                args.document,
                args.sheet,
                args.cell,
                args.value,
                port=args.port,
                json_value=args.json,
            )
        if subcommand == "calc-write-range":
            return libreoffice_uno.calc_write_range(args.document, args.sheet, args.range, args.rows_json, port=args.port)
        raise DctlError("UNKNOWN", f"Unsupported LibreOffice command '{subcommand}'.")
    if command in {"docx", "word"}:
        subcommand = args.docx_command
        if subcommand == "inspect":
            return docx_files.inspect(args.path)
        if subcommand == "read":
            return docx_files.read(args.path, include_empty=args.include_empty)
        if subcommand == "paragraphs":
            return docx_files.paragraphs(args.path, include_empty=not args.skip_empty)
        if subcommand == "append":
            return docx_files.append(args.path, args.text, style=args.style)
        if subcommand == "insert-before":
            return docx_files.insert_before(args.path, args.index, args.text, style=args.style)
        if subcommand == "set-paragraph":
            return docx_files.set_paragraph(args.path, args.index, args.text)
        if subcommand == "replace":
            return docx_files.replace(args.path, args.find, args.replace)
        raise DctlError("UNKNOWN", f"Unsupported DOCX command '{subcommand}'.")
    if command in {"xlsx", "excel"}:
        subcommand = args.xlsx_command
        if subcommand == "inspect":
            return xlsx_files.inspect(args.path)
        if subcommand == "sheets":
            return xlsx_files.sheets(args.path)
        if subcommand == "read":
            return xlsx_files.read(args.path, args.sheet, args.range)
        if subcommand == "write-cell":
            return xlsx_files.write_cell(args.path, args.sheet, args.cell, args.value, json_value=args.json)
        if subcommand == "write-range":
            return xlsx_files.write_range(args.path, args.sheet, args.range, args.rows_json)
        raise DctlError("UNKNOWN", f"Unsupported XLSX command '{subcommand}'.")
    raise DctlError("UNKNOWN", f"Unsupported command '{command}'.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manager = DesktopManager()
    meta = build_meta(manager)
    try:
        data = dispatch(args, manager)
        emit_success(data, meta)
        return 0
    except Exception as exc:
        error = as_dctl_error(exc)
        emit_error(error, meta)
        return error.exit_code
