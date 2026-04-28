# Configuration

`dctl` is convention-over-configuration. Most behavior is controlled through command flags rather than config files.

## Environment Variables

### `DCTL_BROWSER_HOME`

Overrides the browser session home directory.

Default: `<project-root>/.dctl/browser`

Directory layout:

```
.dctl/browser/
  profiles/
    work/            # Browser profile data (cookies, login state)
  sessions/
    work.json        # Session metadata
```

## Browser Sessions

Managed browser sessions use these Chromium flags:

- `--remote-debugging-port=<PORT>` — CDP endpoint
- `--user-data-dir=<PROFILE_DIR>` — persistent profile
- `--restore-last-session` — restore tabs from previous run

This gives managed sessions:
- cookie and login persistence
- local profile state
- tab restoration across restarts
- stable session names for reconnect

## Dependency Discovery

`dctl capabilities` and `dctl doctor` detect available helpers at runtime by checking PATH and importable Python modules.

### Linux Helpers

| Tool | Purpose |
|---|---|
| `xdg-open` | File and URL launching |
| `xdotool` | X11 window management and input |
| `ydotool` | Wayland input (requires `ydotoold`) |
| `grim` | Wayland screenshots |
| `spectacle` | KDE screenshots |
| `scrot` | X11 screenshots |
| `soffice` / `libreoffice` | LibreOffice UNO bridge |

### macOS Helpers

| Tool | Purpose |
|---|---|
| `open` | File and URL launching |
| `screencapture` | Screenshots |

### Windows

No external helpers required — all backends use native APIs via ctypes and comtypes.

## Permissions

### Linux

- AT-SPI accessibility bus must be reachable from the session
- `ydotool` requires access to the uinput event path or a running `ydotoold`

### macOS

- **Accessibility** permission required for semantic UI control and input events
- **Screen Recording** permission required for screenshots

### Windows

- No special permissions beyond normal user access

## No Config File

`dctl` currently uses command arguments, environment variables, and local browser session files. There is no central configuration file.
