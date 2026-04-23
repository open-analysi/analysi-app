"""Prompts for SkillsIR progressive retrieval."""

from analysi.agentic_orchestration.langgraph.skills.context import SkillContext

RETRIEVAL_PROMPT = """## Your Objective
{objective}

## Task Input
{task_input}

## Available Skills (can request files from any)
{skill_registry}

## Already Loaded (don't request again)
{loaded_files_list}

## Files That Don't Exist (don't request these)
{not_found_files}

## Available Files (can request these)
{file_trees}

## Token Budget
Used: {token_count} / {token_limit}

## How Skills Are Organized

Skills follow a consistent structure. Use this to guide your retrieval:

| Directory | Purpose | When to Load |
|-----------|---------|--------------|
| `SKILL.md` | Overview, navigation, key concepts | Always loaded first (already done) |
| `references/` | Detailed specifications, formats, algorithms | When you need exact formats or rules |
| `templates/` | Patterns to follow, skeleton structures | When creating/composing new artifacts |
| `examples/` | Concrete examples, sample outputs | When you need to match a specific style |
| `repository/` | Production artifacts to reference | When adapting or blending existing work |

## Instructions

1. **Read SKILL.md carefully** - It contains navigation hints like "See references/X for details".
   Follow these pointers when they're relevant to your objective.

2. **Match retrieval to task type:**
   - **Creating/Composing** → Load format specs AND templates (you need the rules AND patterns)
   - **Analyzing/Matching** → Load algorithm specs and examples
   - **Adapting existing work** → Load the source artifact from repository/

3. **Don't under-retrieve:** If the objective involves creating or composing something,
   you likely need both the conceptual guidance (references/) AND the concrete format
   (templates/ or format specs). Loading just one is often insufficient.

4. **ONLY request files from the "Available Files" list above.**
   Do NOT invent or guess file paths. If a file you want doesn't exist in the list,
   work with what's available. The list is exhaustive - if it's not listed, it doesn't exist.

5. **Decide if you have enough context:**
   - If yes: respond with `has_enough=true`
   - If no: list needed files in `needs` array (max 3 per request, must be from Available Files)

Think about what knowledge you need to produce high-quality output for this objective.
"""


def format_skill_registry(registry: dict[str, str]) -> str:
    """Format skill registry for prompt.

    Args:
        registry: Dict of skill name to description.

    Returns:
        Formatted string listing skills.
    """
    if not registry:
        return "(none)"

    lines = []
    for name, description in sorted(registry.items()):
        lines.append(f"- **{name}**: {description}")
    return "\n".join(lines)


def format_loaded_files(loaded: dict[str, dict[str, str]]) -> str:
    """Format list of already loaded files.

    Args:
        loaded: Dict of skill -> {path: content}.

    Returns:
        Formatted string listing loaded files.
    """
    if not loaded:
        return "(none)"

    lines = []
    for skill, files in sorted(loaded.items()):
        for path in sorted(files.keys()):
            lines.append(f"- {skill}/{path}")
    return "\n".join(lines)


def format_not_found(not_found: set[str]) -> str:
    """Format list of files that were requested but don't exist.

    Args:
        not_found: Set of "skill/path" strings for non-existent files.

    Returns:
        Formatted string listing files that don't exist.
    """
    if not not_found:
        return "(none)"

    return "\n".join(f"- {path}" for path in sorted(not_found))


def format_file_trees(
    trees: dict[str, list[str]], loaded: dict[str, dict[str, str]]
) -> str:
    """Format available (not yet loaded) files.

    Args:
        trees: Dict of skill -> list of file paths.
        loaded: Dict of skill -> {path: content} (already loaded).

    Returns:
        Formatted string listing available files.
    """
    if not trees:
        return "(none)"

    lines = []
    for skill, paths in sorted(trees.items()):
        loaded_paths = set(loaded.get(skill, {}).keys())
        available = [p for p in paths if p not in loaded_paths]
        if available:
            lines.append(f"**{skill}/**")
            for path in sorted(available):
                lines.append(f"  - {path}")
    return "\n".join(lines) if lines else "(all files already loaded)"


def format_retrieval_prompt(
    objective: str,
    task_input: str,
    context: SkillContext,
) -> str:
    """Format the retrieval prompt with context.

    Args:
        objective: What we're trying to accomplish.
        task_input: The input for the task (JSON string).
        context: Current SkillContext with loaded content.

    Returns:
        Formatted prompt ready for LLM.
    """
    return RETRIEVAL_PROMPT.format(
        objective=objective,
        task_input=task_input,
        skill_registry=format_skill_registry(context.registry),
        loaded_files_list=format_loaded_files(context.loaded),
        not_found_files=format_not_found(context.not_found),
        file_trees=format_file_trees(context.trees, context.loaded),
        token_count=context.token_count,
        token_limit=context.token_limit,
    )
