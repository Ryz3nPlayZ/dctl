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

`tabs` returns ranked candidates (`targetScore`) and a `recommendedTargetId`; session-based runs also keep a preferred tab so `active` resolves predictably after `open`/`activate`.

Always verify after mutations. Do not assume a `type` succeeded without checking.
Use `selector` before mutating commands when you need deterministic element targeting.

## Inspection Commands

### Snapshot

```bash
dctl browser snapshot active --session work
```

Returns a structured extraction of the current page without screenshots:

- high-level visible text (`visibleText`)
- semantic structure (`headings`, `landmarks`, `contentBlocks`, `interactions`)
- detected math payloads (`latex`) from MathJax/KaTeX/MathML/TeX script nodes
- detected visual structures (`visuals`) from visible SVG/canvas/image surfaces
- quality diagnostics (`quality`) with explicit issue codes

Use `--text-limit N` and `--max-items N` to control payload size.

Use strict quality enforcement when you want fail-fast behavior:

```bash
dctl browser snapshot active --session work --strict --min-text 200 --max-text 12000
```

In strict mode, dctl raises an error if extraction quality checks detect problems (too little content, truncation, weak structure, etc.).

### DOM and Accessibility Tree

```bash
dctl browser dom active --selector '#main' --depth 3 --strict-selector --session work
dctl browser ax active --selector '#main' --strict-selector --session work
dctl browser text active --selector '#main' --strict-selector --session work
dctl browser selector active '#main button' --sample-limit 10 --session work
dctl browser actions active --query "submit" --role button --sample-limit 25 --session work
```

- `dom` returns raw HTML structure
- `ax` returns the browser's accessibility tree
- `text` returns extracted text content
- `selector` returns match counts, visibility/editability stats, and sample elements
- `actions` returns machine-friendly clickable/actionable elements with stable `actionId` values for follow-up `click-action`

`--strict-selector` makes `dom`/`ax`/`text`/`wait-selector` fail with `MULTIPLE_MATCHES` when the selector is ambiguous.

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
For `type` and `click`, selectors must resolve to exactly one element; ambiguous selectors now fail with `MULTIPLE_MATCHES`.

### Click

```bash
dctl browser click active 'button[aria-label="Send"]' --session work
dctl browser click-action active 0 --query "Send" --role button --session work
dctl browser act active --query "Send" --role button --wait-selector '.toast-success' --snapshot --session work
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
dctl browser eval active "({ready: document.readyState, href: location.href})" --return-by-value --session work
```

Use `--no-await-promise` if the expression returns a promise you don't want to wait for. Use `--return-by-value` to request plain JSON values instead of remote object handles when possible.

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

Supported operations: `activate`, `click`, `type`, `press`, `eval`, `actions`, `click-action`, `act`, `wait-selector`, `wait-url`, `snapshot`, `text`, `dom`, `ax`, `selector`, `selection`, `caret`.

Batch execution resolves the page target once and reuses it across operations, which reduces repeated tab-resolution overhead for simple browse flows.

`snapshot` batch ops also accept `text_limit`, `max_items`, `min_text`, `max_text`, and `strict`.
`text` / `dom` / `ax` / `wait-selector` batch ops accept `strict_selector`.
`selector` batch ops accept `sample_limit`.
`actions` batch ops accept `query`, `role`, and `sample_limit`; `click-action` batch ops require `action_id` (and can include `query`/`role` filters).
`act` batch ops accept `query`, `role`, optional `action_id`, optional `wait_selector` / `wait_url`, and optional snapshot flags (`snapshot`, `snapshot_strict`, `snapshot_text_limit`, `snapshot_max_items`, `snapshot_min_text`, `snapshot_max_text`).

Batch responses include `timingsMs` for total execution and per-op latency.

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
dctl browser wait-selector active 'textarea' --timeout 5 --strict-selector --session work
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
