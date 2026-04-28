# Agent Integration

This directory contains artifacts for integrating `dctl` into LLM agent loops.

## Files

| File | Description |
|---|---|
| `dctl_tools.json` | Tool definitions in JSON Schema format. Maps to OpenAI and Anthropic tool-use formats. |
| `system_prompt_addon.md` | System prompt instructions explaining the selector syntax and workflow patterns. |

## Quick Integration (Anthropic Python SDK)

```python
import json
from anthropic import Anthropic

client = Anthropic()

with open("agents/dctl_tools.json") as f:
    dctl_tools = json.load(f)["tools"]

with open("agents/system_prompt_addon.md") as f:
    dctl_instructions = f.read()

system_prompt = f"You are a desktop automation agent. {dctl_instructions}"

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system=system_prompt,
    tools=dctl_tools,
    messages=[{"role": "user", "content": "Open the browser and search for 'dctl desktop control'"}],
)
```

## Quick Integration (OpenAI Python SDK)

```python
import json
from openai import OpenAI

client = OpenAI()

with open("agents/dctl_tools.json") as f:
    dctl_tools = json.load(f)["tools"]

with open("agents/system_prompt_addon.md") as f:
    dctl_instructions = f.read()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": f"You are a desktop automation agent. {dctl_instructions}"},
        {"role": "user", "content": "Open the browser and search for 'dctl desktop control'"},
    ],
    tools=dctl_tools,
)
```

## Tool Mapping

Each `dctl_*` tool maps to a CLI command. Your backend should execute the corresponding command when the agent calls a tool:

| Agent Tool | CLI Command |
|---|---|
| `dctl_system(action='list-windows')` | `dctl list-windows` |
| `dctl_ui(action='click', selector='...')` | `dctl click "..."` |
| `dctl_browser(action='open', url='...')` | `dctl browser open "..."` |
| `dctl_office(type='word', action='append', path='...', text='...')` | `dctl docx append "..." "..."` |

## Integration Patterns

See [ZWORK-INTEGRATION.md](../docs/ZWORK-INTEGRATION.md) for:
- Backend selection rules
- Recommended agent loop
- Gmail and Google Docs workflows
- Safety rules for agents
- Fallback hierarchy
