"""Skill zip import service.

Handles .skill zip file import: validate structure, create skill,
submit each file for content review.

Spec: SecureSkillOnboarding_v1.md, Part 5.
"""

import io
import json
import os
import re
import zipfile
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
    all_gates_passed,
    run_content_gates,
)
from analysi.config.logging import get_logger
from analysi.schemas.skill import SkillCreate
from analysi.schemas.skill_import import SkillImportResponse, SkillManifest
from analysi.services.content_review import ContentReviewService
from analysi.services.knowledge_module import KnowledgeModuleService

logger = get_logger(__name__)

# Limits
MAX_ZIP_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILE_DECOMPRESSED = 1 * 1024 * 1024  # 1 MB per file decompressed
MAX_FILES = 100
ALLOWED_EXTENSIONS = {".md", ".txt", ".json", ".py", ".cy"}
REQUIRED_FILES = {"SKILL.md"}

# Manifest field constraints
MAX_NAME_LENGTH = 200
CY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class SkillImportError(ValueError):
    """Raised when zip import validation fails.

    Carries structured error info for the frontend to render directly.
    """

    def __init__(
        self,
        error_code: str,
        title: str,
        message: str,
        hint: str | None = None,
        details: dict | None = None,
    ):
        self.error_code = error_code
        self.title = title
        self.message = message
        self.hint = hint
        self.details = details or {}
        super().__init__(message)


def _parse_yaml_frontmatter(text: str) -> dict | None:
    """Extract YAML frontmatter from markdown text.

    Expects the pattern:
        ---
        key: value
        ---

    Returns parsed dict, or None if no frontmatter found.
    Uses PyYAML for full YAML support (multi-line scalars, lists, etc.)
    with a simple key:value fallback for malformed YAML.
    """
    import yaml

    text = text.lstrip()
    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end == -1:
        return None

    block = text[3:end].strip()
    if not block:
        return None

    try:
        result = yaml.safe_load(block)
        if isinstance(result, dict) and result:
            return result
    except yaml.YAMLError:
        pass

    # Fallback: simple key: value parsing for malformed YAML
    # (e.g. unquoted colons in values like "description: Step 1: do thing")
    result = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        result[key.strip()] = value.strip()
    return result or None


def _strip_common_prefix(names: list[str]) -> dict[str, str]:
    """Strip a common directory prefix from zip entry names.

    When a zip is created by compressing a folder (e.g. macOS Compress),
    all entries share a prefix like 'my-skill/'. This function detects
    that and returns a mapping of {original_name: stripped_name}.

    Only strips if ALL non-directory entries share the same single
    top-level directory prefix.
    """
    # Get non-directory entries
    files = [n for n in names if not n.endswith("/")]
    if not files:
        return {n: n for n in names}

    # Check if all files share a common directory prefix
    parts = [f.split("/", 1) for f in files]
    if not all(len(p) == 2 for p in parts):
        # Some files are at root level — no common prefix
        return {n: n for n in names}

    prefix = parts[0][0]
    if not all(p[0] == prefix for p in parts):
        return {n: n for n in names}

    # All files share the same top-level directory — strip it
    result = {}
    for name in names:
        if name == prefix + "/":
            continue  # Skip the directory entry itself
        if name.startswith(prefix + "/"):
            result[name] = name[len(prefix) + 1 :]
        else:
            result[name] = name
    return result


def _name_to_cy_name(name: str) -> str:
    """Derive a cy_name from a human-readable name.

    'Alert Triage Skill' → 'alert_triage_skill'
    'My Cool-Runbook v2' → 'my_cool_runbook_v2'
    """
    # Lowercase, replace non-alphanumeric with underscore, collapse
    cy = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    # Ensure starts with a letter
    if cy and not cy[0].isalpha():
        cy = "skill_" + cy
    return cy or "unnamed_skill"


class SkillImportService:
    """Service for importing skills from .skill zip files."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def import_from_zip(
        self,
        file_content: bytes,
        tenant_id: str,
        actor_user_id: UUID | None = None,
        actor_roles: list[str] | None = None,
        app: str = "default",
    ) -> SkillImportResponse:
        """Import a skill from a zip file.

        Flow:
        1. Validate zip structure (SKILL.md required)
        2. Load manifest from manifest.json or SKILL.md frontmatter
        3. Run content gates on ALL files — reject entire import if any fail
        4. Submit each file for content review
        5. Return import summary

        Args:
            file_content: Raw bytes of the zip file.
            tenant_id: Tenant identifier.
            actor_user_id: User performing the import.
            actor_roles: Roles for bypass check.

        Returns:
            SkillImportResponse with skill_id and review_ids.

        Raises:
            SkillImportError: If validation fails.
        """
        # Size check
        max_mb = MAX_ZIP_SIZE // (1024 * 1024)
        if len(file_content) > MAX_ZIP_SIZE:
            raise SkillImportError(
                error_code="archive_too_large",
                title="Archive too large",
                message=f"The zip file exceeds the {max_mb}MB size limit.",
                hint=f"Reduce the archive size to under {max_mb}MB and try again.",
            )

        # Open zip
        try:
            zip_buffer = io.BytesIO(file_content)
            zf = zipfile.ZipFile(zip_buffer, "r")
        except zipfile.BadZipFile:
            raise SkillImportError(
                error_code="invalid_archive",
                title="Invalid archive",
                message="The uploaded file is not a valid zip archive.",
                hint="Make sure you are uploading a .zip file.",
            )

        with zf:
            # Strip common directory prefix (e.g. 'my-skill/SKILL.md' → 'SKILL.md')
            raw_names = zf.namelist()
            name_map = _strip_common_prefix(raw_names)
            names = set(name_map.values())

            # Validate structure
            self._validate_structure(names, zf, name_map)

            # Build manifest: prefer manifest.json, fall back to SKILL.md frontmatter
            manifest = self._load_manifest(zf, names, name_map)

            # Collect files (excluding manifest.json)
            content_files = self._collect_content_files(zf, names, name_map)

            # Run content gates on ALL files first
            gate_failures = self._run_content_gates_on_all(
                content_files, actor_roles=actor_roles
            )
            if gate_failures:
                failed_files = [f["file"] for f in gate_failures]
                raise SkillImportError(
                    error_code="content_gate_violation",
                    title="Content policy violation",
                    message=(
                        f"{len(gate_failures)} file(s) failed content safety checks: "
                        + ", ".join(failed_files)
                    ),
                    hint="Remove or fix the flagged files and re-export the zip.",
                    details={"failures": gate_failures},
                )

            # Create or find existing skill
            km_service = KnowledgeModuleService(self.session)
            existing_skill = await km_service.get_skill_by_cy_name(
                tenant_id, manifest.cy_name
            )
            if existing_skill:
                skill_id = existing_skill.component.id
                logger.info(
                    "skill_import_reusing_existing",
                    cy_name=manifest.cy_name,
                    skill_id=str(skill_id),
                )
            else:
                skill_create = SkillCreate(
                    name=manifest.name,
                    cy_name=manifest.cy_name,
                    description=manifest.description,
                    categories=manifest.categories,
                    app=app,
                )
                skill = await km_service.create_skill(tenant_id, skill_create)
                skill_id = skill.component.id

            # Submit each file for content review
            review_service = ContentReviewService(self.session)
            review_ids: list[UUID] = []

            for filename, content in content_files.items():
                review = await review_service.submit_for_review(
                    content=content,
                    filename=filename,
                    skill_id=skill_id,
                    tenant_id=tenant_id,
                    pipeline_name="skill_validation",
                    trigger_source="zip_import",
                    actor_user_id=actor_user_id,
                    actor_roles=actor_roles,
                )
                review_ids.append(review.id)

            return SkillImportResponse(
                skill_id=skill_id,
                name=manifest.name,
                documents_submitted=len(review_ids),
                review_ids=review_ids,
            )

    def _validate_structure(
        self, names: set[str], zf: zipfile.ZipFile, name_map: dict[str, str]
    ) -> None:
        """Validate zip contains required files and respects limits.

        Args:
            names: Normalized file names (prefix stripped).
            zf: The zip file (for size checks using original names).
            name_map: {original_name: normalized_name} mapping.
        """
        for required in REQUIRED_FILES:
            if required not in names:
                raise SkillImportError(
                    error_code="missing_skill_md",
                    title="Missing SKILL.md",
                    message=(
                        "Every skill package needs a SKILL.md file at the root "
                        "that describes the skill."
                    ),
                    hint="Add a SKILL.md file to the root of your zip and re-export.",
                )

        # Build reverse map for size lookups
        reverse_map = {v: k for k, v in name_map.items()}

        # Filter out directories
        file_names = {n for n in names if not n.endswith("/")}
        if len(file_names) > MAX_FILES:
            raise SkillImportError(
                error_code="too_many_files",
                title="Too many files",
                message=f"The archive contains {len(file_names)} files, but the maximum is {MAX_FILES}.",
                hint=f"Reduce the number of files to {MAX_FILES} or fewer.",
            )

        allowed_ext_str = ", ".join(sorted(ALLOWED_EXTENSIONS))
        for name in file_names:
            # Path traversal check
            if ".." in name.split("/") or name.startswith("/"):
                raise SkillImportError(
                    error_code="path_traversal",
                    title="Invalid file path",
                    message=f"The file path {name!r} contains a path traversal sequence.",
                    details={"file": name},
                )

            # Extension check — extensionless files are also blocked
            _, ext = os.path.splitext(name)
            if not ext:
                raise SkillImportError(
                    error_code="blocked_extension",
                    title="Unsupported file type",
                    message=f"The file {name!r} has no extension.",
                    hint=f"Only these file types are allowed: {allowed_ext_str}",
                    details={"file": name},
                )
            if ext.lower() not in ALLOWED_EXTENSIONS:
                raise SkillImportError(
                    error_code="blocked_extension",
                    title="Unsupported file type",
                    message=f"The file extension {ext!r} in {name!r} is not allowed.",
                    hint=f"Only these file types are allowed: {allowed_ext_str}",
                    details={"file": name, "extension": ext},
                )

            # Decompressed file size check (use original name for zip lookup)
            original = reverse_map.get(name, name)
            info = zf.getinfo(original)
            max_file_mb = MAX_FILE_DECOMPRESSED // (1024 * 1024)
            if info.file_size > MAX_FILE_DECOMPRESSED:
                raise SkillImportError(
                    error_code="file_too_large",
                    title="File too large",
                    message=(
                        f"The file {name!r} is {info.file_size:,} bytes, "
                        f"which exceeds the {max_file_mb}MB per-file limit."
                    ),
                    hint=f"Reduce the file to under {max_file_mb}MB.",
                    details={"file": name, "size_bytes": info.file_size},
                )

    def _load_manifest(
        self, zf: zipfile.ZipFile, names: set[str], name_map: dict[str, str]
    ) -> SkillManifest:
        """Load skill manifest from manifest.json or SKILL.md frontmatter.

        Priority:
        1. manifest.json — explicit, used as-is
        2. SKILL.md YAML frontmatter — infer name, description, derive cy_name
        """
        reverse_map = {v: k for k, v in name_map.items()}

        if "manifest.json" in names:
            original = reverse_map.get("manifest.json", "manifest.json")
            try:
                manifest_data = json.loads(zf.read(original))
            except json.JSONDecodeError:
                raise SkillImportError(
                    error_code="invalid_manifest",
                    title="Invalid manifest",
                    message="manifest.json is not valid JSON.",
                    hint="Check for syntax errors in manifest.json (trailing commas, missing quotes).",
                )
            try:
                manifest = SkillManifest.model_validate(manifest_data)
            except Exception:
                raise SkillImportError(
                    error_code="invalid_manifest",
                    title="Invalid manifest",
                    message="manifest.json does not match the expected schema.",
                    hint='Required fields: "name", "cy_name", "description".',
                )
            self._validate_manifest(manifest)
            return manifest

        # No manifest.json — extract from SKILL.md frontmatter
        original = reverse_map.get("SKILL.md", "SKILL.md")
        skill_md = zf.read(original).decode("utf-8")
        frontmatter = _parse_yaml_frontmatter(skill_md)
        if not frontmatter:
            raise SkillImportError(
                error_code="missing_manifest",
                title="Missing skill metadata",
                message=(
                    "No manifest.json found and SKILL.md has no YAML frontmatter. "
                    "The importer needs at least a skill name to proceed."
                ),
                hint=(
                    "Add a manifest.json or YAML frontmatter to SKILL.md:\n"
                    "---\nname: My Skill\ndescription: What it does\n---"
                ),
            )

        name = frontmatter.get("name", "").strip()
        if not name:
            raise SkillImportError(
                error_code="invalid_manifest",
                title="Missing skill name",
                message="SKILL.md frontmatter is missing the required 'name' field.",
                hint="Add 'name: Your Skill Name' to the YAML frontmatter block.",
            )

        cy_name = frontmatter.get("cy_name") or _name_to_cy_name(name)
        description = frontmatter.get("description", "")

        manifest = SkillManifest(
            name=name,
            cy_name=cy_name,
            description=description,
            version=frontmatter.get("version", "1.0.0"),
            categories=frontmatter.get("categories", []),
        )
        self._validate_manifest(manifest)
        return manifest

    def _validate_manifest(self, manifest: SkillManifest) -> None:
        """Validate manifest field constraints beyond Pydantic typing."""
        if not manifest.name or not manifest.name.strip():
            raise SkillImportError(
                error_code="invalid_manifest",
                title="Invalid skill name",
                message="The skill name cannot be empty.",
                hint="Provide a non-empty 'name' in your manifest or SKILL.md frontmatter.",
            )

        if len(manifest.name) > MAX_NAME_LENGTH:
            raise SkillImportError(
                error_code="invalid_manifest",
                title="Skill name too long",
                message=f"The skill name is {len(manifest.name)} characters, but the maximum is {MAX_NAME_LENGTH}.",
                hint=f"Shorten the name to {MAX_NAME_LENGTH} characters or fewer.",
            )

        if not CY_NAME_PATTERN.match(manifest.cy_name):
            raise SkillImportError(
                error_code="invalid_manifest",
                title="Invalid cy_name",
                message=(
                    f"The cy_name {manifest.cy_name!r} is not valid. "
                    "It must be snake_case: lowercase letters, digits, and underscores, starting with a letter."
                ),
                hint="Example: 'alert_triage', 'nist_nvd_lookup'.",
            )

    def _collect_content_files(
        self, zf: zipfile.ZipFile, names: set[str], name_map: dict[str, str]
    ) -> dict[str, str]:
        """Read all content files from zip (excluding manifest.json).

        Returns dict keyed by normalized names (prefix stripped).
        """
        reverse_map = {v: k for k, v in name_map.items()}
        content_files: dict[str, str] = {}
        for name in sorted(names):
            if name.endswith("/") or name == "manifest.json":
                continue
            original = reverse_map.get(name, name)
            try:
                content_files[name] = zf.read(original).decode("utf-8")
            except UnicodeDecodeError:
                raise SkillImportError(
                    error_code="invalid_encoding",
                    title="Invalid file encoding",
                    message=f"The file {name!r} is not valid UTF-8 text.",
                    hint="Make sure all files in the archive are saved as UTF-8.",
                    details={"file": name},
                )
        return content_files

    def _run_content_gates_on_all(
        self,
        content_files: dict[str, str],
        actor_roles: list[str] | None = None,
    ) -> list[dict]:
        """Run content gates on all files. Returns list of failures.

        Owner role skips content_policy_gate and python_ast_gate (cybersecurity
        skills legitimately contain attack patterns and utility scripts).
        Structural gates (empty, length, format) always run.
        """
        from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
            filter_gates_for_owner,
        )
        from analysi.agentic_orchestration.langgraph.content_review.pipeline import (
            get_pipeline_by_name,
        )
        from analysi.services.content_review import BYPASS_ROLES

        pipeline = get_pipeline_by_name("skill_validation")
        gates = pipeline.content_gates()

        is_owner = any(r in BYPASS_ROLES for r in (actor_roles or []))
        if is_owner:
            gates = filter_gates_for_owner(gates)

        failures = []
        for filename, content in content_files.items():
            results = run_content_gates(content, filename, gates)
            if not all_gates_passed(results):
                failed_checks = [r for r in results if not r.passed]
                errors = []
                for r in failed_checks:
                    errors.extend(r.errors)
                failures.append({"file": filename, "errors": errors})

        return failures
