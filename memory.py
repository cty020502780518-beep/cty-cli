"""Memory system — persistent storage of user/project/feedback knowledge.

Mirrors Claude Code's auto-memory at:
  ~/.claude/projects/<project>/memory/

Storage: ~/.cty-cli/memory/*.json
"""
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


STORAGE_DIR = Path.home() / ".cty-cli" / "memory"


@dataclass
class Memory:
    id: str
    type: str          # user | project | feedback | reference
    title: str
    content: str
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not self.created_at:
            self.created_at = ts
        if not self.updated_at:
            self.updated_at = ts


class MemoryManager:
    """Manages persistent memories across sessions.

    Startup: loads all *.json → bootstrap_prompt() injects into system prompt.
    Runtime: agent can save/recall/delete via exposed tools.
    """

    def __init__(self):
        self._dir = STORAGE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memories: dict[str, Memory] = {}
        self._load_all()

    # ── Startup ──────────────────────────────────────────────────────

    def _load_all(self):
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._memories[data["id"]] = Memory(**data)
            except (json.JSONDecodeError, KeyError):
                pass

    def bootstrap_prompt(self) -> str:
        """Lightweight index injected into system prompt (~50 tokens/entry)."""
        if not self._memories:
            return ""
        lines = ["## User Memories (auto-loaded)"]
        for m in self._memories.values():
            lines.append(f"- [{m.type}] {m.title}")
        return "\n".join(lines)

    # ── Runtime CRUD ─────────────────────────────────────────────────

    def save(self, type_: str, title: str, content: str) -> Memory:
        import re

        slug = re.sub(r"[^a-z0-9-]+", "-", title.lower().strip())[:50]
        mem = Memory(id=slug, type=type_, title=title, content=content)
        self._memories[slug] = mem
        (self._dir / f"{slug}.json").write_text(
            json.dumps(mem.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return mem

    def recall(self, query: str) -> list[Memory]:
        """Keyword-match recall. Production would use embeddings + vector search."""
        q = query.lower()
        results = []
        for m in self._memories.values():
            score = 0
            if q in m.title.lower():
                score += 10
            if q in m.content.lower():
                score += 5
            if q in m.type.lower():
                score += 2
            if score > 0:
                results.append((score, m))
        results.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in results[:5]]

    def delete(self, memory_id: str) -> bool:
        if memory_id not in self._memories:
            return False
        del self._memories[memory_id]
        fpath = self._dir / f"{memory_id}.json"
        if fpath.exists():
            fpath.unlink()
        return True

    def list_all(self) -> list[Memory]:
        return list(self._memories.values())
