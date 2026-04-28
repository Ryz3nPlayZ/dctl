# Browser Guide

`dctl browser` provides browser automation through Chrome DevTools Protocol (CDP). It is the right tool for web apps — Gmail, Google Docs, Google Sheets, CRMs, internal tools, and any browser-hosted workflow.

## Session Modes

### Managed Sessions (Recommended)

```bash
dctl browser start --session work --app chrome --url https://mail.google.com
```

Managed sessions give you:
- persistent browser profiles under `.dctl/browser/profiles/<name>`
- login state, cookies, and local profile data preserved across starts
- reconnect by session name
- session metadata in `.dctl/browser/sessions/<name>.json`

### Attaching to Existing Browsers

If a browser is already running with remote debugging enabled:

```bash
dctl browser discover                  # Find debug-enabled browsers
dctl browser attach --port 9222        # Attach to a specific endpoint
```

## Recommended Workflow

1. Start or attach to a browser session
2. Inspect current tab state (`tabs`, `active-tab`, `snapshot`)
3. Navigate to the target (`open`)
4. Wait for the target surface (`wait-selector`, `wait-url`)
5. Read the current state (`snapshot`, `text`, `dom`)
6. Perform the action (`type`, `click`, `press`, `eval`)
7. Verify the result (`snapshot`, `text`, `dom`)

Always verify after mutations. Do not assume a `type` succeeded without checking.

## Inspection Commands

### Snapshot

```bash
dctl browser snapshot active --session work
```

Returns a high-level text representation of the page. Good for understanding what's visible and interactive. Use `--text-limit N` to cap output length (default 4000 chars).

### DOM and Accessibility Tree

```bash
dctl browser dom active --selector '#main' --depth 3 --session work
dctl browser ax active --selector '#main' --session work
dctl browser text active --selector '#main' --session work
```

- `dom` returns raw HTML structure
- `ax` returns the browser's accessibility tree
- `text` returns extracted text content

### Selection and Caret

```bash
dctl browser selection active --session work
dctl browser caret active --selector 'textarea' --start 5 --end 5 --session work
```

`caret` sets the insertion point in an input or contenteditable element. Use it when you need to insert or replace text at a specific position.

## Editing Commands

### Type

```bash
dctl browser type active "Hello" --selector 'input[name="q"]' --clear --session work
```

`--clear` clears the existing content before typing. Always specify `--selector` to target the right element.

### Click

```bash
dctl browser click active 'button[aria-label="Send"]' --session work
```

### Press

```bash
dctl browser press active ctrl+enter --session work
dctl browser press active shift+tab --session work
```

Key combos use `+` as separator. `Enter` is mapped to a paragraph separator in editable contexts for correct behavior in editors like Google Docs.

### JavaScript Evaluation

```bash
dctl browser eval active "document.title" --session work
dctl browser eval active "document.querySelector('input').value" --session work
```

Use `--no-await-promise` if the expression returns a promise you don't want to wait for.

## Batch Mode

Chain multiple operations in a single round trip to reduce latency:

```bash
dctl browser batch active '[
  {"op":"snapshot"},
  {"op":"wait-selector","selector":"textarea","timeout":5},
  {"op":"type","selector":"textarea","clear":true,"text":"Hello"},
  {"op":"press","combo":"ctrl+enter"}
]' --session work
```

Supported operations: `activate`, `click`, `type`, `press`, `eval`, `wait-selector`, `wait-url`, `snapshot`, `text`, `selection`, `caret`.

## Gmail Workflow

Gmail has pitfalls that trip up generic automation. Follow this pattern:

1. Open compose
2. Wait for `input[aria-label="To recipients"]`
3. Wait for `input[name="subjectbox"]`
4. Wait for the body editor `div[aria-label="Message Body"][contenteditable="true"]`
5. Type into each field with `--clear`
6. Verify the DOM values after typing
7. Send with `ctrl+enter`
8. Verify sent state

Gmail renders inbox previews where subject and body text appear adjacent in the conversation list. That preview is not the compose form. Always target the actual compose DOM elements.

## Google Docs Workflow

1. Focus the correct tab
2. Inspect with `snapshot` to find the insertion point
3. Place the caret with `click` or `caret`
4. Use `press` for formatting shortcuts (ctrl+b, ctrl+i, etc.)
5. Use `type` for content
6. Verify after each paragraph or formatting block

For detailed document structure inspection, use `dom` or `ax` before editing.

## Wait Primitives

```bash
dctl browser wait-url active "docs.google.com" --timeout 10 --session work
dctl browser wait-selector active 'textarea' --timeout 5 --session work
```

Use these after navigation or clicks that trigger page transitions. They poll until the condition is met or the timeout expires.

## Fallback Hierarchy

When browser control isn't enough:

1. Try `eval` for JavaScript-level access
2. Try `dom` for raw HTML structure
3. Try `ax` for the accessibility tree
4. Try `caret` for precise positioning
5. Try keyboard flow with `press`
6. Fall back to desktop commands (`dctl click`, `dctl type`, `dctl key`)
