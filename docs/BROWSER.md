# Browser Guide

`dctl browser` is the browser control plane.

Use it when the browser is the real application surface, especially for:

- Gmail
- Google Docs
- Google Sheets
- browser-based internal tools
- web apps that need tab, DOM, and keyboard control

## Two Browser Modes

### 1. Managed sessions

This is the default recommended path for agents.

```bash
python3 -m dctl browser start --session work --app chrome --url https://mail.google.com
```

Why this matters:

- login state persists
- cookies persist
- browser profile data persists
- the agent can reconnect by session name

Managed sessions live under:

- `.dctl/browser/profiles/<session>`
- `.dctl/browser/sessions/<session>.json`

### 2. Debug-enabled existing browsers

If a browser was started with a CDP endpoint, `dctl` can attach to it.

```bash
python3 -m dctl browser discover
python3 -m dctl browser attach --port 9222
```

This works only if the browser already exposes remote debugging.

## Recommended Browser Workflow

1. Start or attach to a browser session.
2. Inspect the current tab state.
3. Navigate or open the target app.
4. Verify the page state with `snapshot`, `text`, or `dom`.
5. Type or press keys into the exact target.
6. Verify after each meaningful action.

## Tab and State Commands

Use these first:

```bash
python3 -m dctl browser tabs --session work
python3 -m dctl browser active-tab --session work
python3 -m dctl browser snapshot active --session work
```

Good agent behavior:

- identify the current tab before editing
- use the tab ID or `active` target explicitly
- re-snapshot after navigation or send actions

## Editing Rules

### Prefer precise selectors

For simple web forms, use direct selectors.

Examples:

```bash
python3 -m dctl browser type active "sent from dctl" --selector 'input[name="subjectbox"]' --clear --session work
python3 -m dctl browser type active "this shit works" --selector 'div[aria-label="Message Body"][contenteditable="true"]' --clear --session work
```

### Prefer browser-native editing over raw clicks

For browser-hosted apps, use:

- `type`
- `press`
- `caret`
- `selection`
- `eval`

Avoid relying on coordinates unless the app has no usable DOM or accessibility surface.

### Use `press` for shortcuts

Examples:

```bash
python3 -m dctl browser press active ctrl+enter --session work
python3 -m dctl browser press active shift+enter --session work
```

`Enter` is mapped to a paragraph separator in editable browser contexts so Google Docs and similar editors behave more like a human typing.

## Caret Control

Use `caret` when you need a precise insertion point inside an input or contenteditable region.

```bash
python3 -m dctl browser caret active --selector '#box' --start 3 --end 3 --session work
```

This is the right primitive for:

- inserting text at a known position
- replacing a selected span
- working with a form field without retyping the whole value

## Batch Mode

`browser batch` is the efficiency primitive.

Use it when the agent would otherwise make several round trips in a row.

Example:

```bash
python3 -m dctl browser batch active '[
  {"op":"snapshot"},
  {"op":"wait-selector","selector":"input[name=subjectbox]","timeout":10},
  {"op":"type","selector":"input[name=subjectbox]","clear":true,"text":"sent from dctl"},
  {"op":"type","selector":"div[aria-label=\"Message Body\"][contenteditable=\"true\"]","clear":true,"text":"this shit works"},
  {"op":"press","combo":"ctrl+enter"}
]'
```

## Gmail Guidance

Gmail is a useful test surface because it is common and awkward.

Use this pattern:

1. open compose
2. verify the compose fields exist
3. set recipient
4. set subject
5. set body
6. verify the DOM values
7. send
8. verify the sent state

Important:

- Gmail often renders previews where the subject and first body line appear adjacent in the conversation list
- that preview is not the same thing as the actual subject field
- always inspect the compose DOM or the message detail view if you care about exact header values

## Google Docs Guidance

For Docs, the best path is:

- use the managed browser session
- keep the document open in a known tab
- inspect with `snapshot`
- place the caret with click or `caret`
- use `press` for formatting shortcuts
- use `type` for the actual content

If the agent needs to make detailed edits, it should verify the document state after every paragraph or formatting block.

## When Browser Control Is Not Enough

If a browser app hides meaningful structure behind canvas-only rendering or custom widgets, `dctl` should not guess.

Fallbacks:

- try `eval`
- try `dom`
- try `ax`
- try `caret`
- then use keyboard flow
- then fall back to desktop control
