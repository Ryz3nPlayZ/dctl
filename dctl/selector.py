from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from dctl.errors import DctlError


FIELD_RE = re.compile(r"^(app|window|role|name|text|state|path)(~?):(.+)$")


@dataclass(slots=True)
class Term:
    field: str
    value: Any
    fuzzy: bool = False
    kind: str = "field"


@dataclass(slots=True)
class Selector:
    groups: list[list[Term]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": [
                [
                    {"field": term.field, "value": term.value, "fuzzy": term.fuzzy, "kind": term.kind}
                    for term in group
                ]
                for group in self.groups
            ]
        }


def _split_unquoted(text: str, token: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    in_quote = False
    while i < len(text):
        char = text[i]
        if char == '"' and (i == 0 or text[i - 1] != "\\"):
            in_quote = not in_quote
            buf.append(char)
            i += 1
            continue
        if not in_quote and text.startswith(token, i):
            parts.append("".join(buf).strip())
            buf = []
            i += len(token)
            continue
        buf.append(char)
        i += 1
    parts.append("".join(buf).strip())
    return [part for part in parts if part]


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
        value = value.replace('\\"', '"').replace("\\\\", "\\")
    return value


def parse_selector(text: str) -> Selector:
    text = text.strip()
    if not text:
        raise DctlError("INVALID_SELECTOR", "Selector cannot be empty.")

    groups: list[list[Term]] = []
    for group_text in _split_unquoted(text, " OR "):
        group: list[Term] = []
        for part in _split_unquoted(group_text, " AND "):
            part = part.strip()
            if not part:
                continue
            if part.startswith("@"):
                coords = part[1:].split(",", 1)
                if len(coords) != 2:
                    raise DctlError("INVALID_SELECTOR", f"Invalid coordinate selector: {part}")
                try:
                    x, y = int(coords[0]), int(coords[1])
                except ValueError as exc:
                    raise DctlError("INVALID_SELECTOR", f"Invalid coordinate selector: {part}") from exc
                group.append(Term(field="coords", value=(x, y), kind="coords"))
                continue

            match = FIELD_RE.match(part)
            if not match:
                raise DctlError("INVALID_SELECTOR", f"Unsupported selector term: {part}")
            field, fuzzy, value = match.groups()
            group.append(Term(field=field, value=_unquote(value), fuzzy=bool(fuzzy)))

        if group:
            groups.append(group)

    if not groups:
        raise DctlError("INVALID_SELECTOR", "Selector did not contain any valid terms.")
    return Selector(groups=groups)


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _contains_bounds(bounds: dict[str, Any] | None, x: int, y: int) -> bool:
    if not bounds:
        return False
    return (
        bounds["x"] <= x <= bounds["x"] + bounds["width"]
        and bounds["y"] <= y <= bounds["y"] + bounds["height"]
    )


def match_selector(element: dict[str, Any], selector: Selector) -> bool:
    app_name = _norm((element.get("app") or {}).get("name"))
    window_title = _norm((element.get("window") or {}).get("title"))
    role = _norm(element.get("role"))
    name = _norm(element.get("name"))
    text = _norm(element.get("text"))
    value = _norm(element.get("value"))
    states = {_norm(state) for state in element.get("state") or []}
    path = _norm(element.get("path"))
    bounds = element.get("bounds")

    for group in selector.groups:
        if all(_match_term(term, app_name, window_title, role, name, text, value, states, path, bounds) for term in group):
            return True
    return False


def _match_term(
    term: Term,
    app_name: str,
    window_title: str,
    role: str,
    name: str,
    text: str,
    value: str,
    states: set[str],
    path: str,
    bounds: dict[str, Any] | None,
) -> bool:
    if term.kind == "coords":
        x, y = term.value
        return _contains_bounds(bounds, x, y)

    target = _norm(term.value)
    if term.field == "app":
        return target in app_name if term.fuzzy else app_name == target
    if term.field == "window":
        return target in window_title if term.fuzzy else window_title == target
    if term.field == "role":
        return target in role if term.fuzzy else role == target
    if term.field == "name":
        return target in name if term.fuzzy else name == target
    if term.field == "text":
        haystack = " ".join(part for part in (text, value, name) if part)
        return target in haystack if term.fuzzy else target in {text, value, name}
    if term.field == "state":
        return target in states
    if term.field == "path":
        return target == path
    return False

