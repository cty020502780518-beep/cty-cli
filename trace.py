"""Execution trace — structured step-by-step logging.

Records every decision, tool call, and confirmation in the agent loop.
Produces a human-readable trace summary on completion.

面试加分项 — 展示了 agent 可观测性设计。
"""
import time
from dataclasses import dataclass, field


@dataclass
class Step:
    seq: int
    timestamp: str
    action: str          # think | tool_call | tool_result | confirm | system
    detail: str
    tool_name: str = ""
    tool_params_str: str = ""
    tokens_used: int = 0
    duration_ms: float = 0.0


class Tracer:
    def __init__(self):
        self.steps: list[Step] = []
        self._seq = 0
        self._start = time.time()
        self._last_time = self._start

    def _add(self, action: str, detail: str = "", **kwargs):
        now = time.time()
        self._seq += 1
        self.steps.append(Step(
            seq=self._seq,
            timestamp=time.strftime("%H:%M:%S"),
            action=action,
            detail=detail.strip(),
            duration_ms=(now - self._last_time) * 1000,
            **kwargs,
        ))
        self._last_time = now

    def think(self, text: str):
        self._add("think", text[:200])

    def tool_call(self, name: str, params: dict):
        params_str = ", ".join(f"{k}={repr(v)[:80]}" for k, v in list(params.items())[:4])
        self._add("tool_call", f"{name}({params_str})", tool_name=name, tool_params_str=params_str)

    def tool_result(self, name: str, result: str, tokens_used: int = 0):
        summary = result[:150].replace("\n", " ")
        self._add("tool_result", summary, tool_name=name, tokens_used=tokens_used)

    def confirm(self, tool_name: str, decision: str):
        self._add("confirm", f"{tool_name}: {decision}", tool_name=tool_name)

    def system(self, detail: str):
        self._add("system", detail)

    def summary(self) -> str:
        """Return a formatted trace summary."""
        if not self.steps:
            return "(no steps recorded)"

        elapsed = time.time() - self._start
        total_tokens = sum(s.tokens_used for s in self.steps)
        tool_count = sum(1 for s in self.steps if s.action == "tool_call")

        lines = [
            "╔══════════════════════════════════════════════════╗",
            f"║  Trace: {len(self.steps)} steps in {elapsed:.1f}s".ljust(52) + "║",
            "╠══════════════════════════════════════════════════╣",
        ]

        for s in self.steps:
            icon = {"think": "💭", "tool_call": "🔧", "tool_result": "  ↳",
                    "confirm": "🔐", "system": "⚡"}.get(s.action, "  ")
            line = f"  {icon} {s.action}: {s.detail}"
            if len(line) > 100:
                line = line[:97] + "..."
            lines.append(line)

        lines.extend([
            "╠══════════════════════════════════════════════════╣",
            f"║  Tools: {tool_count} | Tokens: ~{total_tokens:,}".ljust(52) + "║",
            "╚══════════════════════════════════════════════════╝",
        ])
        return "\n".join(lines)
