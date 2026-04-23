from __future__ import annotations


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_locator(
    *,
    app_name: str | None = None,
    window_title: str | None = None,
    path: str | None = None,
) -> str:
    parts: list[str] = []
    if app_name:
        parts.append(f"app:{_quote(app_name)}")
    if window_title:
        parts.append(f"window:{_quote(window_title)}")
    if path:
        parts.append(f"path:{path}")
    return " AND ".join(parts) if parts else ""

