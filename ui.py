"""Simple console UI — prints streaming output directly to terminal.

Design: stream-first, no buffering. Every TextChunk from the LLM
goes straight to stdout so the user sees the response in real time.
"""
import sys
from typing import Optional


class TerminalUI:
    """Minimal console UI. Prints directly, no buffering."""

    def __init__(self):
        self._status_text = "Ready"

    # ── Header ─────────────────────────────────────────────────────────

    def update_header(self, model: str, tokens: str, cwd: str):
        self._status_text = f"CTY-Cli | model={model} | {tokens} | {cwd}"

    def print_header(self):
        print(f"\033[2J\033[H", end="")  # Clear screen
        print(f"╔══════════════════════════════════════════════╗")
        print(f"║  CTY-Cli v0.1.0                              ║")
        print(f"║  Type /help for commands, /exit to quit      ║")
        print(f"╚══════════════════════════════════════════════╝")
        print()

    # ── Real-time streaming output ─────────────────────────────────────

    @staticmethod
    def _sanitize(text: str) -> str:
        """Replace lone surrogates (U+D800–U+DFFF) that break UTF-8 output."""
        return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")

    def stream_text(self, text: str):
        """Print a chunk of text immediately to stdout (no buffering)."""
        sys.stdout.write(self._sanitize(text))
        sys.stdout.flush()

    def agent_text(self, text: str):
        """Stream a chunk of agent response text."""
        sys.stdout.write(self._sanitize(text))
        sys.stdout.flush()

    def tool_call(self, tool_name: str, detail: str, status: str):
        print(f"\n  [{status}] {tool_name}: {detail}")

    def tool_result(self, summary: str):
        # Show first line only to avoid noise
        first_line = self._sanitize(summary).strip().split("\n")[0][:120]
        print(f"  <- {first_line}")

    def system(self, text: str):
        print(f"  [{text}]")

    def user_echo(self, text: str):
        pass  # User's own input is already on screen

    def newline(self):
        print()

    # ── Permission prompt ───────────────────────────────────────────────

    def ask_permission(self, tool_name: str, detail: str) -> str:
        """Prompt user for permission. Returns: y, n, or a (always)."""
        print(f"\n  [PERMISSION] Allow {tool_name}?")
        print(f"  {detail}")
        print(f"  [y] yes  [n] no  [a] always allow {tool_name}")
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "n"
        if choice in ("y", "yes", ""):
            return "y"
        elif choice in ("a", "always"):
            return "a"
        else:
            return "n"

    # ── Input ───────────────────────────────────────────────────────────

    def get_input(self) -> str:
        try:
            return input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return "/exit"
