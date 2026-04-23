# dctl

`dctl` is a headless desktop control CLI for LLM agents.

It gives an agent a structured, non-interactive control plane for the desktop:

- JSON-first output
- deterministic commands
- semantic UI access when available
- raw fallbacks when needed
- browser, office, DOCX, and XLSX adapters for precise work

Start here:

- [Getting Started](docs/GETTING-STARTED.md)
- [Command Reference](docs/COMMANDS.md)
- [Browser Guide](docs/BROWSER.md)
- [Office Guide](docs/OFFICE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Development](docs/DEVELOPMENT.md)
- [zWork Integration](docs/ZWORK-INTEGRATION.md)

## What It Is For

`dctl` is meant for agents that need to:

- launch and inspect desktop apps
- click, type, scroll, and focus deterministically
- read UI state from accessibility trees when available
- control browser tabs and browser-hosted apps without a terminal session
- edit Word and Excel files with structure-aware commands
- mix shell, file, browser, and office workflows in one run

## Current State

Implemented and working in this repo:

- Linux-first implementation
- unified CLI contract intended to carry over to macOS
- AT-SPI semantic backend on Linux
- `xdotool` fallback for window/input control on Linux when usable
- `ydotool` support for text and key fallback when configured
- app launch and `.desktop` enumeration
- screenshot capture through Linux helper backends
- native macOS backend behind the same CLI contract using AX, Quartz, `open`, and `screencapture`
- managed browser sessions with persistent profiles
- browser attachment to debug-enabled existing sessions
- direct DOCX and XLSX editing
- worksheet-oriented DOCX/XLSX helpers for question sheets and table filling

macOS support is implemented in code, but this repo has only been exercised live on Linux in this session.

## Quick Start

```bash
python3 -m dctl doctor
python3 -m dctl capabilities
python3 -m dctl list-apps
python3 -m dctl list-launchable
```

Browser session example:

```bash
python3 -m dctl browser start --session work --app chrome --url https://mail.google.com
python3 -m dctl browser sessions
python3 -m dctl browser tabs --session work
```

Document example:

```bash
python3 -m dctl docx worksheet-map paper.docx
python3 -m dctl docx answer-question paper.docx --question "What is photosynthesis?" --answer "Plants convert light energy into chemical energy."
python3 -m dctl xlsx fill-cell sheet.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number" --value 8
```

## Runtime Expectations

Best Linux experience:

- AT-SPI accessibility bus available
- `xdg-open` installed
- `grim`, `spectacle`, or `scrot` installed
- `xdotool` available for X11 or XWayland fallback

Wayland note:

- semantic AT-SPI access is the preferred path
- `ydotool` may work for input fallback, but it requires a running `ydotoold` and usable socket access
- `xdotool` is only useful where X11/XWayland access is actually available

## Why This Matters for zWork

zWork is strongest when it can stay text-native. `dctl` is the desktop layer that lets zWork:

- avoid brittle screenshot-only control
- use the browser as a controlled text surface
- edit files directly when the format is known
- fall back to GUI control only when necessary
