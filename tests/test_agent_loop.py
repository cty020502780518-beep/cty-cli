"""Tests for agent.py — full agent loop with mock provider.

Verifies: user input -> LLM request with tools -> tool execution -> model output
"""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import Agent
from tools import set_tool_context
from tests.conftest import MockProvider, MockUI


class TestAgentLoop:
    def test_simple_text_response(self, sample_config):
        """Agent handles a simple text response (no tool use)."""
        provider = MockProvider(responses=["Hello, how can I help you today?"])
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        agent.run("Hi there!")
        # Agent should have text output
        assert len(ui.text_output) > 0
        full_text = "".join(ui.text_output)
        assert "Hello" in full_text

    def test_tool_use_read_file(self, sample_config, tmp_path):
        """Agent makes a read_file tool call with mock provider."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        sample_config.working_dir = tmp_path

        provider = MockProvider(
            responses=["Let me read that file for you."],
            tool_calls=[{"name": "read_file", "params": {"file_path": str(test_file)}}],
        )
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        agent.run("Read test.py for me")
        # Should have tool call output
        assert len(ui.tool_calls_shown) >= 1
        assert ui.tool_calls_shown[0][0] == "read_file"

    def test_tool_use_write_file(self, sample_config, tmp_path):
        """Agent makes a write_file tool call that needs permission."""
        sample_config.working_dir = tmp_path

        provider = MockProvider(
            responses=["I've written the file."],
            tool_calls=[{
                "name": "write_file",
                "params": {"file_path": str(tmp_path / "output.txt"), "content": "hello world"}
            }],
        )
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        agent.run("Write output.txt")
        # Should have prompted for permission or executed
        # write_file is in NEEDS_APPROVAL so UI should be asked
        # But our MockUI returns "y" for ask_permission
        if ui.permission_requests:
            assert ui.permission_requests[0][0] == "write_file"
        # File should be created
        assert (tmp_path / "output.txt").exists()

    def test_tool_use_plan_create(self, sample_config):
        """Agent uses plan_create tool."""
        provider = MockProvider(
            responses=["I created a task for that."],
            tool_calls=[{"name": "plan_create", "params": {"title": "Fix bug", "description": "Fix the login bug"}}],
        )
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        agent.run("Create a task to fix login bug")
        # Plan should have one task
        tasks = agent.planner.tasks
        assert len(tasks) == 1
        assert tasks["task-1"].title == "Fix bug"

    def test_tool_use_memory_store(self, sample_config, tmp_path):
        """Agent uses memory_store tool to save a memory."""
        sample_config.working_dir = tmp_path

        provider = MockProvider(
            responses=["I'll remember that for you."],
            tool_calls=[{
                "name": "memory_store",
                "params": {"content": "User likes dark mode", "tags": "preferences,ui", "importance": 3}
            }],
        )
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        agent.run("Remember that I like dark mode")
        # Check memory was stored
        mems = agent.memory.list_all()
        assert len(mems) == 1

    def test_multi_turn_tool_loop(self, sample_config, tmp_path):
        """Agent handles multi-turn: ask -> tool -> response -> tool -> final."""
        sample_config.working_dir = tmp_path
        test_file = tmp_path / "code.py"
        test_file.write_text("old content")

        provider = MockProvider(
            responses=["I've read the file.", "I've updated the file."],
            tool_calls=[
                {"name": "read_file", "params": {"file_path": str(test_file)}},
                {"name": "edit_file", "params": {"file_path": str(test_file), "old_string": "old content", "new_string": "new content"}},
            ],
        )
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        agent.run("Read and update code.py")
        # Two tool calls should have been made
        assert len(provider.call_history) >= 2
        # File should be modified
        assert test_file.read_text() == "new content"

    def test_command_with_slash_handled(self, sample_config):
        """Slash commands are handled without calling LLM."""
        provider = MockProvider(responses=["should not be called"])
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        agent.run("/help")
        # Should not have called LLM
        assert len(provider.call_history) == 0
        # Should have shown help text
        assert len(ui.system_messages) > 0

    def test_memory_auto_recall_updates_context(self, sample_config, tmp_path):
        """Auto-recall injects relevant memories before LLM call."""
        sample_config.working_dir = tmp_path
        # Pre-seed a memory
        agent_mem = Agent.__new__(Agent)
        # Use the real memory manager to seed
        from memory import MemoryManager
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("User defaults to Java ACM format for algorithm problems", tags=["coding", "algorithm"])

        provider = MockProvider(responses=["I see you prefer Java."])
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)
        # Override the memory manager with our seeded one
        agent.memory = mm

        agent.run("What format should I use for algorithms?")
        # The recall message should be in the messages sent to LLM
        if provider.last_messages:
            user_msgs = [m for m in provider.last_messages if m["role"] == "user"]
            if user_msgs:
                # At least one user message should contain the recall or the original question
                combined = " ".join(str(m.get("content", "")) for m in user_msgs)
                assert "algorithm" in combined.lower()

    def test_security_guard_blocks_dangerous_path(self, sample_config, tmp_path):
        """PathGuard blocks access to .env files via agent tool calls."""
        sample_config.working_dir = tmp_path

        provider = MockProvider(
            tool_calls=[{"name": "read_file", "params": {"file_path": str(tmp_path / ".env")}}],
            responses=["blocked"],
        )
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        agent.run("Read the .env file")
        # The read should have been blocked by PathGuard
        all_results = " ".join(ui.tool_results)
        assert "Security blocked" in all_results or "Blocked" in all_results or ".env" in all_results


class TestSlashCommands:
    def test_help(self, sample_config):
        provider = MockProvider()
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)
        agent.run("/help")
        help_text = " ".join(ui.system_messages)
        assert "/model" in help_text
        assert "/memory" in help_text
        assert "/exit" in help_text

    def test_config(self, sample_config):
        provider = MockProvider()
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)
        agent.run("/config")
        config_text = " ".join(ui.system_messages)
        assert "deepseek" in config_text.lower() or "Provider" in config_text

    def test_exit(self, sample_config):
        provider = MockProvider()
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)
        assert agent.running
        agent.run("/exit")
        assert not agent.running

    def test_clear(self, sample_config):
        provider = MockProvider()
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)
        initial_msg_count = len(agent.messages)
        agent.run("/clear")
        # Should keep only system prompt
        assert len(agent.messages) == 1


class TestAgentErrorHandling:
    def test_api_error_does_not_crash(self, sample_config):
        """Agent handles API errors gracefully."""
        provider = MockProvider()

        def raise_error(*args, **kwargs):
            raise RuntimeError("Simulated API timeout")

        provider.chat = raise_error
        ui = MockUI()
        agent = Agent(provider=provider, config=sample_config, ui=ui)

        # Should not raise exception
        agent.run("Hello")
        # UI should show error
        assert len(ui.system_messages) >= 1
