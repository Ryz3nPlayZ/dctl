# Architecture

`dctl` is organized by capability, not by a single monolithic desktop backend.

The intent is to give an LLM a small number of deterministic primitives that can be composed into larger workflows.

## Core Layers

### 1. Desktop orchestration

`dctl` routes every command through a `DesktopManager` that chooses the best available backend for the current platform and session.

That orchestration layer handles:

- capability detection
- platform selection
- graceful fallback between backends
- structured errors when a capability is missing

### 2. Semantic UI access

This is the preferred path when an app exposes accessibility information.

Linux uses AT-SPI.
macOS uses AX / ApplicationServices.

This layer supports:

- tree enumeration
- element lookup
- text/value reading
- element actions when available
- focus and selection logic

### 3. Windowing and raw input

When semantic access is incomplete, `dctl` falls back to windowing and injection helpers.

Linux currently uses:

- `xdotool` when X11 or XWayland is reachable
- `ydotool` when configured for Wayland-native injection

The point is not to depend on these first. The point is to keep the CLI useful when the semantic path is incomplete.

### 4. Capture

Capture is used for inspection and recovery, but it is not the primary control surface.

Linux prefers:

- `grim`
- `spectacle`
- `scrot`

macOS uses `screencapture`.

### 5. Browser control

Browser control is a separate substrate.

`dctl browser` wraps Chrome DevTools Protocol and supports:

- persistent managed browser sessions
- attachment to debug-enabled browsers
- tab enumeration and activation
- DOM / AX / text / selection inspection
- typed and key-based editing
- batch operations for fewer round trips

This is the right layer for browser-hosted editors and other web apps.

### 6. Office and file-model adapters

These are the precision layers for structured documents and spreadsheets.

- `dctl libreoffice` uses UNO
- `dctl docx` uses `python-docx`
- `dctl xlsx` uses `openpyxl`

The design goal is to edit known file formats directly when possible instead of pretending everything must be done through clicks.

## Design Principles

### Semantic before pixels

If the app exposes structured state, use that first.

Examples:

- accessibility tree over screenshots
- document model over GUI typing
- sheet/cell semantics over pointer coordinates

### Replayable locators

The agent should be able to take a returned target and use it again later.

Examples:

- accessibility selectors
- browser tab IDs
- browser session names
- worksheet row and column labels

### Stateless commands

Each CLI invocation stands alone.

That keeps the interface predictable for agents and easy to restart after errors.

### Clear degradation

When a capability is unavailable, `dctl` should say so directly.

The output should explain:

- what is missing
- what backend was attempted
- how to recover

## Browser Session Model

`dctl browser start --session NAME` creates a persistent browser profile under `.dctl/browser/profiles/NAME`.

Session metadata is stored under `.dctl/browser/sessions/NAME.json`.

That gives `dctl` a managed browser surface with:

- login persistence
- cookies and local profile state
- stable session names
- attach and resume behavior

This is the correct base for agent-owned browser control.

## zWork Integration Philosophy

zWork should not think of `dctl` as a screenshot tool.

It should think of `dctl` as:

- browser hands
- office hands
- file-format hands
- desktop fallback hands

That division is what lets the agent stay mostly text-native while still operating GUI software when necessary.

