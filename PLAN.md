# Plan: dctl - Headless Desktop Control CLI for LLM Agents

## Product Goal

`dctl` is a standalone CLI that gives an LLM structured, non-interactive control over a user's desktop on macOS and Linux.

The point is not generic desktop automation for humans. The point is to give an agent:

- machine-readable access to GUI state
- deterministic commands for GUI actions
- precise fallbacks when semantic APIs are incomplete
- a unified interface across Linux and macOS

zWork will use `dctl` as the agent's "hands" for software that has no good native integration, including browsers, office apps, desktop utilities, Electron apps, file choosers, and ordinary GUI workflows.

---

## Problem Statement

LLMs are strong at:

- text
- planning
- shell commands
- files
- structured tool use

LLMs are weak at:

- opaque GUIs
- visual state hidden behind desktop apps
- precise clicks and focus changes
- workflows inside software with proprietary or awkward file formats

Today, zWork can run commands and edit files, but it cannot reliably:

- launch and focus desktop apps
- inspect current GUI state as structured data
- read labels, controls, values, and visible text from accessible apps
- click, type, scroll, and keypress with deterministic targeting
- bridge shell/file workflows with GUI workflows

`dctl` closes that gap.

---

## Scope

### In Scope for v1

- Launch apps and files
- Enumerate running apps and top-level windows
- Dump accessibility trees as JSON
- Query elements by selector
- Read text, values, labels, and state from accessible elements
- Click, focus, type, scroll, and press keys
- Capture screenshots
- Query what is at a screen coordinate
- Wait for UI state transitions
- Report permissions, dependencies, and capability availability
- Work on Linux and macOS with graceful degradation

### Explicitly Out of Scope for v1

- Windows support
- Full OCR-first automation
- Persistent background daemon
- Macro recording/replay
- Browser-specific protocol integrations
- Full compositor-specific Wayland support for every window manager

### Important v1 Limitation

`dctl` is strongest when an application exposes a usable accessibility tree.

Apps with poor accessibility support, custom rendering, game-like UIs, or canvas-heavy surfaces may require screenshot-based or OCR-based fallbacks. Those fallbacks should be planned for, but semantic accessibility access is the primary v1 path.

---

## Success Criteria

`dctl` is successful when an LLM can complete common GUI workflows entirely through CLI calls and structured output, without interactive terminal sessions.

Example workflows:

- open a browser, focus the address bar, navigate, and click a button
- launch a document app, locate a toolbar command, and trigger it
- inspect a dialog, read its labels and buttons, and choose the correct action
- wait for a file picker to appear, navigate it, and confirm a file selection
- combine shell/file work with GUI work in a single agent plan

---

## Core Design Principles

1. `JSON-first`
Every command returns structured JSON by default. Human-readable output is secondary.

2. `Headless and non-interactive`
No prompts, no pagers, no curses UI, no terminal interactivity requirements.

3. `Semantic before pixels`
Prefer accessibility APIs and native value/action interfaces before raw coordinate clicks.

4. `Capability-aware`
Detect what is actually available on this machine and report it clearly.

5. `Graceful degradation`
Use the best available backend for each capability and fail with actionable recovery data.

6. `Stateless commands with replayable locators`
Each invocation is independent. Returned elements include canonical locators that can be reused in later invocations.

7. `Agent-oriented ergonomics`
Output must be compact, stable, explicit, and easy for an LLM to reason about.

---

## User Model

The end user is non-technical. The direct caller is an AI agent.

This means:

- installation can have setup steps, but runtime behavior must be simple
- errors must explain what is missing in plain language
- permissions must be surfaced explicitly
- the CLI should avoid requiring the agent to infer platform-specific quirks

---

## Operating Model

`dctl` is not a general scripting shell. It is a desktop control plane with a small number of deterministic commands.

The agent workflow should look like:

1. Check capabilities and permissions
2. Launch or focus the target app
3. Query the app/window/tree
4. Resolve a control or text target
5. Perform the action
6. Re-query or wait for the expected result

---

## Capability Model

The implementation should be split by capability, not just by platform.

### Semantic UI

- accessibility tree enumeration
- element lookup
- element actions
- text/value extraction
- state inspection

### Windowing

- list top-level windows
- correlate windows to apps
- focus or raise a window when supported
- report geometry

### Input

- native accessibility actions when possible
- text insertion via accessibility value APIs when possible
- fallback key/mouse injection when necessary

### Capture

- full-screen screenshot
- region screenshot
- window screenshot when supported
- coordinate normalization against screenshots

### Launch

- list launchable apps
- launch app by name, desktop entry, bundle id, or path
- open a file or URL in the default app

### Diagnostics

- permissions
- dependencies
- backend selection
- degraded capabilities

---

## Platform Landscape

## Linux

Linux must be treated as multiple capability layers, not one backend.

### Accessibility

Primary semantic UI backend:

- AT-SPI2 over D-Bus

Expected use:

- enumerate accessible applications
- walk UI trees
- inspect roles, names, descriptions, states, actions, text, values
- perform semantic actions when supported

### Windowing

Linux window management differs by environment.

- X11: can use EWMH/X11 tooling
- Wayland: there is no universal `wmctrl` equivalent
- Wayland compositors vary significantly

Implication:

- `list-windows` and `focus` must degrade by backend
- window metadata may be partial on Wayland
- app/window correlation may sometimes be accessibility-first rather than compositor-first

### Capture

Linux screenshot support also varies.

- X11: native X11 tools work well
- Wayland: portal-based capture is the neutral path
- compositor-specific tools may exist and can be used opportunistically

Implication:

- prefer portal-aware screenshot support on Wayland-class environments
- support direct tools where available

### Input

Linux input injection is where most platform pain lives.

- semantic AT-SPI actions are preferred
- X11 raw input can use standard tools
- Wayland raw input may require privileged or consent-based paths

Implication:

- `type` should first try accessibility-native text/value insertion
- `click` should first try accessibility actions on matched elements
- raw input is fallback, not the primary design path

## macOS

macOS has strong native APIs, but capability is gated by permissions.

### Accessibility

Primary semantic UI backend:

- AXUIElement APIs

Expected use:

- enumerate apps and accessible windows
- inspect roles, labels, values, and actions
- perform semantic actions and focus

### Windowing

Window enumeration and geometry should use window services APIs, then be correlated with accessibility where needed.

### Capture

macOS supports screenshot capture, but screen capture permissions must be considered part of the product design.

### Input

As on Linux, semantic action/value APIs should be preferred first.
Fallback click and key simulation can be used where native accessibility actions are insufficient.

---

## Permission and Trust Model

Permissions are part of the product surface, not an edge case.

`dctl capabilities` and `dctl doctor` must report them explicitly.

### Linux Checks

- AT-SPI bus reachable
- D-Bus session available
- X11 or Wayland session detected
- portal availability
- raw input helpers available
- raw input helper privilege requirements

### macOS Checks

- Accessibility permission
- Screen Recording permission
- Automation permission if Apple Events are used

### Principle

No command should fail with a vague backend exception if the real issue is missing trust, permission, or helper setup.

---

## CLI Surface

All commands return JSON by default.

```text
dctl capabilities
dctl doctor

dctl list-apps
dctl list-windows
dctl list-launchable
dctl launch <TARGET>
dctl open <PATH_OR_URL>

dctl tree [--app APP] [--window WINDOW] [--depth N]
dctl element <SELECTOR>
dctl read <SELECTOR>
dctl describe <X> <Y>
dctl wait <SELECTOR> [--timeout SECONDS] [--interval MS]

dctl focus <SELECTOR>
dctl click <SELECTOR>
dctl type <TEXT> [--into SELECTOR]
dctl key <COMBO>
dctl scroll <SELECTOR_OR_DIRECTION> [--amount N]

dctl screenshot [--screen N] [--window WINDOW] [--region X,Y,W,H] [--output PATH] [--base64]
```

### Command Notes

- `capabilities`: machine-readable backend/capability matrix
- `doctor`: same core data, but with explicit remediation hints
- `launch`: launch app by app name, desktop entry, bundle id, or executable path
- `open`: open a file or URL using the platform default handler
- `tree`: dump accessibility tree
- `element`: resolve selector and return matches
- `read`: read text/value/label content from a resolved element
- `describe`: return semantic info for what is at screen coordinates, plus screenshot-relative context when possible
- `wait`: poll until selector matches, disappears, or changes state
- `type`: prefer semantic text insertion first, injection second

---

## Output Contract

All commands should return a predictable top-level envelope.

### Success

```json
{
  "status": "ok",
  "data": {},
  "meta": {
    "platform": "linux",
    "session_type": "wayland",
    "backend": {
      "accessibility": "atspi",
      "windowing": "portal",
      "capture": "portal",
      "input": "atspi+ydotool"
    },
    "warnings": [],
    "timestamp": "2026-04-22T21:00:00Z"
  }
}
```

### Error

```json
{
  "status": "error",
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Screen capture is not available because Screen Recording permission is missing.",
    "suggestion": "Grant Screen Recording permission, then rerun `dctl doctor`.",
    "details": {
      "capability": "capture",
      "backend": "quartz"
    }
  },
  "meta": {
    "platform": "macos",
    "timestamp": "2026-04-22T21:00:00Z"
  }
}
```

### Element Shape

```json
{
  "id": "ephemeral-backend-id",
  "locator": "app:\"Firefox\" AND path:/window[0]/toolbar[0]/text[0]",
  "app": {
    "name": "Firefox",
    "pid": 12345
  },
  "window": {
    "title": "Example Domain",
    "id": "window-ref"
  },
  "role": "text_field",
  "name": "Address and search bar",
  "description": "",
  "value": "https://example.com",
  "text": "https://example.com",
  "state": [
    "enabled",
    "visible",
    "focused",
    "editable"
  ],
  "actions": [
    "focus",
    "set_value"
  ],
  "bounds": {
    "x": 132,
    "y": 88,
    "width": 820,
    "height": 32
  }
}
```

### Important Locator Rule

`id` is backend-ephemeral and must not be the only reference.

Every returned element must also include a canonical `locator` string that can be reused by later commands. This is how `dctl` remains stateless while still supporting multi-step workflows.

---

## Selector Model

Selectors should be expressive enough for agents, but small enough to be stable.

### Supported Terms

- `app:"Firefox"`
- `window:"Preferences"`
- `role:button`
- `name:"Save"`
- `name~:"save"`
- `text:"Hello"`
- `text~:"hello"`
- `state:focused`
- `state:enabled`
- `path:/window[0]/toolbar[1]/button[2]`
- `@500,300`

### Boolean Grammar

```text
selector ::= or_expr
or_expr ::= and_expr ("OR" and_expr)*
and_expr ::= primary ("AND" primary)*
primary ::= app | window | role | name | text | state | path | coords
```

### Resolution Rules

- exact match terms narrow first
- case-insensitive terms are explicit with `~`
- if multiple candidates remain, return all candidates
- candidates should be ranked by visibility, enabled state, focused window, and spatial relevance

### Why This Matters

The agent must be able to:

- ask for broad context when uncertain
- refine selectors iteratively
- avoid depending on invisible internal backend IDs

---

## Backend Strategy

The architecture should choose providers per capability.

## Python Package Layout

```text
dctl/
├── dctl/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── models.py
│   ├── errors.py
│   ├── output.py
│   ├── selector.py
│   ├── capabilities.py
│   ├── doctor.py
│   ├── locator.py
│   ├── platform/
│   │   ├── __init__.py
│   │   ├── detect.py
│   │   ├── manager.py
│   │   ├── base.py
│   │   ├── linux/
│   │   │   ├── __init__.py
│   │   │   ├── accessibility_atspi.py
│   │   │   ├── capture_x11.py
│   │   │   ├── capture_portal.py
│   │   │   ├── input_x11.py
│   │   │   ├── input_wayland.py
│   │   │   ├── launch.py
│   │   │   ├── windows_x11.py
│   │   │   └── windows_fallback.py
│   │   └── macos/
│   │       ├── __init__.py
│   │       ├── accessibility_ax.py
│   │       ├── capture_quartz.py
│   │       ├── input_native.py
│   │       ├── input_fallback.py
│   │       ├── launch.py
│   │       └── windows_quartz.py
│   └── utils/
│       ├── image.py
│       ├── process.py
│       └── text.py
├── tests/
├── pyproject.toml
└── README.md
```

## Backend Manager Responsibilities

The manager should:

- detect OS and session type
- select a provider for each capability
- expose a single unified API to the CLI
- annotate outputs with which backend was used
- downgrade capabilities cleanly if a provider is unavailable

### Unified Capability Interface

The base interfaces should be grouped by capability, not one giant monolith.

Suggested interfaces:

- `AccessibilityProvider`
- `WindowProvider`
- `InputProvider`
- `CaptureProvider`
- `LaunchProvider`
- `DiagnosticsProvider`

This is cleaner than forcing every platform module to fully implement every feature the same way.

---

## Action Strategy

Actions should use a strict fallback order.

### Click

1. Resolve selector to accessible element
2. If element exposes a native action such as press/click, use it
3. Otherwise focus the containing window if possible
4. Otherwise click element center by coordinates using raw input
5. If none are available, fail with capability-specific error

### Type

1. Resolve target element if provided
2. If target exposes editable value/text interface, set value semantically
3. Otherwise focus target
4. Fallback to raw keystroke injection

### Focus

1. Use semantic focus on the element if available
2. Fallback to window raise/focus
3. Fallback to coordinate click if explicitly allowed

### Read

Prefer:

- text interface
- value interface
- accessible label/name/description

Do not rely on screenshots for `read` in v1 except as a future fallback mode.

---

## Coordinate and Screen Model

This is v1 infrastructure, not future polish.

`dctl` must define one normalized coordinate model for:

- element bounds
- window bounds
- screenshots
- `describe`
- coordinate selectors

### Requirements

- global desktop coordinates across all monitors
- screen metadata in responses
- scale factor reporting
- enough metadata to map screenshot pixels back to desktop coordinates

### Why This Matters

Without a coherent coordinate model, the following become unreliable:

- `@x,y` selectors
- screenshot region capture
- fallback clicks
- window geometry
- multi-monitor workflows

---

## Error Model

Errors must be stable and machine-readable.

### Core Error Codes

- `UNKNOWN`
- `INVALID_SELECTOR`
- `ELEMENT_NOT_FOUND`
- `MULTIPLE_MATCHES`
- `ACTION_NOT_SUPPORTED`
- `CAPABILITY_UNAVAILABLE`
- `PERMISSION_DENIED`
- `DEPENDENCY_MISSING`
- `BACKEND_FAILURE`
- `TIMEOUT`
- `PLATFORM_NOT_SUPPORTED`

### Error Requirements

Every error should include:

- stable code
- plain message
- remediation suggestion
- backend and capability context
- candidate matches where relevant

---

## Diagnostics Commands

These are first-class commands, not polish work.

### `dctl capabilities`

Should report:

- platform and session type
- active provider per capability
- whether each top-level command is available
- degraded features

### `dctl doctor`

Should additionally report:

- missing permissions
- missing helper tools
- missing environment variables or services
- setup hints per platform

For non-technical users, this is how supportability happens.

---

## Packaging and Dependency Strategy

Use Python for the CLI and platform integration.

Suggested core dependencies:

- `typer`
- `pydantic`

Platform-conditional dependencies:

- Linux accessibility bindings
- macOS accessibility bindings

### Dependency Principles

- prefer native APIs over shelling out when practical
- use external CLIs for fallback or platform glue where justified
- do not hardcode a single distro package manager in docs or error messages
- capability detection must be runtime-based

---

## Testing Strategy

Testing must reflect capability combinations, not just operating systems.

### Unit Tests

- selector parser
- locator rendering/parsing
- output envelope formatting
- error mapping
- backend selection logic
- coordinate normalization helpers

### Integration Test Matrix

#### Linux

- X11 with accessibility plus X11 input/capture
- Wayland with accessibility plus portal capture
- Wayland with accessibility plus privileged input helper
- GNOME
- KDE
- at least one wlroots-based compositor if possible

#### macOS

- Accessibility granted, Screen Recording denied
- Accessibility granted, Screen Recording granted
- common apps such as Finder, Safari, text editor

### Manual Workflow Tests

- launch browser and navigate
- interact with system file picker
- click toolbar button in office-style app
- read dialog labels and confirm/cancel actions
- type into text field via semantic path
- fallback to injected typing where semantic entry fails

---

## Implementation Plan

## Phase 1: Contract and Skeleton

Files:

- `pyproject.toml`
- `dctl/__init__.py`
- `dctl/__main__.py`
- `dctl/cli.py`
- `dctl/models.py`
- `dctl/errors.py`
- `dctl/output.py`
- `dctl/selector.py`
- `dctl/locator.py`
- `dctl/platform/base.py`
- `dctl/platform/detect.py`
- `dctl/platform/manager.py`

Deliverables:

- command skeleton
- JSON envelope
- selector parser
- canonical locator format
- backend manager interface

Milestone:

- mock commands return valid structured output and stable errors

## Phase 2: Diagnostics and Capability Detection

Files:

- `dctl/capabilities.py`
- `dctl/doctor.py`
- platform detection modules

Deliverables:

- `dctl capabilities`
- `dctl doctor`
- permission/dependency matrix
- backend selection reporting

Milestone:

- user can run one command and understand what will and will not work on this machine

## Phase 3: Linux Semantic Backend

Files:

- `dctl/platform/linux/accessibility_atspi.py`
- `dctl/platform/linux/launch.py`
- `dctl/platform/linux/windows_fallback.py`

Deliverables:

- list apps
- tree dump
- element resolution
- read value/text/state
- semantic click/focus where available
- app launch support

Milestone:

- Linux agent can inspect and act on accessible UI without raw input

## Phase 4: Linux Capture, Windowing, and Input

Files:

- `dctl/platform/linux/windows_x11.py`
- `dctl/platform/linux/capture_x11.py`
- `dctl/platform/linux/capture_portal.py`
- `dctl/platform/linux/input_x11.py`
- `dctl/platform/linux/input_wayland.py`

Deliverables:

- screenshot support
- improved window enumeration
- raw input fallback support
- coordinate-based describe and fallback click

Milestone:

- Linux workflows work across X11 and degrade correctly on Wayland

## Phase 5: macOS Backend

Files:

- `dctl/platform/macos/accessibility_ax.py`
- `dctl/platform/macos/windows_quartz.py`
- `dctl/platform/macos/capture_quartz.py`
- `dctl/platform/macos/input_native.py`
- `dctl/platform/macos/input_fallback.py`
- `dctl/platform/macos/launch.py`

Deliverables:

- semantic accessibility support
- window enumeration
- screenshot support
- launch/open support
- semantic and fallback input

Milestone:

- macOS reaches Linux feature parity where platform policy allows it

## Phase 6: Agent Workflow Polish

Files:

- CLI and tests
- README

Deliverables:

- `wait`
- `describe`
- `list-launchable`
- strong error suggestions
- examples for zWork integration
- packaging and installation docs

Milestone:

- zWork can complete real multi-step GUI workflows using only non-interactive CLI calls

---

## zWork Integration Guidance

zWork should expose `dctl` as several narrow tools rather than one generic shell wrapper.

Examples:

- `desktop_capabilities`
- `desktop_launch`
- `desktop_list_apps`
- `desktop_list_windows`
- `desktop_tree`
- `desktop_element`
- `desktop_read`
- `desktop_click`
- `desktop_type`
- `desktop_key`
- `desktop_screenshot`

### Why

Narrow tools make agent prompting and tool selection more reliable than one arbitrary `run_command` bridge.

---

## Open Decisions

1. Whether `doctor` should be human-oriented text by default or JSON by default with an optional pretty mode
2. Whether `launch` should support fuzzy app matching or require exact app identity by default
3. Whether `wait` should support conditions beyond existence, such as focused, enabled, hidden, or value changed
4. Which Linux helper tools are supported in v1 versus documented as optional
5. Whether a future OCR mode should live in `dctl` or in a separate companion tool

---

## Future Enhancements

- OCR and text search for inaccessible apps
- live UI event watching
- drag and drop
- semantic table extraction for office apps
- recorded workflow replay
- richer browser helpers
- Windows support

---

## Summary

`dctl` should be built as an agent-first desktop control plane.

The right design is:

- semantic accessibility APIs first
- capability-specific backends
- non-interactive JSON contracts
- explicit diagnostics and permissions
- coordinate-safe fallbacks
- strong degradation behavior across Linux and macOS

That is the foundation zWork needs if the agent is going to use the desktop like a human, but reason about it like a machine.
