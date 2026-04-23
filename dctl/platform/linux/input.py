from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import subprocess

from dctl.errors import DctlError


INPUT_EVENT_CODES = Path("/usr/include/linux/input-event-codes.h")

KEY_ALIASES = {
    "ctrl": "KEY_LEFTCTRL",
    "control": "KEY_LEFTCTRL",
    "shift": "KEY_LEFTSHIFT",
    "alt": "KEY_LEFTALT",
    "option": "KEY_LEFTALT",
    "meta": "KEY_LEFTMETA",
    "super": "KEY_LEFTMETA",
    "cmd": "KEY_LEFTMETA",
    "command": "KEY_LEFTMETA",
    "enter": "KEY_ENTER",
    "return": "KEY_ENTER",
    "esc": "KEY_ESC",
    "escape": "KEY_ESC",
    "tab": "KEY_TAB",
    "space": "KEY_SPACE",
    "backspace": "KEY_BACKSPACE",
    "delete": "KEY_DELETE",
    "del": "KEY_DELETE",
    "insert": "KEY_INSERT",
    "home": "KEY_HOME",
    "end": "KEY_END",
    "pageup": "KEY_PAGEUP",
    "pagedown": "KEY_PAGEDOWN",
    "pgup": "KEY_PAGEUP",
    "pgdn": "KEY_PAGEDOWN",
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "minus": "KEY_MINUS",
    "equal": "KEY_EQUAL",
    "comma": "KEY_COMMA",
    "period": "KEY_DOT",
    "dot": "KEY_DOT",
    "slash": "KEY_SLASH",
    "backslash": "KEY_BACKSLASH",
    "semicolon": "KEY_SEMICOLON",
    "apostrophe": "KEY_APOSTROPHE",
    "grave": "KEY_GRAVE",
    "capslock": "KEY_CAPSLOCK",
}

YDOTOOL_BUTTONS = {
    "left": "0xC0",
    "right": "0xC1",
    "middle": "0xC2",
}


def probe_xdotool(helper_path: str | None) -> bool:
    if not helper_path:
        return False
    result = subprocess.run(
        [helper_path, "getmouselocation"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    output = (result.stdout or "").strip().lower()
    return bool(output) and "failed creating new xdo instance" not in output


def probe_ydotool(helper_path: str | None) -> bool:
    if not helper_path:
        return False
    result = subprocess.run(
        [helper_path, "debug"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    output = (result.stdout or "").strip().lower()
    return result.returncode == 0 and "failed to connect socket" not in output


@lru_cache(maxsize=1)
def evdev_key_codes() -> dict[str, int]:
    codes: dict[str, int] = {}
    if not INPUT_EVENT_CODES.exists():
        return codes
    pattern = re.compile(r"#define\s+(KEY_[A-Z0-9_]+)\s+([0-9xa-fA-F]+)")
    for line in INPUT_EVENT_CODES.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        name, value = match.groups()
        codes[name] = int(value, 0)
    return codes


def ydotool_key_args(combo: str) -> list[str]:
    codes = evdev_key_codes()
    tokens = [token.strip() for token in combo.replace("-", "+").split("+") if token.strip()]
    if not tokens:
        raise DctlError("INVALID_SELECTOR", "Key combo cannot be empty.")

    resolved: list[int] = []
    for token in tokens:
        code_name = _token_to_key_name(token)
        code = codes.get(code_name)
        if code is None:
            raise DctlError(
                "INVALID_SELECTOR",
                f"Unsupported key token '{token}' for ydotool.",
                suggestion="Use common key names like ctrl, shift, alt, enter, or literal letters and digits.",
            )
        resolved.append(code)

    args = [f"{code}:1" for code in resolved]
    args.extend(f"{code}:0" for code in reversed(resolved))
    return args


def ydotool_mousemove_args(x: int, y: int) -> list[str]:
    return ["mousemove", "--absolute", "-x", str(x), "-y", str(y)]


def ydotool_click_args(button: str = "left", repeat: int = 1) -> list[str]:
    code = YDOTOOL_BUTTONS.get(button.lower())
    if code is None:
        raise DctlError("INVALID_SELECTOR", f"Unsupported mouse button '{button}'.")
    args = ["click"]
    if repeat > 1:
        args.extend(["--repeat", str(repeat), "--next-delay", "25"])
    args.append(code)
    return args


def _token_to_key_name(token: str) -> str:
    lower = token.lower()
    if lower in KEY_ALIASES:
        return KEY_ALIASES[lower]
    if len(lower) == 1 and lower.isalpha():
        return f"KEY_{lower.upper()}"
    if len(lower) == 1 and lower.isdigit():
        return f"KEY_{lower}"
    if lower.startswith("f") and lower[1:].isdigit():
        return f"KEY_{lower.upper()}"
    return f"KEY_{re.sub(r'[^a-z0-9]', '', lower).upper()}"
