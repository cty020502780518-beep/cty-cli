"""Tests for tools.py — file ops, search, and guard integration."""
import os
from pathlib import Path
import pytest

import tools
from security import PathGuard, CommandGuard


class TestFileTools:
    def test_read_file(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.read_file(str(temp_workspace / "test.txt"))
        assert "line 1" in result
        assert "line 2" in result

    def test_read_file_with_offset(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.read_file(str(temp_workspace / "test.txt"), offset=1)
        assert "line 2" in result
        assert "line 3" in result

    def test_read_file_with_limit(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.read_file(str(temp_workspace / "test.txt"), offset=0, limit=1)
        assert "line 1" in result
        assert "line 2" not in result

    def test_read_file_not_found(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.read_file(str(temp_workspace / "nonexistent.txt"))
        assert "not found" in result

    def test_write_file(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        path = str(temp_workspace / "new_file.txt")
        result = tools.write_file(path, "hello world")
        assert "Wrote" in result
        assert Path(path).exists()

    def test_write_file_blocked_by_guard(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.write_file(str(temp_workspace / ".env"), "SECRET=xxx")
        assert "Security blocked" in result

    def test_edit_file(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.edit_file(
            str(temp_workspace / "test.txt"),
            "line 2",
            "modified line 2"
        )
        assert "Applied edit" in result
        content = (temp_workspace / "test.txt").read_text()
        assert "modified line 2" in content

    def test_edit_file_not_found(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.edit_file(
            str(temp_workspace / "nonexistent.txt"),
            "old",
            "new"
        )
        assert "not found" in result.lower()

    def test_edit_file_no_match(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.edit_file(
            str(temp_workspace / "test.txt"),
            "this text does not exist in the file",
            "new"
        )
        assert "not found" in result.lower() and "old_string" in result.lower()

    def test_edit_file_multiple_matches(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        # Create file with duplicate lines
        (temp_workspace / "dup.txt").write_text("dup\ndup\n")
        result = tools.edit_file(
            str(temp_workspace / "dup.txt"),
            "dup",
            "replaced"
        )
        assert "appears" in result.lower() and "2" in result

    def test_list_files(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.list_files(str(temp_workspace))
        assert "test.txt" in result

    def test_list_files_not_found(self, temp_workspace):
        tools._context["path_guard"] = PathGuard(workspace_root=temp_workspace)
        result = tools.list_files(str(temp_workspace / "nonexistent"))
        assert "not found" in result.lower()


class TestCommandExecution:
    def test_safe_command(self):
        tools._context["command_guard"] = CommandGuard()
        result = tools.execute_command("echo hello")
        assert "hello" in result

    def test_blocked_command(self):
        tools._context["command_guard"] = CommandGuard()
        result = tools.execute_command("rm -rf /tmp/test")
        assert "Security blocked" in result

    def test_command_output_truncation(self):
        tools._context["command_guard"] = CommandGuard()
        result = tools.execute_command("echo hello")
        assert len(result) < 50000


class TestSearchCode:
    def test_search_in_workspace(self, temp_workspace):
        result = tools.search_code("line", path=str(temp_workspace))
        assert "line 1" in result

    def test_search_no_match(self, temp_workspace):
        result = tools.search_code("xyznonexistentpattern", path=str(temp_workspace))
        assert "No matches" in result

    def test_invalid_regex(self):
        result = tools.search_code("[invalid", path=".")
        assert "Invalid regex" in result


class TestToolDispatch:
    def test_unknown_tool(self):
        result = tools.execute_tool("nonexistent_tool", {})
        assert "unknown tool" in result.lower()

    def test_invalid_params_filtered(self):
        # execute_tool filters params to valid ones, so extra params shouldn't fail
        result = tools.execute_tool("read_file", {"file_path": str(Path.cwd() / "main.py"), "extra_bad_param": 123})
        # Should still work since read_file just gets file_path
        assert "Error" not in result or "not found" in result  # might work if main.py exists


class TestMemoryTools:
    def test_memory_save(self, tmp_path):
        from memory import MemoryManager
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        tools._context["memory"] = mm
        result = tools.memory_save("user", "Test Preference", "User prefers dark mode")
        assert "Stored" in result

    def test_memory_recall(self, tmp_path):
        from memory import MemoryManager
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        mm.add("User prefers Java ACM format", tags=["coding"], source="agent")
        tools._context["memory"] = mm
        result = tools.memory_recall("Java")
        assert "Java" in result

    def test_memory_store(self, tmp_path):
        from memory import MemoryManager
        mm = MemoryManager(scope="workspace", workspace_root=tmp_path)
        tools._context["memory"] = mm
        result = tools.memory_store("New memory from agent", tags="auto,test", importance=3)
        assert "Stored memory" in result
