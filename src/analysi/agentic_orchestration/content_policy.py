"""Content policy for filtering agent-created files before Hydra submission.

Blocks executable files and suspicious patterns to prevent code injection.
Approved files are routed through the Hydra extraction pipeline for
classification, validation, and placement.
"""

import re
from pathlib import Path
from typing import ClassVar

from analysi.config.logging import get_logger

logger = get_logger(__name__)


class ContentPolicy:
    """Filter agent-created files before Hydra submission.

    This is the first line of defense - quick deterministic checks.
    Approved files go through the full Hydra pipeline for LLM-based validation.

    Blocked:
    - Executable extensions (.py, .sh, .js, etc.)
    - Suspicious code patterns in markdown (eval, exec, rm -rf, etc.)

    Approved (for Hydra):
    - Markdown files (.md)
    - Text files (.txt)
    - JSON files (.json)
    """

    BLOCKED_EXTENSIONS: ClassVar[set[str]] = {
        ".py",
        ".sh",
        ".bash",
        ".js",
        ".ts",
        ".rb",
        ".pl",
        ".exe",
        ".bin",
        ".so",
        ".dll",
        ".ps1",
        ".psm1",
        ".php",
    }

    # Patterns that indicate potentially dangerous content in markdown files
    # These check for code blocks that contain suspicious commands/code
    SUSPICIOUS_PATTERNS: ClassVar[list[str]] = [
        # Python code execution
        r"```python\s*\n.*?(import\s+os|subprocess|eval\(|exec\(|__import__|compile\()",
        # Bash dangerous commands in fenced code blocks (stop at closing ```)
        r"```(?:bash|sh)\s*\n(?:(?!```)[\s\S])*?(rm\s+-rf|curl[^\n]*\|\s*\b(?:sh|bash)\b|wget[^\n]*\|\s*\b(?:sh|bash)\b|mkfifo|nc\s+-e)",
        # JavaScript/script injection
        r"<script\b",
        r"javascript:",
        r"on(?:load|error|click|mouseover)\s*=",
        # Shell command injection in markdown
        r"`\$\([^)]+\)`",  # $(command) execution in inline code
        r"`[^`]*rm\s+-rf[^`]*`",  # rm -rf in inline code (with or without semicolon)
        # Bare dangerous commands anywhere in content
        r"\brm\s+-rf\s+/",  # rm -rf targeting root or absolute paths
        # Hidden content in HTML comments (invisible in rendered markdown)
        r"<!--[\s\S]*?(?:exec\(|eval\(|import\s+os|subprocess|rm\s+-rf|curl.*\||\bsystem\(|__import__)[\s\S]*?-->",
    ]

    # Compiled patterns for efficiency
    _compiled_patterns: list[re.Pattern] | None = None
    _compiled_count: int = 0  # Track pattern count for cache invalidation

    @classmethod
    def _get_patterns(cls) -> list[re.Pattern]:
        """Get compiled regex patterns (cached, invalidated on pattern list change)."""
        if cls._compiled_patterns is None or cls._compiled_count != len(
            cls.SUSPICIOUS_PATTERNS
        ):
            cls._compiled_patterns = [
                re.compile(pattern, re.IGNORECASE | re.DOTALL)
                for pattern in cls.SUSPICIOUS_PATTERNS
            ]
            cls._compiled_count = len(cls.SUSPICIOUS_PATTERNS)
        return cls._compiled_patterns

    def filter_new_files(
        self, files: list[Path]
    ) -> tuple[list[Path], list[dict[str, str]]]:
        """Filter files, returning (approved, rejected_with_reasons).

        Args:
            files: List of file paths to check

        Returns:
            Tuple of (approved_files, rejected_files_with_reasons)
            Each rejected entry has 'path' and 'reason' keys.
        """
        approved = []
        rejected = []

        for filepath in files:
            result = self._check_file(filepath)
            if result["approved"]:
                approved.append(filepath)
            else:
                rejected.append({"path": str(filepath), "reason": result["reason"]})

        if rejected:
            logger.warning(
                "content_policy_blocked_files",
                blocked_count=len(rejected),
                reasons=[r["reason"] for r in rejected],
            )

        return approved, rejected

    def _check_file(self, filepath: Path) -> dict:
        """Check a single file against policy rules.

        Returns dict with 'approved' (bool) and 'reason' (str or None).
        """
        ext = filepath.suffix.lower()

        # Block executables by extension
        if ext in self.BLOCKED_EXTENSIONS:
            return {"approved": False, "reason": f"Executable extension: {ext}"}

        # Check content for suspicious patterns (markdown/text only)
        if ext in {".md", ".markdown", ".txt"}:
            try:
                content = filepath.read_text(errors="ignore")
                suspicious = self._check_suspicious_content(content)
                if suspicious:
                    return {"approved": False, "reason": suspicious}
            except OSError as e:
                return {"approved": False, "reason": f"Cannot read file: {e}"}

        return {"approved": True, "reason": None}

    def _check_suspicious_content(self, content: str) -> str | None:
        """Check content for suspicious patterns.

        Returns reason string if suspicious, None if clean.
        """
        for pattern in self._get_patterns():
            if pattern.search(content):
                # Truncate pattern for logging (avoid showing full regex)
                pattern_preview = (
                    pattern.pattern[:40] + "..."
                    if len(pattern.pattern) > 40
                    else pattern.pattern
                )
                return f"Suspicious pattern detected: {pattern_preview}"
        return None


def check_suspicious_content(content: str) -> list[str]:
    """Standalone function to check content for suspicious patterns.

    Used by Hydra validate_output node for additional validation.

    Args:
        content: Markdown content to check

    Returns:
        List of error messages (empty if clean)
    """
    errors = []
    policy = ContentPolicy()

    for pattern in policy._get_patterns():
        if pattern.search(content):
            pattern_preview = (
                pattern.pattern[:40] + "..."
                if len(pattern.pattern) > 40
                else pattern.pattern
            )
            errors.append(f"Content contains suspicious pattern: {pattern_preview}")

    return errors
