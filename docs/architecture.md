# Architecture

CTY-Cli follows a modular agent harness design inspired by Claude Code's internal architecture. The core idea is: **the agent loop doesn't care which LLM sits behind it, which tools it calls, or where data comes from — each layer is abstracted.**

## High-Level Flow

```
User Input
    │
    ▼
┌──────────────┐
│   main.py    │  Entry point, REPL, slash-command dispatch
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  agent.py    │────▶│  providers/  │────▶│  LLM APIs    │
│  Core Loop   │     │  base.py     │     │  DeepSeek    │
│  LLM ⇄ Tool  │     │  anthropic   │     │  Anthropic   │
│  roundtrip   │     │  openai_     │     │  OpenAI      │
└──┬───┬───┬───┘     │  compat.py   │     │  (Groq, etc) │
   │   │   │         └──────────────┘     └──────────────┘
   │   │   │
   ▼   ▼   ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│tools │ │context│ │permi-│ │trace │ │plan  │ │memory│
│.py   │ │.py   │ │ssions│ │.py   │ │.py   │ │.py   │
│      │ │      │ │.py   │ │      │ │      │ │      │
│14    │ │Token │ │3-tier│ │Step- │ │Task  │ │JSONL │
│tools │ │estim │ │safety│ │by-   │ │track │ │persi-│
│+exec │ │+comp │ │model │ │step  │ │ing   │ │stent │
└──┬───┘ └──────┘ └──┬───┘ └──────┘ └──────┘ └──┬───┘
   │                  │                          │
   ▼                  ▼                          ▼
┌──────┐       ┌──────────┐             ┌──────────────┐
│secu- │       │ui.py     │             │skills.py     │
│rity  │       │Terminal  │             │Progressive   │
│.py   │       │streaming │             │skill loading │
│Path+ │       │output    │             │              │
│Cmd   │       └──────────┘             └──────────────┘
│Guard │
└──────┘
```

## Agent Loop (Detailed)

```
┌──────────────────────────────────────────────────────┐
│                    Agent Loop                         │
│                                                      │
│  1. User enters query                                │
│         │                                            │
│  2. Memory auto-recall                               │
│     Search memory.jsonl for relevant context         │
│         │                                            │
│  3. Context Manager                                  │
│     Assemble messages + system prompt                │
│     Compress if over token threshold                 │
│         │                                            │
│  4. Provider API call (streaming)                    │
│     Yield TextChunk | ToolUseChunk                   │
│         │                                            │
│  5. If TextChunk: stream to UI, accumulate           │
│     If ToolUseChunk:                                 │
│       a. Check permissions (auto/ask/block)          │
│       b. Check PathGuard/CommandGuard                │
│       c. Present to user if needs approval           │
│       d. Execute tool                                │
│       e. Record in trace                             │
│       f. Feed result back to LLM                     │
│         │                                            │
│  6. Loop until: no more tool calls OR max turns       │
│                                                      │
│  7. Display final text response                      │
└──────────────────────────────────────────────────────┘
```

## Provider Abstraction

All LLM streaming responses are normalized into two chunk types:

```python
TextChunk      — plain text (streamed character-by-character)
ToolUseChunk   — complete tool call (name + params)
```

Whether it's Anthropic's `content_block_start/delta/stop` events or OpenAI's `chat.completions.chunk` with `delta.tool_calls`, the agent loop receives the same interface. See `providers/base.py`.

### Streaming Behavior

| Mode | Behavior | Why |
|------|----------|-----|
| **Chat (no tools)** | Full streaming, each token printed immediately | Best UX |
| **Tool calling (DeepSeek/OpenAI compat)** | Non-streaming, response returned as complete text chunks | Streaming + tool calls is unreliable on DeepSeek; pre-aggregated for compatibility |
| **Tool calling (Anthropic native)** | Full streaming, tool_use blocks aggregated from stream events | Anthropic's streaming protocol supports inline tool_use |

## Permission Model

See [docs/security.md](security.md) for the full security model.

```
auto-allow  ─── read tools, skills, memory tools (no prompt)
ask          ─── write tools, exec tools (user must approve)
always-allow ─── user can grant session-wide permission (remembered for session)
blocked      ─── dangerous commands + out-of-workspace paths
```

## Memory System

See [docs/memory.md](memory.md) for the full memory design.

## Key Design Decisions

1. **Streaming-first UI**: Every text chunk goes directly to stdout — no buffering, no intermediate rendering layer
2. **Progressive skill loading**: Skills are indexed at startup (~80 tokens each), full bodies loaded on demand (2k-5k tokens)
3. **Heuristic compression**: When context exceeds 80% of model limit, old messages are summarized without an extra LLM call
4. **Non-streaming tool mode**: DeepSeek's streaming + tool calling combination is unreliable, so we fall back to non-streaming for tool calls
5. **Mock-first testing**: All agent loop tests use a mock provider — no real API keys needed for CI
