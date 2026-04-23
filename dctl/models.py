from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WindowInfo:
    id: str
    title: str
    app_name: str
    pid: int | None = None
    focused: bool | None = None
    bounds: Bounds | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.bounds is None:
            data["bounds"] = None
        return data


@dataclass(slots=True)
class AppInfo:
    name: str
    pid: int | None = None
    id: str | None = None
    windows: list[WindowInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pid": self.pid,
            "id": self.id,
            "windows": [window.to_dict() for window in self.windows],
        }


@dataclass(slots=True)
class ElementInfo:
    id: str
    locator: str
    role: str
    name: str
    app: dict[str, Any]
    window: dict[str, Any] | None = None
    description: str | None = None
    value: Any | None = None
    text: str | None = None
    state: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    bounds: Bounds | None = None
    path: str | None = None
    children: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "locator": self.locator,
            "role": self.role,
            "name": self.name,
            "app": self.app,
            "window": self.window,
            "description": self.description,
            "value": self.value,
            "text": self.text,
            "state": list(self.state),
            "actions": list(self.actions),
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "path": self.path,
            "children": list(self.children),
        }
        return data

