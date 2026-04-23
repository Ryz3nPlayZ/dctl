# Development

This repo is a Python CLI package.

## Project Layout

- `dctl/` - implementation
- `tests/` - unit tests
- `README.md` - landing page
- `PLAN.md` - product planning and implementation history

## Install for Development

```bash
python3 -m pip install -e .
```

On macOS, include the optional backend extra:

```bash
python3 -m pip install -e '.[macos]'
```

## Run the CLI from Source

```bash
PYTHONPATH=/home/zemul/Programming/dctl python3 -m dctl capabilities
```

## Run Tests

```bash
PYTHONPATH=/home/zemul/Programming/dctl python3 -m unittest discover -s tests -v
```

## Compile Check

```bash
python3 -m compileall dctl
```

## Coding Conventions

- keep commands deterministic
- return structured JSON
- do not make interactive prompts part of runtime behavior
- prefer semantic backends over injection helpers
- prefer capability-aware failure messages over silent fallback

## When Adding a New Command

Add it in this order:

1. parser wiring in `dctl/cli.py`
2. implementation in the relevant adapter or backend
3. capability detection if the command depends on a helper
4. tests for the happy path and the failure path
5. README / docs updates

## When Adding Browser Behavior

Browser work usually needs all of these:

- command-line plumbing
- CDP command or runtime evaluation
- a session-aware test
- a selector that matches actual browser DOM structure
- a verification step after mutation

## When Adding Office Behavior

For DOCX/XLSX features:

- test against a temporary file
- verify the original file is preserved when backups are expected
- verify the modified structure, not just the command return value

