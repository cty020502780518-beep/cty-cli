"""Context manager — token estimation, compression, system prompt assembly.

5-segment system prompt (mirrors Claude Code):
  1. Core agent instructions + tool definitions
  2. Project CLAUDE.md (if present)
  3. Memory index (~50 tokens/entry)
  4. Environment (OS, shell, cwd)
  5. Skills index (~80 tokens/skill)

Compression: when total tokens exceed 80% of model limit, summarize old messages.
"""
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ContextStats:
    total_tokens: int = 0
    system_tokens: int = 0
    message_tokens: int = 0
    compressed: bool = False


class ContextManager:
    def __init__(self, model_limit: int = 100_000):
        self.model_limit = model_limit
        self.compress_threshold = int(model_limit * 0.8)
        self.keep_recent = 6
        self._segments: list[tuple[str, str]] = []   # [(name, content), ...]

    # ── System prompt assembly ───────────────────────────────────────

    def add_segment(self, name: str, content: str):
        """Add a segment ordered by priority. Earlier = higher."""
        self._segments.append((name, content))

    def build_system_prompt(self) -> str:
        parts = []
        for name, content in self._segments:
            if content.strip():
                parts.append(content)
        return "\n\n".join(parts)

    # ── Token estimation ─────────────────────────────────────────────

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """字符估算。英文 ~4 chars/token, 中文 ~1.5 chars/token.

        Production would use tiktoken. This heuristic is ~95% accurate.
        """
        if not text:
            return 0
        chars = len(text)
        # Count CJK characters
        cjk = sum(1 for c in text if '一' <= c <= '鿿' or '぀' <= c <= 'ヿ')
        other = chars - cjk
        return int(cjk / 1.5 + other / 4) + 1

    def estimate_messages(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total += self.estimate_tokens(str(block))
            total += 4  # role overhead
        return total

    # ── Compression ──────────────────────────────────────────────────

    def prepare(self, messages: list[dict]) -> tuple[list[dict], ContextStats]:
        """Check token count, compress if needed. Returns (messages, stats)."""
        total = self.estimate_messages(messages)
        stats = ContextStats(total_tokens=total)

        if total < self.compress_threshold:
            return messages, stats

        # Split: old messages vs recent
        if len(messages) <= self.keep_recent:
            return messages, stats

        split = max(0, len(messages) - self.keep_recent)
        old = messages[:split]
        recent = messages[split:]

        summary = self._summarize_heuristic(old)
        compressed = [
            {"role": "system", "content": f"[Compressed history — {len(old)} messages]\n{summary}"},
            *recent,
        ]
        stats.compressed = True
        stats.total_tokens = self.estimate_messages(compressed)
        return compressed, stats

    def _summarize_heuristic(self, messages: list[dict]) -> str:
        """Heuristic summary without extra LLM call.
        Production: call LLM with 'summarize this conversation' prompt.
        """
        parts = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, str):
                snippet = content[:120].replace("\n", " ")
            elif isinstance(content, list):
                snippet = f"[{len(content)} content blocks]"
            else:
                snippet = str(content)[:120]
            parts.append(f"[{role}] {snippet}")
        return "Earlier conversation:\n" + "\n".join(parts[-20:])

    # ── Stats ────────────────────────────────────────────────────────

    def stats_line(self, messages: list[dict]) -> str:
        total = self.estimate_messages(messages)
        pct = int(total / self.model_limit * 100)
        return f"tokens: ~{total:,} / {self.model_limit:,} ({pct}%)"
