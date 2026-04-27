"""
Windows UIAutomation + Win32 accessibility provider.

Uses comtypes to bind to the native IUIAutomation COM interface.
On non-Windows platforms this module raises ImportError at load time — the
platform manager must guard against that.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from dctl.errors import DctlError
from dctl.locator import build_locator
from dctl.models import AppInfo, Bounds, ElementInfo, WindowInfo
from dctl.selector import Selector, match_selector


# ---------------------------------------------------------------------------
# UIA role-name normalisation
# ---------------------------------------------------------------------------

_UIA_CONTROL_TYPES: dict[int, str] = {
    50000: "button",
    50001: "calendar",
    50002: "check_box",
    50003: "combo_box",
    50004: "edit",
    50005: "hyperlink",
    50006: "image",
    50007: "list_item",
    50008: "list",
    50009: "menu",
    50010: "menu_bar",
    50011: "menu_item",
    50012: "progress_bar",
    50013: "radio_button",
    50014: "scroll_bar",
    50015: "slider",
    50016: "spinner",
    50017: "status_bar",
    50018: "tab",
    50019: "tab_item",
    50020: "text",
    50021: "tool_bar",
    50022: "tool_tip",
    50023: "tree",
    50024: "tree_item",
    50025: "custom",
    50026: "group",
    50027: "thumb",
    50028: "data_grid",
    50029: "data_item",
    50030: "document",
    50031: "split_button",
    50032: "window",
    50033: "pane",
    50034: "header",
    50035: "header_item",
    50036: "table",
    50037: "title_bar",
    50038: "separator",
    50039: "semantic_zoom",
    50040: "app_bar",
}

WINDOW_ROLES = {"window", "pane", "dialog"}


def _control_type_name(ct: int) -> str:
    return _UIA_CONTROL_TYPES.get(ct, f"unknown_{ct}")


# ---------------------------------------------------------------------------
# Record / provider
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class UIARecord:
    app_name: str
    window_title: str | None
    path: str
    element: Any          # IUIAutomationElement
    serialized: dict[str, Any]


class WindowsUIAProvider:
    """
    Wraps the Windows UIAutomation COM API via comtypes.

    All public methods mirror the interface established by LinuxAtspiProvider
    and MacOSBackend so the DesktopManager can call them uniformly.
    """

    def __init__(self) -> None:
        self._uia = self._load_uia()

    # ------------------------------------------------------------------
    # Dependency loading
    # ------------------------------------------------------------------

    def _load_uia(self) -> Any:
        try:
            import comtypes.client  # type: ignore[import]
            uia = comtypes.client.CreateObject(
                "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                interface=comtypes.client.GetModule("UIAutomationClient").IUIAutomation,
            )
            return uia
        except Exception:
            # Fallback: try the well-known ProgID
            try:
                import comtypes.client
                import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
                uia = comtypes.client.CreateObject(UIA.CUIAutomation)
                return uia
            except Exception as exc:
                raise DctlError(
                    "DEPENDENCY_MISSING",
                    "Windows UIAutomation COM bindings are not available.",
                    suggestion=(
                        "Ensure comtypes is installed (`pip install comtypes`) "
                        "and UIAutomationClient.dll is registered on this system."
                    ),
                ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_apps(self) -> list[AppInfo]:
        seen_pids: dict[int, AppInfo] = {}
        for record in self._iter_top_level():
            pid = record.serialized.get("app", {}).get("pid") or 0
            name = record.serialized.get("app", {}).get("name") or "unknown"
            win = WindowInfo(
                id=record.serialized["id"],
                title=record.serialized["name"],
                app_name=name,
                pid=pid,
                focused="focused" in (record.serialized.get("state") or []),
                bounds=_bounds_from_dict(record.serialized.get("bounds")),
            )
            if pid not in seen_pids:
                seen_pids[pid] = AppInfo(name=name, pid=pid, id=str(pid), windows=[])
            seen_pids[pid].windows.append(win)
        return list(seen_pids.values())

    def list_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        for record in self._iter_top_level():
            s = record.serialized
            pid = (s.get("app") or {}).get("pid")
            windows.append(
                WindowInfo(
                    id=s["id"],
                    title=s["name"],
                    app_name=(s.get("app") or {}).get("name") or "",
                    pid=pid,
                    focused="focused" in (s.get("state") or []),
                    bounds=_bounds_from_dict(s.get("bounds")),
                )
            )
        return windows

    def get_tree(self, app_name: str | None = None, depth: int = 5) -> list[dict[str, Any]]:
        roots: list[dict[str, Any]] = []
        for record in self._iter_top_level():
            if app_name and app_name.lower() not in record.app_name.lower():
                continue
            full = self._serialize(record.element, record.app_name, record.window_title, record.path, depth)
            roots.append(full.serialized)
        return roots

    def find_elements(self, selector: Selector) -> list[UIARecord]:
        matches: list[UIARecord] = []
        seen: set[str] = set()
        for top in self._iter_top_level():
            for record in self._walk(top.element, top.app_name, top.window_title, top.path, selector, seen):
                matches.append(record)
        return matches

    def read_element(self, record: UIARecord) -> dict[str, Any]:
        s = record.serialized
        return {
            "locator": s["locator"],
            "name": s["name"],
            "role": s["role"],
            "text": s.get("text"),
            "value": s.get("value"),
            "description": s.get("description"),
            "state": s.get("state"),
        }

    def click(self, record: UIARecord) -> dict[str, Any]:
        """Try InvokePattern first, fall back to raising ACTION_NOT_SUPPORTED."""
        element = record.element
        try:
            import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
            pattern = element.GetCurrentPattern(UIA.UIA_InvokePatternId)
            if pattern:
                pattern.QueryInterface(UIA.IUIAutomationInvokePattern).Invoke()
                return {"action": "invoke", "locator": record.serialized["locator"], "backend": "uia"}
        except Exception:
            pass
        try:
            import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
            pattern = element.GetCurrentPattern(UIA.UIA_LegacyIAccessiblePatternId)
            if pattern:
                acc = pattern.QueryInterface(UIA.IUIAutomationLegacyIAccessiblePattern)
                acc.DoDefaultAction()
                return {"action": "default_action", "locator": record.serialized["locator"], "backend": "uia"}
        except Exception:
            pass
        raise DctlError(
            "ACTION_NOT_SUPPORTED",
            "Element does not expose InvokePattern or a default accessible action.",
            suggestion="Use coordinate fallback: `dctl click @X,Y`.",
        )

    def focus(self, record: UIARecord) -> dict[str, Any]:
        try:
            record.element.SetFocus()
            return {"focused": True, "locator": record.serialized["locator"], "backend": "uia"}
        except Exception as exc:
            raise DctlError(
                "ACTION_NOT_SUPPORTED",
                "SetFocus failed on this element.",
                suggestion="Try focusing the window first or use a coordinate click.",
            ) from exc

    def set_text(self, record: UIARecord, text: str) -> dict[str, Any]:
        element = record.element
        try:
            import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
            pattern = element.GetCurrentPattern(UIA.UIA_ValuePatternId)
            if pattern:
                pattern.QueryInterface(UIA.IUIAutomationValuePattern).SetValue(text)
                return {"locator": record.serialized["locator"], "method": "value_pattern", "backend": "uia"}
        except Exception:
            pass
        raise DctlError(
            "ACTION_NOT_SUPPORTED",
            "Element does not expose ValuePattern for text entry.",
            suggestion="Focus the element and use `dctl type` for raw keystroke injection.",
        )

    def element_at(self, x: int, y: int) -> dict[str, Any]:
        try:
            import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
            from ctypes import Structure, c_long
            class POINT(Structure):
                _fields_ = [("x", c_long), ("y", c_long)]
            pt = POINT(x=x, y=y)
            element = self._uia.ElementFromPoint(pt)
            if element:
                app_name, pid = _app_name_from_element(element)
                record = self._serialize(element, app_name, None, "/element", 0)
                return record.serialized
        except Exception:
            pass
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"No UIAutomation element found at {x},{y}.",
            suggestion="Capture a screenshot and inspect the UI manually.",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _iter_top_level(self) -> Iterator[UIARecord]:
        """Yield all top-level windows from the UIA root."""
        try:
            import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
            root = self._uia.GetRootElement()
            condition = self._uia.CreateTrueCondition()
            walker = self._uia.CreateTreeWalker(condition)
            child = walker.GetFirstChildElement(root)
            while child is not None:
                app_name, _pid = _app_name_from_element(child)
                record = self._serialize(child, app_name, None, "/window[0]", 0)
                yield record
                child = walker.GetNextSiblingElement(child)
        except Exception:
            return

    def _walk(
        self,
        element: Any,
        app_name: str,
        window_title: str | None,
        path: str,
        selector: Selector,
        seen: set[str],
    ) -> Iterator[UIARecord]:
        record = self._serialize(element, app_name, window_title, path, 0)
        key = record.serialized["locator"] or record.serialized["id"]
        if key not in seen:
            if match_selector(record.serialized, selector):
                seen.add(key)
                yield record
        try:
            import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
            condition = self._uia.CreateTrueCondition()
            walker = self._uia.CreateTreeWalker(condition)
            next_window_title = window_title
            if record.serialized["role"] in WINDOW_ROLES and record.serialized["name"]:
                next_window_title = record.serialized["name"]
            child = walker.GetFirstChildElement(element)
            index = 0
            while child is not None:
                ct = _safe_int(child, "CurrentControlType", 50025)
                role = _control_type_name(ct)
                child_path = f"{path}/{role}[{index}]"
                yield from self._walk(child, app_name, next_window_title, child_path, selector, seen)
                child = walker.GetNextSiblingElement(child)
                index += 1
        except Exception:
            return

    def _serialize(
        self,
        element: Any,
        app_name: str,
        window_title: str | None,
        path: str,
        depth: int,
    ) -> UIARecord:
        ct = _safe_int(element, "CurrentControlType", 50025)
        role = _control_type_name(ct)
        name = _safe_str(element, "CurrentName")
        description = _safe_str(element, "CurrentHelpText")
        pid = _safe_int(element, "CurrentProcessId", 0)
        enabled = _safe_bool(element, "CurrentIsEnabled")
        focused = _safe_bool(element, "CurrentHasFocus")
        offscreen = _safe_bool(element, "CurrentIsOffscreen")

        bounds = _rect_to_bounds(element)
        text_value = _extract_text_value(element)
        value_str = _extract_value(element)
        state: list[str] = []
        if enabled:
            state.append("enabled")
        if focused:
            state.append("focused")
        if not offscreen:
            state.append("visible")
        actions = _detect_actions(element)

        next_window_title = name if role in WINDOW_ROLES and name else window_title
        locator = build_locator(app_name=app_name, window_title=next_window_title, path=path)

        elem_info = ElementInfo(
            id=f"uia:{pid}:{path}",
            locator=locator,
            role=role,
            name=name,
            description=description or None,
            app={"name": app_name, "pid": pid},
            window={"title": next_window_title, "id": f"window:{next_window_title}"} if next_window_title else None,
            value=value_str,
            text=text_value or value_str,
            state=state,
            actions=actions,
            bounds=bounds,
            path=path,
            children=[],
        )

        if depth > 0:
            try:
                import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
                condition = self._uia.CreateTrueCondition()
                walker = self._uia.CreateTreeWalker(condition)
                child = walker.GetFirstChildElement(element)
                index = 0
                while child is not None:
                    child_ct = _safe_int(child, "CurrentControlType", 50025)
                    child_role = _control_type_name(child_ct)
                    child_path = f"{path}/{child_role}[{index}]"
                    child_record = self._serialize(child, app_name, next_window_title, child_path, depth - 1)
                    elem_info.children.append(child_record.serialized)
                    child = walker.GetNextSiblingElement(child)
                    index += 1
            except Exception:
                pass

        return UIARecord(
            app_name=app_name,
            window_title=next_window_title,
            path=path,
            element=element,
            serialized=elem_info.to_dict(),
        )


# ---------------------------------------------------------------------------
# Low-level helpers (module-level to avoid method overhead)
# ---------------------------------------------------------------------------

def _safe_str(element: Any, attr: str, default: str = "") -> str:
    try:
        val = getattr(element, attr)
        return str(val) if val is not None else default
    except Exception:
        return default


def _safe_int(element: Any, attr: str, default: int = 0) -> int:
    try:
        return int(getattr(element, attr))
    except Exception:
        return default


def _safe_bool(element: Any, attr: str, default: bool = False) -> bool:
    try:
        return bool(getattr(element, attr))
    except Exception:
        return default


def _app_name_from_element(element: Any) -> tuple[str, int]:
    """Return (process_name, pid) for a UIA element using Win32 process APIs."""
    pid = _safe_int(element, "CurrentProcessId", 0)
    name = _process_name_for_pid(pid)
    return name, pid


def _process_name_for_pid(pid: int) -> str:
    if pid <= 0:
        return "unknown"
    try:
        import ctypes
        import ctypes.wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return f"pid-{pid}"
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        ctypes.windll.kernel32.CloseHandle(handle)
        full_path = buf.value
        if full_path:
            import os
            return os.path.splitext(os.path.basename(full_path))[0]
        return f"pid-{pid}"
    except Exception:
        return f"pid-{pid}"


def _rect_to_bounds(element: Any) -> Bounds | None:
    try:
        rect = element.CurrentBoundingRectangle
        # IUIAutomationElement.CurrentBoundingRectangle is a tagRECT
        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)
        if right <= left or bottom <= top:
            return None
        return Bounds(x=left, y=top, width=right - left, height=bottom - top)
    except Exception:
        return None


def _bounds_from_dict(bounds: dict[str, int] | None) -> Bounds | None:
    if not bounds:
        return None
    return Bounds(
        x=bounds.get("x", 0),
        y=bounds.get("y", 0),
        width=bounds.get("width", 0),
        height=bounds.get("height", 0),
    )


def _extract_text_value(element: Any) -> str | None:
    """Read text via TextPattern if available."""
    try:
        import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
        pattern = element.GetCurrentPattern(UIA.UIA_TextPatternId)
        if pattern:
            tp = pattern.QueryInterface(UIA.IUIAutomationTextPattern)
            doc_range = tp.DocumentRange
            return doc_range.GetText(4096) or None
    except Exception:
        pass
    return None


def _extract_value(element: Any) -> str | None:
    """Read current value via ValuePattern if available."""
    try:
        import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
        pattern = element.GetCurrentPattern(UIA.UIA_ValuePatternId)
        if pattern:
            vp = pattern.QueryInterface(UIA.IUIAutomationValuePattern)
            return str(vp.CurrentValue) or None
    except Exception:
        pass
    return None


def _detect_actions(element: Any) -> list[str]:
    actions: list[str] = []
    try:
        import comtypes.gen.UIAutomationClient as UIA  # type: ignore[import]
        if element.GetCurrentPattern(UIA.UIA_InvokePatternId):
            actions.append("invoke")
        if element.GetCurrentPattern(UIA.UIA_ValuePatternId):
            actions.append("set_value")
        if element.GetCurrentPattern(UIA.UIA_TogglePatternId):
            actions.append("toggle")
        if element.GetCurrentPattern(UIA.UIA_SelectionItemPatternId):
            actions.append("select")
        if element.GetCurrentPattern(UIA.UIA_ExpandCollapsePatternId):
            actions.append("expand_collapse")
    except Exception:
        pass
    return actions
