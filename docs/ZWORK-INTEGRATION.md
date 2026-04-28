# Agent Integration Guide

This guide covers how to integrate `dctl` into an LLM agent loop. The same patterns apply to any agent framework — Claude, GPT-4, Gemini, or custom systems.

## Mental Model

An agent should treat `dctl` as four distinct control surfaces:

- **Browser hands** — `dctl browser` for web apps
- **File hands** — `dctl docx` and `dctl xlsx` for structured documents
- **Office hands** — `dctl libreoffice` for live app control
- **Desktop hands** — desktop commands for apps with no better path

Stay text-native whenever possible. Use the most structured path available.

## Backend Selection Rules

### `.docx` files → `dctl docx`

Do not route through the browser or GUI.

```bash
dctl docx inspect file.docx
dctl docx worksheet-map file.docx
dctl docx answer-question file.docx --question "..." --answer "..."
```

### `.xlsx` files → `dctl xlsx`

Go straight to the workbook model.

```bash
dctl xlsx worksheet-map sheet.xlsx
dctl xlsx fill-cell sheet.xlsx Sheet1 --row-label "..." --column-label "..." --value "..."
```

### Web apps → `dctl browser`

For Gmail, Google Docs, Google Sheets, and browser-hosted tools.

```bash
dctl browser start --session work --app chrome --url https://mail.google.com
dctl browser snapshot active --session work
dctl browser type active "Hello" --selector 'input[name="q"]' --clear --session work
```

### Everything else → Desktop commands

Only when no structured path is available.

```bash
dctl click 'role:button AND name:"Save"'
dctl type "text" --into 'role:text_field'
```

## Recommended Agent Loop

1. Inspect capabilities with `dctl capabilities`
2. Decide the control surface: file, browser, office, or desktop
3. Snapshot current state
4. Perform one bounded action
5. Verify the result
6. Repeat

**Do not skip verification for editing tasks.** Always re-read after mutation.

## Tool Mapping

If exposing `dctl` as agent tools, prefer narrow tools over a generic shell wrapper:

| Tool | Maps to |
|---|---|
| `desktop_list_apps` | `dctl list-apps` |
| `desktop_list_windows` | `dctl list-windows` |
| `desktop_tree` | `dctl tree` |
| `desktop_element` | `dctl element <selector>` |
| `desktop_read` | `dctl read <selector>` |
| `desktop_click` | `dctl click <selector>` |
| `desktop_type` | `dctl type <text> --into <selector>` |
| `desktop_key` | `dctl key <combo>` |
| `desktop_screenshot` | `dctl screenshot` |
| `browser_start` | `dctl browser start` |
| `browser_snapshot` | `dctl browser snapshot` |
| `browser_type` | `dctl browser type` |

Narrow tools make agent prompting and tool selection more reliable.

## Gmail Workflow

Gmail is a common test surface with specific pitfalls:

1. Open compose
2. Wait for `input[aria-label="To recipients"]`
3. Wait for `input[name="subjectbox"]`
4. Wait for the body editor `div[aria-label="Message Body"][contenteditable="true"]`
5. Type into each field with `--clear`
6. Re-read DOM values before sending
7. Send with `ctrl+enter`
8. Verify sent state

Do not trust the inbox preview as proof of subject/body content. The conversation list shows adjacent text that looks like the compose form but isn't.

## Google Docs Workflow

1. Focus the correct tab
2. Inspect with `snapshot`
3. Place the caret
4. Use `press` for formatting shortcuts
5. Use `type` for content
6. Verify after each paragraph or formatting block

## Office Workflow

For worksheet-style documents:

1. Run `worksheet-map` to understand the structure
2. Find the question/prompt pattern
3. Write only the answer text
4. Preserve formatting anchors
5. Verify the final document

This applies to homework sheets, form-style documents, tables with prompts and answer cells, and spreadsheets with headers and labeled rows.

## Safety Rules

- Do not guess at hidden GUI state — inspect first
- Do not chain destructive edits without checking intermediate results
- Use managed browser sessions for login persistence
- Use file-model edits for known formats
- Prefer `batch` when several browser actions can be verified together

## Fallback Hierarchy

When the primary path isn't enough:

1. `browser eval` — JavaScript-level access
2. `browser dom` — raw HTML structure
3. `browser ax` — accessibility tree
4. `browser caret` — precise positioning
5. Keyboard flow with `browser press`
6. Desktop commands (`dctl click`, `dctl type`, `dctl key`)
7. Screenshot + `describe` only as last resort
