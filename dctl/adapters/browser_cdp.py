from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from typing import Any
from urllib import parse, request

import websockets

from dctl.errors import DctlError


def _fetch_json(url: str, method: str = "GET") -> Any:
    req = request.Request(url, method=method)
    try:
        with request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        raise DctlError(
            "BACKEND_FAILURE",
            f"Unable to reach Chrome DevTools endpoint {url}.",
            suggestion="Start a debug-enabled browser with `dctl browser start` or pass `--endpoint`.",
        ) from exc
    except json.JSONDecodeError as exc:
        raise DctlError(
            "BACKEND_FAILURE",
            f"Chrome DevTools endpoint {url} returned invalid JSON.",
        ) from exc


def _fetch_text(url: str, method: str = "GET") -> str:
    req = request.Request(url, method=method)
    try:
        with request.urlopen(req, timeout=5) as response:
            return response.read().decode("utf-8")
    except OSError as exc:
        raise DctlError(
            "BACKEND_FAILURE",
            f"Unable to reach Chrome DevTools endpoint {url}.",
            suggestion="Start a debug-enabled browser with `dctl browser start` or pass `--endpoint`.",
        ) from exc


def normalize_endpoint(endpoint: str | None = None, port: int | None = None) -> str:
    if endpoint:
        return endpoint.rstrip("/")
    if port is not None:
        return f"http://127.0.0.1:{port}"
    for candidate in range(9222, 9233):
        url = f"http://127.0.0.1:{candidate}/json/version"
        try:
            _fetch_json(url)
        except DctlError:
            continue
        return f"http://127.0.0.1:{candidate}"
    raise DctlError(
        "CAPABILITY_UNAVAILABLE",
        "No Chrome DevTools endpoint was found.",
        suggestion="Start one with `dctl browser start` or pass `--endpoint http://127.0.0.1:PORT`.",
    )


def browser_version(endpoint: str | None = None, port: int | None = None) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port)
    payload = _fetch_json(f"{base}/json/version")
    payload["endpoint"] = base
    return payload


def list_targets(endpoint: str | None = None, port: int | None = None) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port)
    targets = _fetch_json(f"{base}/json/list")
    return {"endpoint": base, "items": targets}


def _browser_candidates(app: str | None = None) -> list[str]:
    requested = app.strip().lower() if app else None
    buckets: dict[str, list[str]] = {
        "brave": [
            shutil.which("brave") or "",
            shutil.which("brave-browser") or "",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ],
        "chrome": [
            shutil.which("google-chrome-stable") or "",
            shutil.which("google-chrome") or "",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ],
        "chromium": [
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ],
    }
    if requested:
        if requested not in buckets:
            raise DctlError(
                "INVALID_SELECTOR",
                f"Unsupported browser app '{app}'.",
                suggestion="Use one of: brave, chrome, chromium.",
            )
        candidates = buckets[requested]
    else:
        candidates = buckets["brave"] + buckets["chrome"] + buckets["chromium"]
    return [candidate for candidate in candidates if candidate and Path(candidate).exists()]


def resolve_browser_executable(app: str | None = None, explicit_path: str | None = None) -> str:
    if explicit_path:
        if not Path(explicit_path).exists():
            raise DctlError("DEPENDENCY_MISSING", f"Browser executable does not exist: {explicit_path}")
        return explicit_path
    candidates = _browser_candidates(app)
    if not candidates:
        raise DctlError(
            "DEPENDENCY_MISSING",
            "No supported Chromium-based browser executable was found.",
            suggestion="Install Brave, Google Chrome, or Chromium, or pass `--exec`.",
        )
    return candidates[0]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_browser(
    *,
    app: str | None = None,
    executable: str | None = None,
    port: int | None = None,
    url: str | None = None,
    headless: bool = False,
) -> dict[str, Any]:
    browser_exec = resolve_browser_executable(app, executable)
    selected_port = port or _find_free_port()
    user_data_dir = tempfile.mkdtemp(prefix="dctl-browser-")
    command = [
        browser_exec,
        f"--remote-debugging-port={selected_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        command.append("--headless=new")
    if url:
        command.append(url)
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    endpoint = f"http://127.0.0.1:{selected_port}"
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            _fetch_json(f"{endpoint}/json/version")
            return {
                "app": app or Path(browser_exec).name,
                "executable": browser_exec,
                "pid": process.pid,
                "port": selected_port,
                "endpoint": endpoint,
                "user_data_dir": user_data_dir,
                "headless": headless,
            }
        except DctlError:
            time.sleep(0.2)
    process.terminate()
    raise DctlError(
        "TIMEOUT",
        f"Timed out waiting for a Chrome DevTools endpoint on port {selected_port}.",
    )


def stop_browser(pid: int, user_data_dir: str | None = None) -> dict[str, Any]:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        raise DctlError("ELEMENT_NOT_FOUND", f"No browser process with pid {pid} exists.")
    if user_data_dir:
        shutil.rmtree(user_data_dir, ignore_errors=True)
    return {"pid": pid, "stopped": True, "user_data_dir_removed": bool(user_data_dir)}


def open_target(url: str, endpoint: str | None = None, port: int | None = None) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port)
    encoded = parse.quote(url, safe=":/?&=%#,+")
    target = _fetch_json(f"{base}/json/new?{encoded}", method="PUT")
    return {"endpoint": base, "target": target}


def activate_target(target: str, endpoint: str | None = None, port: int | None = None) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port)
    resolved = resolve_target(target, endpoint=base)
    result = _fetch_text(f"{base}/json/activate/{resolved['id']}")
    return {"endpoint": base, "target": resolved, "result": result}


def close_target(target: str, endpoint: str | None = None, port: int | None = None) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port)
    resolved = resolve_target(target, endpoint=base)
    result = _fetch_text(f"{base}/json/close/{resolved['id']}")
    return {"endpoint": base, "target": resolved, "result": result}


def resolve_target(target: str, *, endpoint: str | None = None, port: int | None = None) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port)
    items = _fetch_json(f"{base}/json/list")
    exact = [item for item in items if target in {item.get("id"), item.get("title"), item.get("url")}]
    if len(exact) == 1:
        return exact[0]
    partial = [
        item
        for item in items
        if target == "active" or target.lower() in (item.get("title", "") + " " + item.get("url", "")).lower()
    ]
    if target == "active":
        pages = [item for item in items if item.get("type") == "page"]
        if not pages:
            raise DctlError("ELEMENT_NOT_FOUND", "No page targets are available.")
        return pages[0]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"No browser target matching '{target}' was found.",
            suggestion="Run `dctl browser targets` to inspect available tabs.",
        )
    raise DctlError(
        "MULTIPLE_MATCHES",
        f"Browser target selector '{target}' matched multiple tabs.",
        details={"candidates": partial[:20]},
    )


@dataclass(slots=True)
class KeySpec:
    key: str
    code: str
    key_code: int
    modifiers: int
    text: str | None


def parse_key_combo(combo: str) -> KeySpec:
    parts = [part.strip() for part in combo.split("+") if part.strip()]
    if not parts:
        raise DctlError("INVALID_SELECTOR", "Key combo cannot be empty.")
    modifiers = 0
    mapping = {"alt": 1, "ctrl": 2, "control": 2, "meta": 4, "cmd": 4, "super": 4, "shift": 8}
    normalized_parts: list[str] = []
    for part in parts[:-1]:
        key = part.lower()
        if key not in mapping:
            raise DctlError("INVALID_SELECTOR", f"Unsupported key modifier '{part}'.")
        modifiers |= mapping[key]
        normalized_parts.append(key)

    key_name = parts[-1]
    lower = key_name.lower()
    named: dict[str, tuple[str, str, int]] = {
        "enter": ("Enter", "Enter", 13),
        "tab": ("Tab", "Tab", 9),
        "escape": ("Escape", "Escape", 27),
        "esc": ("Escape", "Escape", 27),
        "backspace": ("Backspace", "Backspace", 8),
        "delete": ("Delete", "Delete", 46),
        "space": (" ", "Space", 32),
        "left": ("ArrowLeft", "ArrowLeft", 37),
        "up": ("ArrowUp", "ArrowUp", 38),
        "right": ("ArrowRight", "ArrowRight", 39),
        "down": ("ArrowDown", "ArrowDown", 40),
        "home": ("Home", "Home", 36),
        "end": ("End", "End", 35),
    }
    if lower in named:
        key, code, key_code = named[lower]
        text = None if modifiers else (key if len(key) == 1 else None)
        return KeySpec(key=key, code=code, key_code=key_code, modifiers=modifiers, text=text)
    if lower.startswith("f") and lower[1:].isdigit():
        number = int(lower[1:])
        if 1 <= number <= 12:
            return KeySpec(key=f"F{number}", code=f"F{number}", key_code=111 + number, modifiers=modifiers, text=None)
    if len(key_name) == 1:
        char = key_name
        if char.isalpha():
            code = f"Key{char.upper()}"
            key_code = ord(char.upper())
        elif char.isdigit():
            code = f"Digit{char}"
            key_code = ord(char)
        else:
            code = char
            key_code = ord(char)
        text = None if modifiers else char
        return KeySpec(key=char, code=code, key_code=key_code, modifiers=modifiers, text=text)
    raise DctlError("INVALID_SELECTOR", f"Unsupported key '{key_name}'.")


async def _send_command_async(ws_url: str, method: str, params: dict[str, Any] | None = None) -> Any:
    async with websockets.connect(ws_url, open_timeout=5, close_timeout=1, max_size=10_000_000) as websocket:
        session = _AsyncTargetSession(websocket)
        return await session.call(method, params)


class _AsyncTargetSession:
    def __init__(self, websocket: Any) -> None:
        self.websocket = websocket
        self._next_id = 1

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        message_id = self._next_id
        self._next_id += 1
        await self.websocket.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            payload = json.loads(await asyncio.wait_for(self.websocket.recv(), timeout=5))
            if payload.get("id") != message_id:
                continue
            if "error" in payload:
                error = payload["error"]
                raise DctlError(
                    "BACKEND_FAILURE",
                    f"CDP command {method} failed: {error.get('message', 'unknown error')}",
                    details={"command": method, "params": params or {}, "error": error},
                )
            return payload.get("result", {})


def _send_command(target: dict[str, Any], method: str, params: dict[str, Any] | None = None) -> Any:
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        raise DctlError(
            "ACTION_NOT_SUPPORTED",
            "Target does not expose a websocket debugger URL.",
            details={"target": target},
        )
    return asyncio.run(_send_command_async(ws_url, method, params))


def _run_in_target_session(target: dict[str, Any], operation: Any) -> Any:
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        raise DctlError(
            "ACTION_NOT_SUPPORTED",
            "Target does not expose a websocket debugger URL.",
            details={"target": target},
        )

    async def runner() -> Any:
        async with websockets.connect(ws_url, open_timeout=5, close_timeout=1, max_size=10_000_000) as websocket:
            session = _AsyncTargetSession(websocket)
            return await operation(session)

    return asyncio.run(runner())


def _prepare_page_target(target_selector: str, endpoint: str | None = None, port: int | None = None) -> tuple[str, dict[str, Any]]:
    base = normalize_endpoint(endpoint, port)
    target = resolve_target(target_selector, endpoint=base)
    if target.get("type") != "page":
        raise DctlError("ACTION_NOT_SUPPORTED", "Only page targets are supported for page interaction commands.")
    return base, target


def _runtime_evaluate(
    target: dict[str, Any],
    expression: str,
    await_promise: bool = True,
    return_by_value: bool = False,
) -> dict[str, Any]:
    return _send_command(
        target,
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": return_by_value,
        },
    )


def _extract_remote_value(result: dict[str, Any]) -> Any:
    remote = result.get("result", result)
    if "value" in remote:
        return remote["value"]
    return {
        "type": remote.get("type"),
        "subtype": remote.get("subtype"),
        "description": remote.get("description"),
        "objectId": remote.get("objectId"),
    }


def evaluate(
    target_selector: str,
    expression: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    await_promise: bool = True,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port)
    _send_command(target, "Page.enable")
    result = _runtime_evaluate(target, expression, await_promise=await_promise)
    return {"endpoint": base, "target": target, "result": _extract_remote_value(result)}


def dom(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    selector: str | None = None,
    depth: int = 3,
    pierce: bool = True,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port)
    async def operation(session: _AsyncTargetSession) -> dict[str, Any]:
        root = await session.call("DOM.getDocument", {"depth": depth, "pierce": pierce})
        if not selector:
            return {"root": root["root"]}
        node = await session.call("DOM.querySelector", {"nodeId": root["root"]["nodeId"], "selector": selector})
        node_id = int(node.get("nodeId", 0))
        if node_id == 0:
            raise DctlError("ELEMENT_NOT_FOUND", f"No DOM node matches selector '{selector}'.")
        described = await session.call("DOM.describeNode", {"nodeId": node_id, "depth": depth, "pierce": pierce})
        outer_html = await session.call("DOM.getOuterHTML", {"nodeId": node_id})
        return {"selector": selector, "node": described["node"], "outer_html": outer_html.get("outerHTML")}

    payload = _run_in_target_session(target, operation)
    if not selector:
        return {"endpoint": base, "target": target, "root": payload["root"]}
    return {
        "endpoint": base,
        "target": target,
        "selector": payload["selector"],
        "node": payload["node"],
        "outer_html": payload["outer_html"],
    }


def accessibility_tree(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    selector: str | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port)
    if selector:
        async def operation(session: _AsyncTargetSession) -> dict[str, Any]:
            root = await session.call("DOM.getDocument", {"depth": 1, "pierce": True})
            node = await session.call("DOM.querySelector", {"nodeId": root["root"]["nodeId"], "selector": selector})
            node_id = int(node.get("nodeId", 0))
            if node_id == 0:
                raise DctlError("ELEMENT_NOT_FOUND", f"No DOM node matches selector '{selector}'.")
            return await session.call("Accessibility.getPartialAXTree", {"nodeId": node_id, "fetchRelatives": True})

        payload = _run_in_target_session(target, operation)
        return {"endpoint": base, "target": target, "selector": selector, "nodes": payload.get("nodes", [])}
    payload = _send_command(target, "Accessibility.getFullAXTree")
    return {"endpoint": base, "target": target, "nodes": payload.get("nodes", [])}


def text(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    selector: str | None = None,
) -> dict[str, Any]:
    if selector:
        expression = f"""
(() => {{
  const node = document.querySelector({json.dumps(selector)});
  if (!node) return null;
  return {{
    text: node.innerText ?? node.textContent ?? "",
    value: node.value ?? null,
    tag: node.tagName ?? null
  }};
}})()
""".strip()
    else:
        expression = """
(() => ({
  title: document.title,
  text: document.body ? (document.body.innerText ?? document.body.textContent ?? "") : "",
  activeTag: document.activeElement ? document.activeElement.tagName : null
}))()
""".strip()
    base, target = _prepare_page_target(target_selector, endpoint, port)
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    return {"endpoint": base, "target": target, "result": _extract_remote_value(result)}


def selection(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    expression = """
(() => ({
  text: window.getSelection ? String(window.getSelection()) : "",
  activeTag: document.activeElement ? document.activeElement.tagName : null
}))()
""".strip()
    base, target = _prepare_page_target(target_selector, endpoint, port)
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    return {"endpoint": base, "target": target, "result": _extract_remote_value(result)}


def _node_id_for_selector(target: dict[str, Any], selector: str) -> int:
    async def operation(session: _AsyncTargetSession) -> int:
        root = await session.call("DOM.getDocument", {"depth": 1, "pierce": True})
        node = await session.call("DOM.querySelector", {"nodeId": root["root"]["nodeId"], "selector": selector})
        node_id = int(node.get("nodeId", 0))
        if node_id == 0:
            raise DctlError("ELEMENT_NOT_FOUND", f"No DOM node matches selector '{selector}'.")
        return node_id

    return _run_in_target_session(target, operation)


def click(
    target_selector: str,
    selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port)
    async def operation(session: _AsyncTargetSession) -> dict[str, int]:
        await session.call("Page.bringToFront")
        root = await session.call("DOM.getDocument", {"depth": 1, "pierce": True})
        node = await session.call("DOM.querySelector", {"nodeId": root["root"]["nodeId"], "selector": selector})
        node_id = int(node.get("nodeId", 0))
        if node_id == 0:
            raise DctlError("ELEMENT_NOT_FOUND", f"No DOM node matches selector '{selector}'.")
        quads = (await session.call("DOM.getContentQuads", {"nodeId": node_id})).get("quads", [])
        if not quads:
            raise DctlError(
                "ACTION_NOT_SUPPORTED",
                f"Unable to resolve click coordinates for selector '{selector}'.",
            )
        quad = quads[0]
        x = int(round((quad[0] + quad[2] + quad[4] + quad[6]) / 4))
        y = int(round((quad[1] + quad[3] + quad[5] + quad[7]) / 4))
        await session.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "left", "clickCount": 1})
        await session.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await session.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        return {"x": x, "y": y}

    coords = _run_in_target_session(target, operation)
    return {
        "endpoint": base,
        "target": target,
        "selector": selector,
        "x": coords["x"],
        "y": coords["y"],
    }


def type_text(
    target_selector: str,
    text_value: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    selector: str | None = None,
    clear: bool = False,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port)
    _send_command(target, "Page.bringToFront")
    if selector:
        expression = f"""
(() => {{
  const node = document.querySelector({json.dumps(selector)});
  if (!node) return false;
  node.focus();
  if ({json.dumps(clear)}) {{
    if ('value' in node) {{
      node.value = '';
    }} else if (node.isContentEditable) {{
      node.textContent = '';
    }}
  }}
  return true;
}})()
""".strip()
        result = _runtime_evaluate(target, expression)
        if not _extract_remote_value(result):
            raise DctlError("ELEMENT_NOT_FOUND", f"No DOM node matches selector '{selector}'.")
    elif clear:
        _runtime_evaluate(
            target,
            """
(() => {
  const node = document.activeElement;
  if (!node) return false;
  if ('value' in node) node.value = '';
  else if (node.isContentEditable) node.textContent = '';
  return true;
})()
""".strip(),
        )
    _send_command(target, "Input.insertText", {"text": text_value})
    return {"endpoint": base, "target": target, "selector": selector, "text": text_value}


def press_key(
    target_selector: str,
    combo: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port)
    _send_command(target, "Page.bringToFront")
    spec = parse_key_combo(combo)
    key_down = {
        "type": "keyDown",
        "modifiers": spec.modifiers,
        "key": spec.key,
        "code": spec.code,
        "windowsVirtualKeyCode": spec.key_code,
        "nativeVirtualKeyCode": spec.key_code,
    }
    if spec.text:
        key_down["text"] = spec.text
        key_down["unmodifiedText"] = spec.text
    _send_command(target, "Input.dispatchKeyEvent", key_down)
    _send_command(
        target,
        "Input.dispatchKeyEvent",
        {
            "type": "keyUp",
            "modifiers": spec.modifiers,
            "key": spec.key,
            "code": spec.code,
            "windowsVirtualKeyCode": spec.key_code,
            "nativeVirtualKeyCode": spec.key_code,
        },
    )
    return {
        "endpoint": base,
        "target": target,
        "combo": combo,
        "modifiers": spec.modifiers,
        "key": spec.key,
        "code": spec.code,
    }


def send_command(
    target_selector: str,
    method: str,
    params_json: str | None = None,
    *,
    endpoint: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port)
    params = json.loads(params_json) if params_json else {}
    result = _send_command(target, method, params)
    return {"endpoint": base, "target": target, "method": method, "params": params, "result": result}
