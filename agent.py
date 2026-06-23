"""Core agent loop — LLM <-> Tool roundtrip.

The heart of CTY-Cli. Mirrors Claude Code's harness:
  user input -> LLM stream -> detect tool_use -> check permissions ->
  execute tool -> feed result back -> loop -> final response
"""
import json
from typing import Optional

from providers.base import BaseProvider, TextChunk, ToolUseChunk
from tools import (
    TOOL_DEFINITIONS,
    TOOL_MAP,
    execute_tool,
    set_tool_context,
)
from permissions import PermissionManager, tool_risk, describe_risk, NEEDS_APPROVAL
from security import PathGuard, CommandGuard
from context import ContextManager
from trace import Tracer
from plan import PlanManager
from memory import MemoryManager
from skills import SkillManager
from ui import TerminalUI


CORE_SYSTEM_PROMPT = """You are CTY-Cli, a coding agent that helps with software engineering tasks.

## Your Capabilities
- Read, write, and edit files on the user's filesystem
- Execute shell commands (tests, builds, git, etc.)
- Search code with regex patterns
- Break complex tasks into tracked plan steps
- Save and recall memories across sessions
- Load skills for specialized workflows

## How You Work
1. When given a task, use `plan_create` to break it into steps
2. Read relevant files before making changes
3. Use `edit_file` for precise changes (returns a diff)
4. Run tests after making changes -- if they fail, fix and rerun
5. Mark plan tasks as completed when done
6. Save anything worth remembering with `memory_save`

## Safety
- Never execute destructive commands without confirmation
- Do not read or write files outside the project directory unless asked
- Report what you changed and why when done

## Output Style
Be concise. Show your work (what you're reading, what you're changing).
"""


class Agent:
    """Orchestrates the full agent lifecycle."""

    def __init__(self, provider: BaseProvider, config, ui: TerminalUI):
        self.provider = provider
        self.config = config
        self.ui = ui

        self.permissions = PermissionManager()
        self.context = ContextManager()
        self.tracer = Tracer()
        self.planner = PlanManager()
        self.memory = MemoryManager(
            scope=getattr(config, 'memory_scope', 'workspace'),
            workspace_root=config.working_dir,
        )
        self.skills = SkillManager()
        self.path_guard = PathGuard(workspace_root=config.working_dir)
        self.command_guard = CommandGuard()

        set_tool_context(
            plan_manager=self.planner,
            memory_manager=self.memory,
            skill_manager=self.skills,
            path_guard=self.path_guard,
            command_guard=self.command_guard,
        )

        self.messages: list[dict] = []
        self._running = True
        self._build_system_prompt()

    # -- System prompt assembly ------------------------------------------

    def _build_system_prompt(self):
        import platform
        from pathlib import Path

        self.context.add_segment("core", CORE_SYSTEM_PROMPT)

        for fname in ["CTY.md", "CLAUDE.md", "CODEBUDDY.md"]:
            project_md = Path.cwd() / fname
            if project_md.is_file():
                content = project_md.read_text(encoding="utf-8", errors="replace")
                self.context.add_segment("project", f"## Project Instructions ({fname})\n\n{content}")
                break

        mem_prompt = self.memory.bootstrap_prompt()
        if mem_prompt:
            self.context.add_segment("memory", mem_prompt)

        env_prompt = (
            f"## Environment\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"Shell: bash\n"
            f"Working directory: {Path.cwd()}\n"
            f"Date: 2026-06-22"
        )
        self.context.add_segment("env", env_prompt)

        skills_prompt = self.skills.bootstrap_prompt()
        if skills_prompt:
            self.context.add_segment("skills", skills_prompt)

        system = self.context.build_system_prompt()
        self.messages = [self.provider.make_system_message(system)]

    # -- Public entry ---------------------------------------------------

    def run(self, user_input: str):
        """Process one user input through the agent loop."""
        self.tracer = Tracer()

        if user_input.startswith("/"):
            self._handle_command(user_input)
            return

        # Auto-recall relevant memories before LLM call
        recall = self.memory.auto_recall(user_input)
        if recall:
            self.messages.append(self.provider.make_user_message(
                f"{recall}\n\n---\nUser: {user_input}"
            ))
        else:
            self.messages.append(self.provider.make_user_message(user_input))
        self._agent_loop()

    # -- Agent loop -----------------------------------------------------

    def _agent_loop(self, max_tool_turns: int = 10):
        """The core loop: LLM -> tool_use -> execute -> loop."""
        accumulated_text: list[str] = []
        turns = 0
        last_tool_call = ""  # Cycle detection

        while turns < max_tool_turns and self._running:
            turns += 1

            prepared_msgs, stats = self.context.prepare(self.messages)
            self.tracer.system(f"context: {self.context.stats_line(self.messages)}")

            # Snapshot for rollback on API error
            msg_snapshot = len(self.messages)

            try:
                stream = self.provider.chat(prepared_msgs, tools=TOOL_DEFINITIONS)

                had_tool_use = False
                response_text = ""
                tool_results: list[tuple] = []  # [(chunk, result_str), ...]

                for chunk in stream:
                    if isinstance(chunk, TextChunk):
                        response_text += chunk.text
                        accumulated_text.append(chunk.text)
                        self.ui.agent_text(chunk.text)

                    elif isinstance(chunk, ToolUseChunk):
                        had_tool_use = True

                        if response_text.strip():
                            self.tracer.think(response_text[:200])

                        tool_name = chunk.name
                        params = chunk.params

                        # Cycle detection
                        call_sig = f"{tool_name}:{str(params)[:100]}"
                        if call_sig == last_tool_call:
                            self.ui.system(f"Detected repeat call to {tool_name}, breaking loop")
                            tool_results.append((chunk, "Error: repetitive tool call detected. Move on."))
                            response_text = ""
                            break
                        last_tool_call = call_sig

                        self.tracer.tool_call(tool_name, params)
                        detail = describe_risk(tool_name, params)

                        allowed, reason = self.permissions.check(tool_name, params)

                        if not allowed and tool_name in NEEDS_APPROVAL:
                            choice = self.ui.ask_permission(tool_name, detail)
                            if choice == "a":
                                self.permissions.approve(tool_name, remember=True)
                                allowed = True
                            elif choice == "y":
                                self.permissions.approve(tool_name)
                                allowed = True
                            else:
                                self.permissions.deny(tool_name)
                                self.tracer.confirm(tool_name, "denied")
                                result = f"User denied execution of {tool_name}"

                        if allowed or tool_name not in NEEDS_APPROVAL:
                            self.ui.tool_call(tool_name, detail, reason)
                            self.tracer.confirm(tool_name, reason)
                            try:
                                result = execute_tool(tool_name, params)
                            except Exception as e:
                                result = f"Error: {e}"
                        else:
                            result = f"Permission denied: {tool_name}"

                        self.tracer.tool_result(tool_name, result, tokens_used=self.context.estimate_tokens(result))
                        self.ui.tool_result(result)

                        if tool_name == "load_skill" and "Loaded skill" in result:
                            skill_name = params.get("name", "")
                            body = self.skills.load_full(skill_name)
                            if body:
                                self.messages[0] = self.provider.make_system_message(
                                    self.messages[0]["content"] + f"\n\n## Active Skill: {skill_name}\n{body}"
                                )

                        tool_results.append((chunk, result))
                        response_text = ""

                # Phase 2: after stream ends, add all tool messages in proper order
                if tool_results:
                    for chunk, result in tool_results:
                        self.messages.append(
                            self.provider.make_tool_use_message(chunk.id, chunk.name, chunk.params)
                        )
                        self.messages.append(
                            self.provider.make_tool_result_message(chunk.id, result)
                        )

            except Exception as e:
                self.ui.system(f"API error: {e}")
                self.tracer.system(f"error: {e}")
                # Rollback any partial tool messages from this turn
                del self.messages[msg_snapshot:]
                break

            if not had_tool_use:
                if response_text.strip():
                    self.tracer.think(response_text[:200])
                break

        # Save final response
        final_text = "".join(accumulated_text)
        if final_text.strip():
            self.messages.append(self.provider.make_assistant_message(final_text))

    # -- Command handler -------------------------------------------------

    def _handle_command(self, line: str):
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit"):
            self._running = False
            self.ui.system("Goodbye.")

        elif cmd == "/help":
            self.ui.system(
                "/model <name>        Switch model\n"
                "/provider <name>     Switch provider\n"
                "/providers           List providers\n"
                "/models              List models\n"
                "/config              Show config\n"
                "/trace               Show execution trace\n"
                "/plan                Show plan\n"
                "/skills              List skills\n"
                "/memory list         List all memories\n"
                "/memory add <text>   Add a memory\n"
                "/memory search <q>   Search memories\n"
                "/memory delete <id>  Delete a memory\n"
                "/memory clear        Clear all memories\n"
                "/memory export       Export memories as JSON\n"
                "/clear               Clear conversation\n"
                "/exit                Quit"
            )

        elif cmd == "/model":
            if arg:
                result = self.config.switch_model(arg)
                self.provider.model = self.config.model
                self.ui.system(result)
            else:
                self.ui.system(self.config.list_models())

        elif cmd == "/provider":
            if arg:
                result = self.config.switch_provider(arg)
                self.ui.system(result)
                self.ui.system("Restart required for provider change.")

        elif cmd == "/providers":
            self.ui.system(self.config.list_providers())

        elif cmd == "/models":
            self.ui.system(self.config.list_models(arg if arg else None))

        elif cmd == "/config":
            self.ui.system(self.config.summary())

        elif cmd == "/trace":
            self.ui.system(self.tracer.summary())

        elif cmd == "/plan":
            self.ui.system(self.planner.list_all())

        elif cmd == "/skills":
            self.ui.system(self.skills.list_skills())

        elif cmd == "/memory":
            # Subcommand: /memory list|add|search|delete|clear|export
            sub_parts = arg.split(maxsplit=1)
            sub = sub_parts[0].lower() if sub_parts else "list"
            sub_arg = sub_parts[1] if len(sub_parts) > 1 else ""

            if sub == "list" or sub == "":
                mems = self.memory.list_all()
                if not mems:
                    self.ui.system("No memories saved yet. Use /memory add <text> to add one.")
                else:
                    lines = [f"  [{i}] [{m.id[:8]}] [{','.join(m.tags) if m.tags else 'no tags'}] {m.content[:100]}" for i, m in enumerate(mems, 1)]
                    self.ui.system(f"{len(mems)} memories (stored at {self.memory.storage_path}):\n" + "\n".join(lines))

            elif sub == "add":
                if not sub_arg:
                    self.ui.system("Usage: /memory add <text to remember>")
                else:
                    try:
                        entry = self.memory.add(sub_arg, source="user")
                        self.ui.system(f"Saved: [{entry.id[:8]}] {entry.content[:100]}")
                    except ValueError as e:
                        self.ui.system(f"Cannot save: {e}")

            elif sub == "search":
                if not sub_arg:
                    self.ui.system("Usage: /memory search <query>")
                else:
                    results = self.memory.search(sub_arg)
                    if not results:
                        self.ui.system(f"No matches for '{sub_arg}'")
                    else:
                        lines = [f"  [{m.id[:8]}] [{','.join(m.tags) if m.tags else 'no tags'}] {m.content[:120]}" for m in results]
                        self.ui.system(f"Found {len(results)}:\n" + "\n".join(lines))

            elif sub == "delete":
                if not sub_arg:
                    self.ui.system("Usage: /memory delete <id-prefix>")
                else:
                    # Find by prefix
                    found = [m for m in self.memory.list_all() if m.id.startswith(sub_arg)]
                    if not found:
                        self.ui.system(f"No memory with id prefix '{sub_arg}'")
                    elif len(found) > 1:
                        self.ui.system(f"Multiple matches. Be more specific:\n" + "\n".join(f"  [{m.id[:8]}] {m.content[:60]}" for m in found))
                    else:
                        self.memory.delete(found[0].id)
                        self.ui.system(f"Deleted: [{found[0].id[:8]}] {found[0].content[:80]}")

            elif sub == "clear":
                count = self.memory.clear()
                self.ui.system(f"Cleared {count} memories.")

            elif sub == "export":
                data = self.memory.export()
                import json
                output = json.dumps(data, ensure_ascii=False, indent=2)
                self.ui.system(f"Export ({len(data)} entries):\n{output}")

            else:
                self.ui.system(f"Unknown /memory subcommand: {sub}. Try /memory list|add|search|delete|clear|export")

        elif cmd == "/clear":
            self.messages = [self.messages[0]]
            self.ui.system("Conversation cleared.")

        else:
            self.ui.system(f"Unknown: {cmd}. Type /help.")

    @property
    def running(self) -> bool:
        return self._running
