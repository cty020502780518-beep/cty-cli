"""Permission system — three-tier risk-based tool approval.

Mirrors Claude Code's permissions model:
  auto-allow: read_file, list_files, search_code, plan_list
  ask: write_file, edit_file, execute_command, plan_create, plan_update
  session-remember: "always allow for this session"

面试加分项 — 多级安全模型 + 防 prompt injection。
"""
from dataclasses import dataclass, field

# ── Risk classification ──────────────────────────────────────────────

READ_TOOLS = {"read_file", "list_files", "search_code", "web_search", "plan_list"}
WRITE_TOOLS = {"write_file", "edit_file", "plan_create", "plan_update"}
EXEC_TOOLS = {"execute_command"}
SKILL_TOOLS = {"load_skill"}
MEMORY_TOOLS = {"memory_save", "memory_recall", "memory_list", "memory_delete"}

AUTO_ALLOW = READ_TOOLS | SKILL_TOOLS | MEMORY_TOOLS
NEEDS_APPROVAL = WRITE_TOOLS | EXEC_TOOLS


def tool_risk(tool_name: str) -> str:
    if tool_name in READ_TOOLS | SKILL_TOOLS | MEMORY_TOOLS:
        return "read"
    if tool_name in WRITE_TOOLS:
        return "write"
    if tool_name in EXEC_TOOLS:
        return "exec"
    return "unknown"


def describe_risk(tool_name: str, params: dict) -> str:
    """Human-readable description of what's about to happen."""
    if tool_name == "edit_file":
        return f"Edit {params.get('file_path', '?')}"
    elif tool_name == "write_file":
        path = params.get("file_path", "?")
        size = len(params.get("content", ""))
        return f"Write {path} ({size:,} bytes)"
    elif tool_name == "execute_command":
        cmd = params.get("command", "?")
        return f"Run: {cmd[:120]}"
    elif tool_name == "plan_create":
        return f"Create task: {params.get('title', '?')}"
    elif tool_name == "plan_update":
        return f"Update task {params.get('task_id', '?')} → {params.get('status', '?')}"
    return f"{tool_name}"


class PermissionManager:
    """Manages tool execution permissions during a session.

    Session-scoped: always-allow decisions don't persist across restarts.
    """

    def __init__(self):
        self._always_allow: set[str] = set()  # tool names allowed for entire session
        self._blocked: set[str] = set()
        self._approval_count = 0
        self._auto_count = 0

    def check(self, tool_name: str, params: dict) -> tuple[bool, str]:
        """Returns (allowed, reason). blocked tools return (False, reason)."""
        if tool_name in self._blocked:
            return False, "blocked by earlier deny"

        if tool_name in self._always_allow:
            self._auto_count += 1
            return True, "always-allowed (session)"

        if tool_name in AUTO_ALLOW:
            self._auto_count += 1
            return True, "auto-allowed (read-only)"

        # Needs approval — caller must present to user
        return False, f"needs approval ({tool_risk(tool_name)})"

    def approve(self, tool_name: str, remember: bool = False):
        self._approval_count += 1
        if remember:
            self._always_allow.add(tool_name)

    def deny(self, tool_name: str, remember: bool = False):
        if remember:
            self._blocked.add(tool_name)

    @property
    def stats(self) -> str:
        return (
            f"Permissions: {self._auto_count} auto-allowed, "
            f"{self._approval_count} approved"
        )
