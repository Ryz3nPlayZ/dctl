from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from docx import Document

from dctl.errors import DctlError


def _path(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise DctlError("ELEMENT_NOT_FOUND", f"Document not found: {resolved}")
    return resolved


def _iter_paragraphs(document: Any) -> Iterable[Any]:
    for paragraph in document.paragraphs:
        yield paragraph
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph


def inspect(path: str) -> dict[str, Any]:
    doc_path = _path(path)
    document = Document(doc_path)
    return {
        "path": str(doc_path),
        "paragraph_count": len(document.paragraphs),
        "table_count": len(document.tables),
        "title": document.core_properties.title or None,
        "subject": document.core_properties.subject or None,
    }


def read(path: str, include_empty: bool = False) -> dict[str, Any]:
    doc_path = _path(path)
    document = Document(doc_path)
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    if not include_empty:
        paragraphs = [paragraph for paragraph in paragraphs if paragraph.strip()]
    return {
        "path": str(doc_path),
        "paragraphs": paragraphs,
        "text": "\n".join(paragraphs),
    }


def paragraphs(path: str, include_empty: bool = True) -> dict[str, Any]:
    doc_path = _path(path)
    document = Document(doc_path)
    items = []
    for index, paragraph in enumerate(document.paragraphs):
        if not include_empty and not paragraph.text.strip():
            continue
        items.append({"index": index, "text": paragraph.text, "style": paragraph.style.name if paragraph.style else None})
    return {"path": str(doc_path), "items": items}


def append(path: str, text_value: str, style: str | None = None) -> dict[str, Any]:
    doc_path = _path(path)
    document = Document(doc_path)
    paragraph = document.add_paragraph(text_value)
    if style:
        paragraph.style = style
    document.save(doc_path)
    return {"path": str(doc_path), "appended": text_value, "paragraph_index": len(document.paragraphs) - 1}


def insert_before(path: str, index: int, text_value: str, style: str | None = None) -> dict[str, Any]:
    doc_path = _path(path)
    document = Document(doc_path)
    if index < 0 or index >= len(document.paragraphs):
        raise DctlError("INVALID_SELECTOR", f"Paragraph index {index} is out of range.")
    paragraph = document.paragraphs[index].insert_paragraph_before(text_value)
    if style:
        paragraph.style = style
    document.save(doc_path)
    return {"path": str(doc_path), "inserted_before": index, "text": text_value}


def set_paragraph(path: str, index: int, text_value: str) -> dict[str, Any]:
    doc_path = _path(path)
    document = Document(doc_path)
    if index < 0 or index >= len(document.paragraphs):
        raise DctlError("INVALID_SELECTOR", f"Paragraph index {index} is out of range.")
    document.paragraphs[index].text = text_value
    document.save(doc_path)
    return {"path": str(doc_path), "paragraph_index": index, "text": text_value}


def replace(path: str, find_text: str, replace_text: str) -> dict[str, Any]:
    doc_path = _path(path)
    document = Document(doc_path)
    replacements = 0
    fallback_resets = 0

    for paragraph in _iter_paragraphs(document):
        run_replacements = 0
        for run in paragraph.runs:
            if find_text in run.text:
                run.text = run.text.replace(find_text, replace_text)
                run_replacements += 1
        if run_replacements:
            replacements += run_replacements
            continue
        if find_text in paragraph.text:
            paragraph.text = paragraph.text.replace(find_text, replace_text)
            replacements += 1
            fallback_resets += 1

    document.save(doc_path)
    return {
        "path": str(doc_path),
        "find": find_text,
        "replace": replace_text,
        "replacements": replacements,
        "paragraph_reset_fallbacks": fallback_resets,
    }
