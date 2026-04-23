from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from typing import Any

import uno

from dctl.errors import DctlError


def resolve_soffice_path(explicit: str | None = None) -> str:
    if explicit:
        if not Path(explicit).exists():
            raise DctlError("DEPENDENCY_MISSING", f"LibreOffice executable does not exist: {explicit}")
        return explicit
    candidates = [
        shutil.which("soffice") or "",
        shutil.which("libreoffice") or "",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise DctlError(
        "DEPENDENCY_MISSING",
        "LibreOffice was not found.",
        suggestion="Install LibreOffice or pass `--exec` to `dctl libreoffice start`.",
    )


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_office(port: int | None = None, headless: bool = False, executable: str | None = None) -> dict[str, Any]:
    soffice = resolve_soffice_path(executable)
    selected_port = port or _find_free_port()
    command = [
        soffice,
        f"--accept=socket,host=127.0.0.1,port={selected_port};urp;StarOffice.ComponentContext",
        "--nologo",
        "--nodefault",
        "--norestore",
        "--nofirststartwizard",
    ]
    if headless:
        command.append("--headless")
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            _connect(selected_port)
            return {
                "pid": process.pid,
                "port": selected_port,
                "headless": headless,
                "executable": soffice,
            }
        except DctlError:
            time.sleep(0.25)
    process.terminate()
    raise DctlError(
        "TIMEOUT",
        f"Timed out waiting for LibreOffice on port {selected_port}.",
    )


def stop_office(pid: int) -> dict[str, Any]:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        raise DctlError("ELEMENT_NOT_FOUND", f"No LibreOffice process with pid {pid} exists.")
    return {"pid": pid, "stopped": True}


def _property(name: str, value: Any) -> Any:
    prop = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    prop.Name = name
    prop.Value = value
    return prop


def _connect(port: int) -> tuple[Any, Any]:
    local_context = uno.getComponentContext()
    resolver = local_context.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver",
        local_context,
    )
    try:
        context = resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
    except Exception as exc:
        raise DctlError(
            "BACKEND_FAILURE",
            f"Unable to connect to LibreOffice on port {port}.",
            suggestion="Start one with `dctl libreoffice start`.",
        ) from exc
    desktop = context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
    return context, desktop


def _iter_components(desktop: Any) -> list[Any]:
    enum = desktop.getComponents().createEnumeration()
    components = []
    while enum.hasMoreElements():
        components.append(enum.nextElement())
    return components


def _component_type(component: Any) -> str:
    if component.supportsService("com.sun.star.text.TextDocument"):
        return "writer"
    if component.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
        return "calc"
    return "unknown"


def _file_url(path: str) -> str:
    return uno.systemPathToFileUrl(str(Path(path).expanduser().resolve()))


def _system_path(file_url: str | None) -> str | None:
    if not file_url:
        return None
    if file_url.startswith("file://"):
        return uno.fileUrlToSystemPath(file_url)
    return file_url


def _component_info(component: Any) -> dict[str, Any]:
    location = component.getLocation() if hasattr(component, "getLocation") else ""
    title = component.getTitle() if hasattr(component, "getTitle") else ""
    return {
        "id": location or title,
        "title": title,
        "url": location or None,
        "path": _system_path(location),
        "type": _component_type(component),
        "modified": bool(component.isModified()) if hasattr(component, "isModified") else None,
    }


def list_documents(port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    return {"port": port, "items": [_component_info(component) for component in _iter_components(desktop)]}


def _resolve_component(desktop: Any, document: str) -> Any:
    components = _iter_components(desktop)
    matches = []
    for component in components:
        info = _component_info(component)
        haystack = [info["id"], info["title"], info["url"], info["path"]]
        if document in {item for item in haystack if item}:
            return component
        if any(document.lower() in item.lower() for item in haystack if isinstance(item, str)):
            matches.append(component)
    if len(matches) == 1:
        return matches[0]

    candidate_path = Path(document).expanduser()
    if candidate_path.exists():
        file_url = _file_url(str(candidate_path))
        for component in components:
            info = _component_info(component)
            if info["url"] == file_url:
                return component
        return desktop.loadComponentFromURL(
            file_url,
            "_blank",
            0,
            (
                _property("Hidden", False),
                _property("ReadOnly", False),
            ),
        )

    if not matches:
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"No LibreOffice document matching '{document}' was found.",
            suggestion="Run `dctl libreoffice docs` or pass a document path.",
        )
    raise DctlError(
        "MULTIPLE_MATCHES",
        f"LibreOffice document selector '{document}' matched multiple documents.",
        details={"candidates": [_component_info(component) for component in matches[:20]]},
    )


def open_document(path: str, port: int = 2002, hidden: bool = False) -> dict[str, Any]:
    _context, desktop = _connect(port)
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise DctlError("ELEMENT_NOT_FOUND", f"Document not found: {resolved}")
    component = desktop.loadComponentFromURL(
        _file_url(str(resolved)),
        "_blank",
        0,
        (
            _property("Hidden", hidden),
            _property("ReadOnly", False),
        ),
    )
    return {"port": port, "document": _component_info(component)}


def document_info(document: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    return {"port": port, "document": _component_info(component)}


def save_document(document: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    component.store()
    return {"port": port, "document": _component_info(component), "saved": True}


def close_document(document: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    info = _component_info(component)
    component.close(True)
    return {"port": port, "document": info, "closed": True}


def writer_text(document: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    if _component_type(component) != "writer":
        raise DctlError("ACTION_NOT_SUPPORTED", "Document is not a Writer text document.")
    text = component.getText().getString()
    return {"port": port, "document": _component_info(component), "text": text}


def writer_paragraphs(document: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    if _component_type(component) != "writer":
        raise DctlError("ACTION_NOT_SUPPORTED", "Document is not a Writer text document.")
    enum = component.getText().createEnumeration()
    items = []
    index = 0
    while enum.hasMoreElements():
        paragraph = enum.nextElement()
        items.append({"index": index, "text": paragraph.getString()})
        index += 1
    return {"port": port, "document": _component_info(component), "items": items}


def _store_if_backed(component: Any) -> bool:
    location = component.getLocation() if hasattr(component, "getLocation") else ""
    if location:
        component.store()
        return True
    return False


def writer_append(document: str, text_value: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    if _component_type(component) != "writer":
        raise DctlError("ACTION_NOT_SUPPORTED", "Document is not a Writer text document.")
    text_object = component.getText()
    cursor = text_object.createTextCursor()
    cursor.gotoEnd(False)
    if text_object.getString():
        paragraph_break = uno.getConstantByName("com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK")
        text_object.insertControlCharacter(cursor, paragraph_break, False)
    text_object.insertString(cursor, text_value, False)
    saved = _store_if_backed(component)
    return {"port": port, "document": _component_info(component), "saved": saved, "text": text_value}


def writer_set_paragraph(document: str, index: int, text_value: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    if _component_type(component) != "writer":
        raise DctlError("ACTION_NOT_SUPPORTED", "Document is not a Writer text document.")
    enum = component.getText().createEnumeration()
    current = 0
    while enum.hasMoreElements():
        paragraph = enum.nextElement()
        if current == index:
            paragraph.setString(text_value)
            saved = _store_if_backed(component)
            return {"port": port, "document": _component_info(component), "paragraph_index": index, "saved": saved}
        current += 1
    raise DctlError("INVALID_SELECTOR", f"Paragraph index {index} is out of range.")


def calc_sheets(document: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    if _component_type(component) != "calc":
        raise DctlError("ACTION_NOT_SUPPORTED", "Document is not a Calc spreadsheet.")
    names = list(component.getSheets().getElementNames())
    return {"port": port, "document": _component_info(component), "items": names}


def calc_read(document: str, sheet_name: str, cell_range: str, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    if _component_type(component) != "calc":
        raise DctlError("ACTION_NOT_SUPPORTED", "Document is not a Calc spreadsheet.")
    sheets = component.getSheets()
    if not sheets.hasByName(sheet_name):
        raise DctlError("ELEMENT_NOT_FOUND", f"Worksheet '{sheet_name}' was not found.")
    sheet = sheets.getByName(sheet_name)
    values = [list(row) for row in sheet.getCellRangeByName(cell_range).getDataArray()]
    return {
        "port": port,
        "document": _component_info(component),
        "sheet": sheet_name,
        "range": cell_range,
        "values": values,
    }


def _parse_value(raw_value: str, json_value: bool) -> Any:
    if not json_value:
        return raw_value
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise DctlError("INVALID_SELECTOR", f"Value is not valid JSON: {raw_value}") from exc


def _set_calc_cell_value(cell: Any, value: Any) -> None:
    if isinstance(value, bool):
        cell.setValue(1 if value else 0)
        return
    if isinstance(value, (int, float)):
        cell.setValue(float(value))
        return
    if isinstance(value, str) and value.startswith("="):
        cell.setFormula(value)
        return
    cell.setString(str(value))


def calc_write_cell(
    document: str,
    sheet_name: str,
    cell_ref: str,
    raw_value: str,
    *,
    port: int = 2002,
    json_value: bool = False,
) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    if _component_type(component) != "calc":
        raise DctlError("ACTION_NOT_SUPPORTED", "Document is not a Calc spreadsheet.")
    sheets = component.getSheets()
    if not sheets.hasByName(sheet_name):
        raise DctlError("ELEMENT_NOT_FOUND", f"Worksheet '{sheet_name}' was not found.")
    value = _parse_value(raw_value, json_value)
    sheet = sheets.getByName(sheet_name)
    _set_calc_cell_value(sheet.getCellRangeByName(cell_ref), value)
    saved = _store_if_backed(component)
    return {
        "port": port,
        "document": _component_info(component),
        "sheet": sheet_name,
        "cell": cell_ref,
        "value": value,
        "saved": saved,
    }


def calc_write_range(document: str, sheet_name: str, cell_range: str, rows_json: str, *, port: int = 2002) -> dict[str, Any]:
    _context, desktop = _connect(port)
    component = _resolve_component(desktop, document)
    if _component_type(component) != "calc":
        raise DctlError("ACTION_NOT_SUPPORTED", "Document is not a Calc spreadsheet.")
    sheets = component.getSheets()
    if not sheets.hasByName(sheet_name):
        raise DctlError("ELEMENT_NOT_FOUND", f"Worksheet '{sheet_name}' was not found.")
    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError as exc:
        raise DctlError("INVALID_SELECTOR", "Range data must be valid JSON.") from exc
    if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
        raise DctlError("INVALID_SELECTOR", "Range data must be a JSON array of arrays.")
    sheet = sheets.getByName(sheet_name)
    cell_range_object = sheet.getCellRangeByName(cell_range)
    row_count = cell_range_object.Rows.Count
    col_count = cell_range_object.Columns.Count
    if len(rows) != row_count or any(len(row) != col_count for row in rows):
        raise DctlError(
            "INVALID_SELECTOR",
            f"Range {cell_range} expects {row_count}x{col_count} values.",
        )
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            _set_calc_cell_value(cell_range_object.getCellByPosition(col_index, row_index), value)
    saved = _store_if_backed(component)
    return {
        "port": port,
        "document": _component_info(component),
        "sheet": sheet_name,
        "range": cell_range,
        "rows": rows,
        "saved": saved,
    }
