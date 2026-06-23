"""Tests for permissions.py — risk classification and approval flow."""
from permissions import (
    PermissionManager,
    tool_risk,
    describe_risk,
    AUTO_ALLOW,
    NEEDS_APPROVAL,
    READ_TOOLS,
    WRITE_TOOLS,
    EXEC_TOOLS,
)


class TestRiskClassification:
    def test_read_tools_are_auto_allow(self):
        for tool in READ_TOOLS:
            assert tool in AUTO_ALLOW, f"{tool} should be auto-allowed"

    def test_write_tools_need_approval(self):
        for tool in WRITE_TOOLS:
            assert tool in NEEDS_APPROVAL, f"{tool} should need approval"

    def test_exec_tools_need_approval(self):
        for tool in EXEC_TOOLS:
            assert tool in NEEDS_APPROVAL, f"{tool} should need approval"

    def test_tool_risk_read(self):
        assert tool_risk("read_file") == "read"
        assert tool_risk("search_code") == "read"

    def test_tool_risk_write(self):
        assert tool_risk("write_file") == "write"
        assert tool_risk("edit_file") == "write"

    def test_tool_risk_exec(self):
        assert tool_risk("execute_command") == "exec"

    def test_tool_risk_unknown(self):
        assert tool_risk("nonexistent_tool") == "unknown"


class TestDescribeRisk:
    def test_describe_edit_file(self):
        result = describe_risk("edit_file", {"file_path": "/tmp/test.py"})
        assert "/tmp/test.py" in result

    def test_describe_write_file(self):
        result = describe_risk("write_file", {"file_path": "/tmp/test.py", "content": "hello world"})
        assert "/tmp/test.py" in result
        assert "11" in result or "bytes" in result

    def test_describe_execute_command(self):
        result = describe_risk("execute_command", {"command": "git status"})
        assert "git status" in result

    def test_describe_plan(self):
        result = describe_risk("plan_create", {"title": "Fix bug"})
        assert "Fix bug" in result


class TestPermissionManager:
    def test_auto_allow_read(self):
        pm = PermissionManager()
        allowed, reason = pm.check("read_file", {})
        assert allowed
        assert "auto-allowed" in reason

    def test_needs_approval_write(self):
        pm = PermissionManager()
        allowed, reason = pm.check("write_file", {"file_path": "/tmp/test.txt"})
        assert not allowed
        assert "needs approval" in reason

    def test_needs_approval_exec(self):
        pm = PermissionManager()
        allowed, reason = pm.check("execute_command", {"command": "ls"})
        assert not allowed
        assert "needs approval" in reason

    def test_approve_once(self):
        pm = PermissionManager()
        pm.approve("write_file")
        allowed, reason = pm.check("write_file", {"file_path": "/tmp/test.txt"})
        assert not allowed  # Approve once doesn't add to always_allow

    def test_approve_always(self):
        pm = PermissionManager()
        pm.approve("write_file", remember=True)
        allowed, reason = pm.check("write_file", {"file_path": "/tmp/test.txt"})
        assert allowed
        assert "always-allowed" in reason

    def test_deny_remember(self):
        pm = PermissionManager()
        pm.blocked = set()
        pm.deny("execute_command", remember=True)
        # Actually, deny with remember=True adds to _blocked
        assert "execute_command" in pm._blocked

    def test_stats(self):
        pm = PermissionManager()
        pm.check("read_file", {})
        stats = pm.stats
        assert "auto-allowed" in stats
