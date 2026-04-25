"""SkillContext and Pydantic models for SkillsIR."""

from dataclasses import dataclass, field

from pydantic import BaseModel


class FileRequest(BaseModel):
    """A request to load a specific file from a skill."""

    skill: str
    path: str
    reason: str  # Why this file is needed (for observability)


class RetrievalDecision(BaseModel):
    """LLM's decision about context sufficiency."""

    has_enough: bool
    needs: list[FileRequest] = []  # Empty if has_enough=True


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses simple heuristic: ~4 characters per token on average.
    This is a rough approximation suitable for budget tracking.
    """
    return len(text) // 4


@dataclass
class SkillContext:
    """Accumulated knowledge from skills with budget tracking.

    Tracks loaded files from skills and enforces token limits
    to prevent context overflow.
    """

    registry: dict[str, str] = field(default_factory=dict)
    """All skill descriptions: skill_name -> description"""

    trees: dict[str, list[str]] = field(default_factory=dict)
    """File trees per skill: skill_name -> [file_paths]"""

    loaded: dict[str, dict[str, str]] = field(default_factory=dict)
    """Loaded content: skill_name -> {path: content}"""

    not_found: set[str] = field(default_factory=set)
    """Files that were requested but don't exist: {"skill/path", ...}"""

    token_count: int = 0
    """Current token count across all loaded content."""

    token_limit: int = 50000
    """Maximum tokens allowed (configurable)."""

    def add(self, skill: str, path: str, content: str) -> bool:
        """Add content to context if within budget.

        Args:
            skill: Skill name.
            path: File path within skill.
            content: File content.

        Returns:
            True if added successfully, False if would exceed token limit.
        """
        tokens = estimate_tokens(content)
        if self.token_count + tokens > self.token_limit:
            return False

        if skill not in self.loaded:
            self.loaded[skill] = {}
        self.loaded[skill][path] = content
        self.token_count += tokens
        return True

    def mark_not_found(self, skill: str, path: str) -> None:
        """Record that a requested file doesn't exist.

        Args:
            skill: Skill name.
            path: File path within skill.
        """
        self.not_found.add(f"{skill}/{path}")

    def for_prompt(self) -> str:
        """Format loaded content for LLM prompt injection.

        Returns:
            Formatted string with all loaded content organized by skill.
        """
        parts = []
        for skill_name, files in self.loaded.items():
            parts.append(f"### Skill: {skill_name}")
            for path, content in files.items():
                parts.append(f"\n#### {path}\n```\n{content}\n```")
        return "\n".join(parts)
