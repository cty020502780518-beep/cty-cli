"""
Tool system — defines the tools the agent can use and executes them.
Mirrors the MCP/tool-use layer in Claude Code.

13 tools total:
  4 file ops: read_file, write_file, edit_file (+diff), list_files
  3 system:   execute_command, search_code, web_search
  3 plan:     plan_create, plan_update, plan_list
  2 memory:   memory_save, memory_recall
  1 skill:    load_skill
"""
import difflib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ── Tool definitions (what we tell the LLM) ─────────────────────────────

TOOL_DEFINITIONS = [
    # ── File operations ──
    {
        "name": "read_file",
        "description": "Read a file from the local filesystem. Returns content with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {"type": "integer", "description": "Line number to start reading from (0-indexed)"},
                "limit": {"type": "integer", "description": "Maximum number of lines to read"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with new content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path where the file should be written"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Perform exact string replacement in a file. Returns a unified diff of the change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file to edit"},
                "old_string": {"type": "string", "description": "Exact text to find and replace"},
                "new_string": {"type": "string", "description": "Text to replace it with"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories at a path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list"},
            },
            "required": ["path"],
        },
    },
    # ── System ──
    {
        "name": "execute_command",
        "description": "Run a shell command and return its output. Use for running tests, git, builds, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "working_dir": {"type": "string", "description": "Directory to run the command in"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in files using regex. Returns file:line:content matches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "File or directory to search in"},
                "file_glob": {"type": "string", "description": "Only search files matching this glob (e.g. *.py)"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for up-to-date information. Returns titles, URLs, and snippets. Use this when you need current facts, news, or information beyond your training cutoff.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "max_results": {"type": "integer", "description": "Maximum number of results (default: 5, max: 10)"},
            },
            "required": ["query"],
        },
    },
    # ── Plan / Task tracking ──
    {
        "name": "plan_create",
        "description": "Create a new task in the plan. Break complex work into tracked steps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title (short and actionable)"},
                "description": {"type": "string", "description": "What needs to be done (optional)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "plan_update",
        "description": "Update a task status: pending, in_progress, completed, or cancelled.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID (e.g. task-1)"},
                "status": {"type": "string", "description": "New status: pending, in_progress, completed, or cancelled"},
            },
            "required": ["task_id", "status"],
        },
    },
    {
        "name": "plan_list",
        "description": "List all plan tasks and their status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── Memory ──
    {
        "name": "memory_save",
        "description": "Save something worth remembering for future sessions: user preferences, project context, feedback.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Category: user, project, feedback, or reference"},
                "title": {"type": "string", "description": "Short title for this memory"},
                "content": {"type": "string", "description": "What to remember"},
            },
            "required": ["type", "title", "content"],
        },
    },
    {
        "name": "memory_recall",
        "description": "Search saved memories by keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword or phrase to search for"},
            },
            "required": ["query"],
        },
    },
    # ── Skill loading ──
    {
        "name": "load_skill",
        "description": "Activate a skill by name. Its full instructions will be injected into the system prompt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the skill to load"},
            },
            "required": ["name"],
        },
    },
]


# ── Shared state (injected at startup) ──────────────────────────────────

_context: dict[str, Any] = {}


def set_tool_context(plan_manager=None, memory_manager=None, skill_manager=None):
    """Inject runtime dependencies into the tool layer."""
    _context["plan"] = plan_manager
    _context["memory"] = memory_manager
    _context["skills"] = skill_manager


# ── Helpers ─────────────────────────────────────────────────────────────

MAX_OUTPUT_CHARS = 50_000


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n\n... (truncated {len(text) - MAX_OUTPUT_CHARS:,} chars)"
    return text


def _format_file(content: str, start_line: int = 0) -> str:
    return "\n".join(f"{start_line + i + 1:6}\t{line}" for i, line in enumerate(content.split("\n")))


def _generate_diff(old: str, new: str, filepath: str) -> str:
    """Generate a unified diff for display."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm="",
    ))
    if not diff_lines:
        return "(no changes)"
    return "\n".join(diff_lines)


# ── File tools ──────────────────────────────────────────────────────────

def read_file(file_path: str, offset: int = 0, limit: Optional[int] = None) -> str:
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        return f"Error: file not found: {p}"
    if p.is_dir():
        return f"Error: path is a directory: {p}\n\nContents:\n" + list_files(str(p))
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file: {e}"

    lines = content.split("\n")
    if limit is not None:
        lines = lines[offset : offset + limit]
    elif offset > 0:
        lines = lines[offset:]
    return _truncate(_format_file("\n".join(lines), offset if not limit else offset))


def write_file(file_path: str, content: str) -> str:
    p = Path(file_path).expanduser().resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content):,} bytes to {p}"
    except Exception as e:
        return f"Error writing file: {e}"


def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        return f"Error: file not found: {p}"
    try:
        original = p.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"

    count = original.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {p}\n\nTip: use read_file to check exact content including whitespace."
    if count > 1:
        return (
            f"Error: old_string appears {count} times in {p}. "
            f"Provide more surrounding context to make it unique."
        )

    new_content = original.replace(old_string, new_string, 1)
    try:
        p.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return f"Error writing file: {e}"

    delta = len(new_content) - len(original)
    diff = _generate_diff(original, new_content, str(p))
    return f"Applied edit to {p} ({delta:+d} bytes)\n\n```diff\n{diff}\n```"


def list_files(path: str) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: path not found: {p}"
    if p.is_file():
        return f"{p} ({p.stat().st_size:,} bytes)"

    items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    lines = []
    for item in items[:200]:
        suffix = "/" if item.is_dir() else ""
        try:
            size = item.stat().st_size
        except OSError:
            size = 0
        lines.append(f"  {item.name}{suffix}  ({size:,} bytes)")
    if len(items) > 200:
        lines.append(f"  ... and {len(items) - 200} more items")
    return "\n".join(lines) if lines else "(empty directory)"


# ── System tools ────────────────────────────────────────────────────────

def execute_command(command: str, working_dir: Optional[str] = None) -> str:
    cwd = Path(working_dir).expanduser().resolve() if working_dir else Path.cwd()
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            cwd=str(cwd), timeout=120,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if not output.strip():
            output = f"(exit code: {result.returncode})"
        return _truncate(output)
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 120s"
    except Exception as e:
        return f"Error executing command: {e}"


def search_code(pattern: str, path: str = ".", file_glob: Optional[str] = None) -> str:
    import fnmatch
    search_dir = Path(path).expanduser().resolve()
    if not search_dir.exists():
        return f"Error: path not found: {search_dir}"

    results: list[str] = []
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex: {e}"

    for root, dirs, files in os.walk(search_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__", ".git"}]
        for fname in files:
            if file_glob and not fnmatch.fnmatch(fname, file_glob):
                continue
            fpath = Path(root) / fname
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.split("\n"), 1):
                if regex.search(line):
                    results.append(f"{fpath}:{i}: {line.strip()[:200]}")
                    if len(results) >= 100:
                        return _truncate("\n".join(results))
    if not results:
        return f"No matches found for pattern: {pattern}"
    return "\n".join(results)


# ── Web search ───────────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo. No API key needed."""
    try:
        from ddgs import DDGS
    except ImportError:
        return "Error: ddgs not installed. Run: pip install ddgs"

    max_results = min(max(1, max_results), 10)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region="us-en"))
    except Exception as e:
        return f"Search error: {e}"

    if not results:
        return f"No results found for: {query}"

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        href = r.get("href", "")
        body = r.get("body", "")[:300]
        lines.append(f"{i}. {title}\n   {href}\n   {body}")
    return "\n\n".join(lines)


# ── Plan tools ──────────────────────────────────────────────────────────

def plan_create(title: str, description: str = "") -> str:
    pm = _context.get("plan")
    if not pm:
        return "Error: plan manager not initialized"
    task = pm.create(title, description)
    return f"Created {task.id}: {task.title}"

def plan_update(task_id: str, status: str) -> str:
    pm = _context.get("plan")
    if not pm:
        return "Error: plan manager not initialized"
    return pm.update(task_id, status)

def plan_list() -> str:
    pm = _context.get("plan")
    if not pm:
        return "Error: plan manager not initialized"
    return pm.list_all()


# ── Memory tools ────────────────────────────────────────────────────────

def memory_save(type: str, title: str, content: str) -> str:
    mm = _context.get("memory")
    if not mm:
        return "Error: memory manager not initialized"
    valid_types = {"user", "project", "feedback", "reference"}
    if type not in valid_types:
        return f"Invalid type '{type}'. Use: {', '.join(valid_types)}"
    mem = mm.save(type, title, content)
    return f"Saved memory '{mem.id}' [{mem.type}] — {mem.title}"

def memory_recall(query: str) -> str:
    mm = _context.get("memory")
    if not mm:
        return "Error: memory manager not initialized"
    results = mm.recall(query)
    if not results:
        return f"No memories found for '{query}'"
    lines = [f"Found {len(results)} memories:"]
    for m in results:
        lines.append(f"\n  [{m.type}] {m.title}")
        lines.append(f"  {m.content[:200]}")
    return "\n".join(lines)


# ── Skill tools ─────────────────────────────────────────────────────────

def load_skill(name: str) -> str:
    sm = _context.get("skills")
    if not sm:
        return "Error: skill manager not initialized"
    body = sm.load_full(name)
    if body is None:
        available = ", ".join(sm._skills.keys())
        return f"Skill '{name}' not found. Available: {available}"
    preview = body[:300].replace("\n", " ")
    return f"Loaded skill '{name}' ({len(body):,} chars)\nPreview: {preview}..."


# ── Dispatcher ──────────────────────────────────────────────────────────

TOOL_MAP: dict[str, Callable] = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_files": list_files,
    "execute_command": execute_command,
    "search_code": search_code,
    "web_search": web_search,
    "plan_create": plan_create,
    "plan_update": plan_update,
    "plan_list": plan_list,
    "memory_save": memory_save,
    "memory_recall": memory_recall,
    "load_skill": load_skill,
}


def execute_tool(name: str, params: dict[str, Any]) -> str:
    """Execute a tool by name with the given parameters."""
    if name not in TOOL_MAP:
        return f"Error: unknown tool: {name}"
    try:
        import inspect
        fn = TOOL_MAP[name]
        sig = inspect.signature(fn)
        valid_params = {k: v for k, v in params.items() if k in sig.parameters}
        return fn(**valid_params)
    except TypeError as e:
        return f"Error: invalid parameters for {name}: {e}"
    except Exception as e:
        return f"Error executing {name}: {e}"
