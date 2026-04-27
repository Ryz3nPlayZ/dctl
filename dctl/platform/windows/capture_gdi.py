"""
Windows screen capture via GDI BitBlt.

Captures the full desktop or a specific HWND using the Win32 GDI APIs,
then saves as a PNG via the Pillow library (if available) or a raw BMP
fallback written manually.

Design decisions:
- Uses BitBlt (compatible DC copy) — works without elevated privileges.
- Saves PNG natively via Pillow when installed; falls back to BMP otherwise.
- DXGI Desktop Duplication would give higher performance for full-screen
  games, but BitBlt is universally available and requires no additional deps.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import struct
import os
import tempfile
from pathlib import Path
from typing import Any

from dctl.errors import DctlError


class Win32CaptureProvider:
    def __init__(self) -> None:
        try:
            self._user32 = ctypes.windll.user32
            self._gdi32 = ctypes.windll.gdi32
        except Exception as exc:
            raise DctlError(
                "PLATFORM_NOT_SUPPORTED",
                "Win32 GDI capture APIs are not available.",
                suggestion="This backend requires Windows.",
            ) from exc

    def screenshot(
        self,
        *,
        hwnd: int | None = None,
        region: str | None = None,
        output_path: str | None = None,
        as_base64: bool = False,
    ) -> dict[str, Any]:
        fd, temp_path = tempfile.mkstemp(prefix="dctl-win-", suffix=".png")
        os.close(fd)
        target = Path(output_path) if output_path else Path(temp_path)

        if region:
            x, y, w, h = _parse_region(region)
        elif hwnd:
            rect = ctypes.wintypes.RECT()
            self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
            x, y = rect.left, rect.top
            w, h = rect.right - rect.left, rect.bottom - rect.top
        else:
            x, y = 0, 0
            w = self._user32.GetSystemMetrics(0)
            h = self._user32.GetSystemMetrics(1)

        raw_rgb = self._bitblt_capture(x, y, w, h)
        _save_png(raw_rgb, w, h, target)

        result: dict[str, Any] = {
            "path": str(target),
            "backend": "bitblt",
            "region": f"{x},{y},{w},{h}",
        }
        if as_base64:
            import base64
            result["base64"] = base64.b64encode(target.read_bytes()).decode("ascii")
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _bitblt_capture(self, x: int, y: int, w: int, h: int) -> bytes:
        """Return raw BGR bytes for the desktop region (x,y,w,h)."""
        # Create device contexts
        screen_dc = self._user32.GetDC(0)
        compat_dc = self._gdi32.CreateCompatibleDC(screen_dc)
        bitmap = self._gdi32.CreateCompatibleBitmap(screen_dc, w, h)
        old_bitmap = self._gdi32.SelectObject(compat_dc, bitmap)

        # Perform the blit
        SRCCOPY = 0x00CC0020
        ok = self._gdi32.BitBlt(compat_dc, 0, 0, w, h, screen_dc, x, y, SRCCOPY)
        if not ok:
            self._cleanup_dc(screen_dc, compat_dc, bitmap, old_bitmap)
            raise DctlError("BACKEND_FAILURE", "BitBlt failed; could not capture the screen region.")

        # Extract pixel data via GetDIBits
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", ctypes.wintypes.WORD),
                ("biBitCount", ctypes.wintypes.WORD),
                ("biCompression", ctypes.wintypes.DWORD),
                ("biSizeImage", ctypes.wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", ctypes.wintypes.DWORD),
                ("biClrImportant", ctypes.wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER(
            biSize=ctypes.sizeof(BITMAPINFOHEADER),
            biWidth=w,
            biHeight=-h,  # negative = top-down
            biPlanes=1,
            biBitCount=32,
            biCompression=0,  # BI_RGB
        )
        buf_size = w * h * 4
        buf = (ctypes.c_char * buf_size)()
        lines = self._gdi32.GetDIBits(compat_dc, bitmap, 0, h, buf, ctypes.byref(bmi), 0)
        self._cleanup_dc(screen_dc, compat_dc, bitmap, old_bitmap)
        if lines == 0:
            raise DctlError("BACKEND_FAILURE", "GetDIBits failed; could not extract pixel data.")
        return bytes(buf)

    def _cleanup_dc(self, screen_dc: int, compat_dc: int, bitmap: int, old_bitmap: int) -> None:
        try:
            self._gdi32.SelectObject(compat_dc, old_bitmap)
            self._gdi32.DeleteObject(bitmap)
            self._gdi32.DeleteDC(compat_dc)
            self._user32.ReleaseDC(0, screen_dc)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# PNG / BMP helpers
# ---------------------------------------------------------------------------

def _save_png(raw_bgra: bytes, w: int, h: int, path: Path) -> None:
    """Save BGRA pixel buffer to a PNG file, using Pillow when available."""
    try:
        from PIL import Image  # type: ignore[import]
        img = Image.frombytes("RGBA", (w, h), raw_bgra, "raw", "BGRA")
        img.save(str(path), format="PNG")
        return
    except ImportError:
        pass
    # Fallback: save as 24-bit BMP (convert BGRA -> BGR, drop alpha)
    bmp_path = path.with_suffix(".bmp")
    stride = ((w * 3 + 3) & ~3)
    row_data = bytearray()
    for row in range(h):
        for col in range(w):
            idx = (row * w + col) * 4
            b, g, r = raw_bgra[idx], raw_bgra[idx + 1], raw_bgra[idx + 2]
            row_data += bytes([b, g, r])
        # Pad row to 4-byte boundary
        pad = stride - w * 3
        row_data += b"\x00" * pad
    pixel_data = bytes(row_data)
    file_size = 54 + len(pixel_data)
    header = (
        b"BM"
        + struct.pack("<I", file_size)
        + b"\x00\x00\x00\x00"
        + struct.pack("<I", 54)
        + struct.pack("<IIIHHIIIIII", 40, w, h, 1, 24, 0, len(pixel_data), 0, 0, 0, 0)
    )
    bmp_path.write_bytes(header + pixel_data)
    # Rename to the requested path if it still has .png extension (best effort)
    try:
        bmp_path.rename(path.with_suffix(".bmp"))
    except Exception:
        pass


def _parse_region(geometry: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in geometry.split(",")]
    if len(parts) != 4:
        raise DctlError("INVALID_SELECTOR", f"Invalid region '{geometry}'. Expected X,Y,W,H.")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError as exc:
        raise DctlError("INVALID_SELECTOR", f"Invalid region '{geometry}'. Expected integer X,Y,W,H.") from exc
