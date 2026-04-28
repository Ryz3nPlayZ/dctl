# Architecture

`dctl` is organized by capability, not by a single monolithic desktop backend. Each command routes through a `DesktopManager` that picks the best available backend for the current platform and session.

## Core Layers

### 1. Desktop Orchestration

`DesktopManager` is the central routing layer. It handles:

- platform and session detection
- backend selection per capability
- graceful fallback between backends
- structured error reporting when a capability is unavailable

Every CLI command flows through the manager, which delegates to platform-specific implementations.

### 2. Semantic UI Access

The preferred path for interacting with desktop applications. Uses accessibility APIs to expose structured UI state.

| Platform | Backend | API |
|---|---|---|
| Linux | AT-SPI2 | D-Bus via GObject introspection |
| macOS | AX | AXUIElement / ApplicationServices |
| Windows | UIAutomation | comtypes |

Capabilities:
- tree enumeration and traversal
- element lookup by selector
- text and value reading
- semantic actions (click, set value) when supported
- focus and selection

### 3. Windowing and Raw Input

When semantic access is incomplete, `dctl` falls back to window management and input injection.

| Platform | Windowing | Input |
|---|---|---|
| Linux X11 | xdotool | xdotool |
| Linux Wayland | AT-SPI | ydotool |
| macOS | Quartz / AppKit | CGEvent |
| Windows | Win32 | SendInput |

### 4. Capture

Screenshot support for inspection and verification.

| Platform | Tools |
|---|---|
| Linux | grim, spectacle, scrot |
| macOS | screencapture |
| Windows | GDI |

### 5. Browser Control

A separate substrate built on Chrome DevTools Protocol (CDP). Supports:

- persistent managed browser sessions with profile and login state
- attachment to debug-enabled existing browsers
- tab enumeration, activation, and closure
- DOM, accessibility tree, text, and selection inspection
- typed input with clear, caret control, and key combos
- JavaScript evaluation
- batch operations for fewer round trips

### 6. File-Model Adapters

Direct file editing without GUI interaction.

| Format | Adapter | Library |
|---|---|---|
| `.docx` | `dctl docx` | python-docx |
| `.xlsx` | `dctl xlsx` | openpyxl |
| Live documents | `dctl libreoffice` | UNO bridge |

## Design Principles

**Semantic before pixels.** Accessibility tree over screenshots. Document model over GUI typing. Cell semantics over coordinate clicks.

**Replayable locators.** Every returned element includes a canonical locator string that can be reused in later commands. This is how `dctl` stays stateless while supporting multi-step workflows.

**Stateless commands.** Each CLI invocation stands alone. No background daemon, no session state outside of managed browser profiles.

**Clear degradation.** When a capability is unavailable, the output explains what is missing, which backend was attempted, and how to recover.

**Agent-oriented output.** Compact, stable, explicit JSON that an LLM can parse and reason about without ambiguity.

## Package Structure

```
dctl/
  __init__.py          Version
  __main__.py          Entry point
  cli.py               Argparse CLI definition and dispatch
  models.py            Data models
  errors.py            Error codes and exit codes
  output.py            JSON envelope formatting
  selector.py          Selector parser (boolean AND/OR)
  locator.py           Canonical locator builder
  capabilities.py      Runtime capability matrix
  doctor.py            Diagnostic report builder
  adapters/
    browser_cdp.py     CDP browser adapter
    docx_files.py      DOCX editing
    xlsx_files.py      XLSX editing
    libreoffice_uno.py LibreOffice UNO bridge
  platform/
    base.py            Abstract DesktopBackend
    detect.py          Environment detection
    manager.py         DesktopManager routing
    linux/             Linux backends
    macos/             macOS backends
    windows/           Windows backends
```

## Selector Model

Selectors use a boolean query language for targeting UI elements:

```
selector ::= or_expr
or_expr  ::= and_expr ("OR" and_expr)*
and_expr ::= primary ("AND" primary)*
primary  ::= app | window | role | name | name~ | text | text~ | state | path | @x,y
```

Supported terms:

| Term | Match | Example |
|---|---|---|
| `app:"Firefox"` | Exact app name | `app:"Firefox"` |
| `window:"Settings"` | Exact window title | `window:"Preferences"` |
| `role:button` | Element role | `role:text_field` |
| `name:"Save"` | Exact name | `name:"Submit"` |
| `name~:"save"` | Case-insensitive name | `name~:"save"` |
| `text:"Hello"` | Contains text | `text:"Welcome"` |
| `text~:"hello"` | Case-insensitive text | `text~:"error"` |
| `state:focused` | Element state | `state:editable` |
| `path:/window[0]/button[1]` | Structural path | `path:/window[0]/toolbar[1]/button[2]` |
| `@500,300` | Screen coordinates | `@500,300` |

## Error Model

11 stable error codes with consistent exit codes:

| Code | Exit Code | Meaning |
|---|---|---|
| `UNKNOWN` | 1 | Unhandled exception |
| `ELEMENT_NOT_FOUND` | 2 | Selector matched nothing |
| `MULTIPLE_MATCHES` | 3 | Selector matched multiple elements |
| `ACTION_NOT_SUPPORTED` | 4 | Element doesn't support the requested action |
| `PERMISSION_DENIED` | 5 | OS permission missing |
| `DEPENDENCY_MISSING` | 6 | Required tool not found |
| `PLATFORM_NOT_SUPPORTED` | 7 | Feature not available on this platform |
| `TIMEOUT` | 8 | Operation timed out |
| `INVALID_SELECTOR` | 9 | Selector syntax error |
| `CAPABILITY_UNAVAILABLE` | 10 | Backend can't provide this capability |
| `BACKEND_FAILURE` | 11 | Backend error |

Every error includes a code, human-readable message, and remediation suggestion.
