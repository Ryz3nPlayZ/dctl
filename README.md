# dctl

`dctl` is a headless desktop control CLI for LLM agents.

It is designed for non-interactive tool use:

- JSON-first output
- deterministic commands
- semantic accessibility access when available
- raw Linux fallbacks for windowing, input, launch, and capture
- app-specific semantic adapters for browsers, LibreOffice, DOCX, and XLSX

## Status

Current repository state:

- Linux-first implementation
- unified CLI contract intended to carry over to macOS
- AT-SPI semantic backend on Linux
- `xdotool` window/input fallback on Linux when usable
- `ydotool` support for text and key fallback when configured
- app launch and `.desktop` enumeration
- screenshot capture through Linux helper backends
- native macOS backend wired behind the same CLI contract using AX, Quartz, `open`, and `screencapture`

macOS support is implemented in code but was not live-tested in this Linux session.

## Implemented Commands

```text
dctl capabilities
dctl doctor

dctl list-apps
dctl list-windows
dctl list-launchable
dctl launch <TARGET>
dctl open <PATH_OR_URL>

dctl tree [--app APP] [--depth N]
dctl element <SELECTOR>
dctl read <SELECTOR>
dctl describe <X> <Y>
dctl wait <SELECTOR> [--timeout SECONDS] [--interval MS]

dctl focus <SELECTOR>
dctl click <SELECTOR>
dctl type <TEXT> [--into SELECTOR]
dctl key <COMBO>
dctl scroll <DIRECTION> [--amount N]

dctl screenshot [--window WINDOW_OR_SELECTOR] [--region X,Y,W,H] [--output PATH] [--base64]

dctl browser start [--app brave|chrome|chromium] [--port PORT] [--url URL]
dctl browser targets [--endpoint URL]
dctl browser dom <TARGET> [--selector CSS]
dctl browser ax <TARGET> [--selector CSS]
dctl browser text <TARGET> [--selector CSS]
dctl browser selection <TARGET>
dctl browser click <TARGET> <CSS_SELECTOR>
dctl browser type <TARGET> <TEXT> [--selector CSS] [--clear]
dctl browser press <TARGET> <COMBO>
dctl browser eval <TARGET> <JAVASCRIPT>
dctl browser send <TARGET> <CDP_METHOD> [--params JSON]

dctl libreoffice start [--port PORT] [--headless]
dctl libreoffice docs [--port PORT]
dctl libreoffice open <PATH> [--port PORT]
dctl libreoffice info <DOCUMENT>
dctl libreoffice writer-text <DOCUMENT>
dctl libreoffice writer-paragraphs <DOCUMENT>
dctl libreoffice writer-append <DOCUMENT> <TEXT>
dctl libreoffice writer-set-paragraph <DOCUMENT> <INDEX> <TEXT>
dctl libreoffice calc-sheets <DOCUMENT>
dctl libreoffice calc-read <DOCUMENT> <SHEET> <RANGE>
dctl libreoffice calc-write-cell <DOCUMENT> <SHEET> <CELL> <VALUE> [--json]
dctl libreoffice calc-write-range <DOCUMENT> <SHEET> <RANGE> <ROWS_JSON>

dctl docx inspect <PATH>
dctl docx read <PATH>
dctl docx paragraphs <PATH>
dctl docx append <PATH> <TEXT>
dctl docx insert-before <PATH> <INDEX> <TEXT>
dctl docx set-paragraph <PATH> <INDEX> <TEXT>
dctl docx replace <PATH> <FIND> <REPLACE>
dctl docx backup <PATH>
dctl docx diff <PATH> --against OTHER.docx
dctl docx worksheet-map <PATH>
dctl docx answer-question <PATH> --question TEXT --answer TEXT [--exact]
dctl docx answer-all <PATH> ANSWERS.json [--exact]
dctl docx fill-table <PATH> --table TITLE_OR_INDEX ENTRIES.json

dctl xlsx inspect <PATH>
dctl xlsx sheets <PATH>
dctl xlsx read <PATH> <SHEET> <RANGE>
dctl xlsx write-cell <PATH> <SHEET> <CELL> <VALUE> [--json]
dctl xlsx write-range <PATH> <SHEET> <RANGE> <ROWS_JSON>
dctl xlsx backup <PATH>
dctl xlsx diff <PATH> --against OTHER.xlsx
dctl xlsx worksheet-map <PATH> [--sheet SHEET]
dctl xlsx locate-cell <PATH> <SHEET> --row-label TEXT --column-label TEXT [--table NAME]
dctl xlsx fill-cell <PATH> <SHEET> --row-label TEXT --column-label TEXT --value VALUE [--table NAME] [--json]
dctl xlsx fill-table <PATH> <SHEET> ENTRIES.json [--table NAME]
```

## Linux Runtime Expectations

Best experience:

- AT-SPI accessibility bus available
- `xdg-open` installed
- `grim` or `scrot` installed
- `xdotool` available for X11 or XWayland fallback

Wayland note:

- semantic AT-SPI access is still the preferred path
- `ydotool` may work for input fallback, but it requires a running `ydotoold` and usable socket access
- `xdotool` is only useful where X11/XWayland access is actually available

## Precision Surfaces

For detailed app work, `dctl` now exposes text-native control surfaces instead of relying on screenshots:

- `dctl browser ...`: Chrome DevTools Protocol for DOM, accessibility tree, JS evaluation, click, text input, and raw CDP commands
- `dctl libreoffice ...`: UNO-based Writer/Calc document access and mutation
- `dctl docx ...`: direct Word `.docx` file inspection and editing through `python-docx`
- `dctl xlsx ...`: direct Excel `.xlsx` inspection and editing through `openpyxl`

This is the intended path for precise work in browser-hosted editors, LibreOffice, and Office file formats.

## Worksheet Editing

The `docx` and `xlsx` adapters now include a worksheet-oriented layer:

- `dctl docx worksheet-map` identifies likely question paragraphs and table structures
- `dctl docx answer-question` inserts or replaces an answer directly below a matched question
- `dctl docx answer-all` applies a batch of question/answer edits from JSON
- `dctl docx fill-table` fills table cells by row label and column label
- `dctl xlsx worksheet-map` emits inferred table structure for sheets without formal Excel tables
- `dctl xlsx locate-cell` resolves a semantic row/column label pair to an exact cell
- `dctl xlsx fill-cell` and `dctl xlsx fill-table` write by semantic labels instead of raw coordinates
- both adapters create automatic backups before mutating files

## Development

Run tests:

```bash
PYTHONPATH=/home/zemul/Programming/dctl python3 -m unittest discover -s tests -v
```

Run the CLI directly from source:

```bash
PYTHONPATH=/home/zemul/Programming/dctl python3 -m dctl capabilities
```

## macOS Notes

The macOS backend expects PyObjC bindings for:

- `pyobjc-framework-ApplicationServices`
- `pyobjc-framework-Quartz`
- `pyobjc-framework-Cocoa`

Install them with the `macos` extra or directly with `pip`.

You will also need:

- Accessibility permission for semantic UI control and input events
- Screen Recording permission for screenshots in many environments

## Sources

- Chrome DevTools Protocol: https://chromedevtools.github.io/devtools-protocol/
- Chrome DevTools Protocol Accessibility domain: https://chromedevtools.github.io/devtools-protocol/tot/Accessibility/
- LibreOffice SDK / UNO API: https://api.libreoffice.org/
- LibreOffice TextDocument service: https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1text_1_1TextDocument.html
- `python-docx` API docs: https://python-docx.readthedocs.io/en/latest/
- `openpyxl` docs: https://openpyxl.readthedocs.io/en/stable/
