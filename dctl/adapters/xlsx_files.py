from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries

from dctl.errors import DctlError


def _path(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise DctlError("ELEMENT_NOT_FOUND", f"Workbook not found: {resolved}")
    return resolved


def _sheet(workbook: Any, name: str) -> Any:
    if name not in workbook.sheetnames:
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"Worksheet '{name}' was not found.",
            details={"sheets": workbook.sheetnames},
        )
    return workbook[name]


def inspect(path: str) -> dict[str, Any]:
    workbook_path = _path(path)
    workbook = load_workbook(workbook_path)
    return {
        "path": str(workbook_path),
        "sheet_count": len(workbook.sheetnames),
        "active_sheet": workbook.active.title,
        "sheets": workbook.sheetnames,
    }


def sheets(path: str) -> dict[str, Any]:
    workbook_path = _path(path)
    workbook = load_workbook(workbook_path)
    items = []
    for name in workbook.sheetnames:
        worksheet = workbook[name]
        items.append(
            {
                "name": name,
                "max_row": worksheet.max_row,
                "max_column": worksheet.max_column,
                "tables": list(worksheet.tables.keys()),
            }
        )
    return {"path": str(workbook_path), "items": items}


def read(path: str, sheet_name: str, cell_range: str) -> dict[str, Any]:
    workbook_path = _path(path)
    workbook = load_workbook(workbook_path, data_only=False)
    worksheet = _sheet(workbook, sheet_name)
    values = [[cell.value for cell in row] for row in worksheet[cell_range]]
    return {"path": str(workbook_path), "sheet": sheet_name, "range": cell_range, "values": values}


def _coerce_value(raw: str, json_value: bool) -> Any:
    if not json_value:
        if raw.startswith("="):
            return raw
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DctlError("INVALID_SELECTOR", f"Value is not valid JSON: {raw}") from exc


def _write_value(cell: Any, value: Any) -> None:
    if isinstance(value, str) and value.startswith("="):
        cell.value = value
        return
    cell.value = value


def write_cell(path: str, sheet_name: str, cell_ref: str, raw_value: str, json_value: bool = False) -> dict[str, Any]:
    workbook_path = _path(path)
    workbook = load_workbook(workbook_path)
    worksheet = _sheet(workbook, sheet_name)
    value = _coerce_value(raw_value, json_value)
    _write_value(worksheet[cell_ref], value)
    workbook.save(workbook_path)
    return {"path": str(workbook_path), "sheet": sheet_name, "cell": cell_ref, "value": value}


def write_range(path: str, sheet_name: str, cell_range: str, json_rows: str) -> dict[str, Any]:
    workbook_path = _path(path)
    workbook = load_workbook(workbook_path)
    worksheet = _sheet(workbook, sheet_name)
    try:
        rows = json.loads(json_rows)
    except json.JSONDecodeError as exc:
        raise DctlError("INVALID_SELECTOR", "Range data must be valid JSON.") from exc
    if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
        raise DctlError("INVALID_SELECTOR", "Range data must be a JSON array of arrays.")
    min_col, min_row, max_col, max_row = range_boundaries(cell_range)
    expected_rows = max_row - min_row + 1
    expected_cols = max_col - min_col + 1
    if len(rows) != expected_rows or any(len(row) != expected_cols for row in rows):
        raise DctlError(
            "INVALID_SELECTOR",
            f"Range {cell_range} expects {expected_rows}x{expected_cols} values.",
        )
    for row_offset, row in enumerate(rows):
        for col_offset, value in enumerate(row):
            cell = worksheet.cell(row=min_row + row_offset, column=min_col + col_offset)
            _write_value(cell, value)
    workbook.save(workbook_path)
    return {"path": str(workbook_path), "sheet": sheet_name, "range": cell_range, "rows": rows}
