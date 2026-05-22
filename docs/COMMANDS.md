# Command Reference

All commands return JSON. Use `dctl` directly after install, or `python3 -m dctl` from source.

## Diagnostics

```bash
dctl capabilities       # Machine-readable backend/capability matrix
dctl doctor             # Diagnostic report with issues and remediation hints
```

Run these first when something doesn't work.

## Desktop

### Inventory

```bash
dctl list-apps           # List running applications
dctl list-windows        # List open windows
dctl list-launchable     # List launchable apps (.desktop entries, bundles, etc.)
```

### Launch

```bash
dctl launch <TARGET>     # Launch app by name, desktop entry, or path
dctl open <PATH_OR_URL>  # Open file or URL in default handler
```

### Accessibility Tree

```bash
dctl tree [--app APP] [--window WINDOW] [--depth N]
```

Dumps the accessibility tree as JSON. Default depth is 5.

### Element Lookup

```bash
dctl element <SELECTOR>  # Find elements matching selector
dctl read <SELECTOR>     # Read text/value/label from matched element
dctl describe <X> <Y>    # Return semantic info at screen coordinates
```

### Actions

```bash
dctl focus <SELECTOR>                     # Focus an element
dctl click <SELECTOR>                     # Click an element
dctl type <TEXT> [--into SELECTOR]        # Type text (optionally into a target)
dctl key <COMBO>                          # Press a key combo (e.g. ctrl+s, alt+F4)
dctl scroll <DIRECTION> [--amount N]     # Scroll up/down/left/right
```

### Wait

```bash
dctl wait <SELECTOR> [--timeout SECONDS] [--interval MS]
```

Poll until the selector matches. Default timeout 10s, interval 250ms.

### Screenshot

```bash
dctl screenshot [--window WINDOW] [--region X,Y,W,H] [--output PATH] [--base64]
```

## Browser

### Session Management

```bash
dctl browser start [--session NAME] [--app chrome|chromium|edge] [--url URL] [--headless]
dctl browser stop [--session NAME] [--pid PID]
dctl browser sessions
dctl browser session-info <SESSION>
dctl browser discover [--port PORT] [--endpoint URL]
dctl browser attach [--session NAME] [--port PORT] [--endpoint URL]
```

- `start` creates a persistent agent-owned browser with a named profile
- `discover` finds debug-enabled browsers already running
- `attach` binds to a running debug endpoint
- Sessions persist cookies, login state, and profile data under `.dctl/browser/`

### Tab Control

```bash
dctl browser tabs [--session NAME] [--include-non-pages] [--url-contains TEXT] [--title-contains TEXT]
dctl browser active-tab [--session NAME]
dctl browser targets [--session NAME]
dctl browser open <URL> [--session NAME]
dctl browser activate <TARGET> [--session NAME]
dctl browser close <TARGET> [--session NAME]
```

`tabs` now returns ranked candidates with `targetScore`, `isPreferred`, and `recommendedTargetId`. After `browser activate` or `browser open`, the session keeps a preferred working tab; `active` resolves to that tab when available.

### Inspection

```bash
dctl browser snapshot <TARGET> [--session NAME] [--text-limit N] [--max-items N] [--min-text N] [--max-text N] [--strict]
dctl browser selector <TARGET> <CSS> [--sample-limit N] [--session NAME]
dctl browser actions <TARGET> [--query TEXT] [--role ROLE] [--sample-limit N] [--session NAME]
dctl browser text <TARGET> [--selector CSS] [--strict-selector] [--session NAME]
dctl browser dom <TARGET> [--selector CSS] [--depth N] [--strict-selector] [--session NAME]
dctl browser ax <TARGET> [--selector CSS] [--strict-selector] [--session NAME]
dctl browser selection <TARGET> [--session NAME]
dctl browser caret <TARGET> [--selector CSS] [--start N] [--end N] [--session NAME]
dctl browser wait-url <TARGET> <NEEDLE> [--timeout N] [--session NAME]
dctl browser wait-selector <TARGET> <CSS> [--timeout N] [--strict-selector] [--session NAME]
```

`snapshot` returns a structured view of visible page state (text, headings, landmarks, interactive elements, detected LaTeX/MathML payloads, visual structure hints from SVG/canvas/image surfaces, and extraction coverage diagnostics). Use `--strict` to fail when extraction quality issues are detected.
`selector` is a read-only selector diagnostic to verify match cardinality before interactive commands.

### Editing

```bash
dctl browser act <TARGET> [--query TEXT] [--role ROLE] [--action-id N] [--wait-selector CSS] [--wait-url TEXT] [--snapshot] [--session NAME]
dctl browser click <TARGET> <CSS> [--session NAME]
dctl browser click-action <TARGET> <ACTION_ID> [--query TEXT] [--role ROLE] [--session NAME]
dctl browser type <TARGET> <TEXT> [--selector CSS] [--clear] [--session NAME]
dctl browser press <TARGET> <COMBO> [--session NAME]
dctl browser eval <TARGET> <EXPRESSION> [--session NAME] [--no-await-promise] [--return-by-value]
dctl browser send <TARGET> <CDP_METHOD> [--params JSON] [--session NAME]
```

`browser click` and `browser type --selector ...` fail with `MULTIPLE_MATCHES` when selectors are ambiguous.
`browser text/dom/ax/wait-selector` also fail on ambiguous selectors when `--strict-selector` is enabled.
`browser click-action` fails loudly with explicit diagnostics when `ACTION_ID` is missing or disabled.
`browser act` composes semantic discovery + click + optional wait/snapshot into one deterministic call and returns per-step results.

### Batch Mode

Chain multiple operations in a single round trip:

```bash
dctl browser batch <TARGET> '<JSON_ARRAY>' [--session NAME]
```

Example:

```bash
dctl browser batch active '[
  {"op":"activate"},
  {"op":"wait-selector","selector":"textarea","timeout":5},
  {"op":"type","selector":"textarea","clear":true,"text":"Hello from dctl"},
  {"op":"press","combo":"ctrl+enter"}
]' --session work
```

Supported batch operations: `activate`, `click`, `type`, `press`, `eval`, `actions`, `click-action`, `act`, `wait-selector`, `wait-url`, `snapshot`, `text`, `dom`, `ax`, `selector`, `selection`, `caret`.
Batch responses include `timingsMs` with total and per-operation latency measurements.

## LibreOffice

### Process Control

```bash
dctl libreoffice start [--headless]
dctl libreoffice stop [--pid PID]
dctl libreoffice docs
dctl libreoffice open <PATH>
dctl libreoffice info <DOCUMENT>
dctl libreoffice save <DOCUMENT>
dctl libreoffice close <DOCUMENT>
```

### Writer

```bash
dctl libreoffice writer-text <DOCUMENT>
dctl libreoffice writer-paragraphs <DOCUMENT>
dctl libreoffice writer-append <DOCUMENT> <TEXT>
dctl libreoffice writer-set-paragraph <DOCUMENT> <INDEX> <TEXT>
```

### Calc

```bash
dctl libreoffice calc-sheets <DOCUMENT>
dctl libreoffice calc-read <DOCUMENT> <SHEET> <RANGE>
dctl libreoffice calc-write-cell <DOCUMENT> <SHEET> <CELL> <VALUE>
dctl libreoffice calc-write-range <DOCUMENT> <SHEET> <RANGE> <ROWS_JSON>
```

## DOCX

Direct `.docx` editing via python-docx. No GUI required.

```bash
dctl docx inspect <PATH>
dctl docx read <PATH>
dctl docx paragraphs <PATH>
dctl docx append <PATH> <TEXT>
dctl docx insert-before <PATH> <INDEX> <TEXT>
dctl docx set-paragraph <PATH> <INDEX> <TEXT>
dctl docx replace <PATH> <FIND> <REPLACE>
dctl docx backup <PATH>
dctl docx diff <PATH> --against <OTHER.docx>
dctl docx worksheet-map <PATH>
dctl docx answer-question <PATH> --question <TEXT> --answer <TEXT> [--exact]
dctl docx answer-all <PATH> <ANSWERS.json> [--exact]
dctl docx fill-table <PATH> --table <TITLE_OR_INDEX> <ENTRIES.json>
```

## XLSX

Direct `.xlsx` editing via openpyxl. No GUI required.

```bash
dctl xlsx inspect <PATH>
dctl xlsx sheets <PATH>
dctl xlsx read <PATH> <SHEET> <RANGE>
dctl xlsx write-cell <PATH> <SHEET> <CELL> <VALUE>
dctl xlsx write-range <PATH> <SHEET> <RANGE> <ROWS_JSON>
dctl xlsx backup <PATH>
dctl xlsx diff <PATH> --against <OTHER.xlsx>
dctl xlsx worksheet-map <PATH> [--sheet SHEET]
dctl xlsx locate-cell <PATH> <SHEET> --row-label <TEXT> --column-label <TEXT> [--table NAME]
dctl xlsx fill-cell <PATH> <SHEET> --row-label <TEXT> --column-label <TEXT> --value <VALUE> [--table NAME]
dctl xlsx fill-table <PATH> <SHEET> <ENTRIES.json> [--table NAME]
```

## Decision Guide

| Task | Command |
|---|---|
| Web app interaction | `dctl browser` |
| Edit a `.docx` file | `dctl docx` |
| Edit a `.xlsx` file | `dctl xlsx` |
| Live LibreOffice control | `dctl libreoffice` |
| Desktop app with no better path | `dctl click` / `dctl type` / `dctl key` |
