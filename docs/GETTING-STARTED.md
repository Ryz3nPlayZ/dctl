# Getting Started

This guide gets you from zero to usable desktop control.

## 1. Install

From the repository root:

```bash
python3 -m pip install -e .
```

On macOS, install the optional backend dependencies too:

```bash
python3 -m pip install -e '.[macos]'
```

## 2. Check the environment

Run the two baseline commands first:

```bash
python3 -m dctl doctor
python3 -m dctl capabilities
```

These tell you:

- what platform was detected
- which backend is active
- which helpers are available
- what is missing
- which commands are expected to work

## 3. Start with simple desktop control

List apps and windows:

```bash
python3 -m dctl list-apps
python3 -m dctl list-windows
```

Inspect the UI tree:

```bash
python3 -m dctl tree --depth 3
```

Find or read something:

```bash
python3 -m dctl element "browser"
python3 -m dctl read "compose"
python3 -m dctl describe 100 200
```

## 4. Try a browser session

For agent workflows, use a managed browser session:

```bash
python3 -m dctl browser start --session work --app chrome --url https://example.com
python3 -m dctl browser sessions
python3 -m dctl browser tabs --session work
python3 -m dctl browser snapshot active --session work
```

Useful browser actions:

```bash
python3 -m dctl browser open https://docs.google.com --session work
python3 -m dctl browser activate active --session work
python3 -m dctl browser eval active "location.href='https://mail.google.com'" --session work
```

## 5. Try document workflows

Direct DOCX edits:

```bash
python3 -m dctl docx read notes.docx
python3 -m dctl docx paragraphs notes.docx
python3 -m dctl docx worksheet-map notes.docx
```

Direct XLSX edits:

```bash
python3 -m dctl xlsx sheets sheet.xlsx
python3 -m dctl xlsx worksheet-map sheet.xlsx
python3 -m dctl xlsx locate-cell sheet.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number"
```

## 6. Use the right backend

Rule of thumb:

- use `browser` for web apps and browser-hosted editors
- use `docx` for `.docx` files
- use `xlsx` for `.xlsx` files
- use `libreoffice` when you want live office-app control on Linux
- use desktop commands only when the app does not expose a better semantic surface

## 7. Keep the browser session alive

If you want login persistence, use a named session and keep using the same name:

```bash
python3 -m dctl browser start --session work --app chrome
python3 -m dctl browser stop --session work
python3 -m dctl browser session-info work
```

The profile lives under `.dctl/browser/profiles/work` by default.
