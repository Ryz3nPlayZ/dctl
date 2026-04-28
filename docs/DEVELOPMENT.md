# Development

## Setup

```bash
pip install -e '.[dev]'
```

This installs `dctl` in editable mode with pytest and coverage tools.

Platform extras for backend development:

```bash
pip install -e '.[macos]'     # macOS: pyobjc-framework-ApplicationServices, Quartz, Cocoa
pip install -e '.[windows]'   # Windows: comtypes, Pillow
```

## Running

```bash
dctl capabilities                    # If installed
python3 -m dctl capabilities         # From source without install
PYTHONPATH=. python3 -m dctl doctor  # Explicit path
```

## Testing

```bash
python3 -m pytest tests/ -v
python3 -m pytest tests/ --cov=dctl --cov-report=term-missing
```

Compile check:

```bash
python3 -m compileall dctl
```

## Project Structure

```
dctl/
  dctl/
    __init__.py          Version (0.1.0)
    __main__.py          Entry point → cli.main()
    cli.py               Argparse CLI definition and dispatch (~780 lines)
    models.py            Dataclasses: Bounds, WindowInfo, AppInfo, ElementInfo
    errors.py            DctlError with 11 stable error codes
    output.py            emit_success / emit_error JSON envelope
    selector.py          Selector parser with boolean AND/OR logic
    locator.py           Canonical locator builder
    capabilities.py      Runtime capability matrix per platform
    doctor.py            Diagnostic report builder
    adapters/
      browser_cdp.py     Chrome DevTools Protocol adapter (~1470 lines)
      docx_files.py      DOCX editing via python-docx (~570 lines)
      xlsx_files.py      XLSX editing via openpyxl (~390 lines)
      libreoffice_uno.py LibreOffice UNO bridge (~420 lines)
    platform/
      base.py            Abstract DesktopBackend base class
      detect.py          Environment detection (OS, session, helpers)
      manager.py         DesktopManager — unified API routing (~640 lines)
      linux/
        accessibility_atspi.py  AT-SPI semantic UI access
        input.py               xdotool/ydotool input helpers
        launch.py              App launch via xdg-open/gtk-launch
        windowing.py           xdotool window enumeration
      macos/
        backend.py             AX/Quartz/AppKit full backend
      windows/
        backend.py             Windows unified backend
        accessibility_uia.py   UIAutomation semantic access
        capture_gdi.py         GDI screenshot capture
        input_sendinput.py     SendInput keyboard/mouse
        launch.py              ShellExecuteW app launch
        windowing_win32.py     Win32 window enumeration
  agents/
    dctl_tools.json       Tool definitions for LLM agents
    system_prompt_addon.md Agent prompt instructions
  tests/                  Unit tests
  docs/                   Documentation
  benchmarks/             Evaluation suite
  scripts/                Utility scripts
```

## Coding Conventions

- All commands return structured JSON via `emit_success` / `emit_error`
- No interactive prompts or terminal UI
- Prefer semantic backends over raw input helpers
- Prefer capability-aware failure messages over silent fallback
- Keep commands deterministic — same input, same output

## Adding a New Command

1. Add parser wiring in `dctl/cli.py`
2. Add implementation in the relevant adapter or platform backend
3. Update capability detection in `capabilities.py` if the command depends on a helper
4. Add tests for the happy path and the failure path
5. Update docs

## Adding Browser Behavior

Browser work needs:

- command-line plumbing in `cli.py`
- CDP command or runtime evaluation in `adapters/browser_cdp.py`
- session-aware testing
- selectors that match actual browser DOM structure
- a verification step after any mutation

## Adding Office Behavior

For DOCX/XLSX features:

- test against a temporary file
- verify the original file is preserved when backups are expected
- verify the modified structure, not just the command return value

## Dependencies

Core (always installed):
- `websockets>=12` — CDP browser communication
- `python-docx>=1.1.0` — DOCX editing
- `openpyxl>=3.1.0` — XLSX editing

Platform-conditional:
- macOS: `pyobjc-framework-ApplicationServices`, `pyobjc-framework-Quartz`, `pyobjc-framework-Cocoa`
- Windows: `comtypes>=1.4`, `Pillow>=10`

Development:
- `pytest>=8`, `pytest-cov`
