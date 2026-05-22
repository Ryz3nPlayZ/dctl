"""Cross-platform clipboard read/write via subprocess."""
from __future__ import annotations

import shutil
import subprocess
from typing import Any

from dctl.errors import DctlError


def clipboard_read(env: Any) -> dict[str, Any]:
    backend, args = _read_command(env)
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True, timeout=5)
    except FileNotFoundError:
        raise DctlError(
            "DEPENDENCY_MISSING",
            f"Clipboard tool '{backend}' is not available.",
            suggestion=_install_suggestion(env),
        ) from None
    except subprocess.TimeoutExpired:
        raise DctlError("BACKEND_FAILURE", f"Clipboard read via '{backend}' timed out.") from None
    return {"text": result.stdout.rstrip("\n"), "backend": backend}


def clipboard_write(text: str, env: Any) -> dict[str, Any]:
    backend, args = _write_command(env, text)
    try:
        result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, check=True, timeout=5, input=text)
    except FileNotFoundError:
        raise DctlError(
            "DEPENDENCY_MISSING",
            f"Clipboard tool '{backend}' is not available.",
            suggestion=_install_suggestion(env),
        ) from None
    except subprocess.TimeoutExpired:
        raise DctlError("BACKEND_FAILURE", f"Clipboard write via '{backend}' timed out.") from None
    return {"text": text, "backend": backend}


def _read_command(env: Any) -> tuple[str, list[str]]:
    plat = env.platform
    if plat == "darwin":
        return ("pbpaste", ["pbpaste"])
    if plat == "windows":
        return ("powershell", [env.helpers.get("powershell") or "powershell", "-NoProfile", "-Command", "Get-Clipboard"])
    # Linux
    if env.session_type == "wayland" and shutil.which("wl-paste"):
        return ("wl-paste", ["wl-paste", "--no-newline"])
    if shutil.which("xclip"):
        return ("xclip", ["xclip", "-selection", "clipboard", "-o"])
    if env.session_type == "wayland":
        raise DctlError("DEPENDENCY_MISSING", "No Wayland clipboard tool found.", suggestion="Install wl-clipboard.")
    raise DctlError("DEPENDENCY_MISSING", "No X11 clipboard tool found.", suggestion="Install xclip.")


def _write_command(env: Any, text: str) -> tuple[str, list[str]]:
    plat = env.platform
    if plat == "darwin":
        return ("pbcopy", ["pbcopy"])
    if plat == "windows":
        ps = env.helpers.get("powershell") or "powershell"
        escaped = text.replace("'", "''")
        return ("powershell", [ps, "-NoProfile", "-Command", f"$Input | Set-Clipboard"])
    # Linux
    if env.session_type == "wayland" and shutil.which("wl-copy"):
        return ("wl-copy", ["wl-copy"])
    if shutil.which("xclip"):
        return ("xclip", ["xclip", "-selection", "clipboard"])
    if env.session_type == "wayland":
        raise DctlError("DEPENDENCY_MISSING", "No Wayland clipboard tool found.", suggestion="Install wl-clipboard.")
    raise DctlError("DEPENDENCY_MISSING", "No X11 clipboard tool found.", suggestion="Install xclip.")


def _install_suggestion(env: Any) -> str:
    if env.platform == "linux":
        if env.session_type == "wayland":
            return "Install wl-clipboard (e.g. sudo apt install wl-clipboard)."
        return "Install xclip (e.g. sudo apt install xclip)."
    if env.platform == "darwin":
        return "pbpaste/pbcopy should be pre-installed on macOS."
    return "Ensure PowerShell is available on PATH."
