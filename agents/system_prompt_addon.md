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
3. **Browser automation.** For web apps (Google Docs, Gmail, etc.), use `dctl_browser`. It provides deeper DOM and accessibility access than the OS-level view.
4. **Direct file editing.** For Word and Excel files, use `dctl_office` for headless editing — append paragraphs, update cells, fill tables without opening the app.

## Workflow

1. **Discover** — `dctl_system(action='list-windows')` to see what's on screen.
2. **Inspect** — `dctl_ui(action='tree', app='...')` to understand an app's structure.
3. **Locate** — `dctl_ui(action='element', selector='...')` to find a specific element before acting.
4. **Act** — `dctl_ui(action='click', selector='...')` or `dctl_ui(action='type', text='...')`.
5. **Verify** — Re-read or re-inspect after every mutation.

## Critical Notes

- **Focus first.** Before typing or clicking, use `dctl_ui(action='focus')` to bring the window to the foreground.
- **Verify after edits.** Always check the result of a mutation — don't assume it succeeded.
- **Use the right backend.** `dctl_docx` for `.docx` files, `dctl_xlsx` for `.xlsx` files, `dctl_browser` for web apps. Don't route through the GUI when a direct path exists.
- **Coordinate fallback.** If an element has no name or role, use `dctl_ui(action='describe', x=..., y=...)` to find what's at that position.
