# Instructions for using `dctl` Desktop Control

You have access to `dctl`, a tool suite for controlling the user's desktop environment.

## Core Principles

1. **Semantic first.** Always prefer the accessibility tree over raw coordinates. Find elements using selectors, not pixel positions.
2. **Deterministic selectors.** Use boolean logic to target elements:
   - `app:"Chrome"` — filter by app name
   - `window:"Inbox"` — filter by window title
   - `role:button` — filter by element role (button, menu_item, text_field, etc.)
   - `name:"Submit"` — exact name match
   - `name~:"submit"` — case-insensitive name match
   - `text:"Welcome"` — contains text
   - `text~:"welcome"` — case-insensitive text match
   - `path:/window[0]/pane[1]/button[0]` — structural path
   - Combine with AND/OR: `app:"Code" AND role:tree_item AND name~:"main.py"`
3. **Use the right backend.** Don't route through the GUI when a direct path exists:
   - **Web apps** (Gmail, Docs, any browser tab) → `dctl_browser` for deep CDP control
   - **DOCX/XLSX files** → `dctl_office` for headless file editing
   - **Live LibreOffice** → `dctl_office` with `libreoffice` type for UNO bridge
   - **Native desktop apps** → `dctl_ui` for accessibility tree control
4. **Coordinate fallback.** If an element has no name or role, use `dctl_ui(action='describe', x=..., y=...)` to find what's at that position.

## Workflow

1. **Discover** — `dctl_system(action='list-windows')` to see what's on screen, or `dctl_system(action='doctor')` to check what's available.
2. **Inspect** — `dctl_ui(action='tree', app='...')` for native apps, or `dctl_browser(action='snapshot', target='active')` for web pages.
3. **Locate** — `dctl_ui(action='element', selector='...')` to find a specific element before acting.
4. **Act** — `dctl_ui(action='click', selector='...')` or `dctl_ui(action='type', text='...')`.
5. **Verify** — Re-read or re-inspect after every mutation.

## Browser Automation

Use `dctl_browser` for any web-based task:

- **Session management**: `start` a browser, `stop` it, `sessions` to list active ones, `discover` existing debug-enabled browsers
- **Page inspection**: `snapshot` extracts structured content (text, headings, landmarks, interactions, visuals, LaTeX); `ax` for accessibility tree; `dom` for raw DOM
- **Interaction**: `actions` lists clickable elements with IDs, `click-action` clicks by ID, `act` combines actions+click+snapshot in one call
- **Input**: `type` with CSS selector, `press` for key combos, `click` for coordinate clicks
- **Waiting**: `wait-url` for URL changes, `wait-selector` for element appearance
- **Batch**: `batch` executes multiple operations in sequence with timing

## Document Editing

Use `dctl_office` for headless file operations:

### Word (.docx)
- `inspect` for document structure, `read` for full text, `paragraphs` for paragraph list
- `append` to add text, `insert-before` to insert at index, `set-paragraph` to replace, `replace` for find-and-replace
- `worksheet-map` for form structure, `answer-question` for form Q&A, `fill-table` for bulk table population
- `backup` and `diff` for safe editing workflows

### Excel (.xlsx)
- `inspect` for workbook info, `sheets` for sheet names, `read` for cell data
- `write-cell` / `write-range` for direct writes, `locate-cell` / `fill-cell` for label-based lookups
- `worksheet-map` for table structure, `fill-table` for bulk table fills

### LibreOffice (live control)
- `lo-start` / `lo-stop` to manage the process, `lo-open` / `lo-close` for documents
- `lo-writer-text` / `lo-writer-append` / `lo-writer-set` for Writer control
- `lo-calc-sheets` / `lo-calc-read` / `lo-calc-write-cell` for Calc control

## Critical Notes

- **Focus first.** Before typing or clicking, use `dctl_ui(action='focus')` to bring the window to the foreground.
- **Verify after edits.** Always check the result of a mutation — don't assume it succeeded.
- **Screenshot for verification.** Use `dctl_ui(action='screenshot')` to capture the screen when unsure of state.
- **Clipboard bridge.** `dctl_ui(action='clipboard', clipboard_action='read')` can extract text from apps that don't expose accessibility.
