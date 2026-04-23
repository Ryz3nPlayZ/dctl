from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import time
import subprocess
from typing import Any

from dctl.errors import DctlError


DESKTOP_DIRS = [
    Path.home() / ".local/share/applications",
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]


def _desktop_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for directory in DESKTOP_DIRS:
        if not directory.exists():
            continue
        for file_path in sorted(directory.glob("*.desktop")):
            entry = _parse_desktop_file(file_path)
            if entry:
                entries.append(entry)
    return entries


def _parse_desktop_file(path: Path) -> dict[str, Any] | None:
    data: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key] = value
    except OSError:
        return None

    if data.get("NoDisplay", "").lower() == "true":
        return None
    if data.get("Type") and data.get("Type") != "Application":
        return None

    desktop_id = path.stem
    return {
        "id": desktop_id,
        "name": data.get("Name", desktop_id),
        "exec": data.get("Exec"),
        "icon": data.get("Icon"),
        "path": str(path),
    }


def list_launchable() -> list[dict[str, Any]]:
    return _desktop_entries()


def _match_entry(target: str) -> dict[str, Any] | None:
    target_norm = target.strip().lower()
    for entry in _desktop_entries():
        if target_norm in {entry["id"].lower(), entry["name"].lower(), Path(entry["path"]).name.lower()}:
            return entry
    for entry in _desktop_entries():
        if target_norm in entry["name"].lower():
            return entry
    return None


def _sanitize_exec(exec_value: str) -> list[str]:
    args = shlex.split(exec_value)
    cleaned: list[str] = []
    field_code_re = re.compile(r"%[fFuUdDnNickvm]")
    for arg in args:
        stripped = field_code_re.sub("", arg).strip()
        if stripped:
            cleaned.append(stripped)
    return cleaned


def _needs_accessibility_boost(entry: dict[str, Any], cmd: list[str]) -> bool:
    joined = " ".join(cmd).lower()
    app_id = entry["id"].lower()
    name = entry["name"].lower()
    chromium_like = any(
        token in joined or token in app_id or token in name
        for token in ("brave", "chrome", "chromium", "electron", "code", "cursor", "windsurf", "trae", "kiro")
    )
    return chromium_like


def _augment_for_accessibility(entry: dict[str, Any], cmd: list[str]) -> tuple[list[str], dict[str, str]]:
    env = os.environ.copy()
    env["ACCESSIBILITY_ENABLED"] = "1"

    if _needs_accessibility_boost(entry, cmd):
        if "--force-renderer-accessibility" not in cmd:
            cmd = [*cmd, "--force-renderer-accessibility"]
    return cmd, env


def launch_target(target: str, xdg_open_path: str | None, gtk_launch_path: str | None) -> dict[str, Any]:
    if not target.strip():
        raise DctlError("INVALID_SELECTOR", "Launch target cannot be empty.")

    path = Path(os.path.expanduser(target))
    if path.exists():
        return open_target(str(path), xdg_open_path)

    if target.startswith(("http://", "https://")):
        return open_target(target, xdg_open_path)

    entry = _match_entry(target)
    if entry is None:
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"No launchable application matching '{target}' was found.",
            suggestion="Run `dctl list-launchable` to inspect available applications.",
        )

    exec_value = entry.get("exec")
    if not exec_value:
        raise DctlError(
            "CAPABILITY_UNAVAILABLE",
            f"Desktop entry '{entry['name']}' does not expose an executable command.",
        )

    cmd = _sanitize_exec(exec_value)
    if not cmd:
        raise DctlError(
            "CAPABILITY_UNAVAILABLE",
            f"Desktop entry '{entry['name']}' does not expose a usable command.",
        )

    cmd, env = _augment_for_accessibility(entry, cmd)
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env)
    time.sleep(0.5)
    if process.poll() not in (None, 0):
        stderr = (process.stderr.read() or "").strip() if process.stderr else ""
        raise DctlError(
            "BACKEND_FAILURE",
            f"Failed to launch '{entry['name']}'.",
            suggestion=stderr or "The application exited immediately after launch.",
        )
    return {"launched": entry, "command": cmd, "env": {"ACCESSIBILITY_ENABLED": "1"}}


def open_target(target: str, xdg_open_path: str | None) -> dict[str, Any]:
    if not xdg_open_path:
        raise DctlError(
            "DEPENDENCY_MISSING",
            "xdg-open is not installed.",
            suggestion="Install xdg-utils to enable launch and open commands.",
        )
    subprocess.Popen([xdg_open_path, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"opened": target}
