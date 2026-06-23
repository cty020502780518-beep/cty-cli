"""Tests for context.py — token estimation and compression."""
from context import ContextManager


class TestTokenEstimation:
    def test_empty_text(self):
        assert ContextManager.estimate_tokens("") == 0

    def test_none_text(self):
        assert ContextManager.estimate_tokens(None) == 0

    def test_english_text(self):
        tokens = ContextManager.estimate_tokens("hello world")
        assert tokens > 0
        assert tokens < 10

    def test_chinese_text(self):
        tokens = ContextManager.estimate_tokens("你好世界")
        assert tokens > 0
        # Chinese chars ~1.5 chars/token
        assert tokens <= 5


class TestContextSegments:
    def test_add_segment(self):
        cm = ContextManager()
        cm.add_segment("core", "Core instructions")
        cm.add_segment("env", "Environment info")
        prompt = cm.build_system_prompt()
        assert "Core instructions" in prompt
        assert "Environment info" in prompt

    def test_empty_segment_skipped(self):
        cm = ContextManager()
        cm.add_segment("core", "")
        cm.add_segment("env", "Valid")
        prompt = cm.build_system_prompt()
        assert "Valid" in prompt


class TestCompression:
    def test_no_compression_when_under_threshold(self):
        cm = ContextManager(model_limit=10000)
        messages = [{"role": "user", "content": "Hello"}]
        result, stats = cm.prepare(messages)
        assert not stats.compressed
        assert result == messages

    def test_compression_when_over_threshold(self):
        cm = ContextManager(model_limit=100)
        cm.compress_threshold = 10
        cm.keep_recent = 2
        messages = [
            {"role": "system", "content": "A" * 100},
            {"role": "user", "content": "B" * 100},
            {"role": "assistant", "content": "C" * 100},
            {"role": "user", "content": "D" * 100},
            {"role": "assistant", "content": "E" * 100},
        ]
        result, stats = cm.prepare(messages)
        assert stats.compressed
        # Should have compressed history block + recent messages
        assert any("Compressed" in m.get("content", "") for m in result)

    def test_stats_line(self):
        cm = ContextManager(model_limit=100000)
        messages = [{"role": "user", "content": "Hello world"}]
        line = cm.stats_line(messages)
        assert "tokens:" in line
        assert "/" in line
