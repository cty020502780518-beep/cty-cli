# CTY-Cli

A lightweight **coding agent CLI** and **agent harness demo**. Connects to LLMs (DeepSeek, Claude, GPT-4o) via a provider-agnostic abstraction layer, orchestrates structured tool use with permission controls, and persists knowledge across sessions through a built-in memory system.

CTY-Cli is **not** a wrapper around chat APIs — it is a demonstration of how a Claude Code / Codex-style agent harness is built: provider abstraction, tool loop, permission gates, context management, memory, plan tracking, skills, and execution tracing.

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate    # Linux/macOS
# venv\Scripts\activate     # Windows

# 2. Install dependencies
pip install -r requirements.txt
pip install -e .

# 3. Configure API keys
cp .env.example .env
# Edit .env → add your DEEPSEEK_API_KEY (or ANTHROPIC_API_KEY / OPENAI_API_KEY)

# 4. Run
python main.py
```

Once inside the REPL:
```
> /help          # Show all commands
> What can you do?   # Chat with the agent
> /exit          # Quit
```

## Supported Providers

| Provider | Setup | Notes |
|----------|-------|-------|
| **DeepSeek** (default) | `DEEPSEEK_API_KEY` in `.env` | V3, R1; tool calling uses non-streaming mode for reliability |
| **Anthropic (Claude)** | `ANTHROPIC_API_KEY` in `.env` | Full streaming + native tool_use support |
| **OpenAI (GPT-4o)** | `OPENAI_API_KEY` in `.env` | Compatible mode via chat/completions |
| **Groq / other OpenAI-compatible** | Set `base_url` in config | Any `/v1/chat/completions` endpoint |

Switch providers at runtime:
```
/provider anthropic
/model claude-sonnet-4-6-20250514
```

> **Note on streaming**: Chat mode streams tokens in real-time. Tool calling mode uses non-streaming on DeepSeek/OpenAI-compatible providers (streaming + tool calls is unreliable on those APIs). Anthropic's native provider streams everything including tool use blocks. See [docs/architecture.md](docs/architecture.md).

## Features

### Agent Loop
The core loop (LLM → tool_use → permission check → execute → result → loop) is provider-agnostic. Add a new LLM by implementing ~150 lines of streaming normalization in `providers/`.

### Tools (14 built-in)
| Tool | Risk | Description |
|------|------|-------------|
| `read_file` | read | Read file with line numbers |
| `write_file` | write | Create or overwrite a file |
| `edit_file` | write | Exact string replacement with unified diff output |
| `list_files` | read | List directory contents |
| `execute_command` | exec | Run shell commands |
| `search_code` | read | Regex search across files |
| `web_search` | read | Web search via DuckDuckGo (no API key needed) |
| `plan_create` | write | Create a tracked task |
| `plan_update` | write | Update task status |
| `plan_list` | read | List all tasks |
| `memory_store` | read | Store into persistent memory |
| `memory_save` | read | Save categorized memory |
| `memory_recall` | read | Search stored memories |
| `load_skill` | read | Activate a skill |

### Security (4-layer)
1. **System prompt** guidance (advisory)
2. **Permission manager**: auto-allow / ask / always-allow tiers
3. **PathGuard**: blocks access to `.env`, `.ssh`, credentials, system dirs, and paths outside workspace
4. **CommandGuard**: blocks `rm -rf`, `sudo`, `curl | sh`, `format`, registry modifications, and 30+ other dangerous patterns

See [docs/security.md](docs/security.md) for details.

### Persistent Memory
Cross-session memory with CLI commands (`/memory add|list|search|delete|clear|export`), auto-recall before LLM calls, agent-facing tools (`memory_store`, `memory_recall`), and sensitive info filtering. Stored as JSONL at `.cty/memory.jsonl` (workspace) or `~/.cty/memory.jsonl` (global).

See [docs/memory.md](docs/memory.md) for the full design and a cross-session recall demo.

### Execution Trace
Every agent turn produces a structured trace recording: think, tool_call (name + params), confirm (approved/denied), tool_result. Viewable via `/trace`.

### Context Management
5-segment system prompt (core + project rules + memory index + environment + skills), heuristic token estimation, and automatic compression when exceeding 80% of model context limit.

### Skills
Progressive skill loading: scan SKILL.md files at startup (name + description ~80 tokens each), load full bodies on demand via `load_skill` tool. Compatible with Claude Code skill directories.

## Verification

Run the smoke test to verify everything works:

**Windows (PowerShell):**
```powershell
cd C:\Users\dell\cty-cli
powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1
```

**Linux/macOS (or Git Bash on Windows):**
```bash
cd cty-cli
bash scripts/smoke_test.sh
```

**Manual verification:**
```bash
python -m py_compile *.py providers/*.py    # Compile check
python -m pytest tests/ -v                    # Run tests
python main.py --version                      # Version check
```

## Project Structure

```
cty-cli/
├── main.py              # Entry point, REPL, slash commands
├── agent.py             # Core agent loop (LLM ⇄ Tool roundtrip)
├── tools.py             # 14 tool definitions + execution
├── permissions.py       # 3-tier permission system
├── security.py          # PathGuard + CommandGuard
├── context.py           # Token estimation + compression
├── trace.py             # Step-by-step execution logging
├── plan.py              # Task tracking (exposed as tools)
├── memory.py            # Persistent JSONL memory system
├── skills.py            # Progressive skill loading
├── ui.py                # Terminal UI (direct streaming)
├── config.py            # Provider/model switching + .env loading
├── providers/
│   ├── __init__.py      # Provider factory
│   ├── base.py          # Unified Chunk interface
│   ├── anthropic.py     # Anthropic Messages API
│   └── openai_compat.py # OpenAI/DeepSeek/Groq compatible
├── tests/
│   ├── conftest.py      # Mock provider + fixtures
│   ├── test_config.py
│   ├── test_permissions.py
│   ├── test_security.py
│   ├── test_memory.py
│   ├── test_context.py
│   ├── test_tools.py
│   └── test_agent_loop.py
├── scripts/
│   ├── smoke_test.ps1   # Windows smoke test
│   └── smoke_test.sh    # Linux/macOS smoke test
├── docs/
│   ├── architecture.md
│   ├── security.md
│   ├── memory.md
│   ├── demo.md
│   └── troubleshooting.md
├── .github/workflows/ci.yml
├── .env.example
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Architecture

```
User → CLI (main.py) → Agent Loop → Provider → LLM
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    PermissionGuard  ToolExecutor   ContextManager
          │               │               │
          ▼               ▼               ▼
    [ask/auto/deny]  [14 tools]   [compress/token]
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
     PlanManager     MemoryManager    Trace
     (task tracking) (persistent)    (step log)
```

For a detailed architecture walkthrough, see [docs/architecture.md](docs/architecture.md).

## Demo

Screenshots and videos are planned — see [docs/demo.md](docs/demo.md) for the capture guide.

Placeholder locations:
- `docs/images/startup.png` — Welcome screen
- `docs/images/memory-demo.png` — Memory add/recall workflow
- `docs/images/tool-use.png` — Agent using tools
- `docs/videos/demo.mp4` — Full feature walkthrough

## Current Limitations

This is a **learning and engineering practice project** — not a production-ready coding agent. Honest limitations:

- **Not a sandbox**: Commands execute with the user's real filesystem permissions. CommandGuard is regex-based and can be bypassed with obfuscation.
- **No Docker isolation**: Production coding agents should run in containers or microVMs.
- **Token estimation is heuristic**: Character-count based (~4 chars/token English, ~1.5 chars/token Chinese). Not tiktoken-precise.
- **Memory search is keyword-based**: No semantic/embedding search yet (extension interface is ready).
- **Single-turn plan tracking**: Plan tasks don't persist across sessions.
- **No multi-modal support**: Text-only. No image understanding or generation.
- **No streaming during tool calls on DeepSeek**: Falls back to non-streaming for reliability.

### Planned Improvements

- Docker sandbox / E2B / Firecracker microVM integration
- Embedding-based semantic memory search (Chroma/Qdrant backend)
- More complete benchmark suite (SWE-bench lite, HumanEval)
- Multi-turn repair loop with self-debugging
- Web UI (in addition to terminal)
- Multi-agent collaboration

## Requirements

- Python 3.9+
- Dependencies listed in `requirements.txt`

## License

MIT
