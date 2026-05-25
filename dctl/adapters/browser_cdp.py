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
import sys
import tempfile
import time
from typing import Any
from urllib import parse, request

import websockets

from dctl.errors import DctlError


BROWSER_EXECUTABLE_NAMES = {
    "brave": {"brave", "brave-browser", "brave-browser-stable", "brave.exe"},
    "chrome": {"google-chrome", "google-chrome-stable", "chrome", "chrome.exe", "google chrome"},
    "chromium": {"chromium", "chromium-browser", "chromium.exe"},
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PreparedPageTarget = tuple[str, dict[str, Any]]


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


def _read_session_record_optional(name: str) -> dict[str, Any] | None:
    try:
        return _read_session_record(name)
    except DctlError as exc:
        if exc.code == "ELEMENT_NOT_FOUND":
            return None
        raise


def _session_active_target_id(name: str | None) -> str | None:
    if not name:
        return None
    record = _read_session_record_optional(name)
    if not record:
        return None
    target_id = record.get("active_target_id")
    return str(target_id) if isinstance(target_id, str) and target_id.strip() else None


def _set_session_active_target(name: str | None, target_id: str | None) -> None:
    if not name:
        return
    record = _read_session_record_optional(name)
    if not record:
        return
    updated = {
        **record,
        "active_target_id": target_id,
        "last_active_target_at": _now_iso() if target_id else record.get("last_active_target_at"),
    }
    _write_session_record(name, updated)


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
    for token in cmdline.replace("\0", " ").split():
        if token.startswith("--remote-debugging-port="):
            value = token.split("=", 1)[1].strip()
            if value.isdigit():
                return int(value)
    return None


def _classify_browser_app(command: str) -> str | None:
    # Handle paths with spaces (macOS .app bundles) and plain executables.
    # Check if any known browser name appears as a path component or filename.
    lower = command.lower()
    for app, aliases in BROWSER_EXECUTABLE_NAMES.items():
        for alias in aliases:
            if alias in lower:
                return app
    return None


def _discover_browser_processes(proc_root: str = "/proc") -> list[dict[str, Any]]:
    if proc_root != "/proc":
        return _discover_browser_processes_linux(proc_root)
    if sys.platform == "linux":
        return _discover_browser_processes_linux(proc_root)
    if sys.platform == "darwin":
        return _discover_browser_processes_macos()
    if sys.platform == "win32":
        return _discover_browser_processes_windows()
    return []


def _discover_browser_processes_linux(proc_root: str = "/proc") -> list[dict[str, Any]]:
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


def _discover_browser_processes_macos() -> list[dict[str, Any]]:
    try:
        output = subprocess.check_output(["ps", "aux"], text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return []
    items: list[dict[str, Any]] = []
    for line in output.strip().splitlines()[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        pid_str, command = parts[1], parts[10]
        app = _classify_browser_app(command)
        if not app:
            continue
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        items.append({
            "pid": pid,
            "command": command,
            "app": app,
            "debug_port": _parse_debug_port(command),
            "cmdline": command.split(),
        })
    return items


def _discover_browser_processes_windows() -> list[dict[str, Any]]:
    try:
        output = subprocess.check_output(
            ["wmic", "process", "get", "ProcessId,CommandLine", "/format:list"],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return _discover_browser_processes_windows_tasklist()
    items: list[dict[str, Any]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            if current.get("ProcessId") and current.get("CommandLine"):
                cmd = current["CommandLine"]
                app = _classify_browser_app(cmd)
                if app:
                    try:
                        pid = int(current["ProcessId"])
                    except ValueError:
                        current = {}
                        continue
                    items.append({
                        "pid": pid,
                        "command": cmd,
                        "app": app,
                        "debug_port": _parse_debug_port(cmd),
                        "cmdline": cmd.split(),
                    })
            current = {}
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    return items


def _discover_browser_processes_windows_tasklist() -> list[dict[str, Any]]:
    try:
        output = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return []
    items: list[dict[str, Any]] = []
    all_names: set[str] = set()
    for names in BROWSER_EXECUTABLE_NAMES.values():
        all_names.update(n.lower() for n in names)
    for line in output.strip().splitlines():
        parts = line.strip('"').split('","')
        if len(parts) < 2:
            continue
        name = parts[0].lower()
        exe_name = Path(name).stem.lower() if "\\" in name else name
        if not any(alias in exe_name for alias in all_names):
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        app = _classify_browser_app(name)
        items.append({"pid": pid, "command": name, "app": app, "debug_port": None, "cmdline": [name]})
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
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        "chrome": [
            shutil.which("google-chrome-stable") or "",
            shutil.which("google-chrome") or "",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "chromium": [
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            r"C:\Program Files\Chromium\Application\chrome.exe",
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
                    "active_target_id": existing_record.get("active_target_id") if existing_record else None,
                    "last_active_target_at": existing_record.get("last_active_target_at") if existing_record else None,
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
    if session_name and isinstance(target, dict) and isinstance(target.get("id"), str):
        _set_session_active_target(session_name, str(target["id"]))
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
    if session_name and isinstance(resolved.get("id"), str):
        _set_session_active_target(session_name, str(resolved["id"]))
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
    if session_name and _session_active_target_id(session_name) == resolved.get("id"):
        _set_session_active_target(session_name, None)
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
    pages = [item for item in items if item.get("type") == "page"]
    exact = [item for item in items if target in {item.get("id"), item.get("title"), item.get("url")}]
    if len(exact) == 1:
        return exact[0]
    partial = [
        item
        for item in items
        if target == "active" or target.lower() in (item.get("title", "") + " " + item.get("url", "")).lower()
    ]
    if target == "active":
        if not pages:
            raise DctlError("ELEMENT_NOT_FOUND", "No page targets are available.")
        preferred_target_id = _session_active_target_id(session_name)
        if preferred_target_id:
            for item in pages:
                if item.get("id") == preferred_target_id:
                    return item
        if len(pages) > 1:
            raise DctlError(
                "MULTIPLE_MATCHES",
                "`active` is ambiguous because multiple page targets are available.",
                suggestion="Select a tab by id/title/url (see `dctl browser tabs`) or run `dctl browser activate <target>` to pin one.",
                details={"candidates": pages[:20], "preferredTargetId": preferred_target_id},
            )
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


def _target_score(item: dict[str, Any], preferred_target_id: str | None) -> int:
    score = 0
    target_type = str(item.get("type") or "")
    title = str(item.get("title") or "")
    url = str(item.get("url") or "")
    if target_type == "page":
        score += 10
    else:
        score -= 100
    if preferred_target_id and item.get("id") == preferred_target_id:
        score += 100
    if url.startswith("https://"):
        score += 25
    elif url.startswith("http://"):
        score += 15
    elif url.startswith("chrome://"):
        score -= 35
    elif url.startswith("chrome-extension://"):
        score -= 20
    if "omnibox popup" in title.lower():
        score -= 40
    if title.strip():
        score += 5
    return score


def tabs(
    endpoint: str | None = None,
    port: int | None = None,
    include_non_pages: bool = False,
    url_contains: str | None = None,
    title_contains: str | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    payload = list_targets(endpoint=endpoint, port=port, session_name=session_name)
    raw_items = payload["items"] if include_non_pages else _page_items(payload["items"])
    if url_contains:
        url_needle = url_contains.strip().lower()
        raw_items = [item for item in raw_items if url_needle in str(item.get("url") or "").lower()]
    if title_contains:
        title_needle = title_contains.strip().lower()
        raw_items = [item for item in raw_items if title_needle in str(item.get("title") or "").lower()]
    preferred_target_id = _session_active_target_id(session_name)
    items: list[dict[str, Any]] = []
    for item in raw_items:
        enriched = {
            **item,
            "isPreferred": bool(preferred_target_id and item.get("id") == preferred_target_id),
            "targetScore": _target_score(item, preferred_target_id),
        }
        items.append(enriched)
    items.sort(key=lambda item: int(item.get("targetScore", 0)), reverse=True)
    result = {"endpoint": payload["endpoint"], "items": items, "recommendedTargetId": items[0].get("id") if items else None}
    if preferred_target_id:
        result["preferredTargetId"] = preferred_target_id
    if url_contains:
        result["urlContains"] = url_contains
    if title_contains:
        result["titleContains"] = title_contains
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
    _prepared_target: PreparedPageTarget | None = None,
) -> tuple[str, dict[str, Any]]:
    if _prepared_target is not None:
        base, target = _prepared_target
    else:
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
    return_by_value: bool = False,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    _send_command(target, "Page.enable")
    result = _runtime_evaluate(target, expression, await_promise=await_promise, return_by_value=return_by_value)
    payload = {
        "endpoint": base,
        "target": target,
        "result": _extract_remote_value(result),
        "meta": {"returnByValue": bool(return_by_value)},
    }
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def _snapshot_issue(code: str, message: str, **fields: Any) -> dict[str, Any]:
    issue = {"code": code, "message": message}
    issue.update(fields)
    return issue


def _snapshot_quality(
    result: dict[str, Any],
    *,
    text_limit: int,
    min_text: int,
    max_text: int | None,
) -> dict[str, Any]:
    visible_text = str(result.get("visibleText") or "")
    text_length_raw = result.get("textLength")
    text_length = int(text_length_raw) if isinstance(text_length_raw, int) else len(visible_text)
    headings_count = len(result.get("headings", [])) if isinstance(result.get("headings"), list) else 0
    landmarks_count = len(result.get("landmarks", [])) if isinstance(result.get("landmarks"), list) else 0
    interactions_count = len(result.get("interactions", [])) if isinstance(result.get("interactions"), list) else 0
    blocks_count = len(result.get("contentBlocks", [])) if isinstance(result.get("contentBlocks"), list) else 0
    latex_count = len(result.get("latex", [])) if isinstance(result.get("latex"), list) else 0
    visuals_count = len(result.get("visuals", [])) if isinstance(result.get("visuals"), list) else 0
    extraction_stats = result.get("extractionStats") if isinstance(result.get("extractionStats"), dict) else {}
    truncated_flag = bool(result.get("truncated")) or (text_length > len(visible_text) and len(visible_text) >= text_limit)
    issues: list[dict[str, Any]] = []
    ready_state = str(result.get("readyState") or "")

    if ready_state and ready_state != "complete":
        issues.append(
            _snapshot_issue(
                "PAGE_NOT_READY",
                f"Document readyState is '{ready_state}', extraction may be incomplete.",
                ready_state=ready_state,
            )
        )
    if text_length == 0 and interactions_count == 0 and visuals_count == 0:
        issues.append(
            _snapshot_issue(
                "EMPTY_SURFACE",
                "No visible text, interactive elements, or visual structures were extracted from the page.",
            )
        )
    if text_length < min_text and visuals_count == 0:
        issues.append(
            _snapshot_issue(
                "TOO_LITTLE_CONTENT",
                f"Extracted text is too small ({text_length} chars, expected at least {min_text}).",
                observed=text_length,
                minimum=min_text,
            )
        )
    if max_text is not None and text_length > max_text:
        issues.append(
            _snapshot_issue(
                "TOO_MUCH_CONTENT",
                f"Extracted text is too large ({text_length} chars, expected at most {max_text}).",
                observed=text_length,
                maximum=max_text,
            )
        )
    if truncated_flag:
        issues.append(
            _snapshot_issue(
                "TRUNCATED_CONTENT",
                "Visible text was truncated by text-limit, so the snapshot is incomplete.",
                text_limit=text_limit,
                observed=len(visible_text),
                full_text_length=text_length,
            )
        )
    if text_length > 0 and headings_count == 0 and landmarks_count == 0 and blocks_count == 0 and visuals_count == 0:
        issues.append(
            _snapshot_issue(
                "WEAK_STRUCTURE",
                "No headings, landmarks, or content blocks were extracted from visible content.",
            )
        )
    if text_length > 0 and blocks_count == 0 and visuals_count == 0:
        issues.append(
            _snapshot_issue(
                "NO_CONTENT_BLOCKS",
                "No paragraph/list/article content blocks were extracted from visible content.",
                observed_blocks=blocks_count,
            )
        )
    if interactions_count >= 25 and blocks_count <= 1:
        issues.append(
            _snapshot_issue(
                "INTERACTION_HEAVY_SURFACE",
                "Extraction is dominated by interactive controls, which often means toolbars/chrome overshadow page content.",
                interactions=interactions_count,
                content_blocks=blocks_count,
            )
        )
    if latex_count > 0:
        parseable_latex = [
            item
            for item in result.get("latex", [])
            if isinstance(item, dict) and (item.get("source") or item.get("renderedText"))
        ]
        if not parseable_latex:
            issues.append(
                _snapshot_issue(
                    "LATEX_UNPARSEABLE",
                    "Math content was detected but no parseable LaTeX/MathML payload was extracted.",
                )
            )
    for category, stats in extraction_stats.items():
        if not isinstance(stats, dict):
            continue
        total = int(stats.get("totalVisible", 0)) if isinstance(stats.get("totalVisible"), int) else 0
        returned = int(stats.get("returned", 0)) if isinstance(stats.get("returned"), int) else 0
        truncated = bool(stats.get("truncated"))
        if truncated and total > returned:
            issues.append(
                _snapshot_issue(
                    "CATEGORY_TRUNCATION",
                    f"{category} extraction was truncated ({returned}/{total} items returned).",
                    category=category,
                    total=total,
                    returned=returned,
                )
            )
    return {
        "ok": not issues,
        "issues": issues,
        "metrics": {
            "textLength": text_length,
            "visibleTextLength": len(visible_text),
            "textLimit": text_limit,
            "minText": min_text,
            "maxText": max_text,
            "truncated": truncated_flag,
            "headings": headings_count,
            "landmarks": landmarks_count,
            "interactions": interactions_count,
            "contentBlocks": blocks_count,
            "latex": latex_count,
            "visuals": visuals_count,
            "extractionStats": extraction_stats,
        },
    }


def _raise_if_snapshot_quality_fails(quality: dict[str, Any]) -> None:
    issues = quality.get("issues")
    if not isinstance(issues, list) or not issues:
        return
    raise DctlError(
        "BACKEND_FAILURE",
        "Browser snapshot quality checks failed.",
        suggestion="Increase extraction limits or inspect the page with `dctl browser dom` / `dctl browser ax`.",
        details={"quality": quality},
    )


def snapshot(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    text_limit: int = 4000,
    max_items: int = 120,
    min_text: int = 120,
    max_text: int | None = None,
    strict: bool = False,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    if text_limit < 1:
        raise DctlError("INVALID_SELECTOR", "Snapshot text-limit must be >= 1.")
    if max_items < 1:
        raise DctlError("INVALID_SELECTOR", "Snapshot max-items must be >= 1.")
    if min_text < 0:
        raise DctlError("INVALID_SELECTOR", "Snapshot min-text must be >= 0.")
    if max_text is not None and max_text < min_text:
        raise DctlError("INVALID_SELECTOR", "Snapshot max-text must be >= min-text when provided.")
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    max_items_value = int(max_items)
    text_limit_value = int(text_limit)
    expression = f"""
(() => {{
  const maxItems = {max_items_value};
  const textLimit = {text_limit_value};
  const compact = (value, limit = 280) => {{
    if (typeof value !== 'string') return "";
    return value.replace(/\\s+/g, ' ').trim().slice(0, limit);
  }};
  const attr = (node, name) => {{
    if (!node || typeof node.getAttribute !== 'function') return null;
    const value = node.getAttribute(name);
    return value == null ? null : String(value);
  }};
  const isVisible = (node) => {{
    if (!node || node.nodeType !== 1) return false;
    const style = window.getComputedStyle(node);
    if (!style) return false;
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    if (Number(style.opacity || '1') === 0) return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }};
  const dedupePush = (items, seen, item) => {{
    const key = JSON.stringify(item);
    if (!key || seen.has(key)) return;
    seen.add(key);
    items.push(item);
  }};
  const collectVisible = (selector, mapper) => {{
    const items = [];
    const seen = new Set();
    let totalVisible = 0;
    for (const node of document.querySelectorAll(selector)) {{
      if (!isVisible(node)) continue;
      totalVisible += 1;
      const mapped = mapper(node);
      if (!mapped) continue;
      if (items.length >= maxItems) continue;
      dedupePush(items, seen, mapped);
    }}
    return {{
      items,
      stats: {{
        totalVisible,
        returned: items.length,
        truncated: totalVisible > items.length,
      }},
    }};
  }};
  const bodyText = document.body ? (document.body.innerText ?? document.body.textContent ?? "") : "";
  const normalizedText = bodyText.replace(/\\r/g, '').replace(/\\n{{3,}}/g, '\\n\\n').trim();
  const textLength = normalizedText.length;
  const visibleText = normalizedText.slice(0, textLimit);
  const active = document.activeElement;
  const selection = window.getSelection ? String(window.getSelection()) : "";
  const headingData = collectVisible(
    'h1,h2,h3,h4,h5,h6,[role="heading"]',
    (node) => {{
      const levelAttr = attr(node, 'aria-level');
      const headingLevel = levelAttr ? Number(levelAttr) : Number((node.tagName || '').replace('H', ''));
      return {{
        tag: node.tagName ? node.tagName.toLowerCase() : null,
        level: Number.isFinite(headingLevel) ? headingLevel : null,
        text: compact(node.innerText ?? node.textContent ?? "", 200) || null,
      }};
    }}
  );
  const headings = headingData.items;
  const landmarkData = collectVisible(
    'main,header,footer,nav,aside,form,[role="main"],[role="navigation"],[role="region"],[role="complementary"],[role="contentinfo"],[role="banner"],[role="search"],[role="form"]',
    (node) => {{
      return {{
        tag: node.tagName ? node.tagName.toLowerCase() : null,
        role: attr(node, 'role'),
        label: compact(attr(node, 'aria-label') || attr(node, 'aria-labelledby') || '', 120) || null,
      }};
    }}
  );
  const landmarks = landmarkData.items;
  const interactionData = collectVisible(
    'button,a[href],input,textarea,select,[role="button"],[role="link"],[role="tab"],[role="menuitem"],[role="checkbox"],[role="radio"],[role="combobox"]',
    (node) => {{
      const text = compact(node.innerText ?? node.textContent ?? "", 160);
      const label = compact(attr(node, 'aria-label') || attr(node, 'name') || attr(node, 'title') || text, 160);
      return {{
        tag: node.tagName ? node.tagName.toLowerCase() : null,
        role: attr(node, 'role'),
        type: attr(node, 'type'),
        label: label || null,
        disabled: !!node.disabled || attr(node, 'aria-disabled') === 'true',
      }};
    }}
  );
  const interactions = interactionData.items;
  const contentBlockData = collectVisible(
    'article,section,p,li,pre,code,blockquote,figcaption,[role="article"],[role="listitem"]',
    (node) => {{
      const text = compact(node.innerText ?? node.textContent ?? "", 220);
      if (!text) return null;
      return {{
        tag: node.tagName ? node.tagName.toLowerCase() : null,
        text,
      }};
    }}
  );
  const contentBlocks = contentBlockData.items;
  const latex = [];
  const latexSeen = new Set();
  let latexTotalDetected = 0;
  const pushLatexEntry = (entry) => {{
    if (!entry) return;
    latexTotalDetected += 1;
    if (latex.length >= maxItems) return;
    dedupePush(latex, latexSeen, entry);
  }};
  const pushLatex = (node) => {{
    if (!node) return;
    let source = '';
    if (node.matches && node.matches("script[type^='math/tex']")) {{
      source = node.textContent ?? '';
    }}
    if (!source && typeof node.querySelector === 'function') {{
      const annotation = node.querySelector("annotation[encoding*='tex'],annotation[encoding*='latex'],script[type^='math/tex']");
      if (annotation) source = annotation.textContent ?? '';
    }}
    const renderedText = compact(node.innerText ?? node.textContent ?? "", 400);
    source = compact(source, 400);
    if (!source && !renderedText) return;
    const format = node.matches && node.matches('math,annotation')
      ? 'mathml'
      : node.matches && node.matches('.katex,.katex-display')
        ? 'katex'
        : node.matches && node.matches('.MathJax,mjx-container')
          ? 'mathjax'
          : node.matches && node.matches("script[type^='math/tex']")
            ? 'latex-source'
            : 'unknown';
    pushLatexEntry({{
      format,
      source: source || null,
      renderedText: renderedText || null,
      sourceOrigin: 'dom-node',
    }});
  }};
  for (const node of document.querySelectorAll('math,mjx-container,.MathJax,.katex,.katex-display,[role="math"]')) {{
    if (!isVisible(node)) continue;
    pushLatex(node);
    if (latex.length >= maxItems) break;
  }}
  if (latex.length < maxItems) {{
    for (const node of document.querySelectorAll("script[type^='math/tex'],annotation[encoding*='tex'],annotation[encoding*='latex']")) {{
      pushLatex(node);
      if (latex.length >= maxItems) break;
    }}
  }}
  const pushDelimitedLatex = (format, pattern) => {{
    let match;
    let guard = 0;
    while ((match = pattern.exec(normalizedText)) !== null) {{
      const source = compact(match[1] ?? "", 400);
      if (!source) continue;
      pushLatexEntry({{
        format,
        source,
        renderedText: null,
        sourceOrigin: 'text-delimiter',
      }});
      guard += 1;
      if (guard >= maxItems * 5) break;
    }}
  }};
  pushDelimitedLatex('latex-block-dollar', /\\$\\$([\\s\\S]{{1,700}}?)\\$\\$/g);
  pushDelimitedLatex('latex-inline-paren', /\\\\\\(([\\s\\S]{{1,400}}?)\\\\\\)/g);
  pushDelimitedLatex('latex-block-bracket', /\\\\\\[([\\s\\S]{{1,700}}?)\\\\\\]/g);
  const visuals = [];
  const visualsSeen = new Set();
  let visualsTotalDetected = 0;
  const pushVisualEntry = (entry) => {{
    if (!entry) return;
    visualsTotalDetected += 1;
    if (visuals.length >= maxItems) return;
    dedupePush(visuals, visualsSeen, entry);
  }};
  const countSvg = (node, selector) => {{
    if (!node || typeof node.querySelectorAll !== 'function') return 0;
    return node.querySelectorAll(selector).length;
  }};
  for (const node of document.querySelectorAll('svg,canvas,img,object[type="image/svg+xml"],embed[type="image/svg+xml"]')) {{
    if (!isVisible(node)) continue;
    const tag = node.tagName ? node.tagName.toLowerCase() : null;
    const ariaLabel = compact(attr(node, 'aria-label') || '', 180);
    const title = compact(attr(node, 'title') || '', 180);
    const alt = compact(attr(node, 'alt') || '', 180);
    const role = attr(node, 'role');
    const source = compact(attr(node, 'src') || attr(node, 'data') || '', 280);
    const widthRaw = Number(node.clientWidth || attr(node, 'width') || 0);
    const heightRaw = Number(node.clientHeight || attr(node, 'height') || 0);
    let text = '';
    let shapeCounts = null;
    let kind = 'image';
    if (tag === 'svg') {{
      kind = 'svg';
      const titleNode = node.querySelector('title');
      const descNode = node.querySelector('desc');
      const textNodes = Array.from(node.querySelectorAll('text')).map((entry) => compact(entry.textContent ?? "", 120)).filter(Boolean);
      text = compact([titleNode?.textContent ?? "", descNode?.textContent ?? "", textNodes.join(' ')].join(' '), 260);
      shapeCounts = {{
        path: countSvg(node, 'path'),
        rect: countSvg(node, 'rect'),
        circle: countSvg(node, 'circle'),
        line: countSvg(node, 'line'),
        polyline: countSvg(node, 'polyline'),
        polygon: countSvg(node, 'polygon'),
        text: countSvg(node, 'text'),
      }};
    }} else if (tag === 'canvas') {{
      kind = 'canvas';
    }} else if (source && source.toLowerCase().includes('.svg')) {{
      kind = 'svg-resource';
    }}
    pushVisualEntry({{
      kind,
      tag,
      role: role || null,
      label: ariaLabel || title || alt || null,
      text: text || null,
      source: source || null,
      viewBox: tag === 'svg' ? (attr(node, 'viewBox') || null) : null,
      width: Number.isFinite(widthRaw) && widthRaw > 0 ? widthRaw : null,
      height: Number.isFinite(heightRaw) && heightRaw > 0 ? heightRaw : null,
      shapeCounts,
    }});
  }}
  const extractionStats = {{
    headings: headingData.stats,
    landmarks: landmarkData.stats,
    interactions: interactionData.stats,
    contentBlocks: contentBlockData.stats,
    latex: {{
      totalVisible: latexTotalDetected,
      returned: latex.length,
      truncated: latexTotalDetected > latex.length,
    }},
    visuals: {{
      totalVisible: visualsTotalDetected,
      returned: visuals.length,
      truncated: visualsTotalDetected > visuals.length,
    }},
  }};
  return {{
    title: document.title,
    url: location.href,
    readyState: document.readyState,
    extractionVersion: 3,
    activeElement: active ? {{
      tag: active.tagName ?? null,
      id: active.id || null,
      name: active.getAttribute ? active.getAttribute('name') : null,
      ariaLabel: active.getAttribute ? active.getAttribute('aria-label') : null,
      value: 'value' in active ? active.value : null
    }} : null,
    selection,
    visibleText,
    textLength,
    truncated: textLength > visibleText.length,
    frameCount: window.frames.length,
    headings,
    landmarks,
    interactions,
    contentBlocks,
    latex,
    visuals,
    extractionStats
  }};
}})()
""".strip()
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    extracted = _extract_remote_value(result)
    if not isinstance(extracted, dict):
        raise DctlError("BACKEND_FAILURE", "Browser snapshot returned an unsupported payload.")
    quality = _snapshot_quality(extracted, text_limit=text_limit, min_text=min_text, max_text=max_text)
    extracted["quality"] = quality
    if strict:
        _raise_if_snapshot_quality_fails(quality)
    payload = {"endpoint": base, "target": target, "result": extracted}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def selector_audit(
    target_selector: str,
    selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    sample_limit: int = 20,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    if sample_limit < 1:
        raise DctlError("INVALID_SELECTOR", "Selector sample-limit must be >= 1.")
    if sample_limit > 200:
        raise DctlError("INVALID_SELECTOR", "Selector sample-limit must be <= 200.")
    expression = f"""
(() => {{
  const selector = {json.dumps(selector)};
  const sampleLimit = {int(sample_limit)};
  const compact = (value, limit = 200) => {{
    if (typeof value !== "string") return "";
    return value.replace(/\\s+/g, " ").trim().slice(0, limit);
  }};
  const nodes = Array.from(document.querySelectorAll(selector));
  const samples = [];
  let visibleCount = 0;
  let disabledCount = 0;
  let editableCount = 0;
  for (const node of nodes) {{
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    const visible = !!style && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || "1") !== 0 && rect.width > 0 && rect.height > 0;
    if (visible) visibleCount += 1;
    const disabled = !!node.disabled || (node.getAttribute && node.getAttribute("aria-disabled") === "true");
    if (disabled) disabledCount += 1;
    const editable = !!node.isContentEditable || (node.getAttribute && node.getAttribute("contenteditable") === "true");
    if (editable) editableCount += 1;
    if (samples.length >= sampleLimit) continue;
    const text = compact(node.innerText ?? node.textContent ?? "", 160);
    const label = compact(
      (node.getAttribute && (node.getAttribute("aria-label") || node.getAttribute("name") || node.getAttribute("title"))) || text,
      160
    );
    samples.push({{
      tag: node.tagName ? node.tagName.toLowerCase() : null,
      id: node.id || null,
      role: node.getAttribute ? (node.getAttribute("role") || null) : null,
      type: node.getAttribute ? (node.getAttribute("type") || null) : null,
      label: label || null,
      text: text || null,
      visible,
      disabled,
      editable,
      bounds: {{
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      }},
    }});
  }}
  return {{
    selector,
    matchCount: nodes.length,
    visibleCount,
    disabledCount,
    editableCount,
    unique: nodes.length === 1,
    samples,
    samplesTruncated: nodes.length > samples.length,
    sampleLimit,
  }};
}})()
""".strip()
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    payload = {"endpoint": base, "target": target, "result": _extract_remote_value(result)}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def actions(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    sample_limit: int = 60,
    query: str | None = None,
    role: str | None = None,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    if sample_limit < 1:
        raise DctlError("INVALID_SELECTOR", "Actions sample-limit must be >= 1.")
    if sample_limit > 500:
        raise DctlError("INVALID_SELECTOR", "Actions sample-limit must be <= 500.")
    query_json = json.dumps(query.strip().lower() if query else "")
    role_json = json.dumps(role.strip().lower() if role else "")
    expression = f"""
(() => {{
  const sampleLimit = {int(sample_limit)};
  const queryText = {query_json};
  const roleFilter = {role_json};
  const normalize = (value, limit = 200) => {{
    if (typeof value !== "string") return "";
    return value.replace(/\\s+/g, " ").trim().slice(0, limit);
  }};
  const cssEscape = (value) => {{
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_\\-]/g, "\\\\$&");
  }};
  const implicitRole = (node) => {{
    const tag = (node.tagName || "").toLowerCase();
    if (tag === "a" && node.getAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "summary") return "button";
    if (tag === "input") {{
      const type = (node.getAttribute("type") || "").toLowerCase();
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "button" || type === "submit" || type === "reset") return "button";
    }}
    return null;
  }};
  const selectorHint = (node) => {{
    const tag = (node.tagName || "").toLowerCase() || "*";
    const id = node.id ? String(node.id) : "";
    if (id) return `#${{cssEscape(id)}}`;
    const name = node.getAttribute ? (node.getAttribute("name") || "") : "";
    if (name) return `${{tag}}[name="${{name.replace(/"/g, '\\\\\\"')}}"]`;
    const aria = node.getAttribute ? (node.getAttribute("aria-label") || "") : "";
    if (aria) return `${{tag}}[aria-label="${{aria.replace(/"/g, '\\\\\\"')}}"]`;
    return tag;
  }};
  const nodes = Array.from(
    document.querySelectorAll(
      'button,a[href],input:not([type]),input[type="button"],input[type="submit"],input[type="reset"],input[type="checkbox"],input[type="radio"],label,[role="button"],[role="link"],[role="menuitem"],[role="option"],[role="tab"],summary'
    )
  );
  const items = [];
  let totalVisible = 0;
  let truncated = false;
  for (const node of nodes) {{
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    const visible = !!style && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || "1") !== 0 && rect.width > 0 && rect.height > 0;
    if (!visible) continue;
    totalVisible += 1;
    const text = normalize(node.innerText ?? node.textContent ?? "", 180);
    const valueText = typeof node.value === "string" ? normalize(node.value, 180) : "";
    const label = normalize(
      (node.getAttribute && (node.getAttribute("aria-label") || node.getAttribute("name") || node.getAttribute("title"))) || valueText || text,
      180
    );
    const roleValue = ((node.getAttribute && node.getAttribute("role")) || implicitRole(node) || "").toLowerCase();
    if (roleFilter && roleValue !== roleFilter) continue;
    const haystack = `${{label}} ${{text}}`.toLowerCase();
    if (queryText && !haystack.includes(queryText)) continue;
    const disabled = !!node.disabled || (node.getAttribute && node.getAttribute("aria-disabled") === "true");
    const editable = !!node.isContentEditable || (node.getAttribute && node.getAttribute("contenteditable") === "true");
    items.push({{
      actionId: items.length,
      tag: node.tagName ? node.tagName.toLowerCase() : null,
      role: roleValue || null,
      type: node.getAttribute ? (node.getAttribute("type") || null) : null,
      label: label || null,
      text: text || null,
      disabled,
      editable,
      selectorHint: selectorHint(node),
      bounds: {{
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      }},
    }});
    if (items.length >= sampleLimit) {{
      truncated = true;
      break;
    }}
  }}
  return {{
    query: queryText || null,
    role: roleFilter || null,
    totalVisible,
    returned: items.length,
    sampleLimit,
    truncated,
    items,
  }};
}})()
""".strip()
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    payload = {"endpoint": base, "target": target, "result": _extract_remote_value(result)}
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload


def click_action(
    target_selector: str,
    action_id: int,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    query: str | None = None,
    role: str | None = None,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    if action_id < 0:
        raise DctlError("INVALID_SELECTOR", "Action id must be >= 0.")
    query_json = json.dumps(query.strip().lower() if query else "")
    role_json = json.dumps(role.strip().lower() if role else "")
    expression = f"""
(() => {{
  const actionId = {int(action_id)};
  const queryText = {query_json};
  const roleFilter = {role_json};
  const normalize = (value, limit = 200) => {{
    if (typeof value !== "string") return "";
    return value.replace(/\\s+/g, " ").trim().slice(0, limit);
  }};
  const implicitRole = (node) => {{
    const tag = (node.tagName || "").toLowerCase();
    if (tag === "a" && node.getAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "summary") return "button";
    if (tag === "input") {{
      const type = (node.getAttribute("type") || "").toLowerCase();
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "button" || type === "submit" || type === "reset") return "button";
    }}
    return null;
  }};
  const candidates = [];
  const nodes = Array.from(
    document.querySelectorAll(
      'button,a[href],input:not([type]),input[type="button"],input[type="submit"],input[type="reset"],input[type="checkbox"],input[type="radio"],label,[role="button"],[role="link"],[role="menuitem"],[role="option"],[role="tab"],summary'
    )
  );
  for (const node of nodes) {{
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    const visible = !!style && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || "1") !== 0 && rect.width > 0 && rect.height > 0;
    if (!visible) continue;
    const text = normalize(node.innerText ?? node.textContent ?? "", 180);
    const valueText = typeof node.value === "string" ? normalize(node.value, 180) : "";
    const label = normalize(
      (node.getAttribute && (node.getAttribute("aria-label") || node.getAttribute("name") || node.getAttribute("title"))) || valueText || text,
      180
    );
    const roleValue = ((node.getAttribute && node.getAttribute("role")) || implicitRole(node) || "").toLowerCase();
    if (roleFilter && roleValue !== roleFilter) continue;
    const haystack = `${{label}} ${{text}}`.toLowerCase();
    if (queryText && !haystack.includes(queryText)) continue;
    candidates.push({{ node, label, text, role: roleValue || null }});
  }}
  if (actionId < 0 || actionId >= candidates.length) {{
    return {{
      __error: "ACTION_NOT_FOUND",
      actionId,
      available: candidates.length,
      sample: candidates.slice(0, 10).map((entry, idx) => ({{
        actionId: idx,
        label: entry.label || null,
        text: entry.text || null,
        role: entry.role || null,
      }})),
    }};
  }}
  const chosen = candidates[actionId];
  const disabled = !!chosen.node.disabled || (chosen.node.getAttribute && chosen.node.getAttribute("aria-disabled") === "true");
  if (disabled) {{
    return {{
      __error: "ACTION_DISABLED",
      actionId,
      label: chosen.label || null,
      text: chosen.text || null,
      role: chosen.role || null,
    }};
  }}
  if (typeof chosen.node.focus === "function") chosen.node.focus();
  if (typeof chosen.node.click === "function") chosen.node.click();
  return {{
    actionId,
    label: chosen.label || null,
    text: chosen.text || null,
    role: chosen.role || null,
    clicked: true,
  }};
}})()
""".strip()
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
    payload = _extract_remote_value(result)
    if not isinstance(payload, dict):
        raise DctlError("BACKEND_FAILURE", "Action click returned an unsupported payload.", details={"result": payload})
    if payload.get("__error") == "ACTION_NOT_FOUND":
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"Action id {action_id} was not found for the current page.",
            suggestion="Run `dctl browser actions` to inspect available action ids and labels.",
            details=payload,
        )
    if payload.get("__error") == "ACTION_DISABLED":
        raise DctlError(
            "ACTION_NOT_SUPPORTED",
            f"Action id {action_id} is disabled and cannot be clicked.",
            details=payload,
        )
    output = {"endpoint": base, "target": target, "result": payload}
    if session_name:
        output["session"] = _normalize_session_name(session_name)
    return output


def act(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    query: str | None = None,
    role: str | None = None,
    action_id: int | None = None,
    wait_selector_css: str | None = None,
    wait_url_needle: str | None = None,
    timeout: float = 10.0,
    interval_ms: int = 250,
    snapshot_after: bool = False,
    snapshot_strict: bool = False,
    snapshot_text_limit: int = 4000,
    snapshot_max_items: int = 120,
    snapshot_min_text: int = 120,
    snapshot_max_text: int | None = None,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    prepared_target = _prepared_target or _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name
    )
    base, target = prepared_target
    started = time.perf_counter()
    timings_ms: dict[str, float] = {}
    steps: dict[str, Any] = {}

    actions_started = time.perf_counter()
    actions_payload = actions(
        target_selector,
        endpoint=endpoint,
        port=port,
        session_name=session_name,
        query=query,
        role=role,
        _prepared_target=prepared_target,
    )
    timings_ms["actions"] = round((time.perf_counter() - actions_started) * 1000.0, 3)
    steps["actions"] = actions_payload["result"]

    action_items = steps["actions"].get("items") if isinstance(steps["actions"], dict) else None
    if not isinstance(action_items, list):
        raise DctlError("BACKEND_FAILURE", "Actions inventory returned malformed results.", details={"actions": steps["actions"]})
    chosen_action_id: int
    if action_id is None:
        if not action_items:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                "No actionable element matched the requested semantic filters.",
                details={"query": query, "role": role, "actions": steps["actions"]},
            )
        if len(action_items) != 1:
            raise DctlError(
                "MULTIPLE_MATCHES",
                "Semantic action resolution is ambiguous; refine filters or specify --action-id.",
                suggestion="Use `dctl browser actions` to inspect candidates and then run `dctl browser click-action`.",
                details={"query": query, "role": role, "candidates": action_items[:20]},
            )
        chosen_action_id = int(action_items[0].get("actionId", 0))
    else:
        chosen_action_id = int(action_id)

    click_started = time.perf_counter()
    click_payload = click_action(
        target_selector,
        chosen_action_id,
        endpoint=endpoint,
        port=port,
        session_name=session_name,
        query=query,
        role=role,
        _prepared_target=prepared_target,
    )
    timings_ms["clickAction"] = round((time.perf_counter() - click_started) * 1000.0, 3)
    steps["clickAction"] = click_payload["result"]

    if wait_selector_css:
        wait_selector_started = time.perf_counter()
        wait_selector_payload = wait_selector(
            target_selector,
            wait_selector_css,
            endpoint=endpoint,
            port=port,
            session_name=session_name,
            timeout=timeout,
            interval_ms=interval_ms,
            _prepared_target=prepared_target,
        )
        timings_ms["waitSelector"] = round((time.perf_counter() - wait_selector_started) * 1000.0, 3)
        steps["waitSelector"] = wait_selector_payload["result"]

    if wait_url_needle:
        wait_url_started = time.perf_counter()
        wait_url_payload = wait_url(
            target_selector,
            wait_url_needle,
            endpoint=endpoint,
            port=port,
            session_name=session_name,
            timeout=timeout,
            interval_ms=interval_ms,
            _prepared_target=prepared_target,
        )
        timings_ms["waitUrl"] = round((time.perf_counter() - wait_url_started) * 1000.0, 3)
        steps["waitUrl"] = wait_url_payload["result"]

    if snapshot_after:
        snapshot_started = time.perf_counter()
        snapshot_payload = snapshot(
            target_selector,
            endpoint=endpoint,
            port=port,
            session_name=session_name,
            text_limit=snapshot_text_limit,
            max_items=snapshot_max_items,
            min_text=snapshot_min_text,
            max_text=snapshot_max_text,
            strict=snapshot_strict,
            _prepared_target=prepared_target,
        )
        timings_ms["snapshot"] = round((time.perf_counter() - snapshot_started) * 1000.0, 3)
        steps["snapshot"] = snapshot_payload["result"]

    timings_ms["total"] = round((time.perf_counter() - started) * 1000.0, 3)
    result = {
        "endpoint": base,
        "target": target,
        "query": query,
        "role": role,
        "actionId": chosen_action_id,
        "steps": steps,
        "timingsMs": timings_ms,
    }
    if session_name:
        result["session"] = _normalize_session_name(session_name)
    return result


def dom(
    target_selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    selector: str | None = None,
    depth: int = 3,
    pierce: bool = True,
    strict_selector: bool = False,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    async def operation(session: _AsyncTargetSession) -> dict[str, Any]:
        root = await session.call("DOM.getDocument", {"depth": depth, "pierce": pierce})
        if not selector:
            return {"root": root["root"]}
        if strict_selector:
            node_id = await _node_id_for_selector_in_session(session, selector)
        else:
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
    strict_selector: bool = False,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    if selector:
        async def operation(session: _AsyncTargetSession) -> dict[str, Any]:
            if strict_selector:
                node_id = await _node_id_for_selector_in_session(session, selector)
            else:
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
    strict_selector: bool = False,
    _prepared_target: PreparedPageTarget | None = None,
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
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    if selector and strict_selector:
        _node_id_for_selector(target, selector)
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
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    expression = """
(() => ({
  text: window.getSelection ? String(window.getSelection()) : "",
  activeTag: document.activeElement ? document.activeElement.tagName : null
}))()
""".strip()
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
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
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
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
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
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
    strict_selector: bool = False,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    expression = f"""
(() => {{
  const strictSelector = {json.dumps(strict_selector)};
  const nodes = Array.from(document.querySelectorAll({json.dumps(selector)}));
  if (strictSelector && nodes.length > 1) {{
    return {{__error: 'multiple', count: nodes.length}};
  }}
  const node = nodes[0] || null;
  if (!node) return null;
  if (!{json.dumps(visible)}) {{
    return {{tag: node.tagName ?? null, text: node.innerText ?? node.textContent ?? "", matchCount: nodes.length}};
  }}
  const style = window.getComputedStyle(node);
  const rect = node.getBoundingClientRect();
  const shown = style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  return shown ? {{tag: node.tagName ?? null, text: node.innerText ?? node.textContent ?? "", matchCount: nodes.length}} : null;
}})()
""".strip()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _runtime_evaluate(target, expression, await_promise=True, return_by_value=True)
        payload = _extract_remote_value(result)
        if isinstance(payload, dict) and payload.get("__error") == "multiple":
            raise DctlError(
                "MULTIPLE_MATCHES",
                f"Selector '{selector}' matched multiple DOM nodes while waiting.",
                details={"selector": selector, "count": int(payload.get("count", 0))},
            )
        if payload:
            result = {"endpoint": base, "target": target, "selector": selector, "result": payload}
            if session_name:
                result["session"] = _normalize_session_name(session_name)
            return result
        time.sleep(max(interval_ms, 50) / 1000)
    raise DctlError("TIMEOUT", f"Timed out waiting for selector '{selector}'.")


async def _node_id_for_selector_in_session(session: _AsyncTargetSession, selector: str) -> int:
    root = await session.call("DOM.getDocument", {"depth": 1, "pierce": True})
    matches = await session.call("DOM.querySelectorAll", {"nodeId": root["root"]["nodeId"], "selector": selector})
    node_ids = [int(item) for item in matches.get("nodeIds", [])]
    if not node_ids:
        raise DctlError("ELEMENT_NOT_FOUND", f"No DOM node matches selector '{selector}'.")
    if len(node_ids) > 1:
        raise DctlError(
            "MULTIPLE_MATCHES",
            f"Selector '{selector}' matched multiple DOM nodes; selector must resolve to exactly one element.",
            details={"selector": selector, "count": len(node_ids), "node_ids": node_ids[:20]},
        )
    return node_ids[0]


def _node_id_for_selector(target: dict[str, Any], selector: str) -> int:
    async def operation(session: _AsyncTargetSession) -> int:
        return await _node_id_for_selector_in_session(session, selector)

    return _run_in_target_session(target, operation)


def click(
    target_selector: str,
    selector: str,
    *,
    endpoint: str | None = None,
    port: int | None = None,
    session_name: str | None = None,
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    async def operation(session: _AsyncTargetSession) -> dict[str, int]:
        await session.call("Page.bringToFront")
        node_id = await _node_id_for_selector_in_session(session, selector)
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
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
    _send_command(target, "Page.bringToFront")
    if selector:
        _node_id_for_selector(target, selector)
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
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
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
    _prepared_target: PreparedPageTarget | None = None,
) -> dict[str, Any]:
    base, target = _prepare_page_target(
        target_selector, endpoint, port, session_name=session_name, _prepared_target=_prepared_target
    )
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
    prepared_target = _prepare_page_target(target_selector, endpoint, port, session_name=session_name)
    base, target = prepared_target
    results = []
    op_timings: list[dict[str, Any]] = []
    batch_started = time.perf_counter()
    for operation in operations:
        if not isinstance(operation, dict) or "op" not in operation:
            raise DctlError("INVALID_SELECTOR", "Each batch operation must include an `op` field.")
        op = str(operation["op"])
        op_started = time.perf_counter()
        if op == "activate":
            target_id = target.get("id")
            if not target_id:
                raise DctlError("BACKEND_FAILURE", "Target does not expose an id for activation.", details={"target": target})
            outcome = _fetch_text(f"{base}/json/activate/{target_id}")
            if session_name and isinstance(target_id, str):
                _set_session_active_target(session_name, target_id)
            result = {"endpoint": base, "target": target, "result": outcome}
            if session_name:
                result["session"] = _normalize_session_name(session_name)
            results.append(result)
        elif op == "click":
            results.append(
                click(
                    target_selector,
                    str(operation["selector"]),
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    _prepared_target=prepared_target,
                )
            )
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
                    _prepared_target=prepared_target,
                )
            )
        elif op == "press":
            results.append(
                press_key(
                    target_selector,
                    str(operation["combo"]),
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    _prepared_target=prepared_target,
                )
            )
        elif op == "eval":
            results.append(
                evaluate(
                    target_selector,
                    str(operation["expression"]),
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    return_by_value=bool(operation.get("return_by_value", False)),
                    _prepared_target=prepared_target,
                )
            )
        elif op == "actions":
            results.append(
                actions(
                    target_selector,
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    sample_limit=int(operation.get("sample_limit", 60)),
                    query=(str(operation["query"]) if operation.get("query") is not None else None),
                    role=(str(operation["role"]) if operation.get("role") is not None else None),
                    _prepared_target=prepared_target,
                )
            )
        elif op == "click-action":
            if "action_id" not in operation:
                raise DctlError("INVALID_SELECTOR", "Batch click-action op requires `action_id`.")
            results.append(
                click_action(
                    target_selector,
                    int(operation["action_id"]),
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    query=(str(operation["query"]) if operation.get("query") is not None else None),
                    role=(str(operation["role"]) if operation.get("role") is not None else None),
                    _prepared_target=prepared_target,
                )
            )
        elif op == "act":
            results.append(
                act(
                    target_selector,
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    query=(str(operation["query"]) if operation.get("query") is not None else None),
                    role=(str(operation["role"]) if operation.get("role") is not None else None),
                    action_id=(int(operation["action_id"]) if operation.get("action_id") is not None else None),
                    wait_selector_css=(str(operation["wait_selector"]) if operation.get("wait_selector") is not None else None),
                    wait_url_needle=(str(operation["wait_url"]) if operation.get("wait_url") is not None else None),
                    timeout=float(operation.get("timeout", 10.0)),
                    interval_ms=int(operation.get("interval", 250)),
                    snapshot_after=bool(operation.get("snapshot", False)),
                    snapshot_strict=bool(operation.get("snapshot_strict", False)),
                    snapshot_text_limit=int(operation.get("snapshot_text_limit", 4000)),
                    snapshot_max_items=int(operation.get("snapshot_max_items", 120)),
                    snapshot_min_text=int(operation.get("snapshot_min_text", 120)),
                    snapshot_max_text=(int(operation["snapshot_max_text"]) if operation.get("snapshot_max_text") is not None else None),
                    _prepared_target=prepared_target,
                )
            )
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
                    strict_selector=bool(operation.get("strict_selector", False)),
                    _prepared_target=prepared_target,
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
                    _prepared_target=prepared_target,
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
                    max_items=int(operation.get("max_items", 120)),
                    min_text=int(operation.get("min_text", 120)),
                    max_text=(int(operation["max_text"]) if operation.get("max_text") is not None else None),
                    strict=bool(operation.get("strict", False)),
                    _prepared_target=prepared_target,
                )
            )
        elif op == "text":
            results.append(
                text(
                    target_selector,
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    selector=operation.get("selector"),
                    strict_selector=bool(operation.get("strict_selector", False)),
                    _prepared_target=prepared_target,
                )
            )
        elif op == "dom":
            results.append(
                dom(
                    target_selector,
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    selector=operation.get("selector"),
                    depth=int(operation.get("depth", 3)),
                    pierce=not bool(operation.get("no_pierce", False)),
                    strict_selector=bool(operation.get("strict_selector", False)),
                    _prepared_target=prepared_target,
                )
            )
        elif op == "ax":
            results.append(
                accessibility_tree(
                    target_selector,
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    selector=operation.get("selector"),
                    strict_selector=bool(operation.get("strict_selector", False)),
                    _prepared_target=prepared_target,
                )
            )
        elif op == "selector":
            results.append(
                selector_audit(
                    target_selector,
                    str(operation["selector"]),
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    sample_limit=int(operation.get("sample_limit", 20)),
                    _prepared_target=prepared_target,
                )
            )
        elif op == "selection":
            results.append(
                selection(
                    target_selector,
                    endpoint=endpoint,
                    port=port,
                    session_name=session_name,
                    _prepared_target=prepared_target,
                )
            )
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
                    _prepared_target=prepared_target,
                )
            )
        else:
            raise DctlError("INVALID_SELECTOR", f"Unsupported browser batch op '{op}'.")
        op_timings.append(
            {
                "op": op,
                "durationMs": round((time.perf_counter() - op_started) * 1000.0, 3),
            }
        )
    payload = {
        "endpoint": base,
        "target_selector": target_selector,
        "results": results,
        "timingsMs": {"total": round((time.perf_counter() - batch_started) * 1000.0, 3), "operations": op_timings},
    }
    if session_name:
        payload["session"] = _normalize_session_name(session_name)
    return payload
