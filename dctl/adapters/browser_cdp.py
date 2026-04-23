from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
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


BROWSER_EXECUTABLE_NAMES = {
    "brave": {"brave", "brave-browser", "brave-browser-stable"},
    "chrome": {"google-chrome", "google-chrome-stable", "chrome"},
    "chromium": {"chromium", "chromium-browser"},
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _browser_home() -> Path:
    override = os.environ.get("DCTL_BROWSER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / ".dctl" / "browser"


def _sessions_dir() -> Path:
    path = _browser_home() / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _profiles_dir() -> Path:
    path = _browser_home() / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_session_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in name.strip().lower())
    cleaned = cleaned.strip("-_")
    if not cleaned:
        raise DctlError("INVALID_SELECTOR", f"Invalid browser session name '{name}'.")
    return cleaned


def _session_metadata_path(name: str) -> Path:
    return _sessions_dir() / f"{_normalize_session_name(name)}.json"


def _session_profile_dir(name: str) -> Path:
    path = _profiles_dir() / _normalize_session_name(name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_session_record(name: str) -> dict[str, Any]:
    path = _session_metadata_path(name)
    if not path.exists():
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"No browser session named '{name}' exists.",
            suggestion="Start one with `dctl browser start --session NAME`.",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DctlError("BACKEND_FAILURE", f"Browser session metadata is invalid: {path}") from exc


def _write_session_record(name: str, record: dict[str, Any]) -> dict[str, Any]:
    path = _session_metadata_path(name)
    normalized_name = _normalize_session_name(name)
    record = {**record, "name": normalized_name}
    path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return record


def _session_endpoint(record: dict[str, Any]) -> str:
    port = record.get("port")
    if port is None:
        raise DctlError("BACKEND_FAILURE", f"Browser session '{record.get('name')}' does not have a port.")
    return f"http://127.0.0.1:{int(port)}"


def _is_pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def list_sessions() -> dict[str, Any]:
    items = []
    for path in sorted(_sessions_dir().glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        running = _is_pid_alive(record.get("pid"))
        endpoint = None
        if record.get("port") is not None:
            endpoint = f"http://127.0.0.1:{record['port']}"
        items.append(
            {
                **record,
                "running": running,
                "endpoint": endpoint,
            }
        )
    return {"items": items}


def session_info(name: str) -> dict[str, Any]:
    record = _read_session_record(name)
    endpoint = _session_endpoint(record)
    reachable = False
    try:
        _fetch_json(f"{endpoint}/json/version")
        reachable = True
    except DctlError:
        reachable = False
    return {
        **record,
        "running": _is_pid_alive(record.get("pid")),
        "reachable": reachable,
        "endpoint": endpoint,
    }


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


def normalize_endpoint(
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> str:
    if endpoint:
        return endpoint.rstrip("/")
    if session_name:
        record = _read_session_record(session_name)
        base = _session_endpoint(record)
        try:
            _fetch_json(f"{base}/json/version")
        except DctlError as exc:
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                f"Browser session '{record['name']}' is not reachable.",
                suggestion=f"Restart it with `dctl browser start --session {record['name']}`.",
            ) from exc
        return base
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


def browser_version(
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port, session_name=session_name)
    payload = _fetch_json(f"{base}/json/version")
    payload["endpoint"] = base
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def _page_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("type") == "page"]


def list_targets(
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port, session_name=session_name)
    targets = _fetch_json(f"{base}/json/list")
    payload = {"endpoint": base, "items": targets}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def _parse_debug_port(cmdline: str) -> int | None:
    for token in cmdline.split("\0"):
        if token.startswith("--remote-debugging-port="):
            value = token.split("=", 1)[1].strip()
            if value.isdigit():
                return int(value)
    return None


def _classify_browser_app(command: str) -> str | None:
    executable = Path(command).name.casefold()
    for app, aliases in BROWSER_EXECUTABLE_NAMES.items():
        if executable in aliases:
            return app
    return None


def _discover_browser_processes(proc_root: str = "/proc") -> list[dict[str, Any]]:
    root = Path(proc_root)
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for entry in root.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        cmdline = raw.decode("utf-8", errors="ignore")
        command = cmdline.split("\0", 1)[0]
        app = _classify_browser_app(command)
        if not app:
            continue
        items.append(
            {
                "pid": int(entry.name),
                "command": command,
                "app": app,
                "debug_port": _parse_debug_port(cmdline),
                "cmdline": [part for part in cmdline.split("\0") if part],
            }
        )
    return items


def _candidate_ports(endpoint: str | None = None, port: int | None = None, proc_root: str = "/proc") -> list[int]:
    if port is not None:
        return [port]
    ports: list[int] = []
    if endpoint:
        parsed = parse.urlparse(endpoint)
        if parsed.port:
            ports.append(parsed.port)
    for record in _discover_browser_processes(proc_root=proc_root):
        if record.get("debug_port") is not None:
            ports.append(int(record["debug_port"]))
    for candidate in range(9222, 9233):
        ports.append(candidate)
    unique: list[int] = []
    seen: set[int] = set()
    for candidate in ports:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _pid_for_debug_port(port: int, proc_root: str = "/proc") -> int | None:
    for record in _discover_browser_processes(proc_root=proc_root):
        if int(record.get("debug_port") or 0) == int(port):
            return int(record["pid"])
    return None


def discover(endpoint: str | None = None, port: int | None = None, proc_root: str = "/proc") -> dict[str, Any]:
    processes = _discover_browser_processes(proc_root=proc_root)
    process_by_port = {record["debug_port"]: record for record in processes if record.get("debug_port") is not None}
    attachable: list[dict[str, Any]] = []
    for candidate_port in _candidate_ports(endpoint=endpoint, port=port, proc_root=proc_root):
        base = f"http://127.0.0.1:{candidate_port}"
        try:
            version = _fetch_json(f"{base}/json/version")
            targets = _fetch_json(f"{base}/json/list")
        except DctlError:
            continue
        record = process_by_port.get(candidate_port)
        attachable.append(
            {
                "endpoint": base,
                "port": candidate_port,
                "browser": version.get("Browser"),
                "process": record,
                "page_count": len(_page_items(targets)),
                "pages": [
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "url": item.get("url"),
                    }
                    for item in _page_items(targets)
                ],
            }
        )
    unavailable = [record for record in processes if record.get("debug_port") is None]
    return {"attachable": attachable, "unavailable": unavailable, "managed_sessions": list_sessions()["items"]}


def attach(
    endpoint: str | None = None,
    port: int | None = None,
    proc_root: str = "/proc",
    session_name: str | None = None,
) -> dict[str, Any]:
    if endpoint or port is not None or session_name:
        base = normalize_endpoint(endpoint, port, session_name=session_name)
        version = browser_version(endpoint=base, session_name=session_name)
        tabs_payload = tabs(endpoint=base, session_name=session_name)
        return {"endpoint": base, "version": version, "tabs": tabs_payload["items"]}

    discovered = discover(proc_root=proc_root)
    if not discovered["attachable"]:
        raise DctlError(
            "CAPABILITY_UNAVAILABLE",
            "No attachable browser session was found.",
            suggestion="Enable remote debugging on the running browser or use `dctl browser start`.",
        )
    if len(discovered["attachable"]) > 1:
        raise DctlError(
            "MULTIPLE_MATCHES",
            "Multiple attachable browser sessions were found.",
            suggestion="Choose one with `--port` or `--endpoint`.",
            details={"candidates": discovered["attachable"]},
        )
    item = discovered["attachable"][0]
    version = browser_version(endpoint=item["endpoint"])
    tabs_payload = tabs(endpoint=item["endpoint"])
    return {"endpoint": item["endpoint"], "version": version, "tabs": tabs_payload["items"], "process": item.get("process")}


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
    session_name: str | None = None,
) -> dict[str, Any]:
    browser_exec = resolve_browser_executable(app, executable)
    normalized_session = _normalize_session_name(session_name) if session_name else None
    existing_record: dict[str, Any] | None = None
    if normalized_session:
        try:
            existing_record = _read_session_record(normalized_session)
            base = _session_endpoint(existing_record)
            _fetch_json(f"{base}/json/version")
            payload = {
                **existing_record,
                "endpoint": base,
                "running": _is_pid_alive(existing_record.get("pid")),
                "reachable": True,
                "managed": True,
                "existing_session": True,
            }
            return payload
        except DctlError:
            pass

    selected_port = port or (int(existing_record["port"]) if existing_record and existing_record.get("port") else None) or _find_free_port()
    if normalized_session:
        user_data_dir = str(_session_profile_dir(normalized_session))
    else:
        user_data_dir = tempfile.mkdtemp(prefix="dctl-browser-")
    command = [
        browser_exec,
        f"--remote-debugging-port={selected_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if normalized_session:
        command.append("--restore-last-session")
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
            actual_pid = _pid_for_debug_port(selected_port) or process.pid
            payload = {
                "app": app or Path(browser_exec).name,
                "executable": browser_exec,
                "pid": actual_pid,
                "port": selected_port,
                "endpoint": endpoint,
                "user_data_dir": user_data_dir,
                "headless": headless,
            }
            if normalized_session:
                previous_created_at = existing_record.get("created_at") if existing_record else None
                record = {
                    "name": normalized_session,
                    "app": app or Path(browser_exec).name,
                    "executable": browser_exec,
                    "pid": actual_pid,
                    "port": selected_port,
                    "user_data_dir": user_data_dir,
                    "headless": headless,
                    "created_at": previous_created_at or _now_iso(),
                    "last_started_at": _now_iso(),
                    "last_stopped_at": existing_record.get("last_stopped_at") if existing_record else None,
                }
                _write_session_record(normalized_session, record)
                payload["session"] = normalized_session
                payload["managed"] = True
                payload["existing_session"] = False
            return payload
        except DctlError:
            time.sleep(0.2)
    process.terminate()
    raise DctlError(
        "TIMEOUT",
        f"Timed out waiting for a Chrome DevTools endpoint on port {selected_port}.",
    )


def stop_browser(
    pid: int | None = None,
    user_data_dir: str | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    normalized_session = _normalize_session_name(session_name) if session_name else None
    record: dict[str, Any] | None = None
    if normalized_session:
        record = _read_session_record(normalized_session)
        pid = pid or int(record["pid"]) if record.get("pid") else None
        if pid is None and record.get("port") is not None:
            pid = _pid_for_debug_port(int(record["port"]))
        user_data_dir = user_data_dir or str(record.get("user_data_dir") or "")
    if pid is None:
        raise DctlError("INVALID_SELECTOR", "Stopping a browser requires `--pid` or `--session`.")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        if not normalized_session:
            raise DctlError("ELEMENT_NOT_FOUND", f"No browser process with pid {pid} exists.")
    removed = False
    if user_data_dir and not normalized_session:
        shutil.rmtree(user_data_dir, ignore_errors=True)
        removed = True
    payload = {"pid": pid, "stopped": True, "user_data_dir_removed": removed}
    if normalized_session and record is not None:
        updated = {
            **record,
            "pid": None,
            "last_stopped_at": _now_iso(),
        }
        _write_session_record(normalized_session, updated)
        payload["session"] = normalized_session
        payload["managed"] = True
        payload["user_data_dir"] = user_data_dir
    return payload


def open_target(
    url: str,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port, session_name=session_name)
    encoded = parse.quote(url, safe=":/?&=%#,+")
    target = _fetch_json(f"{base}/json/new?{encoded}", method="PUT")
    payload = {"endpoint": base, "target": target}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def activate_target(
    target: str,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port, session_name=session_name)
    resolved = resolve_target(target, endpoint=base, session_name=session_name)
    result = _fetch_text(f"{base}/json/activate/{resolved['id']}")
    payload = {"endpoint": base, "target": resolved, "result": result}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def close_target(
    target: str,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port, session_name=session_name)
    resolved = resolve_target(target, endpoint=base, session_name=session_name)
    result = _fetch_text(f"{base}/json/close/{resolved['id']}")
    payload = {"endpoint": base, "target": resolved, "result": result}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def resolve_target(
    target: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port, session_name=session_name)
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


def tabs(
    endpoint: str | None = None,
    port: int | None = None,
    include_non_pages: bool = False,
    session_name: str | None = None,
) -> dict[str, Any]:
    payload = list_targets(endpoint=endpoint, port=port, session_name=session_name)
    items = payload["items"] if include_non_pages else _page_items(payload["items"])
    result = {"endpoint": payload["endpoint"], "items": items}
    if session_name:
        result["session"] = _normalize_session_name(session_name)
    return result


def active_tab(
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base = normalize_endpoint(endpoint, port, session_name=session_name)
    target = resolve_target("active", endpoint=base, session_name=session_name)
    payload = {"endpoint": base, "target": target}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


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


def _prepare_page_target(
    target_selector: str,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    base = normalize_endpoint(endpoint, port, session_name=session_name)
    target = resolve_target(target_selector, endpoint=base, session_name=session_name)
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
    session_name: str | None = None,
    await_promise: bool = True,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    _send_command(target, "Page.enable")
    result = _runtime_evaluate(target, expression, await_promise=await_promise)
    payload = {"endpoint": base, "target": target, "result": _extract_remote_value(result)}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def snapshot(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    text_limit: int = 4000,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    expression = f"""
(() => {{
  const active = document.activeElement;
  const selection = window.getSelection ? String(window.getSelection()) : "";
  const visibleText = document.body ? (document.body.innerText ?? document.body.textContent ?? "") : "";
  return {{
    title: document.title,
    url: location.href,
    readyState: document.readyState,
    activeElement: active ? {{
      tag: active.tagName ?? null,
      id: active.id || null,
      name: active.getAttribute ? active.getAttribute('name') : null,
      ariaLabel: active.getAttribute ? active.getAttribute('aria-label') : null,
      value: 'value' in active ? active.value : null
    }} : null,
    selection,
    visibleText: visibleText.slice(0, {int(text_limit)}),
    frameCount: window.frames.length
  }};
}})()
""".strip()
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    payload = {"endpoint": base, "target": target, "result": _extract_remote_value(result)}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def dom(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    selector: str | None = None,
    depth: int = 3,
    pierce: bool = True,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
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
        result = {"endpoint": base, "target": target, "root": payload["root"]}
        if session_name:
            result["session"] = _normalize_session_name(session_name)
        return result
    result = {
        "endpoint": base,
        "target": target,
        "selector": payload["selector"],
        "node": payload["node"],
        "outer_html": payload["outer_html"],
    }
    if session_name:
        result["session"] = _normalize_session_name(session_name)
    return result


def accessibility_tree(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    selector: str | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    if selector:
        async def operation(session: _AsyncTargetSession) -> dict[str, Any]:
            root = await session.call("DOM.getDocument", {"depth": 1, "pierce": True})
            node = await session.call("DOM.querySelector", {"nodeId": root["root"]["nodeId"], "selector": selector})
            node_id = int(node.get("nodeId", 0))
            if node_id == 0:
                raise DctlError("ELEMENT_NOT_FOUND", f"No DOM node matches selector '{selector}'.")
            return await session.call("Accessibility.getPartialAXTree", {"nodeId": node_id, "fetchRelatives": True})

        payload = _run_in_target_session(target, operation)
        result = {"endpoint": base, "target": target, "selector": selector, "nodes": payload.get("nodes", [])}
        if session_name:
            result["session"] = _normalize_session_name(session_name)
        return result
    payload = _send_command(target, "Accessibility.getFullAXTree")
    result = {"endpoint": base, "target": target, "nodes": payload.get("nodes", [])}
    if session_name:
        result["session"] = _normalize_session_name(session_name)
    return result


def text(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
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
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    payload = {"endpoint": base, "target": target, "result": _extract_remote_value(result)}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def selection(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    expression = """
(() => ({
  text: window.getSelection ? String(window.getSelection()) : "",
  activeTag: document.activeElement ? document.activeElement.tagName : null
}))()
""".strip()
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    payload = {"endpoint": base, "target": target, "result": _extract_remote_value(result)}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def caret(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    selector: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    start_json = "null" if start is None else str(int(start))
    end_json = "null" if end is None else str(int(end))
    selector_json = "null" if selector is None else json.dumps(selector)
    expression = f"""
(() => {{
  const selector = {selector_json};
  const start = {start_json};
  const end = {end_json};
  const root = selector ? document.querySelector(selector) : document.activeElement;
  if (!root) return null;
  if (root.focus) root.focus();
  const isInput = typeof root.value === 'string' && typeof root.setSelectionRange === 'function';
  if (isInput) {{
    const valueLength = root.value.length;
    const resolvedStart = start == null ? valueLength : Math.max(0, Math.min(start, valueLength));
    const resolvedEnd = end == null ? resolvedStart : Math.max(0, Math.min(end, valueLength));
    root.setSelectionRange(Math.min(resolvedStart, resolvedEnd), Math.max(resolvedStart, resolvedEnd));
    return {{
      kind: 'input',
      selectionStart: root.selectionStart,
      selectionEnd: root.selectionEnd,
      valueLength,
    }};
  }}
  const editable = root.isContentEditable || root.getAttribute?.('contenteditable') === 'true';
  if (!editable) return null;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const positions = [];
  let node;
  let total = 0;
  while ((node = walker.nextNode())) {{
    const length = node.nodeValue ? node.nodeValue.length : 0;
    positions.push({{node, start: total, end: total + length}});
    total += length;
  }}
  const clamp = value => Math.max(0, Math.min(value, total));
  const locate = value => {{
    const target = clamp(value);
    for (const entry of positions) {{
      if (target >= entry.start && target <= entry.end) {{
        return {{node: entry.node, offset: target - entry.start}};
      }}
    }}
    if (positions.length) {{
      const last = positions[positions.length - 1];
      return {{node: last.node, offset: last.node.nodeValue ? last.node.nodeValue.length : 0}};
    }}
    return {{node: root, offset: 0}};
  }};
  const resolvedStart = start == null ? total : clamp(start);
  const resolvedEnd = end == null ? resolvedStart : clamp(end);
  const anchor = locate(Math.min(resolvedStart, resolvedEnd));
  const focus = locate(Math.max(resolvedStart, resolvedEnd));
  const range = document.createRange();
  range.setStart(anchor.node, anchor.offset);
  range.setEnd(focus.node, focus.offset);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  return {{
    kind: 'contenteditable',
    selection: String(selection),
    textLength: total,
  }};
}})()
""".strip()
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    payload = {"endpoint": base, "target": target, "result": _extract_remote_value(result), "selector": selector}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def wait_url(
    target_selector: str,
    needle: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    timeout: float = 10.0,
    interval_ms: int = 250,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _runtime_evaluate(target, "location.href", await_promise=True, return_by_value=True)
        href = _extract_remote_value(result)
        if needle in str(href):
            payload = {"endpoint": base, "target": target, "url": href, "matched": needle}
            if session_name:
                payload["session"] = _normalize_session_name(session_name)
            return payload
        time.sleep(max(interval_ms, 50) / 1000)
    raise DctlError("TIMEOUT", f"Timed out waiting for URL containing '{needle}'.")


def wait_selector(
    target_selector: str,
    selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    timeout: float = 10.0,
    interval_ms: int = 250,
    visible: bool = False,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    expression = f"""
(() => {{
  const node = document.querySelector({json.dumps(selector)});
  if (!node) return null;
  if (!{json.dumps(visible)}) {{
    return {{tag: node.tagName ?? null, text: node.innerText ?? node.textContent ?? ""}};
  }}
  const style = window.getComputedStyle(node);
  const rect = node.getBoundingClientRect();
  const shown = style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  return shown ? {{tag: node.tagName ?? null, text: node.innerText ?? node.textContent ?? ""}} : null;
}})()
""".strip()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
        payload = _extract_remote_value(result)
        if payload:
            result = {"endpoint": base, "target": target, "selector": selector, "result": payload}
            if session_name:
                result["session"] = _normalize_session_name(session_name)
            return result
        time.sleep(max(interval_ms, 50) / 1000)
    raise DctlError("TIMEOUT", f"Timed out waiting for selector '{selector}'.")


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
    session_name: str | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
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
    result = {
        "endpoint": base,
        "target": target,
        "selector": selector,
        "x": coords["x"],
        "y": coords["y"],
    }
    if session_name:
        result["session"] = _normalize_session_name(session_name)
    return result


def type_text(
    target_selector: str,
    text_value: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    selector: str | None = None,
    clear: bool = False,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    _send_command(target, "Page.bringToFront")
    if selector:
        expression = f"""
(() => {{
  let node = document.querySelector({json.dumps(selector)});
  if (!node) return false;
  const ariaLabel = node.getAttribute && node.getAttribute('aria-label');
  if (node.tagName === 'TEXTAREA' && ariaLabel) {{
    const preferred = document.querySelector(
      `[aria-label="${{ariaLabel.replace(/"/g, '&quot;')}}"][contenteditable="true"]`
    );
    if (preferred) node = preferred;
  }}
  node.focus();
  if ({json.dumps(clear)}) {{
    if ('value' in node) {{
      node.value = '';
      if (typeof node.dispatchEvent === 'function') {{
        node.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'deleteContentBackward', data: null }}));
      }}
    }} else if (node.isContentEditable) {{
      node.innerHTML = '';
      if (typeof node.dispatchEvent === 'function') {{
        node.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'deleteContentBackward', data: null }}));
      }}
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
  if ('value' in node) {
    node.value = '';
    if (typeof node.dispatchEvent === 'function') {
      node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward', data: null }));
    }
  } else if (node.isContentEditable) {
    node.innerHTML = '';
    if (typeof node.dispatchEvent === 'function') {
      node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward', data: null }));
    }
  }
  return true;
})()
""".strip(),
        )
    _send_command(target, "Input.insertText", {"text": text_value})
    result = {"endpoint": base, "target": target, "selector": selector, "text": text_value}
    if session_name:
        result["session"] = _normalize_session_name(session_name)
    return result


def press_key(
    target_selector: str,
    combo: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    _send_command(target, "Page.bringToFront")
    spec = parse_key_combo(combo)
    commands: list[str] = []
    if spec.key == "Enter" and spec.modifiers == 0:
        commands = ["insertParagraphSeparator"]
    elif spec.key == "Enter" and spec.modifiers & 8:
        commands = ["insertLineBreak"]
    key_down = {
        "type": "keyDown",
        "modifiers": spec.modifiers,
        "key": spec.key,
        "code": spec.code,
        "windowsVirtualKeyCode": spec.key_code,
        "nativeVirtualKeyCode": spec.key_code,
    }
    if commands:
        key_down["commands"] = commands
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
    result = {
        "endpoint": base,
        "target": target,
        "combo": combo,
        "modifiers": spec.modifiers,
        "key": spec.key,
        "code": spec.code,
    }
    if session_name:
        result["session"] = _normalize_session_name(session_name)
    return result


def send_command(
    target_selector: str,
    method: str,
    params_json: str | None = None,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    params = json.loads(params_json) if params_json else {}
    result = _send_command(target, method, params)
    payload = {"endpoint": base, "target": target, "method": method, "params": params, "result": result}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def batch(
    target_selector: str,
    operations_json: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    try:
        operations = json.loads(operations_json)
    except json.JSONDecodeError as exc:
        raise DctlError("INVALID_SELECTOR", "Batch operations must be valid JSON.") from exc
    if not isinstance(operations, list):
        raise DctlError("INVALID_SELECTOR", "Batch operations must be a JSON array.")
    results = []
    for operation in operations:
        if not isinstance(operation, dict) or "op" not in operation:
            raise DctlError("INVALID_SELECTOR", "Each batch operation must include an `op` field.")
        op = str(operation["op"])
        if op == "activate":
            results.append(activate_target(target_selector, endpoint=endpoint, port=port, session_name=session_name))
        elif op == "click":
            results.append(click(target_selector, str(operation["selector"]), endpoint=endpoint, port=port, session_name=session_name))
        elif op == "type":
            results.append(
                type_text(
                    target_selector,
                    str(operation.get("text", "")),
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    selector=operation.get("selector"),
                    clear=bool(operation.get("clear", False)),
                )
            )
        elif op == "press":
            results.append(press_key(target_selector, str(operation["combo"]), endpoint=endpoint, port=port, session_name=session_name))
        elif op == "eval":
            results.append(evaluate(target_selector, str(operation["expression"]), endpoint=endpoint, port=port, session_name=session_name))
        elif op == "wait-selector":
            results.append(
                wait_selector(
                    target_selector,
                    str(operation["selector"]),
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    timeout=float(operation.get("timeout", 10.0)),
                    interval_ms=int(operation.get("interval", 250)),
                    visible=bool(operation.get("visible", False)),
                )
            )
        elif op == "wait-url":
            results.append(
                wait_url(
                    target_selector,
                    str(operation["needle"]),
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    timeout=float(operation.get("timeout", 10.0)),
                    interval_ms=int(operation.get("interval", 250)),
                )
            )
        elif op == "snapshot":
            results.append(
                snapshot(
                    target_selector,
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    text_limit=int(operation.get("text_limit", 4000)),
                )
            )
        elif op == "text":
            results.append(text(target_selector, endpoint=endpoint, port=port, session_name=session_name, selector=operation.get("selector")))
        elif op == "selection":
            results.append(selection(target_selector, endpoint=endpoint, port=port, session_name=session_name))
        elif op == "caret":
            results.append(
                caret(
                    target_selector,
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    selector=operation.get("selector"),
                    start=operation.get("start"),
                    end=operation.get("end"),
                )
            )
        else:
            raise DctlError("INVALID_SELECTOR", f"Unsupported browser batch op '{op}'.")
    payload = {
        "endpoint": normalize_endpoint(endpoint, port, session_name=session_name),
        "target_selector": target_selector,
        "results": results,
    }
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload
