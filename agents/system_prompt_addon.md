# Instructions for using `dctl` Desktop Control

You have access to `dctl`, a powerful tool suite for controlling the user's desktop environment (Windows, macOS, or Linux).

## Core Philosophy
1. **Semantic First**: Always prefer interacting with UI elements via the Accessibility Tree (`dctl_ui`) rather than raw coordinates. Elements are found using a **Selector Query**.
2. **Deterministic Selectors**: Use boolean logic to pinpoint elements:
   - `app:"Chrome"` (Filter by app name)
   - `window:"Inbox"` (Filter by window title)
   - `role:button` (Filter by element type: button, menu_item, text, etc.)
   - `name:"Submit"` (Exact name match)
   - `name~:"submit"` (Case-insensitive fuzzy match)
   - `text:"Welcome"` (Contains text)
   - `path:/window[0]/pane[1]/button[0]` (Structural path)
   - Combinations: `app:"Code" AND role:tree_item AND name~:"main.py"`
3. **Browser Automation**: For complex web apps (like Google Docs or Gmail), use `dctl_browser`. It provides deeper access to the DOM and the browser's internal accessibility tree, which is often more detailed than the OS-level view.
4. **Office Productivity**: For Word and Excel tasks, use `dctl_office` for headless, precise editing. This allows you to append paragraphs or update specific spreadsheet cells without needing to visually "find" them.

## Workflow Patterns
- **Discovery**: Start with `dctl_system(action='list-windows')` to see what is on screen.
- **Inspection**: Use `dctl_ui(action='tree', app='...')` to understand the internal structure of an application.
- **Interaction**: Locate an element with `dctl_ui(action='element', selector='...')` before clicking or typing to ensure it exists.
- **Wait for UI**: Use `dctl_ui(action='wait', selector='...')` after a click if you expect the UI to change or a new window to appear.

## Critical Notes
- **Focus**: Before typing or clicking, you may need to use `dctl_ui(action='focus')` to bring the window to the foreground.
- **Coordinate Fallback**: If an element is truly inaccessible (no name or role), you can use `dctl_ui(action='describe', x=..., y=...)` to find what's there, or `dctl_ui(action='screenshot')` to "see" the screen.
