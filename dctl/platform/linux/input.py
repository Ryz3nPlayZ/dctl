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

YDOTOOL_SCROLL = {
    "up": "0xC4",
    "down": "0xC5",
    "left": "0xC6",
    "right": "0xC7",
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


_COMMON_KEY_CODES: dict[str, int] = {
    "KEY_RESERVED": 0, "KEY_ESC": 1, "KEY_1": 2, "KEY_2": 3, "KEY_3": 4,
    "KEY_4": 5, "KEY_5": 6, "KEY_6": 7, "KEY_7": 8, "KEY_8": 9, "KEY_9": 10,
    "KEY_0": 11, "KEY_MINUS": 12, "KEY_EQUAL": 13, "KEY_BACKSPACE": 14,
    "KEY_TAB": 15, "KEY_Q": 16, "KEY_W": 17, "KEY_E": 18, "KEY_R": 19,
    "KEY_T": 20, "KEY_Y": 21, "KEY_U": 22, "KEY_I": 23, "KEY_O": 24,
    "KEY_P": 25, "KEY_LEFTBRACE": 26, "KEY_RIGHTBRACE": 27, "KEY_ENTER": 28,
    "KEY_LEFTCTRL": 29, "KEY_A": 30, "KEY_S": 31, "KEY_D": 32, "KEY_F": 33,
    "KEY_G": 34, "KEY_H": 35, "KEY_J": 36, "KEY_K": 37, "KEY_L": 38,
    "KEY_SEMICOLON": 39, "KEY_APOSTROPHE": 40, "KEY_GRAVE": 41,
    "KEY_LEFTSHIFT": 42, "KEY_BACKSLASH": 43, "KEY_Z": 44, "KEY_X": 45,
    "KEY_C": 46, "KEY_V": 47, "KEY_B": 48, "KEY_N": 49, "KEY_M": 50,
    "KEY_COMMA": 51, "KEY_DOT": 52, "KEY_SLASH": 53, "KEY_RIGHTSHIFT": 54,
    "KEY_LEFTALT": 56, "KEY_CAPSLOCK": 58, "KEY_SPACE": 57,
    "KEY_F1": 59, "KEY_F2": 60, "KEY_F3": 61, "KEY_F4": 62,
    "KEY_F5": 63, "KEY_F6": 64, "KEY_F7": 65, "KEY_F8": 66,
    "KEY_F9": 67, "KEY_F10": 68, "KEY_F11": 87, "KEY_F12": 88,
    "KEY_NUMLOCK": 69, "KEY_SCROLLLOCK": 70, "KEY_HOME": 102,
    "KEY_UP": 103, "KEY_PAGEUP": 104, "KEY_LEFT": 105, "KEY_RIGHT": 106,
    "KEY_END": 107, "KEY_DOWN": 108, "KEY_PAGEDOWN": 109, "KEY_INSERT": 110,
    "KEY_DELETE": 111, "KEY_LEFTMETA": 125, "KEY_RIGHTMETA": 126,
    "KEY_RIGHTCTRL": 97, "KEY_RIGHTALT": 100,
}


@lru_cache(maxsize=1)
def evdev_key_codes() -> dict[str, int]:
    if INPUT_EVENT_CODES.exists():
        codes: dict[str, int] = {}
        pattern = re.compile(r"#define\s+(KEY_[A-Z0-9_]+)\s+([0-9xa-fA-F]+)")
        for line in INPUT_EVENT_CODES.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            name, value = match.groups()
            codes[name] = int(value, 0)
        if codes:
            return codes
    return dict(_COMMON_KEY_CODES)


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


def ydotool_scroll_args(direction: str, amount: int = 1) -> list[str]:
    code = YDOTOOL_SCROLL.get(direction.strip().lower())
    if code is None:
        raise DctlError("INVALID_SELECTOR", f"Unsupported scroll direction '{direction}'.")
    args = ["click", "--repeat", str(max(amount, 1)), "--next-delay", "20"]
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
