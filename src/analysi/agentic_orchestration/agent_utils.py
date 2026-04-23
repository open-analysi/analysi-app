"""Utilities for working with agent .md files."""

import re
from pathlib import Path

from analysi.config.logging import get_logger

logger = get_logger(__name__)


def extract_skills_from_agent(agent_path: Path) -> list[str]:
    """Extract skill names from agent .md file YAML frontmatter.

    Agent files use YAML frontmatter with a 'skills' field listing
    required skills as a comma-separated string.

    Example frontmatter:
        ---
        name: runbook-match-agent
        skills: runbooks-manager, cybersecurity-analyst
        ---

    Args:
        agent_path: Path to agent .md file

    Returns:
        List of skill names (e.g., ["runbooks-manager", "cybersecurity-analyst"])
        Returns empty list if no skills field found or file doesn't exist.
    """
    if not agent_path.exists():
        logger.warning("agent_file_not_found", agent_path=agent_path)
        return []

    content = agent_path.read_text()

    # Match YAML frontmatter between --- markers
    frontmatter_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not frontmatter_match:
        logger.debug("no_yaml_frontmatter_found_in", agent_path=agent_path)
        return []

    frontmatter = frontmatter_match.group(1)

    # Extract skills field (handles both quoted and unquoted values)
    skills_match = re.search(r"^skills:\s*(.+)$", frontmatter, re.MULTILINE)
    if not skills_match:
        logger.debug("no_skills_field_found_in", agent_path=agent_path)
        return []

    skills_str = skills_match.group(1).strip()

    # Remove quotes if present
    skills_str = skills_str.strip("'\"")

    # Split by comma and clean up whitespace
    skills = [s.strip() for s in skills_str.split(",")]
    skills = [s for s in skills if s]  # Remove empty strings

    logger.debug("extracted_skills_from", name=agent_path.name, skills=skills)
    return skills


def extract_agent_metadata(agent_path: Path) -> dict[str, str | list[str]]:
    """Extract all metadata from agent .md file YAML frontmatter.

    Args:
        agent_path: Path to agent .md file

    Returns:
        Dict with frontmatter fields. The 'skills' field is parsed into a list.
    """
    if not agent_path.exists():
        return {}

    content = agent_path.read_text()

    # Match YAML frontmatter between --- markers
    frontmatter_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not frontmatter_match:
        return {}

    frontmatter = frontmatter_match.group(1)
    metadata: dict[str, str | list[str]] = {}

    # Parse simple key: value pairs
    for line in frontmatter.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip("'\"")

            if key == "skills":
                # Parse skills as list
                metadata[key] = [s.strip() for s in value.split(",") if s.strip()]
            else:
                metadata[key] = value

    return metadata
