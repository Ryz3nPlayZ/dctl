# Roadmap

## Vision

`dctl` aims to be the standard desktop control layer for AI agents. Every agent that needs to interact with GUI software — browsers, office apps, desktop utilities — should reach for `dctl` as the structured, reliable, non-interactive control plane.

The core principle: **semantic before pixels.** Agents should reason about UI state as structured data, not guess from screenshots.

## Current State (v0.1.0)

Implemented and working:

- **Linux desktop control** — AT-SPI semantic backend, xdotool/ydotool fallback, app launch, window enumeration
- **macOS desktop control** — AX/Quartz/AppKit backend (implemented, needs live testing)
- **Windows desktop control** — UIAutomation/SendInput/GDI/Win32 backend (implemented)
- **Browser automation** — managed CDP sessions, tab control, DOM/AX/text inspection, caret control, batch operations
- **DOCX editing** — full read/write/append/replace, worksheet-map, answer-question, fill-table
- **XLSX editing** — read/write, worksheet-map, locate-cell, fill-cell, fill-table
- **LibreOffice UNO** — live Writer and Calc control on Linux
- **Diagnostics** — `capabilities` and `doctor` commands with per-platform detection
- **Agent integration** — tool definitions, system prompt addon, Python example
- **Evaluation** — benchmark suite with scenario-based testing

## Near-Term (v0.2.0)

### Reliability and Testing
- End-to-end test coverage for all three platforms
- CI pipeline with Linux testing, macOS/Windows on runners
- Integration tests for browser adapter against real pages
- Stress tests for batch mode and session persistence

### macOS Polish
- Live testing on macOS hardware
- Accessibility permission flow documentation
- Screen Recording permission handling
- AppKit integration edge cases

### Windows Polish
- Live testing on Windows
- UIAutomation coverage validation
- SendInput edge cases (Unicode, special keys)

### Browser Improvements
- Firefox CDP support (via remote debugging)
- Network request interception
- File upload/download handling
- Multi-step wait conditions (wait for network idle, wait for element count)

## Mid-Term (v0.3.0)

### Observation Mode
- Watch for UI events (element appears, disappears, state changes)
- Real-time event stream for agent context
- Reduced polling in favor of event-driven updates

### Enhanced Selectors
- Regex support in name/text terms
- Negation operators (`NOT role:panel`)
- Index selectors for disambiguation (`role:button[2]`)
- Relative selectors (child of, sibling of)

### OCR Fallback
- Screenshot + OCR text extraction for inaccessible apps
- Text search across screen regions
- Coordinate inference from OCR results

### Document Intelligence
- Table detection and extraction from DOCX
- Style-aware editing (preserve bold, italic, headers)
- Template-based document generation
- PDF read support

### Performance
- Connection pooling for browser sessions
- Lazy backend initialization
- Parallel command execution where safe

## Long-Term (v1.0.0)

### Stable API Contract
- Pin the output envelope format
- Pin the selector grammar
- Pin the error code set
- Semantic versioning guarantee

### Packaging and Distribution
- PyPI publish
- Homebrew formula
- AUR package
- Windows installer with bundled Python

### Advanced Agent Features
- Workflow recording and replay
- Action macros for common patterns
- Confidence scoring on element matches
- Automatic fallback chain selection

### Extended Platform Support
- Android via accessibility (adb + uiautomator)
- Remote desktop control (SSH + headless)
- Container-aware desktop access

### Ecosystem
- Plugin system for custom backends
- Community-contributed app profiles (known selectors for popular apps)
- Shared agent prompt templates
- Integration with agent frameworks (LangChain, AutoGPT, CrewAI)

## Contributing

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup and coding conventions. Contributions are welcome for any roadmap item — open an issue first to coordinate.
