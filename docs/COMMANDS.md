# Command Reference

This is the practical command map for `dctl`.

## Top-Level Commands

### Diagnostics

```bash
python3 -m dctl capabilities
python3 -m dctl doctor
```

Use these first when something does not work.

### Desktop inventory

```bash
python3 -m dctl list-apps
python3 -m dctl list-windows
python3 -m dctl list-launchable
```

### Launch

```bash
python3 -m dctl launch <TARGET>
python3 -m dctl open <PATH_OR_URL>
```

Use `launch` for apps and `open` for files or URLs.

### Accessibility and interaction

```bash
python3 -m dctl tree [--app APP] [--depth N]
python3 -m dctl element <SELECTOR>
python3 -m dctl read <SELECTOR>
python3 -m dctl describe <X> <Y>
python3 -m dctl wait <SELECTOR> [--timeout SECONDS] [--interval MS]
python3 -m dctl focus <SELECTOR>
python3 -m dctl click <SELECTOR>
python3 -m dctl type <TEXT> [--into SELECTOR]
python3 -m dctl key <COMBO>
python3 -m dctl scroll <DIRECTION> [--amount N]
python3 -m dctl screenshot [--window WINDOW_OR_SELECTOR] [--region X,Y,W,H] [--output PATH] [--base64]
```

## Browser Commands

### Session management

```bash
python3 -m dctl browser start --session work --app chrome --url https://mail.google.com
python3 -m dctl browser stop --session work
python3 -m dctl browser sessions
python3 -m dctl browser session-info work
python3 -m dctl browser discover
python3 -m dctl browser attach --session work
```

Use:

- `start` to create a persistent agent-owned browser
- `discover` to find debug-enabled browsers already running
- `attach` to bind to a running debug endpoint
- `sessions` and `session-info` to inspect managed sessions

### Page and tab control

```bash
python3 -m dctl browser tabs --session work
python3 -m dctl browser active-tab --session work
python3 -m dctl browser targets --session work
python3 -m dctl browser open https://docs.google.com --session work
python3 -m dctl browser activate <TARGET> --session work
python3 -m dctl browser close <TARGET> --session work
```

### Inspection

```bash
python3 -m dctl browser snapshot active --session work
python3 -m dctl browser wait-url active "docs.google.com" --session work
python3 -m dctl browser wait-selector active "input[name=subjectbox]" --session work
python3 -m dctl browser dom active --selector '#main'
python3 -m dctl browser ax active --selector '#main'
python3 -m dctl browser text active --selector '#main'
python3 -m dctl browser selection active --session work
python3 -m dctl browser caret active --selector 'input[name=subjectbox]' --start 0 --end 0 --session work
```

### Editing and control

```bash
python3 -m dctl browser click active 'button[aria-label="Send"]' --session work
python3 -m dctl browser type active "Hello" --selector 'textarea[aria-label="Message Body"]' --session work
python3 -m dctl browser press active ctrl+enter --session work
python3 -m dctl browser eval active "document.title" --session work
python3 -m dctl browser send active Runtime.evaluate --params '{"expression":"document.title"}' --session work
```

### Batch mode

`browser batch` lets you chain actions in one round trip.

Example:

```bash
python3 -m dctl browser batch active '[
  {"op":"activate"},
  {"op":"type","selector":"input[name=subjectbox]","clear":true,"text":"sent from dctl"},
  {"op":"type","selector":"div[aria-label=\"Message Body\"][contenteditable=\"true\"]","clear":true,"text":"this shit works"},
  {"op":"press","combo":"ctrl+enter"}
]'
```

Batch operations support:

- `activate`
- `click`
- `type`
- `press`
- `eval`
- `wait-selector`
- `wait-url`
- `snapshot`
- `text`
- `selection`
- `caret`

## LibreOffice Commands

### Office process control

```bash
python3 -m dctl libreoffice start --headless
python3 -m dctl libreoffice stop --pid <PID>
python3 -m dctl libreoffice docs
python3 -m dctl libreoffice open <PATH>
python3 -m dctl libreoffice info <DOCUMENT>
python3 -m dctl libreoffice save <DOCUMENT>
python3 -m dctl libreoffice close <DOCUMENT>
```

### Writer

```bash
python3 -m dctl libreoffice writer-text <DOCUMENT>
python3 -m dctl libreoffice writer-paragraphs <DOCUMENT>
python3 -m dctl libreoffice writer-append <DOCUMENT> <TEXT>
python3 -m dctl libreoffice writer-set-paragraph <DOCUMENT> <INDEX> <TEXT>
```

### Calc

```bash
python3 -m dctl libreoffice calc-sheets <DOCUMENT>
python3 -m dctl libreoffice calc-read <DOCUMENT> <SHEET> <RANGE>
python3 -m dctl libreoffice calc-write-cell <DOCUMENT> <SHEET> <CELL> <VALUE>
python3 -m dctl libreoffice calc-write-range <DOCUMENT> <SHEET> <RANGE> <ROWS_JSON>
```

## DOCX Commands

```bash
python3 -m dctl docx inspect <PATH>
python3 -m dctl docx read <PATH>
python3 -m dctl docx paragraphs <PATH>
python3 -m dctl docx append <PATH> <TEXT>
python3 -m dctl docx insert-before <PATH> <INDEX> <TEXT>
python3 -m dctl docx set-paragraph <PATH> <INDEX> <TEXT>
python3 -m dctl docx replace <PATH> <FIND> <REPLACE>
python3 -m dctl docx backup <PATH>
python3 -m dctl docx diff <PATH> --against OTHER.docx
python3 -m dctl docx worksheet-map <PATH>
python3 -m dctl docx answer-question <PATH> --question TEXT --answer TEXT [--exact]
python3 -m dctl docx answer-all <PATH> ANSWERS.json [--exact]
python3 -m dctl docx fill-table <PATH> --table TITLE_OR_INDEX ENTRIES.json
```

## XLSX Commands

```bash
python3 -m dctl xlsx inspect <PATH>
python3 -m dctl xlsx sheets <PATH>
python3 -m dctl xlsx read <PATH> <SHEET> <RANGE>
python3 -m dctl xlsx write-cell <PATH> <SHEET> <CELL> <VALUE>
python3 -m dctl xlsx write-range <PATH> <SHEET> <RANGE> <ROWS_JSON>
python3 -m dctl xlsx backup <PATH>
python3 -m dctl xlsx diff <PATH> --against OTHER.xlsx
python3 -m dctl xlsx worksheet-map <PATH> [--sheet SHEET]
python3 -m dctl xlsx locate-cell <PATH> <SHEET> --row-label TEXT --column-label TEXT [--table NAME]
python3 -m dctl xlsx fill-cell <PATH> <SHEET> --row-label TEXT --column-label TEXT --value VALUE [--table NAME]
python3 -m dctl xlsx fill-table <PATH> <SHEET> ENTRIES.json [--table NAME]
```

## Practical Choice Guide

- Use `browser` for Gmail, Google Docs, Google Sheets, and other web apps.
- Use `docx` for structured Word files.
- Use `xlsx` for structured Excel files.
- Use `libreoffice` when you want live office app control on Linux.
- Use `click`, `type`, and `key` only when no semantic or file-native path is better.
