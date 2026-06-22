"""Task planner — agent-driven todo/plan tracking.

Exposes 3 tools to the agent: plan_create, plan_update, plan_list.
The agent autonomously breaks work into tasks, marks progress, and
demonstrates structured task decomposition.
"""
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    status: str = "pending"  # pending | in_progress | completed | cancelled
    created_at: str = ""
    completed_at: str = ""


class PlanManager:
    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self._counter = 0

    def create(self, title: str, description: str = "") -> Task:
        self._counter += 1
        tid = f"task-{self._counter}"
        t = Task(
            id=tid,
            title=title,
            description=description,
            created_at=time.strftime("%H:%M:%S"),
        )
        self.tasks[tid] = t
        return t

    def update(self, task_id: str, status: str) -> str:
        if task_id not in self.tasks:
            return f"Task '{task_id}' not found. Use plan_list to see all tasks."
        valid = {"pending", "in_progress", "completed", "cancelled"}
        if status not in valid:
            return f"Invalid status '{status}'. Use: {', '.join(valid)}"
        self.tasks[task_id].status = status
        if status == "completed":
            self.tasks[task_id].completed_at = time.strftime("%H:%M:%S")
        return f"Task '{self.tasks[task_id].title}' → {status}"

    def list_all(self) -> str:
        if not self.tasks:
            return "(no tasks yet — use plan_create to break work into steps)"

        lines = ["## Plan"]
        status_order = {"in_progress": 0, "pending": 1, "completed": 2, "cancelled": 3}
        sorted_tasks = sorted(self.tasks.values(), key=lambda t: status_order.get(t.status, 9))

        icons = {
            "pending": "☐",
            "in_progress": "▶",
            "completed": "✓",
            "cancelled": "✗",
        }

        for t in sorted_tasks:
            icon = icons.get(t.status, "?")
            lines.append(f"  {icon} [{t.status}] {t.title}")
            if t.description:
                lines.append(f"      {t.description[:100]}")

        done = sum(1 for t in self.tasks.values() if t.status == "completed")
        total = len(self.tasks)
        lines.append(f"\n  {done}/{total} completed")
        return "\n".join(lines)
