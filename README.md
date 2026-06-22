# CTY-Cli

A minimalist Claude Code-style coding agent. Runs in your terminal, connects to any LLM (DeepSeek, Claude, GPT-4o), and operates on your local filesystem with structured tool use.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      main.py                             │
│              Entry point / REPL / /commands              │
└──────────┬──────────────────────────────────────────────┘
           │
     ┌─────▼──────┐     ┌─────────────┐     ┌────────────┐
     │  agent.py  │────▶│ providers/  │────▶│ LLM APIs   │
     │  Core Loop │     │ base.py     │     │ DeepSeek   │
     │  LLM⇄Tool  │     │ anthropic.py│     │ Anthropic  │
     │  roundtrip │     │ openai_com  │     │ OpenAI     │
     └─────┬──────┘     └─────────────┘     └────────────┘
           │
  ┌────────┼────────┬──────────┬──────────┬──────────┐
  │        │        │          │          │          │
  ▼        ▼        ▼          ▼          ▼          ▼
tools   context  permiss   trace      plan      skills
.py     .py      ions.py   .py        .py       .py
(12     (token   (3-level  (step-by-  (task     (progressive
tools)  mgmt)    safety)   step log)  tracking) load)
  │                                          │
  ▼                                          ▼
memory.py    ~/.cty-cli/skills/
(session                                    (scan SKILL.md
persist)                                    files at startup)
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API key
cp .env.example .env
# Edit .env → add your DEEPSEEK_API_KEY

# 3. Run
python main.py
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/model <name>` | Switch model |
| `/provider <name>` | Switch provider (deepseek/anthropic/openai) |
| `/providers` | List available providers |
| `/models` | List models for current provider |
| `/config` | Show current configuration |
| `/trace` | Show last execution trace |
| `/plan` | Show current task plan |
| `/skills` | List available skills |
| `/memory` | List saved memories |
| `/clear` | Clear conversation |
| `/exit` | Quit |

## Available Tools

| Tool | Risk | Description |
|------|------|-------------|
| `read_file` | read | Read file with line numbers |
| `write_file` | write | Create/overwrite file |
| `edit_file` | write | Exact string replacement (+ diff) |
| `list_files` | read | List directory contents |
| `execute_command` | exec | Run shell commands |
| `search_code` | read | Regex search in files |
| `plan_create` | write | Create a task |
| `plan_update` | write | Update task status |
| `plan_list` | read | List all tasks |
| `memory_save` | read | Save to persistent memory |
| `memory_recall` | read | Search memories |
| `load_skill` | read | Activate a skill |

## Project Structure

```
cty-cli/
├── main.py              # Entry point + REPL
├── agent.py             # Core agent loop
├── tools.py             # 12 tool definitions + execution
├── permissions.py       # 3-tier permission system
├── context.py           # Token estimation + compression
├── trace.py             # Step-by-step execution logging
├── plan.py              # Task tracking (exposed as tools)
├── memory.py            # Persistent memory (~/.cty-cli/memory/)
├── skills.py            # Progressive skill loading
├── ui.py                # Terminal UI (direct streaming)
├── config.py            # Model/provider switching
├── providers/
│   ├── __init__.py      # Factory
│   ├── base.py          # Unified Chunk interface
│   ├── anthropic.py     # Anthropic Messages API
│   └── openai_compat.py # OpenAI/DeepSeek/Groq
├── .env.example
├── requirements.txt
└── README.md
```

## Key Design Decisions

### Provider Abstraction
All LLM streaming responses are normalized into `TextChunk | ToolUseChunk`.
The agent loop doesn't know which provider is behind it — Anthropic's `tool_use`
blocks and OpenAI's `function_calls` are converted to the same internal format.

### Progressive Skill Loading
Skills are scanned at startup (name + description ≈ 80 tokens each).
The full SKILL.md body (~2k-5k tokens) loads only when the agent calls
`load_skill(name)`. This mirrors Claude Code's progressive loading mechanism.

### Token Estimation
Uses a character-count heuristic (≈95% accurate) to avoid the tiktoken dependency.
Chinese characters ≈ 1.5 chars/token, English ≈ 4 chars/token.

### Compression
When messages exceed 80% of the model's context window, older messages are
summarized and replaced with a `[Compressed history]` block. The most recent
6 messages are always preserved in full.

### Permission Model
- **auto-allow**: read-only tools (read_file, search_code, list_files, plan_list)
- **ask**: write tools (write_file, edit_file, plan_create, plan_update)
- **ask**: exec tools (execute_command)
- **always-allow**: user can grant session-wide approval for any tool

## Requirements

- Python 3.9+
- anthropic >= 0.39.0
- openai >= 1.0.0
- python-dotenv >= 1.0.0
