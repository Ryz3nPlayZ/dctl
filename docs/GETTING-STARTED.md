# Getting Started

## Prerequisites

- Python 3.11+
- Linux, macOS, or Windows

## Install

From the repository root:

```bash
pip install -e .
```

For macOS backends:

```bash
pip install -e '.[macos]'
```

For Windows backends:

```bash
pip install -e '.[windows]'
```

For development (includes pytest):

```bash
pip install -e '.[dev]'
```

After install, the `dctl` command is available on PATH. You can also run `python3 -m dctl`.

## Verify the Installation

Run diagnostics first:

```bash
dctl doctor
dctl capabilities
```

These report:
- which platform and session type was detected
- which backend is active for each capability
- which helper tools are available or missing
- which commands are expected to work
- permission and setup issues with remediation hints

## First Commands

### Desktop

```bash
# List running applications
dctl list-apps

# List open windows
dctl list-windows

# Dump the accessibility tree
dctl tree --depth 3

# Find a specific element
dctl element 'app:"Firefox" AND role:text_field'

# Read text from an element
dctl read 'role:text_field AND name:"Address"'

# Click a button
dctl click 'role:button AND name:"Save"'

# Type into a field
dctl type "Hello" --into 'role:text_field AND name:"Search"'
```

### Browser

Start a managed browser session:

```bash
dctl browser start --session work --app chrome --url https://example.com
dctl browser tabs --session work
dctl browser snapshot active --session work
```

Navigate and interact:

```bash
dctl browser open https://docs.google.com --session work
dctl browser type active "Hello" --selector 'input[name="q"]' --clear --session work
dctl browser press active enter --session work
```

### Documents

Read and edit DOCX files:

```bash
dctl docx read notes.docx
dctl docx paragraphs notes.docx
dctl docx worksheet-map notes.docx
dctl docx answer-question notes.docx --question "Name:" --answer "Ada Lovelace"
```

Read and edit XLSX files:

```bash
dctl xlsx sheets data.xlsx
dctl xlsx read data.xlsx Sheet1 A1:D10
dctl xlsx worksheet-map data.xlsx
dctl xlsx fill-cell data.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number" --value 8
```

## Choosing the Right Backend

| Task | Use |
|---|---|
| Web apps (Gmail, Google Docs, etc.) | `dctl browser` |
| `.docx` files | `dctl docx` |
| `.xlsx` files | `dctl xlsx` |
| Live LibreOffice control on Linux | `dctl libreoffice` |
| Desktop apps with no better path | Desktop commands (`click`, `type`, `key`) |

The general rule: prefer the most structured path available. File-model editing beats browser control beats desktop input.

## Runtime Dependencies

### Linux

Best experience with:
- AT-SPI accessibility bus available
- `xdg-open` for file/URL launching
- `xdotool` for X11/XWayland input fallback
- `ydotool` + `ydotoold` for Wayland input fallback
- `grim`, `spectacle`, or `scrot` for screenshots
- `soffice` or `libreoffice` for LibreOffice commands

### macOS

- Accessibility permission (System Settings > Privacy & Security > Accessibility)
- Screen Recording permission for screenshots

### Windows

- No special permissions beyond normal user access

## Next Steps

- [Command Reference](COMMANDS.md) — full CLI reference
- [Browser Guide](BROWSER.md) — browser automation in depth
- [Office Guide](OFFICE.md) — document editing in depth
- [Architecture](ARCHITECTURE.md) — how dctl works internally
