# Memory System

CTY-Cli has a persistent, cross-session memory system that allows the agent to remember user preferences, project context, and important decisions across restarts.

## Design Philosophy

The memory system is designed to be **observable** (you can always see what's stored), **filtered** (sensitive info is blocked), and **lightweight** (no vector database required, but extensible to one).

## Storage

Memories are stored as JSONL (one JSON object per line) at:

| Scope | Path |
|-------|------|
| **workspace** (default) | `<project>/.cty/memory.jsonl` |
| **global** | `~/.cty/memory.jsonl` |

Set `MEMORY_SCOPE=global` in `.env` to switch to global storage.

### Why JSONL?

- Human-readable with any text editor
- Append-only friendly (just add a line)
- Git-friendly (can be committed to share project context with the team)
- Easy to export, backup, and migrate

## Data Structure

Each memory entry:

```json
{
  "id": "a1b2c3d4e5f6",
  "content": "User prefers Java ACM format for algorithm problems",
  "tags": ["coding", "algorithm", "format"],
  "source": "user",
  "scope": "workspace",
  "importance": 3,
  "created_at": "2026-06-23T15:30:00",
  "updated_at": "2026-06-23T15:30:00"
}
```

| Field | Description |
|-------|-------------|
| `id` | SHA-256 hash of content (first 12 chars), used for dedup and lookup |
| `content` | The memory text |
| `tags` | Categorization tags (free-form) |
| `source` | Who created it: `user` (CLI), `agent` (model), `auto` (system) |
| `scope` | `workspace` or `global` |
| `importance` | 1 (low) to 5 (critical) — affects search ranking |
| `created_at` | ISO timestamp |
| `updated_at` | ISO timestamp |

## CLI Commands

All available from the REPL:

| Command | Description |
|---------|-------------|
| `/memory add <text>` | Save a new memory manually |
| `/memory list` | List all memories (most recent first) |
| `/memory search <query>` | Search by keyword |
| `/memory delete <id-prefix>` | Delete by ID prefix (first 8 chars) |
| `/memory clear` | Remove all memories |
| `/memory export` | Export all memories as JSON |

Example session:

```
> /memory add I always write algorithm solutions in Java using ACM format
  Saved: [a1b2c3d4] I always write algorithm solutions in Java using ACM format

> /memory list
  3 memories (stored at C:\Users\dell\cty-cli\.cty\memory.jsonl):
  [1] [a1b2c3d4] [no tags] I always write algorithm solutions in Java using ACM format
  [2] [e5f6g7h8] [coding,pref] Default to pytest for testing
  [3] [i9j0k1l2] [project] This project targets Python 3.9+

> /memory search python
  Found 2:
  [e5f6g7h8] [coding,pref] Default to pytest for testing
  [i9j0k1l2] [project] This project targets Python 3.9+

> /memory export
  (JSON output of all entries)
```

## Agent Tools

The agent has two tools for memory:

### `memory_store`

Stores information for future sessions. Called when the user shares a preference, project convention, or feedback.

Parameters: `content` (required), `tags` (optional, comma-separated), `importance` (optional, 1-5)

### `memory_recall`

Searches stored memories. Called before answering questions that might need context from prior sessions.

Parameters: `query` (required)

## Auto-Recall

Before each user message is sent to the LLM, the memory system searches for relevant entries and, if found, prepends them to the message:

```
## Relevant Memories
1. [coding,algorithm,format] User prefers Java ACM format for algorithm problems

---
User: What format should I use for writing this algorithm?
```

This is limited to 5 results maximum to preserve context window space.

## Search Algorithm

The current implementation uses a lightweight multi-factor scoring:

1. **Keyword match** (+10 for exact match, +3 per term match)
2. **Tag match** (+8 for exact tag match, +2 per partial)
3. **Importance bonus** (+1.5 per importance level)
4. **Recency decay** (newer memories score higher, decaying over days)
5. **Word overlap** (+2 per overlapping word, simple Jaccard-inspired)

Future extension point: swap in an embedding-based vector search backend by implementing the `MemoryBackend` abstract class.

## Sensitive Information Filtering

Before storage, all memory content is scanned for:

- API keys (`sk-...`, `sk-ant-...`, `ghp_...`)
- Passwords and tokens (heuristic patterns)
- Bearer tokens
- Credit card numbers (15-19 digits)
- Chinese ID numbers (18 digits with checksum pattern)
- Private file paths (`.env`, `id_rsa`, `credentials.json`)

If detected, the save is rejected with a descriptive error. This filtering is done **before** data hits disk — the rejection happens in memory.

## Privacy & Limitations

**What memory does NOT store:**
- Raw conversation history
- API keys, tokens, passwords
- Personal identity documents
- Private file contents

**Current limitations:**
1. **No encryption at rest**: Memory files are plain JSONL. For sensitive projects, encrypt the `.cty/` directory or use filesystem encryption
2. **No sharing controls**: Workspace memories are project-scoped but not access-controlled
3. **Search is keyword-based**: Complex semantic queries will improve with the planned embedding backend
4. **No automatic expiration**: Old memories are not auto-purged (but recency scoring down-ranks them)

## Demo: Cross-Session Recall

### Session 1
```
> /memory add I default to Java ACM format for all algorithm problems
  Saved: [a1b2c3d4]

> /exit
  Goodbye.
```

### Session 2 (after restart)
```
CTY-Cli v0.1.0
> What language and format should I use for algorithm problems?

[Agent auto-recalls the memory, then responds:]
Based on your preferences, you use Java ACM format for algorithm problems.
I'll keep that in mind for any code I write for you.
```

## Extension: Embedding/Vector Backend

To add a vector search backend (e.g., Chroma, Qdrant, or local embeddings):

1. Implement `MemoryBackend` abstract class
2. Add to `memory.py` with a factory function
3. Set `MEMORY_BACKEND=chroma` in config

```python
class ChromaMemoryBackend(MemoryBackend):
    def add(self, entry): ...
    def search(self, query, limit=5): ...  # Uses embeddings
    # ... etc
```

The `MemoryManager` API stays identical — only the backend changes.
