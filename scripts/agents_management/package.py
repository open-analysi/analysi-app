#!/usr/bin/env python3
"""
Package production agents and skills using skilltree as the source of truth.

skilltree.yaml declares all dependencies with group (prod/dev) and type
(skill/agent). This script reads `skilltree list --json` and copies prod
dependencies into their deployment directories:

  - Agents  → agents/dist/     (Docker COPY'd into container)
  - Skills  → content/foundation/skills/  (installed via content packs)

Subcommands:
    agents          Copy prod agents into agents/dist/
    skills          Copy prod skills into content/foundation/skills/
    skills --check  Verify skills are in sync (for pre-commit)
    all             Package both agents and skills

Usage:
    make package-agents          # python package.py agents
    make package-skills          # python package.py skills
    make check-skills            # python package.py skills --check
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# manifest.json is regenerated from SKILL.md frontmatter on every sync, so
# nothing needs to be preserved across cleans.
PRESERVE_FILES: set[str] = set()

# Files/dirs to skip when copying skill sources. manifest.json is skipped
# because we generate it fresh from frontmatter rather than copying whatever
# upstream (or a previous run) produced.
SKIP_NAMES = {"manifest.json", "CLAUDE.md", ".DS_Store"}


def _get_skilltree_deps() -> list[dict]:
    """Get dependency list from skilltree."""
    try:
        result = subprocess.run(
            ["skilltree", "list", "--json"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(BASE_DIR),
        )
    except FileNotFoundError:
        print("ERROR: skilltree not found on PATH")
        print("  Install: npm install -g @anthropic-ai/skilltree")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: skilltree list failed: {e.stderr}")
        sys.exit(1)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse skilltree output: {e}")
        print(f"  Output: {result.stdout[:200]}")
        sys.exit(1)


def _prod_deps(deps: list[dict], dep_type: str) -> list[dict]:
    """Filter to prod dependencies of a given type."""
    return [d for d in deps if d["group"] == "prod" and d["type"] == dep_type]


# ── Agent packaging ──────────────────────────────────────────────────────────


def _resolve_agent_path(dep: dict) -> Path | None:
    """Resolve an agent dependency to its file on disk."""
    source = dep["source"]

    if source.startswith("./"):
        # Local agent — source is a relative path
        path = BASE_DIR / source
        return path if path.exists() else None

    # Remote agent — skilltree installs to .claude/agents/
    path = BASE_DIR / ".claude" / "agents" / f"{dep['name']}.md"
    return path if path.exists() else None


def package_agents() -> int:
    """Copy prod agents into agents/dist/."""
    deps = _get_skilltree_deps()
    agents = _prod_deps(deps, "agent")
    production_dir = BASE_DIR / "agents" / "dist"

    print("=" * 70)
    print("Packaging agents into agents/dist/")
    print(f"  Source of truth: skilltree.yaml ({len(agents)} prod agents)")
    print("=" * 70)
    print()

    copied = 0
    errors = []

    for dep in sorted(agents, key=lambda d: d["name"]):
        src = _resolve_agent_path(dep)
        # Agent files may use a custom name from skilltree (e.g., workflow-builder-agent → workflow-builder.md)
        dst_name = f"{dep['name']}.md"
        dst = production_dir / dst_name

        if not src:
            print(f"  ✗ {dep['name']} — not found (source: {dep['source']})")
            errors.append(dep["name"])
            continue

        shutil.copy2(src, dst)
        label = dep["source"] if dep["source"].startswith("./") else ".claude/agents/"
        print(f"  ✓ {dst_name} ← {label}")
        copied += 1

    print()
    print("=" * 70)
    print(f"  Packaged: {copied}/{len(agents)}")
    if errors:
        print(f"  Missing:  {', '.join(errors)}")
    print("=" * 70)
    print()

    return 1 if errors else 0


# ── Skill packaging ──────────────────────────────────────────────────────────


def _resolve_skill_path(dep: dict) -> Path | None:
    """Resolve a skill dependency to its directory on disk.

    For local skills, the source path points directly.
    For remote skills, skilltree installs into .claude/skills/<name>/.
    """
    source = dep["source"]

    if source.startswith("./"):
        path = BASE_DIR / source
        return path if path.is_dir() else None

    # Remote skill — installed by skilltree
    path = BASE_DIR / ".claude" / "skills" / dep["name"]
    return path if path.is_dir() else None


def _content_name(skill_name: str) -> str:
    """Convert skill name (hyphens) to content directory name (underscores)."""
    return skill_name.replace("-", "_")


def _clean_skill_dir(dst: Path) -> dict[str, bytes]:
    """Remove old skill content, preserving manifest.json. Returns preserved files."""
    preserved: dict[str, bytes] = {}
    for fname in PRESERVE_FILES:
        fpath = dst / fname
        if fpath.exists():
            preserved[fname] = fpath.read_bytes()

    if dst.is_dir():
        for p in dst.rglob("*"):
            if p.is_dir():
                p.chmod(p.stat().st_mode | 0o700)
        for item in dst.iterdir():
            if item.name not in PRESERVE_FILES:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
    else:
        dst.mkdir(parents=True)

    return preserved


def _parse_skill_frontmatter(skill_md: Path) -> dict[str, str]:
    """Extract YAML frontmatter fields from SKILL.md.

    Supports the subset we actually use: plain ``key: value`` lines and the
    folded-scalar form ``key: >-`` followed by indented continuation lines.
    Avoids a PyYAML dependency so the script runs under the Makefile's plain
    ``python`` invocation without extra setup.
    """
    if not skill_md.exists():
        return {}

    text = skill_md.read_text()
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}

    fields: dict[str, str] = {}
    lines = match.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2)

        if value in {">-", ">", "|-", "|"}:
            # Folded / literal scalar: take indented continuation lines.
            # Any indent works as long as it's greater than the key's indent
            # (which is 0 for frontmatter).
            parts: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                parts.append(lines[i].strip())
                i += 1
            joiner = " " if value in {">-", ">"} else "\n"
            fields[key] = joiner.join(p for p in parts if p)
            continue

        # Plain scalar — strip surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        fields[key] = value
        i += 1

    return fields


def _build_default_manifest(content_dir_name: str, skill_dir: Path) -> dict:
    """Build a manifest.json for a skill from its SKILL.md frontmatter.

    The pack installer silently skips skill directories that lack a
    manifest.json (cli/src/commands/packs/install.ts), so we always generate
    one. Source frontmatter supplies ``name``, ``description``, and ``version``;
    everything else is a fixed default.
    """
    fm = _parse_skill_frontmatter(skill_dir / "SKILL.md")
    name = fm.get("name") or content_dir_name.replace("_", "-")
    return {
        "version": fm.get("version", "1.0.0"),
        "categories": ["security"],
        "status": "enabled",
        "visible": True,
        "system_only": False,
        "app": "default",
        "extraction_eligible": True,
        "root_document_path": "SKILL.md",
        "config": {},
        "name": name,
        "cy_name": name.replace("-", "_"),
        "description": fm.get("description", ""),
    }


def _sync_skill(src: Path, dst: Path) -> None:
    """Sync a single skill from source to destination directory."""
    preserved = _clean_skill_dir(dst)

    # Copy new content from source
    for item in src.iterdir():
        if item.name.startswith(".") or item.name in SKIP_NAMES:
            continue
        dst_path = dst / item.name
        if item.is_dir():
            shutil.copytree(item, dst_path)
        else:
            shutil.copy2(item, dst_path)

    # Fix permissions — skilltree may install as read-only
    for p in dst.rglob("*"):
        if p.is_file():
            p.chmod(0o644)
        elif p.is_dir():
            p.chmod(0o755)

    # Restore preserved files
    for fname, content in preserved.items():
        (dst / fname).write_bytes(content)

    # Generate manifest.json from SKILL.md frontmatter. Always rewritten so
    # that source-of-truth stays in the skill itself, not in target artifacts.
    manifest = _build_default_manifest(dst.name, dst)
    manifest_path = dst / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_path.chmod(0o644)


def package_skills() -> int:
    """Sync prod skills into content/foundation/skills/."""
    deps = _get_skilltree_deps()
    skills = _prod_deps(deps, "skill")
    target_dir = BASE_DIR / "content" / "foundation" / "skills"

    print("=" * 70)
    print("Packaging skills into content/foundation/skills/")
    print(f"  Source of truth: skilltree.yaml ({len(skills)} prod skills)")
    print("=" * 70)
    print()

    synced = 0
    errors = []

    for dep in sorted(skills, key=lambda d: d["name"]):
        content_dir_name = _content_name(dep["name"])
        src = _resolve_skill_path(dep)
        dst = target_dir / content_dir_name

        if not src:
            print(f"  ✗ {content_dir_name} — source not found ({dep['source']})")
            errors.append(content_dir_name)
            continue

        _sync_skill(src, dst)

        if dep["source"].startswith("./"):
            label = dep["source"]
        else:
            label = f".claude/skills/{dep['name']}"
        print(f"  ✓ {content_dir_name} ← {label}")
        synced += 1

    print()
    print("=" * 70)
    print(f"  Synced: {synced}/{len(skills)}")
    if errors:
        print(f"  Missing: {', '.join(errors)}")
    print("=" * 70)
    print()

    return 1 if errors else 0


def check_skills() -> int:
    """Verify content/foundation/skills/ matches skill sources.

    Returns 0 if in sync, 1 if out of sync.
    """
    deps = _get_skilltree_deps()
    skills = _prod_deps(deps, "skill")
    target_dir = BASE_DIR / "content" / "foundation" / "skills"

    out_of_sync = []

    for dep in sorted(skills, key=lambda d: d["name"]):
        content_dir_name = _content_name(dep["name"])
        src = _resolve_skill_path(dep)
        dst = target_dir / content_dir_name

        if not src or not dst.is_dir():
            out_of_sync.append(content_dir_name)
            continue

        # Compare file contents (excluding preserved files and dotfiles)
        result = subprocess.run(
            [
                "diff",
                "-rqB",
                str(src),
                str(dst),
                "--exclude=manifest.json",
                "--exclude=CLAUDE.md",
                "--exclude=.DS_Store",
                "--exclude=.*",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            out_of_sync.append(content_dir_name)

    if out_of_sync:
        print(
            "ERROR: content/foundation/skills/ is out of sync\n"
            f"  Out of sync: {', '.join(out_of_sync)}\n\n"
            "  Fix: Edit skills in their source location,\n"
            "  then run: make package-skills\n"
        )
        return 1

    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: package.py <agents|skills|all> [--check]")
        return 1

    command = sys.argv[1]

    if command == "agents":
        return package_agents()
    if command == "skills":
        if "--check" in sys.argv:
            return check_skills()
        return package_skills()
    if command == "all":
        rc = package_agents()
        rc |= package_skills()
        return rc
    print(f"Unknown command: {command}")
    print("Usage: package.py <agents|skills|all> [--check]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
