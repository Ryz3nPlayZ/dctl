from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from dctl.errors import DctlError
from dctl.locator import build_locator
from dctl.models import AppInfo, Bounds, ElementInfo, WindowInfo
from dctl.selector import Selector, match_selector


WINDOW_ROLES = {"frame", "window", "dialog", "alert", "file chooser", "page tab"}


@dataclass(slots=True)
class AccessibleRecord:
    app_name: str
    window_title: str | None
    path: str
    element: Any
    serialized: dict[str, Any]


class LinuxAtspiProvider:
    _initialized = False

    def __init__(self) -> None:
        self.Atspi = self._load_atspi()
        self._ensure_bus()
        if not LinuxAtspiProvider._initialized:
            self.Atspi.init()
            LinuxAtspiProvider._initialized = True

    def _load_atspi(self) -> Any:
        try:
            import gi

            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
        except Exception as exc:
            raise DctlError(
                "DEPENDENCY_MISSING",
                "Linux accessibility bindings are not available.",
                suggestion="Install Python GObject introspection bindings and the AT-SPI typelib package.",
            ) from exc
        return Atspi

    def _ensure_bus(self) -> None:
        from dctl.capabilities import collect_capabilities
        from dctl.platform.detect import detect_environment

        env = detect_environment()
        capabilities = collect_capabilities(env)
        if not capabilities["diagnostics"]["checks"].get("atspi_bus"):
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "The AT-SPI accessibility bus is not available in this session.",
                suggestion="Enable accessibility support for the desktop session and rerun `dctl doctor`.",
                details={"capability": "accessibility", "backend": "atspi"},
            )

    def list_apps(self) -> list[AppInfo]:
        apps: list[AppInfo] = []
        for app in self._iter_apps():
            windows = self._window_infos_for_app(app)
            apps.append(
                AppInfo(
                    name=app.get_name() or "",
                    pid=self._safe_call(app.get_process_id),
                    id=self._element_id(app, "/application"),
                    windows=windows,
                )
            )
        return apps

    def list_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        for app in self._iter_apps():
            windows.extend(self._window_infos_for_app(app))
        return windows

    def get_tree(self, app_name: str | None = None, depth: int = 5) -> list[dict[str, Any]]:
        roots: list[dict[str, Any]] = []
        for app in self._iter_apps():
            name = app.get_name() or ""
            if app_name and app_name.lower() not in name.lower():
                continue
            roots.append(self._serialize_accessible(app, name, None, "/application", depth).serialized)
        return roots

    def find_elements(self, selector: Selector) -> list[AccessibleRecord]:
        matches: list[AccessibleRecord] = []
        for app in self._iter_apps():
            app_name = app.get_name() or ""
            matches.extend(self._search_accessible(app, selector, app_name, None, "/application"))
        return matches

    def read_element(self, record: AccessibleRecord) -> dict[str, Any]:
        element = record.serialized
        return {
            "locator": element["locator"],
            "name": element["name"],
            "role": element["role"],
            "text": element.get("text"),
            "value": element.get("value"),
            "description": element.get("description"),
            "state": element.get("state"),
        }

    def click(self, record: AccessibleRecord) -> dict[str, Any]:
        element = record.element
        for preferred in ("click", "press", "activate", "open", "jump"):
            index = self._action_index(element, preferred)
            if index is not None:
                ok = bool(self._safe_call(lambda: element.do_action(index)))
                if ok:
                    return {"action": preferred, "locator": record.serialized["locator"]}

        raise DctlError(
            "ACTION_NOT_SUPPORTED",
            "Element does not expose a semantic click action.",
            suggestion="Use coordinate fallback input if an input helper is available.",
        )

    def focus(self, record: AccessibleRecord) -> dict[str, Any]:
        ok = bool(self._safe_call(record.element.grab_focus))
        if ok:
            return {"focused": True, "locator": record.serialized["locator"]}
        raise DctlError(
            "ACTION_NOT_SUPPORTED",
            "Element does not expose a semantic focus action.",
            suggestion="Use coordinate fallback input if an input helper is available.",
        )

    def set_text(self, record: AccessibleRecord, text: str) -> dict[str, Any]:
        element = record.element
        if self._safe_call(element.is_editable_text):
            ok = bool(self._safe_call(lambda: element.set_text_contents(text)))
            if ok:
                return {"locator": record.serialized["locator"], "method": "set_text_contents"}
        if self._safe_call(element.is_text):
            ok = bool(self._safe_call(lambda: element.set_text_contents(text)))
            if ok:
                return {"locator": record.serialized["locator"], "method": "set_text_contents"}
        raise DctlError(
            "ACTION_NOT_SUPPORTED",
            "Element does not expose a semantic text editing interface.",
            suggestion="Use raw input typing fallback if an input helper is available.",
        )

    def element_at(self, x: int, y: int) -> dict[str, Any]:
        for app in self._iter_apps():
            app_name = app.get_name() or ""
            candidate = self._safe_call(lambda: app.get_accessible_at_point(x, y, self.Atspi.CoordType.SCREEN))
            if candidate:
                record = self._serialize_with_context(candidate, app_name, x, y)
                if record:
                    return record.serialized
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"No accessible element found at {x},{y}.",
            suggestion="Capture a screenshot or inspect the app tree for more context.",
        )

    def _search_accessible(
        self,
        accessible: Any,
        selector: Selector,
        app_name: str,
        window_title: str | None,
        path: str,
    ) -> list[AccessibleRecord]:
        current = self._serialize_accessible(accessible, app_name, window_title, path, 0)
        next_window_title = window_title
        if self._is_window(current.serialized["role"]):
            next_window_title = current.serialized["name"] or window_title

        matches: list[AccessibleRecord] = []
        if match_selector(current.serialized, selector):
            matches.append(current)

        child_count = self._safe_call(accessible.get_child_count, default=0)
        for index in range(child_count or 0):
            child = self._safe_call(lambda idx=index: accessible.get_child_at_index(idx))
            if child is None:
                continue
            child_role = self._safe_call(child.get_role_name, default="unknown") or "unknown"
            child_path = f"{path}/{self._normalize_role(child_role)}[{index}]"
            matches.extend(self._search_accessible(child, selector, app_name, next_window_title, child_path))
        return matches

    def _serialize_with_context(self, accessible: Any, app_name: str, x: int, y: int) -> AccessibleRecord | None:
        queue: list[tuple[Any, str | None, str]] = [(accessible, None, "/application")]
        while queue:
            current, window_title, path = queue.pop(0)
            record = self._serialize_accessible(current, app_name, window_title, path, 0)
            bounds = record.serialized.get("bounds")
            if bounds and bounds["x"] <= x <= bounds["x"] + bounds["width"] and bounds["y"] <= y <= bounds["y"] + bounds["height"]:
                return record
            child_count = self._safe_call(current.get_child_count, default=0)
            next_window_title = window_title
            if self._is_window(record.serialized["role"]):
                next_window_title = record.serialized["name"] or window_title
            for index in range(child_count or 0):
                child = self._safe_call(lambda idx=index: current.get_child_at_index(idx))
                if child is None:
                    continue
                child_role = self._safe_call(child.get_role_name, default="unknown") or "unknown"
                child_path = f"{path}/{self._normalize_role(child_role)}[{index}]"
                queue.append((child, next_window_title, child_path))
        return None

    def _serialize_accessible(
        self,
        accessible: Any,
        app_name: str,
        window_title: str | None,
        path: str,
        depth: int,
    ) -> AccessibleRecord:
        role = self._safe_call(accessible.get_role_name, default="unknown") or "unknown"
        name = self._safe_call(accessible.get_name, default="") or ""
        description = self._safe_call(accessible.get_description, default="") or ""
        pid = self._safe_call(accessible.get_process_id)
        bounds = self._bounds_for(accessible)
        text_value = self._text_for(accessible)
        current_value = self._value_for(accessible)
        state = self._states_for(accessible)
        actions = self._actions_for(accessible)
        next_window_title = name if self._is_window(role) and name else window_title
        locator = build_locator(app_name=app_name, window_title=next_window_title, path=path)

        element = ElementInfo(
            id=self._element_id(accessible, path),
            locator=locator,
            role=self._normalize_role(role),
            name=name,
            description=description,
            app={"name": app_name, "pid": pid},
            window={"title": next_window_title, "id": f"window:{next_window_title}"} if next_window_title else None,
            value=current_value,
            text=text_value,
            state=state,
            actions=actions,
            bounds=bounds,
            path=path,
            children=[],
        )

        if depth > 0:
            child_count = self._safe_call(accessible.get_child_count, default=0)
            for index in range(child_count or 0):
                child = self._safe_call(lambda idx=index: accessible.get_child_at_index(idx))
                if child is None:
                    continue
                child_role = self._safe_call(child.get_role_name, default="unknown") or "unknown"
                child_path = f"{path}/{self._normalize_role(child_role)}[{index}]"
                child_record = self._serialize_accessible(child, app_name, next_window_title, child_path, depth - 1)
                element.children.append(child_record.serialized)

        return AccessibleRecord(
            app_name=app_name,
            window_title=next_window_title,
            path=path,
            element=accessible,
            serialized=element.to_dict(),
        )

    def _window_infos_for_app(self, app: Any) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        app_name = app.get_name() or ""
        child_count = self._safe_call(app.get_child_count, default=0)
        for index in range(child_count or 0):
            child = self._safe_call(lambda idx=index: app.get_child_at_index(idx))
            if child is None:
                continue
            role = self._normalize_role(self._safe_call(child.get_role_name, default="unknown") or "unknown")
            if not self._is_window(role):
                continue
            windows.append(
                WindowInfo(
                    id=self._element_id(child, f"/window[{index}]"),
                    title=self._safe_call(child.get_name, default="") or "",
                    app_name=app_name,
                    pid=self._safe_call(child.get_process_id),
                    focused="focused" in self._states_for(child),
                    bounds=self._bounds_for(child),
                )
            )
        return windows

    def _bounds_for(self, accessible: Any) -> Bounds | None:
        extents = self._safe_call(lambda: accessible.get_extents(self.Atspi.CoordType.SCREEN))
        if not extents:
            return None
        return Bounds(x=int(extents.x), y=int(extents.y), width=int(extents.width), height=int(extents.height))

    def _text_for(self, accessible: Any) -> str | None:
        if not self._safe_call(accessible.is_text, default=False):
            return None
        count = int(self._safe_call(accessible.get_character_count, default=0) or 0)
        if count <= 0:
            return None
        return self._safe_call(lambda: accessible.get_text(0, count), default=None)

    def _value_for(self, accessible: Any) -> Any | None:
        if self._safe_call(accessible.is_value, default=False):
            return self._safe_call(accessible.get_current_value)
        if self._safe_call(accessible.is_text, default=False):
            count = int(self._safe_call(accessible.get_character_count, default=0) or 0)
            if count > 0:
                return self._safe_call(lambda: accessible.get_text(0, count), default=None)
        return None

    def _states_for(self, accessible: Any) -> list[str]:
        state_set = self._safe_call(accessible.get_state_set)
        if not state_set:
            return []
        names: list[str] = []
        for state in self._safe_call(state_set.get_states, default=[]) or []:
            names.append(self._normalize_role(str(state.value_name if hasattr(state, "value_name") else state)))
        return sorted({name for name in names if name})

    def _actions_for(self, accessible: Any) -> list[str]:
        if not self._safe_call(accessible.is_action, default=False):
            return []
        count = int(self._safe_call(accessible.get_n_actions, default=0) or 0)
        actions: list[str] = []
        for index in range(count):
            action_name = self._safe_call(lambda idx=index: accessible.get_action_name(idx), default="")
            if action_name:
                actions.append(action_name.lower())
        return actions

    def _action_index(self, accessible: Any, action_name: str) -> int | None:
        count = int(self._safe_call(accessible.get_n_actions, default=0) or 0)
        target = action_name.lower()
        for index in range(count):
            current = self._safe_call(lambda idx=index: accessible.get_action_name(idx), default="")
            if current and current.lower() == target:
                return index
        return None

    def _iter_apps(self) -> Iterable[Any]:
        for desktop_index in range(int(self.Atspi.get_desktop_count())):
            desktop = self.Atspi.get_desktop(desktop_index)
            child_count = self._safe_call(desktop.get_child_count, default=0)
            for child_index in range(child_count or 0):
                app = self._safe_call(lambda idx=child_index: desktop.get_child_at_index(idx))
                if app is not None:
                    yield app

    def _element_id(self, accessible: Any, path: str) -> str:
        pid = self._safe_call(accessible.get_process_id, default="unknown")
        return f"atspi:{pid}:{path}"

    def _is_window(self, role_name: str) -> bool:
        return self._normalize_role(role_name) in WINDOW_ROLES

    def _normalize_role(self, role_name: str) -> str:
        return role_name.strip().lower().replace("_", " ")

    def _safe_call(self, func: Any, default: Any = None) -> Any:
        try:
            return func()
        except Exception:
            return default

