"""
Windows application launch provider.

Supports:
  - Opening files and URLs via ShellExecuteW (mimics xdg-open / macOS `open`)
  - Discovering installed applications from the Windows registry
    (HKCU and HKLM App Paths + Start Menu shortcuts)
  - Launching a named application by display name, executable name, or path
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from dctl.errors import DctlError


class Win32LaunchProvider:
    def list_launchable(self) -> list[dict[str, Any]]:
        """Return a list of discoverable apps from the registry and Start Menu."""
        apps: dict[str, dict[str, Any]] = {}

        # 1. Registry App Paths (covers most installed Win32 apps)
        try:
            import winreg  # type: ignore[import]
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        count = winreg.QueryInfoKey(key)[0]
                        for i in range(count):
                            subkey_name = winreg.EnumKey(key, i)
                            try:
                                with winreg.OpenKey(key, subkey_name) as sub:
                                    exe_path, _ = winreg.QueryValueEx(sub, "")
                                    exe_path = str(exe_path).strip().strip('"')
                                    name = Path(subkey_name).stem
                                    if exe_path and name not in apps:
                                        apps[name] = {
                                            "id": name.lower(),
                                            "name": name,
                                            "path": exe_path,
                                            "source": "registry",
                                        }
                            except Exception:
                                continue
                except Exception:
                    continue
        except ImportError:
            pass

        # 2. Start Menu shortcuts (covers UWP and additional installed apps)
        start_menu_roots = [
            Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]
        for root in start_menu_roots:
            if not root.exists():
                continue
            for lnk in root.rglob("*.lnk"):
                name = lnk.stem
                if name not in apps:
                    apps[name] = {
                        "id": name.lower(),
                        "name": name,
                        "path": str(lnk),
                        "source": "start_menu",
                    }

        return sorted(apps.values(), key=lambda a: a["name"].lower())

    def launch(self, target: str) -> dict[str, Any]:
        """
        Launch an application or file by:
          1. Direct path / URL → ShellExecuteW
          2. Match by name in list_launchable
          3. Try executable name directly
        """
        if not target.strip():
            raise DctlError("INVALID_SELECTOR", "Launch target cannot be empty.")

        expanded = os.path.expandvars(os.path.expanduser(target))

        # If it looks like a URL or an existing file, open it directly.
        if target.startswith(("http://", "https://", "ftp://", "file://")):
            return self.open_target(target)
        if Path(expanded).exists():
            return self.open_target(expanded)

        # Search registry / start menu
        apps = self.list_launchable()
        target_lower = target.strip().lower()
        matched = None
        for app in apps:
            if target_lower in {app["id"].lower(), app["name"].lower(), Path(app["path"]).stem.lower()}:
                matched = app
                break
        if matched is None:
            for app in apps:
                if target_lower in app["name"].lower():
                    matched = app
                    break

        if matched:
            self._shell_exec(matched["path"])
            return {"launched": matched}

        # Last resort: try CreateProcess / shell
        try:
            proc = subprocess.Popen([target], shell=False)
            return {"launched": {"name": target, "path": target}, "pid": proc.pid}
        except FileNotFoundError:
            pass
        try:
            proc = subprocess.Popen(target, shell=True)
            return {"launched": {"name": target, "path": target}, "pid": proc.pid}
        except Exception as exc:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"No application matching '{target}' could be found or launched.",
                suggestion="Run `dctl list-launchable` for available applications.",
            ) from exc

    def open_target(self, target: str) -> dict[str, Any]:
        """Open a file or URL using the default handler (ShellExecuteW)."""
        self._shell_exec(target)
        return {"opened": target}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _shell_exec(self, target: str) -> None:
        try:
            import ctypes
            result = ctypes.windll.shell32.ShellExecuteW(0, "open", target, None, None, 1)
            # ShellExecuteW returns > 32 on success
            if result <= 32:
                raise DctlError(
                    "BACKEND_FAILURE",
                    f"ShellExecuteW returned {result} for '{target}'.",
                    suggestion="Check that the path or URL is valid and accessible.",
                )
        except DctlError:
            raise
        except Exception as exc:
            raise DctlError(
                "BACKEND_FAILURE",
                f"ShellExecuteW failed for '{target}': {exc}",
            ) from exc
