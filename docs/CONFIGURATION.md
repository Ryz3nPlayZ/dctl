# Configuration

`dctl` is mostly convention-over-configuration, but there are still a few important knobs.

## Environment Variables

### `DCTL_BROWSER_HOME`

Overrides the browser session home directory.

Default:

```text
<project-root>/.dctl/browser
```

Used for:

- managed browser profiles
- browser session metadata

Directory layout:

```text
.dctl/browser/
  profiles/
    work/
  sessions/
    work.json
```

## Browser Session Behavior

Managed browser sessions use:

- `--remote-debugging-port=<PORT>`
- `--user-data-dir=<PROFILE_DIR>`
- `--restore-last-session` when a named session is used

That means the browser keeps:

- cookies
- logins
- local profile state
- persisted tabs and session data where the browser supports it

## Dependency Discovery

`dctl capabilities` and `dctl doctor` inspect helpers on PATH and importable Python modules.

Useful Linux helpers:

- `gdbus`
- `xdg-open`
- `xdotool`
- `ydotool`
- `grim`
- `spectacle`
- `scrot`
- `soffice` or `libreoffice`

Useful macOS helpers:

- `open`
- `screencapture`

## Permissions

### Linux

For best semantic coverage, the accessibility bus must be reachable from the session.

For `ydotool`, the current user may need access to the uinput event path or a running helper service.

### macOS

You will usually need:

- Accessibility permission for semantic UI control and input events
- Screen Recording permission for many screenshot cases

## No Central Config File Yet

`dctl` currently uses:

- command arguments
- environment variables
- local browser session files

There is not a single canonical config file yet.

