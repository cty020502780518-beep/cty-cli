"""Persistent memory system — cross-session knowledge retention.

Storage: JSONL file at .cty/memory.jsonl (workspace) or ~/.cty/memory.jsonl (global).
Configurable via MEMORY_SCOPE environment variable or config.

Features:
  - Persistent JSONL storage with workspace/global scope
  - CLI commands: /memory add|list|search|delete|clear|export
  - Auto-recall: retrieves relevant memories before LLM call
  - Sensitive info filtering on save
  - Lightweight keyword + tag + recency search
  - Extension interface for embedding/vector backends
"""

import json
import hashlib
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Sensitive info patterns (blocked from storage) ────────────────────

SENSITIVE_PATTERNS = [
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), "API key (sk-...)"),
    (re.compile(r'sk-ant-[a-zA-Z0-9_-]{20,}'), "Anthropic API key"),
    (re.compile(r'AIza[0-9A-Za-z\-_]{35}'), "Google API key"),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), "GitHub personal access token"),
    (re.compile(r'gho_[a-zA-Z0-9]{36}'), "GitHub OAuth token"),
    (re.compile(r'github_pat_[a-zA-Z0-9_]{20,}'), "GitHub fine-grained token"),
    (re.compile(r'(?:password|passwd|pwd)\s*[:=]\s*\S+', re.IGNORECASE), "password assignment"),
    (re.compile(r'(?:secret|token|key)\s*[:=]\s*\S{10,}', re.IGNORECASE), "secret/token/key assignment"),
    (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*'), "Bearer token"),
    (re.compile(r'\b\d{15,19}\b'), "possible credit card number"),
    (re.compile(r'\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'), "Chinese ID number"),
    (re.compile(r'\b[A-Z]:\\[^\s]*\\(?:\.env|id_rsa|credentials\.json)\b', re.IGNORECASE), "private file path (Windows)"),
    (re.compile(r'\b/(?:home|root|Users)/[^\s]*/(?:\.env|id_rsa|credentials\.json)\b', re.IGNORECASE), "private file path (Unix)"),
    (re.compile(r'(?:ACCESS_KEY|SECRET_KEY|API_KEY|AUTH_TOKEN|DATABASE_URL)\s*[:=]\s*\S+', re.IGNORECASE), "env var credential"),
]


# ── Data model ────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    id: str
    content: str
    tags: list[str] = field(default_factory=list)
    source: str = "user"       # "user" | "agent" | "auto"
    scope: str = "workspace"   # "workspace" | "global"
    importance: int = 1        # 1 (low) to 5 (critical)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not self.created_at:
            self.created_at = ts
        if not self.updated_at:
            self.updated_at = ts

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "tags": self.tags,
            "source": self.source,
            "scope": self.scope,
            "importance": self.importance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(
            id=d.get("id", ""),
            content=d.get("content", ""),
            tags=d.get("tags", []),
            source=d.get("source", "user"),
            scope=d.get("scope", "workspace"),
            importance=d.get("importance", 1),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


# ── Extension interface for future vector/embedding backends ──────────

class MemoryBackend(ABC):
    """Abstract backend for memory storage and retrieval.

    Current: JSONL file backend.
    Future: vector DB (Chroma, Qdrant), SQLite, or embedding-based search.
    """

    @abstractmethod
    def add(self, entry: MemoryEntry) -> None: ...

    @abstractmethod
    def get(self, entry_id: str) -> Optional[MemoryEntry]: ...

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]: ...

    @abstractmethod
    def delete(self, entry_id: str) -> bool: ...

    @abstractmethod
    def clear(self, scope: Optional[str] = None) -> int: ...

    @abstractmethod
    def list_all(self) -> list[MemoryEntry]: ...

    @abstractmethod
    def export(self) -> list[dict]: ...


# ── JSONL backend ─────────────────────────────────────────────────────

class JSONLMemoryBackend(MemoryBackend):
    """JSONL-file-based memory storage. One JSON object per line."""

    def __init__(self, file_path: Path):
        self._path = file_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, MemoryEntry] = {}
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        entry = MemoryEntry.from_dict(d)
                        self._entries[entry.id] = entry
                    except (json.JSONDecodeError, KeyError):
                        pass
        except Exception:
            pass

    def _save_all(self):
        with open(self._path, "w", encoding="utf-8") as f:
            for entry in self._entries.values():
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def add(self, entry: MemoryEntry) -> None:
        self._entries[entry.id] = entry
        self._save_all()

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        return self._entries.get(entry_id)

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        query_lower = query.lower()
        query_terms = query_lower.split()
        scored: list[tuple[float, MemoryEntry]] = []

        now = time.time()
        for entry in self._entries.values():
            score = 0.0
            content_lower = entry.content.lower()

            # Keyword match
            if query_lower in content_lower:
                score += 10.0
            else:
                term_matches = sum(1 for t in query_terms if t in content_lower)
                score += term_matches * 3.0

            # Tag match
            for tag in entry.tags:
                tag_lower = tag.lower()
                if query_lower in tag_lower:
                    score += 8.0
                elif any(t in tag_lower for t in query_terms):
                    score += 2.0

            # Importance bonus
            score += entry.importance * 1.5

            # Recency score (newer = higher)
            try:
                ts = time.mktime(time.strptime(entry.updated_at, "%Y-%m-%dT%H:%M:%S"))
                age_days = (now - ts) / 86400.0
                score += max(0, 5.0 - age_days * 0.1)
            except (ValueError, OSError):
                pass

            # Simple Jaccard-like overlap on word sets
            if query_terms:
                entry_words = set(content_lower.split())
                query_words = set(query_terms)
                overlap = len(query_words & entry_words)
                if overlap > 0:
                    score += overlap * 2.0

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def delete(self, entry_id: str) -> bool:
        if entry_id not in self._entries:
            return False
        del self._entries[entry_id]
        self._save_all()
        return True

    def clear(self, scope: Optional[str] = None) -> int:
        if scope:
            to_remove = [k for k, v in self._entries.items() if v.scope == scope]
            for k in to_remove:
                del self._entries[k]
            self._save_all()
            return len(to_remove)
        else:
            count = len(self._entries)
            self._entries.clear()
            self._save_all()
            return count

    def list_all(self) -> list[MemoryEntry]:
        return sorted(self._entries.values(), key=lambda e: e.updated_at, reverse=True)

    def export(self) -> list[dict]:
        return [e.to_dict() for e in self.list_all()]


# ── Sensitive info check ──────────────────────────────────────────────

def _check_sensitive(text: str) -> Optional[str]:
    """Return description of first sensitive pattern found, or None if clean."""
    for pattern, description in SENSITIVE_PATTERNS:
        if pattern.search(text):
            return description
    return None


# ── Memory Manager ────────────────────────────────────────────────────

class MemoryManager:
    """High-level memory manager with auto-recall, filtering, and CLI support.

    Usage:
        mm = MemoryManager(scope="workspace", workspace_root=Path.cwd())
        mm.add("User prefers Java ACM format", tags=["coding", "style"], source="user")
        results = mm.search("algorithm format")
        recall_text = mm.auto_recall("write an algorithm in my preferred format")
    """

    def __init__(self, scope: str = "workspace", workspace_root: Optional[Path] = None):
        self.scope = scope
        self.workspace_root = workspace_root or Path.cwd()

        if scope == "global":
            storage_path = Path.home() / ".cty" / "memory.jsonl"
        else:
            storage_path = self.workspace_root / ".cty" / "memory.jsonl"

        self._backend: MemoryBackend = JSONLMemoryBackend(storage_path)
        self._auto_recall_limit = 5

    @property
    def storage_path(self) -> Path:
        if isinstance(self._backend, JSONLMemoryBackend):
            return self._backend._path
        return Path("")

    # ── CRUD ──────────────────────────────────────────────────────────

    def add(self, content: str, tags: Optional[list[str]] = None,
            source: str = "user", importance: int = 1,
            scope: Optional[str] = None) -> MemoryEntry:
        """Add a memory entry. Returns the entry, or raises ValueError on sensitive content."""
        # Security check
        sensitive = _check_sensitive(content)
        if sensitive:
            raise ValueError(f"Cannot save memory: contains {sensitive}")

        entry_id = hashlib.sha256(content.encode()).hexdigest()[:12]
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            tags=tags or [],
            source=source,
            scope=scope or self.scope,
            importance=max(1, min(5, importance)),
        )
        self._backend.add(entry)
        return entry

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        return self._backend.search(query, limit)

    def list_all(self) -> list[MemoryEntry]:
        return self._backend.list_all()

    def delete(self, entry_id: str) -> bool:
        return self._backend.delete(entry_id)

    def clear(self, scope: Optional[str] = None) -> int:
        return self._backend.clear(scope)

    def export(self) -> list[dict]:
        return self._backend.export()

    # ── Auto recall ───────────────────────────────────────────────────

    def auto_recall(self, query: str, limit: int = 5) -> str:
        """Search for relevant memories and return a formatted context string.

        This is injected into the system prompt BEFORE the LLM call.
        """
        entries = self._backend.search(query, limit)
        if not entries:
            return ""

        lines = ["## Relevant Memories"]
        for i, e in enumerate(entries, 1):
            lines.append(f"{i}. [{','.join(e.tags) if e.tags else 'no tags'}] {e.content}")
        return "\n".join(lines)

    # ── System prompt bootstrap ───────────────────────────────────────

    def bootstrap_prompt(self) -> str:
        """Lightweight index for the system prompt (loaded at startup)."""
        entries = self._backend.list_all()
        if not entries:
            return ""

        lines = ["## User Memories (auto-loaded)"]
        for e in entries[:20]:
            tags_str = f"[{','.join(e.tags)}]" if e.tags else ""
            lines.append(f"- {tags_str} {e.content[:120]}")
        if len(entries) > 20:
            lines.append(f"  ... and {len(entries) - 20} more memories")
        return "\n".join(lines)

    # ── Agent tool interface ──────────────────────────────────────────

    def tool_store(self, content: str, tags: str = "", importance: int = 1) -> str:
        """Called by the agent via memory_store tool."""
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        try:
            entry = self.add(content, tags=tag_list, source="agent", importance=importance)
            return f"Stored memory [{entry.id}]: {entry.content[:100]}"
        except ValueError as e:
            return f"Cannot store: {e}"

    def tool_recall(self, query: str) -> str:
        """Called by the agent via memory_recall tool."""
        entries = self.search(query)
        if not entries:
            return f"No memories found for '{query}'"
        lines = [f"Found {len(entries)} memories:"]
        for e in entries:
            tags_str = f"[{','.join(e.tags)}]" if e.tags else ""
            lines.append(f"  [{e.id[:8]}] {tags_str} {e.content}")
        return "\n".join(lines)
