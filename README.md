# dctl

Headless desktop control CLI for LLM agents.

`dctl` gives an AI agent structured, non-interactive control over a user's desktop — JSON-first output, deterministic commands, and semantic UI access with raw fallbacks when needed.

## What It Does

- **Desktop UI automation** — launch apps, enumerate windows, walk accessibility trees, click, type, scroll, and take screenshots
- **Browser control** — managed Chrome sessions via CDP, tab management, DOM/AX inspection, caret control, batch operations
- **Document editing** — direct DOCX and XLSX editing via python-docx and openpyxl, no GUI required
- **LibreOffice bridge** — live Writer and Calc control through the UNO API
- **Cross-platform** — Linux (AT-SPI + xdotool/ydotool), macOS (AX + Quartz), Windows (UIAutomation + SendInput)

## Design Philosophy

**Semantic before pixels.** `dctl` prefers accessibility APIs and structured file formats over screenshot scraping. It falls back to raw input injection only when necessary.

**Stateless commands.** Each CLI invocation is independent. Elements include canonical locators that can be reused in later calls.

**Agent-oriented output.** Every command returns a predictable JSON envelope with status, data, and metadata.

## Install

```bash
pip install -e .
```

Platform extras:

```bash
pip install -e '.[macos]'    # macOS backends
pip install -e '.[windows]'  # Windows backends
```

Requires Python 3.11+.

## Quick Start

```bash
# Check what's available on this machine
dctl doctor
dctl capabilities

# Desktop control
dctl list-apps
dctl list-windows
dctl tree --depth 3
dctl element 'role:button AND name:"Save"'
dctl click 'role:button AND name:"OK"'
dctl type "Hello, world" --into 'role:text_field'

# Browser session
dctl browser start --session work --app chrome --url https://mail.google.com
dctl browser tabs --session work
dctl browser snapshot active --session work
dctl browser type active "Hello" --selector 'input[name="subjectbox"]' --clear --session work

# Document editing
dctl docx read paper.docx
dctl docx worksheet-map paper.docx
dctl docx answer-question paper.docx --question "What is photosynthesis?" --answer "Plants convert light energy into chemical energy."

dctl xlsx sheets data.xlsx
dctl xlsx locate-cell data.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number"
dctl xlsx fill-cell data.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number" --value 8
```

## Output Format

Every command returns JSON:

```json
{
  "status": "ok",
  "data": { ... },
  "meta": {
    "platform": "linux",
    "session_type": "wayland",
    "backend": { ... },
    "timestamp": "2026-04-27T12:00:00Z"
  }
}
```

Errors include a stable code, message, and remediation suggestion:

```json
{
  "status": "error",
  "error": {
    "code": "ELEMENT_NOT_FOUND",
    "message": "No element matched the selector.",
    "suggestion": "Try broadening the selector or use 'tree' to inspect available elements."
  }
}
```

## Documentation

| Document | Description |
|---|---|
| [Getting Started](docs/GETTING-STARTED.md) | Installation and first-run guide |
| [Command Reference](docs/COMMANDS.md) | Full CLI command reference |
| [Architecture](docs/ARCHITECTURE.md) | System design and backend strategy |
| [Browser Guide](docs/BROWSER.md) | Browser automation with CDP |
| [Office Guide](docs/OFFICE.md) | DOCX, XLSX, and LibreOffice editing |
| [Configuration](docs/CONFIGURATION.md) | Environment variables and runtime config |
| [Development](docs/DEVELOPMENT.md) | Contributing and extending dctl |
| [Roadmap](ROADMAP.md) | Project vision and planned milestones |
| [Agent Integration](agents/README.md) | Integrating dctl into LLM agent loops |

## Project Structure

```
dctl/
  dctl/
    cli.py              CLI definition and command dispatch
    models.py           Data models (Bounds, WindowInfo, AppInfo, ElementInfo)
    errors.py           Stable error codes and exit codes
    output.py           JSON output envelope
    selector.py         Selector parser with boolean AND/OR logic
    locator.py          Canonical locator builder
    capabilities.py     Runtime capability detection
    doctor.py           Diagnostic report builder
    adapters/
      browser_cdp.py    Chrome DevTools Protocol adapter
      docx_files.py     DOCX editing via python-docx
      xlsx_files.py     XLSX editing via openpyxl
      libreoffice_uno.py LibreOffice UNO bridge
    platform/
      base.py           Abstract DesktopBackend
      detect.py         OS/session/helper detection
      manager.py        DesktopManager — unified API routing
      linux/            AT-SPI, xdotool, ydotool, grim/scrot
      macos/            AX, Quartz, AppKit, screencapture
      windows/          UIAutomation, SendInput, GDI, Win32
  agents/                LLM agent integration artifacts
  tests/                 Unit tests
  docs/                  Documentation
```

## License

MIT
