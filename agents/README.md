# dctl Agent Integration

This directory contains the necessary artifacts to integrate `dctl` into an LLM Agent (e.g., Claude, GPT-4o).

## Files
- `dctl_tools.json`: The raw tool definitions in JSON Schema format. These can be mapped to OpenAI's `tools` or Anthropic's `tools` format.
- `system_prompt_addon.md`: The instructions that should be appended to the agent's system prompt to explain how to use `dctl` (especially the selector syntax).

## Example Python Integration (Anthropic)

```python
import json
from anthropic import Anthropic

client = Anthropic()

# Load tools from JSON
with open("agents/dctl_tools.json") as f:
    dctl_tools = json.load(f)["tools"]

# Load prompt addon
with open("agents/system_prompt_addon.md") as f:
    dctl_instructions = f.read()

system_prompt = f"You are a desktop automation agent. {dctl_instructions}"

# Start agent loop
response = client.messages.create(
    model="claude-3-5-sonnet-20240620",
    max_tokens=1024,
    system=system_prompt,
    tools=dctl_tools,
    messages=[{"role": "user", "content": "Open Word and type 'Hello World'"}]
)
```

## Tool Mapping
The `dctl_*` tools in the JSON schema map directly to `dctl` CLI commands. When the agent calls a tool, your backend should execute the corresponding CLI command:

| Tool | CLI Command Template |
|---|---|
| `dctl_system(action='list-windows')` | `dctl list-windows` |
| `dctl_ui(action='click', selector='...')` | `dctl click "..."` |
| `dctl_browser(action='open', url='...')` | `dctl browser open "..."` |
| `dctl_office(type='word', action='append', path='...', text='...')` | `dctl docx append "..." "..."` |
```
