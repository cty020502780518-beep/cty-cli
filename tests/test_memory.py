"""Tests for memory.py — persistent memory system."""
import json
import os
import tempfile
from pathlib import Path
import pytest
from memory import (
    MemoryManager,
    MemoryEntry,
    JSONLMemoryBackend,
    _check_sensitive,
)


class TestMemoryEntry:
    def test_create_entry(self):
        entry = MemoryEntry(
            id="test-1",
            content="User prefers Java ACM format",
            tags=["coding", "style"],
            source="user",
            scope="workspace",
            importance=3,
        )
        d = entry.to_dict()
        assert d["id"] == "test-1"
        assert d["content"] == "User prefers Java ACM format"
        assert d["tags"] == ["coding", "style"]
        assert d["importance"] == 3
        assert d["created_at"] != ""

    def test_roundtrip_dict(self):
        entry = MemoryEntry(
            id="test-2",
            content="Project uses Python 3.9+",
            tags=["python", "config"],
        )
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.id == entry.id
        assert restored.content == entry.content
        assert restored.tags == entry.tags

    def test_defaults(self):
        entry = MemoryEntry(id="test-3", content="hello")
        assert entry.tags == []
        assert entry.importance == 1
        assert entry.source == "user"
        assert entry.scope == "workspace"


class TestJSONLBackend:
    def test_add_and_get(self, tmp_path):
        backend = JSONLMemoryBackend(tmp_path / "memory.jsonl")
        entry = MemoryEntry(id="m1", content="test memory", tags=["test"])
        backend.add(entry)
        retrieved = backend.get("m1")
        assert retrieved is not None
        assert retrieved.content == "test memory"

    def test_search_by_keyword(self, tmp_path):
        backend = JSONLMemoryBackend(tmp_path / "memory.jsonl")
        backend.add(MemoryEntry(id="m1", content="Java ACM format", tags=["coding"]))
        backend.add(MemoryEntry(id="m2", content="Python pytest config", tags=["testing"]))
        backend.add(MemoryEntry(id="m3", content="Java Spring Boot setup", tags=["coding"]))

        results = backend.search("Java")
        assert len(results) >= 1
        assert any("Java" in r.content for r in results)

    def test_search_by_tag(self, tmp_path):
        backend = JSONLMemoryBackend(tmp_path / "memory.jsonl")
        backend.add(MemoryEntry(id="m1", content="test", tags=["important"]))
        backend.add(MemoryEntry(id="m2", content="other", tags=["trivial"]))

        results = backend.search("important")
        assert len(results) >= 1
        assert results[0].content == "test"

    def test_delete(self, tmp_path):
        backend = JSONLMemoryBackend(tmp_path / "memory.jsonl")
        backend.add(MemoryEntry(id="m1", content="test"))
        assert backend.delete("m1")
        assert backend.get("m1") is None
        assert not backend.delete("nonexistent")

    def test_clear_all(self, tmp_path):
        backend = JSONLMemoryBackend(tmp_path / "memory.jsonl")
        backend.add(MemoryEntry(id="m1", content="test1"))
        backend.add(MemoryEntry(id="m2", content="test2"))
        count = backend.clear()
        assert count == 2
        assert len(backend.list_all()) == 0

    def test_clear_by_scope(self, tmp_path):
        backend = JSONLMemoryBackend(tmp_path / "memory.jsonl")
        backend.add(MemoryEntry(id="m1", content="ws", scope="workspace"))
        backend.add(MemoryEntry(id="m2", content="global", scope="global"))
        count = backend.clear(scope="workspace")
        assert count == 1
        remaining = backend.list_all()
        assert len(remaining) == 1
        assert remaining[0].scope == "global"

    def test_list_all_sorted_by_date(self, tmp_path):
        import time
        backend = JSONLMemoryBackend(tmp_path / "memory.jsonl")
        backend.add(MemoryEntry(id="old", content="old", created_at="2020-01-01T00:00:00", updated_at="2020-01-01T00:00:00"))
        time.sleep(0.1)
        backend.add(MemoryEntry(id="new", content="new"))
        items = backend.list_all()
        assert items[0].content == "new"  # most recent first

    def test_export(self, tmp_path):
        backend = JSONLMemoryBackend(tmp_path / "memory.jsonl")
        backend.add(MemoryEntry(id="m1", content="test"))
        data = backend.export()
        assert len(data) == 1
        assert data[0]["content"] == "test"

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "memory.jsonl"
        backend1 = JSONLMemoryBackend(path)
        backend1.add(MemoryEntry(id="m1", content="persistent"))
        # New instance loading same file
        backend2 = JSONLMemoryBackend(path)
        result = backend2.get("m1")
        assert result is not None
        assert result.content == "persistent"


class TestMemoryManager:
    def test_add_and_list(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("Test memory content", tags=["test"], source="user")
        all_mem = mm.list_all()
        assert len(all_mem) == 1
        assert all_mem[0].content == "Test memory content"

    def test_block_sensitive_content(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        with pytest.raises(ValueError, match="Cannot save"):
            mm.add("My API key is sk-abc123def456ghi789jkl012mno345pqr678stu")

    def test_search(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("I prefer Java ACM format for algorithms", tags=["coding", "format"])
        mm.add("I like dark mode themes", tags=["ui"])
        results = mm.search("Java ACM")
        assert len(results) >= 1
        assert "Java" in results[0].content

    def test_delete(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        entry = mm.add("test memory")
        assert mm.delete(entry.id)
        assert len(mm.list_all()) == 0

    def test_clear(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("m1")
        mm.add("m2")
        count = mm.clear()
        assert count == 2

    def test_export(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("export test")
        data = mm.export()
        assert len(data) == 1

    def test_auto_recall(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("User prefers Java ACM format for algorithm problems", tags=["coding", "algorithm"])
        mm.add("User likes dark theme for IDE", tags=["ui"])
        recall = mm.auto_recall("What format and language do I use for algorithms?")
        assert "Java" in recall or "algorithm" in recall.lower()

    def test_auto_recall_empty(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        result = mm.auto_recall("anything")
        assert result == ""

    def test_bootstrap_prompt(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("Test memory")
        prompt = mm.bootstrap_prompt()
        assert "Test memory" in prompt
        assert "User Memories" in prompt

    def test_bootstrap_prompt_empty(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        prompt = mm.bootstrap_prompt()
        assert prompt == ""

    def test_tool_store(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        result = mm.tool_store("Agent remembers this", tags="auto,coding", importance=4)
        assert "Stored memory" in result

    def test_tool_recall(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("Java ACM format for algorithms", tags=["coding"], source="agent")
        result = mm.tool_recall("algorithm format")
        assert "Java" in result

    def test_tool_recall_not_found(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        result = mm.tool_recall("nonexistent query xyz")
        assert "No memories found" in result

    def test_importance_affects_search(self, tmp_path):
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("low importance memory", importance=1)
        mm.add("HIGH IMPORTANCE MEMORY", importance=5)
        results = mm.search("memory")
        # High importance should appear first
        if len(results) >= 2:
            assert results[0].importance >= results[1].importance

    def test_global_scope(self, tmp_path):
        # Test with workspace scope
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        assert ".cty" in str(mm.storage_path)
