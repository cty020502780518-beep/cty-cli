"""Skills engine — progressive loading of skill definitions.

Mirrors Claude Code's skill loading mechanism:
  ~/.claude/skills/<skill-name>/SKILL.md

Mechanism:
  1. Scan skill directories at startup → extract name + description (~80 tokens/skill)
  2. Inject lightweight index into system prompt
  3. Expose `load_skill` tool → LLM decides when to activate
  4. On activation, inject full SKILL.md body (~2k-5k tokens) into system prompt
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


SKILL_SEARCH_PATHS = [
    Path.home() / ".cty-cli" / "skills",
    Path.cwd() / ".cty-cli" / "skills",
    Path.home() / ".claude" / "skills",       # Reuse Claude Code skills
    Path.cwd() / ".claude" / "skills",
]


@dataclass
class SkillMeta:
    name: str
    description: str
    path: Path           # Path to SKILL.md
    body: str = ""       # Loaded on demand


class SkillManager:
    def __init__(self, search_paths: Optional[list] = None):
        self._paths = search_paths or SKILL_SEARCH_PATHS
        self._skills: dict[str, SkillMeta] = {}
        self._loaded: set[str] = set()  # Which skills have been loaded into prompt
        self._scan()

    # ── Startup ──────────────────────────────────────────────────────

    def _scan(self):
        """Scan all search paths for SKILL.md files, extract frontmatter."""
        for base in self._paths:
            if not base.is_dir():
                continue
            for skill_dir in sorted(base.iterdir()):
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    # Check directly for SKILL.md at this level
                    continue
                try:
                    meta = self._parse_frontmatter(skill_md)
                    if meta:
                        self._skills[meta.name] = meta
                except Exception:
                    pass

    def _parse_frontmatter(self, path: Path) -> Optional[SkillMeta]:
        """Parse YAML frontmatter from a SKILL.md file."""
        text = path.read_text(encoding="utf-8", errors="replace")
        # Extract --- name: ... --- block
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            return None

        frontmatter = fm_match.group(1)
        name = ""
        description = ""

        for line in frontmatter.split("\n"):
            line = line.strip()
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()

        if not name:
            return None

        # Store the body (everything after frontmatter) for on-demand loading
        body = text[fm_match.end():].strip()
        return SkillMeta(name=name, description=description, path=path, body=body)

    # ── System prompt injection ──────────────────────────────────────

    def bootstrap_prompt(self) -> str:
        """Lightweight skill index for system prompt (~80 tokens/skill)."""
        if not self._skills:
            return ""

        lines = [
            "## Available Skills",
            "Call `load_skill(name)` to activate a skill (its full instructions will be injected).",
            "",
        ]
        for name, meta in self._skills.items():
            loaded = " [active]" if name in self._loaded else ""
            lines.append(f"- **{name}**{loaded}: {meta.description}")

        return "\n".join(lines)

    def load_full(self, name: str) -> Optional[str]:
        """Activate a skill — return full SKILL.md body for injection into system prompt."""
        meta = self._skills.get(name)
        if not meta:
            # Try fuzzy match
            matches = [n for n in self._skills if name.lower() in n.lower()]
            if len(matches) == 1:
                meta = self._skills[matches[0]]
            else:
                return None

        self._loaded.add(meta.name)
        return meta.body

    def unload(self, name: str) -> bool:
        if name in self._loaded:
            self._loaded.remove(name)
            return True
        return False

    def list_skills(self) -> str:
        if not self._skills:
            return "No skills installed."

        lines = ["Installed skills:"]
        for name, meta in self._skills.items():
            status = " [loaded]" if name in self._loaded else ""
            lines.append(f"  {name}{status} — {meta.description}")
        return "\n".join(lines)
