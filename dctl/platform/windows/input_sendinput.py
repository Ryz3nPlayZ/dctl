"""
Windows input injection via SendInput (User32).

Supports:
  - Mouse move + left/right/middle click + double-click
  - Keyboard key down/up with modifier support
  - Unicode text injection (SendInput with KEYEVENTF_UNICODE)
  - Scroll wheel events

All operations use the SendInput Win32 API directly via ctypes.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import time
from typing import Any

from dctl.errors import DctlError


# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
WHEEL_DELTA = 120

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

# Virtual key codes
VK_MAP: dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "return": 0x0D, "enter": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "pause": 0x13, "capslock": 0x14,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E, "del": 0x2E,
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C, "apps": 0x5D,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "numlock": 0x90, "scrolllock": 0x91,
    "prtsc": 0x2C, "printscreen": 0x2C,
}

MODIFIER_VKS = {
    "shift": 0x10,
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12,
    "win": 0x5B, "lwin": 0x5B,
}


# ---------------------------------------------------------------------------
# ctypes struct definitions
# ---------------------------------------------------------------------------

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("_input", _INPUT_UNION),
    ]


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class Win32InputProvider:
    def __init__(self) -> None:
        try:
            self._user32 = ctypes.windll.user32
        except Exception as exc:
            raise DctlError(
                "PLATFORM_NOT_SUPPORTED",
                "Win32 input APIs are not available.",
                suggestion="This backend requires Windows.",
            ) from exc

    def mouse_move(self, x: int, y: int) -> None:
        """Move the cursor to absolute desktop coordinates."""
        # Normalise to 0–65535 range for MOUSEEVENTF_ABSOLUTE
        screen_w = self._user32.GetSystemMetrics(0)  # SM_CXSCREEN
        screen_h = self._user32.GetSystemMetrics(1)  # SM_CYSCREEN
        norm_x = (x * 65535) // max(screen_w - 1, 1)
        norm_y = (y * 65535) // max(screen_h - 1, 1)
        inp = INPUT(type=INPUT_MOUSE)
        inp._input.mi = MOUSEINPUT(
            dx=norm_x,
            dy=norm_y,
            mouseData=0,
            dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
            time=0,
            dwExtraInfo=None,
        )
        self._send([inp])

    def mouse_click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        """Move to (x, y) and click the specified mouse button."""
        self.mouse_move(x, y)
        time.sleep(0.03)
        down_flag, up_flag = {
            "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
            "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
            "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        }.get(button.lower(), (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
        clicks = 2 if double else 1
        for _ in range(clicks):
            self._send([self._mouse_event(down_flag), self._mouse_event(up_flag)])
            if double:
                time.sleep(0.05)

    def scroll(self, direction: str, amount: int = 1) -> None:
        """Inject scroll wheel events."""
        direction = direction.strip().lower()
        if direction in ("up", "down"):
            delta = WHEEL_DELTA * amount * (1 if direction == "up" else -1)
            inp = INPUT(type=INPUT_MOUSE)
            inp._input.mi = MOUSEINPUT(
                dx=0, dy=0, mouseData=ctypes.wintypes.DWORD(delta & 0xFFFFFFFF),
                dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=None,
            )
            self._send([inp])
        elif direction in ("left", "right"):
            delta = WHEEL_DELTA * amount * (1 if direction == "right" else -1)
            inp = INPUT(type=INPUT_MOUSE)
            inp._input.mi = MOUSEINPUT(
                dx=0, dy=0, mouseData=ctypes.wintypes.DWORD(delta & 0xFFFFFFFF),
                dwFlags=MOUSEEVENTF_HWHEEL, time=0, dwExtraInfo=None,
            )
            self._send([inp])
        else:
            raise DctlError("INVALID_SELECTOR", f"Unsupported scroll direction '{direction}'.")

    def type_text(self, text: str) -> None:
        """Inject text as Unicode key events (works for any Unicode character)."""
        inputs: list[INPUT] = []
        for char in text:
            scan = ord(char)
            inputs.append(self._key_event(0, scan, KEYEVENTF_UNICODE))
            inputs.append(self._key_event(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        self._send(inputs)

    def press_key(self, combo: str) -> None:
        """
        Press a key combination such as "ctrl+c", "win+r", "alt+f4".
        Modifier order: any order is accepted; the last token is the key.
        """
        tokens = [t.strip().lower() for t in combo.replace("-", "+").split("+") if t.strip()]
        if not tokens:
            raise DctlError("INVALID_SELECTOR", "Key combo cannot be empty.")
        modifiers, key_token = tokens[:-1], tokens[-1]
        vk = self._token_to_vk(key_token)
        mod_vks = [MODIFIER_VKS[m] for m in modifiers if m in MODIFIER_VKS]

        down_inputs = [self._key_event(m, 0, 0) for m in mod_vks]
        down_inputs.append(self._key_event(vk, 0, 0))
        up_inputs = [self._key_event(vk, 0, KEYEVENTF_KEYUP)]
        up_inputs += [self._key_event(m, 0, KEYEVENTF_KEYUP) for m in reversed(mod_vks)]
        self._send(down_inputs + up_inputs)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _send(self, inputs: list[INPUT]) -> None:
        n = len(inputs)
        arr = (INPUT * n)(*inputs)
        sent = self._user32.SendInput(n, arr, ctypes.sizeof(INPUT))
        if sent != n:
            raise DctlError(
                "BACKEND_FAILURE",
                f"SendInput sent {sent}/{n} events.",
                suggestion="Check for elevated process UAC or input blocked by security software.",
            )

    @staticmethod
    def _mouse_event(flags: int) -> INPUT:
        inp = INPUT(type=INPUT_MOUSE)
        inp._input.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=None)
        return inp

    @staticmethod
    def _key_event(vk: int, scan: int, flags: int) -> INPUT:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp._input.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
        return inp

    def _token_to_vk(self, token: str) -> int:
        if token in VK_MAP:
            return VK_MAP[token]
        if len(token) == 1:
            # VkKeyScanW returns (shift << 8 | vk)
            result = self._user32.VkKeyScanW(ord(token))
            vk = result & 0xFF
            if vk != 0xFF:
                return vk
        raise DctlError("INVALID_SELECTOR", f"Unsupported Windows key token '{token}'.")
