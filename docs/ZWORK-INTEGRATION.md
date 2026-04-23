# zWork Integration

This is the guide for using `dctl` as the desktop control layer for zWork.

## The Mental Model

zWork should treat `dctl` as the agent's hands:

- browser hands
- office hands
- file-format hands
- desktop fallback hands

The goal is to stay text-native whenever possible.

## Backend Choice Rules

### Use `docx` first for `.docx`

If the task is to edit a Word file directly, do not route it through the browser or a GUI unless you have to.

Use:

```bash
python3 -m dctl docx inspect file.docx
python3 -m dctl docx worksheet-map file.docx
python3 -m dctl docx answer-question file.docx --question "..." --answer "..."
```

### Use `xlsx` first for `.xlsx`

If the task is spreadsheet editing, go straight to the workbook model.

Use:

```bash
python3 -m dctl xlsx worksheet-map sheet.xlsx
python3 -m dctl xlsx locate-cell sheet.xlsx Sheet1 --row-label "..." --column-label "..."
python3 -m dctl xlsx fill-cell sheet.xlsx Sheet1 --row-label "..." --column-label "..." --value "..."
```

### Use `browser` for web apps

For Gmail, Google Docs, Google Sheets, and browser-hosted CRMs or tools, use the browser adapter.

Use a managed session:

```bash
python3 -m dctl browser start --session work --app chrome --url https://mail.google.com
```

Then keep that session open and reuse it by name.

## Recommended Agent Loop

1. Inspect capabilities.
2. Decide whether the task is file-native, browser-native, or desktop-only.
3. Snapshot the current state.
4. Perform one bounded action.
5. Verify the result.
6. Repeat.

Do not skip verification for editing tasks.

## Browser Workflow for zWork

Use this flow for browser-hosted tasks:

1. `browser start` or `browser attach`
2. `browser tabs` and `browser active-tab`
3. `browser snapshot active`
4. `browser wait-selector` for the editor or form
5. `browser type`, `browser press`, or `browser caret`
6. `browser snapshot active` again
7. send only after the compose or editor state is correct

### Gmail example

For Gmail, do not trust the inbox preview as proof of the subject field.

Instead:

1. open compose
2. verify `input[aria-label="To recipients"]`
3. verify `input[name="subjectbox"]`
4. verify the real body editor, not just a hidden textarea mirror
5. re-read the DOM values before sending

This avoids the exact subject/body confusion that often happens with generic automation.

### Google Docs example

For Google Docs, the flow should be:

1. focus the correct tab
2. place the caret
3. use `press` for formatting shortcuts
4. use `type` for the actual text
5. verify the page state after each block

If the document structure matters, inspect with `snapshot`, `dom`, or `text` before editing.

## Office Workflow for zWork

For worksheet-like documents:

- use `docx worksheet-map` or `xlsx worksheet-map`
- find the prompt/question structure
- write only the answer text
- preserve formatting anchors
- verify the final document after writing

That is the right way to handle:

- homework sheets
- form-style documents
- tables with prompts and answer cells
- spreadsheets with headers and labeled rows

## Safety Rules for Agents

- Do not guess at hidden GUI state.
- Do not chain destructive edits without checking the intermediate result.
- Use managed browser sessions for login persistence.
- Use file-model edits for known formats.
- Prefer `batch` when several browser actions are independent and can be verified together.

## When to Fall Back

If the app does not expose enough structure:

- try `browser eval`
- try `browser dom`
- try `browser caret`
- try `browser press`
- then use desktop `click` / `type` / `key`

Do not start with screen scraping unless the app forces it.

