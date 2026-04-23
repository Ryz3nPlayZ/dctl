from __future__ import annotations

import importlib.util
from typing import Any

from dctl.platform.detect import EnvironmentInfo, command_ok
from dctl.platform.linux.input import probe_xdotool, probe_ydotool


def _linux_atspi_importable() -> bool:
    return importlib.util.find_spec("gi") is not None


def _module_importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _linux_atspi_bus_available(env: EnvironmentInfo) -> bool:
    if not env.helpers.get("gdbus"):
        return False
    return command_ok(
        [
            env.helpers["gdbus"],
            "introspect",
            "--session",
            "--dest",
            "org.a11y.Bus",
            "--object-path",
            "/org/a11y/bus",
        ]
    )


def collect_capabilities(env: EnvironmentInfo) -> dict[str, Any]:
    providers: dict[str, str | None] = {
        "accessibility": None,
        "windowing": None,
        "capture": None,
        "input": None,
        "launch": None,
        "browser": None,
        "office": None,
        "docx": None,
        "xlsx": None,
    }

    diagnostics: dict[str, Any] = {
        "helpers": env.helpers,
        "checks": {},
    }

    commands: dict[str, bool] = {}
    warnings: list[str] = []

    if env.platform == "linux":
        atspi_importable = _linux_atspi_importable()
        atspi_bus = _linux_atspi_bus_available(env) if atspi_importable else False
        xdotool_usable = probe_xdotool(env.helpers.get("xdotool"))
        ydotool_usable = probe_ydotool(env.helpers.get("ydotool"))
        websockets_importable = _module_importable("websockets")
        docx_importable = _module_importable("docx")
        openpyxl_importable = _module_importable("openpyxl")
        uno_importable = _module_importable("uno")
        browser_binaries = [helper for helper in (
            env.helpers.get("brave"),
            env.helpers.get("google-chrome-stable"),
            env.helpers.get("google-chrome"),
            env.helpers.get("chromium"),
        ) if helper]
        diagnostics["checks"]["atspi_importable"] = atspi_importable
        diagnostics["checks"]["atspi_bus"] = atspi_bus
        diagnostics["checks"]["xdotool_usable"] = xdotool_usable
        diagnostics["checks"]["ydotool_usable"] = ydotool_usable
        diagnostics["checks"]["websockets_importable"] = websockets_importable
        diagnostics["checks"]["docx_importable"] = docx_importable
        diagnostics["checks"]["openpyxl_importable"] = openpyxl_importable
        diagnostics["checks"]["uno_importable"] = uno_importable
        diagnostics["checks"]["browser_binaries"] = browser_binaries

        if atspi_importable and atspi_bus:
            providers["accessibility"] = "atspi"
        else:
            warnings.append("AT-SPI is not currently available; semantic UI commands will fail.")

        if env.helpers.get("grim"):
            providers["capture"] = "grim"
        elif env.helpers.get("spectacle"):
            providers["capture"] = "spectacle"
        elif env.helpers.get("scrot"):
            providers["capture"] = "scrot"
        else:
            warnings.append("No screenshot helper is installed.")

        if xdotool_usable:
            providers["input"] = "xdotool"
            providers["windowing"] = "xdotool"
        elif ydotool_usable:
            providers["input"] = "ydotool"
            warnings.append("Using ydotool may require elevated uinput access.")
        else:
            warnings.append("No input injection helper is installed.")

        if providers["windowing"] is None and providers["accessibility"] is not None:
            providers["windowing"] = "atspi"

        if env.helpers.get("xdg-open"):
            providers["launch"] = "xdg-open"
        if websockets_importable:
            providers["browser"] = "cdp"
            if not browser_binaries:
                warnings.append("No Chromium-based browser executable was found; CDP requires either a local browser or an existing debug endpoint.")
        else:
            warnings.append("The `websockets` module is missing; browser CDP commands will fail.")
        if uno_importable and (env.helpers.get("soffice") or env.helpers.get("libreoffice")):
            providers["office"] = "uno"
        elif uno_importable:
            warnings.append("The `uno` module is available but LibreOffice is not on PATH.")
        else:
            warnings.append("The `uno` module is missing; LibreOffice semantic commands will fail.")
        if docx_importable:
            providers["docx"] = "python-docx"
        else:
            warnings.append("The `python-docx` module is missing; DOCX commands will fail.")
        if openpyxl_importable:
            providers["xlsx"] = "openpyxl"
        else:
            warnings.append("The `openpyxl` module is missing; XLSX commands will fail.")

        commands = {
            "capabilities": True,
            "doctor": True,
            "list-apps": providers["accessibility"] is not None or providers["windowing"] is not None,
            "list-windows": providers["accessibility"] is not None or providers["windowing"] is not None,
            "list-launchable": True,
            "launch": providers["launch"] is not None,
            "open": providers["launch"] is not None,
            "tree": providers["accessibility"] is not None,
            "element": providers["accessibility"] is not None or providers["windowing"] is not None,
            "read": providers["accessibility"] is not None or providers["windowing"] is not None,
            "describe": providers["accessibility"] is not None or providers["windowing"] is not None,
            "wait": providers["accessibility"] is not None or providers["windowing"] is not None,
            "focus": providers["accessibility"] is not None or providers["windowing"] is not None or providers["input"] is not None,
            "click": providers["accessibility"] is not None or providers["windowing"] is not None or providers["input"] is not None,
            "type": providers["accessibility"] is not None or providers["input"] is not None,
            "key": providers["input"] is not None,
            "scroll": providers["input"] is not None,
            "screenshot": providers["capture"] is not None,
            "browser": providers["browser"] is not None,
            "libreoffice": providers["office"] is not None,
            "docx": providers["docx"] is not None,
            "word": providers["docx"] is not None,
            "xlsx": providers["xlsx"] is not None,
            "excel": providers["xlsx"] is not None,
        }
    elif env.platform == "darwin":
        ax_importable = importlib.util.find_spec("ApplicationServices") is not None
        quartz_importable = importlib.util.find_spec("Quartz") is not None
        appkit_importable = importlib.util.find_spec("AppKit") is not None
        websockets_importable = _module_importable("websockets")
        docx_importable = _module_importable("docx")
        openpyxl_importable = _module_importable("openpyxl")
        uno_importable = _module_importable("uno")
        diagnostics["checks"]["ax_importable"] = ax_importable
        diagnostics["checks"]["quartz_importable"] = quartz_importable
        diagnostics["checks"]["appkit_importable"] = appkit_importable
        diagnostics["checks"]["websockets_importable"] = websockets_importable
        diagnostics["checks"]["docx_importable"] = docx_importable
        diagnostics["checks"]["openpyxl_importable"] = openpyxl_importable
        diagnostics["checks"]["uno_importable"] = uno_importable

        accessibility_permission = False
        if ax_importable:
            try:
                import ApplicationServices as AS

                try:
                    accessibility_permission = bool(
                        AS.AXIsProcessTrustedWithOptions({AS.kAXTrustedCheckOptionPrompt: False})
                    )
                except Exception:
                    accessibility_permission = bool(AS.AXIsProcessTrusted())
            except Exception:
                accessibility_permission = False
        diagnostics["checks"]["accessibility_permission"] = accessibility_permission

        if quartz_importable and appkit_importable:
            providers["windowing"] = "quartz"
        else:
            warnings.append("Quartz/AppKit PyObjC modules are not available; window enumeration will fail.")

        if env.helpers.get("screencapture"):
            providers["capture"] = "screencapture"
        else:
            warnings.append("`screencapture` is not available; screenshot commands will fail.")

        if env.helpers.get("open"):
            providers["launch"] = "open"
        if websockets_importable:
            providers["browser"] = "cdp"
        else:
            warnings.append("The `websockets` module is missing; browser CDP commands will fail.")
        if uno_importable and (env.helpers.get("soffice") or env.helpers.get("libreoffice")):
            providers["office"] = "uno"
        elif uno_importable:
            warnings.append("The `uno` module is available but LibreOffice is not on PATH.")
        else:
            warnings.append("The `uno` module is missing; LibreOffice semantic commands will fail.")
        if docx_importable:
            providers["docx"] = "python-docx"
        else:
            warnings.append("The `python-docx` module is missing; DOCX commands will fail.")
        if openpyxl_importable:
            providers["xlsx"] = "openpyxl"
        else:
            warnings.append("The `openpyxl` module is missing; XLSX commands will fail.")

        if ax_importable and accessibility_permission:
            providers["accessibility"] = "ax"
            providers["input"] = "quartz"
        elif ax_importable and not accessibility_permission:
            warnings.append("Accessibility permission is not granted; semantic UI and input commands will fail.")
        else:
            warnings.append("ApplicationServices PyObjC module is not available; AX commands will fail.")

        commands = {name: False for name in [
            "capabilities",
            "doctor",
            "list-apps",
            "list-windows",
            "list-launchable",
            "launch",
            "open",
            "tree",
            "element",
            "read",
            "describe",
            "wait",
            "focus",
            "click",
            "type",
            "key",
            "scroll",
            "screenshot",
            "browser",
            "libreoffice",
            "docx",
            "word",
            "xlsx",
            "excel",
        ]}
        commands["capabilities"] = True
        commands["doctor"] = True
        commands["list-launchable"] = providers["launch"] is not None
        commands["launch"] = providers["launch"] is not None
        commands["open"] = providers["launch"] is not None
        commands["list-windows"] = providers["windowing"] is not None
        commands["list-apps"] = providers["windowing"] is not None
        commands["screenshot"] = providers["capture"] is not None
        commands["tree"] = providers["accessibility"] is not None
        commands["element"] = providers["accessibility"] is not None or providers["windowing"] is not None
        commands["read"] = providers["accessibility"] is not None or providers["windowing"] is not None
        commands["describe"] = providers["accessibility"] is not None or providers["windowing"] is not None
        commands["wait"] = providers["accessibility"] is not None or providers["windowing"] is not None
        commands["focus"] = providers["input"] is not None or providers["windowing"] is not None
        commands["click"] = providers["input"] is not None or providers["windowing"] is not None
        commands["type"] = providers["input"] is not None
        commands["key"] = providers["input"] is not None
        commands["scroll"] = providers["input"] is not None
        commands["browser"] = providers["browser"] is not None
        commands["libreoffice"] = providers["office"] is not None
        commands["docx"] = providers["docx"] is not None
        commands["word"] = providers["docx"] is not None
        commands["xlsx"] = providers["xlsx"] is not None
        commands["excel"] = providers["xlsx"] is not None
    else:
        warnings.append(f"Unsupported platform: {env.platform}")
        commands = {"capabilities": True, "doctor": True}

    return {
        "platform": env.platform,
        "session_type": env.session_type,
        "providers": providers,
        "commands": commands,
        "warnings": warnings,
        "diagnostics": diagnostics,
    }
