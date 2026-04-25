"""Integration tests for TenantSkillsSyncer with real PostgreSQL.

Tests the sync of DB-backed skills to filesystem for SDK agent execution.
"""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysi.agentic_orchestration.skills_sync import (
    SkillNotFoundError,
    TenantSkillsSyncer,
)
from analysi.agentic_orchestration.workspace import AgentWorkspace
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestTenantSkillsSyncerIntegration:
    """Integration tests for TenantSkillsSyncer with real PostgreSQL."""

    @pytest.fixture
    def tenant_id(self) -> str:
        return f"test-sync-{uuid4().hex[:8]}"

    @pytest.fixture
    async def session_factory(self, integration_test_engine):
        """Create a session factory for TenantSkillsSyncer."""
        return async_sessionmaker(
            integration_test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @pytest.fixture
    async def seeded_skill(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Create a skill with documents in the database."""
        session = integration_test_session
        km_repo = KnowledgeModuleRepository(session)
        ku_repo = KnowledgeUnitRepository(session)

        skill_cy_name = f"runbooks_manager_{uuid4().hex[:6]}"

        # Create skill
        skill = await km_repo.create_skill(
            tenant_id,
            {
                "name": "runbooks-manager",
                "description": "Security runbooks for investigation",
                "cy_name": skill_cy_name,
            },
        )

        # Create SKILL.md
        skill_md = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "SKILL.md",
                "doc_format": "markdown",
                "markdown_content": "# Runbooks Manager\n\nThis skill manages security runbooks.",
                "content": None,
            },
        )

        # Create a reference document
        reference = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "references/matching/confidence.md",
                "doc_format": "markdown",
                "markdown_content": "# Confidence Rubric\n\nHigh: 80%+\nMedium: 50-80%\nLow: <50%",
                "content": None,
            },
        )

        # Create a repository document
        repo_doc = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "repository/sql-injection.md",
                "doc_format": "markdown",
                "markdown_content": "# SQL Injection Runbook\n\n## Steps\n1. Check logs",
                "content": None,
            },
        )

        # Link documents to skill
        await km_repo.add_document_to_skill(
            tenant_id, skill.component_id, skill_md.component_id, "SKILL.md"
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill.component_id,
            reference.component_id,
            "references/matching/confidence.md",
        )
        await km_repo.add_document_to_skill(
            tenant_id,
            skill.component_id,
            repo_doc.component_id,
            "repository/sql-injection.md",
        )

        return {
            "skill": skill,
            "name": skill.component.name,
            "cy_name": skill_cy_name,
            "skill_md": skill_md,
            "reference": reference,
            "repo_doc": repo_doc,
        }

    async def test_sync_skills_from_db(self, session_factory, tenant_id, seeded_skill):
        """Sync skills from DB creates correct filesystem structure."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".claude" / "skills"

            result = await syncer.sync_skills(target_dir, [seeded_skill["name"]])

            # Verify source is DB
            assert result == {seeded_skill["name"]: "db"}

            # Verify directory structure
            skill_dir = target_dir / seeded_skill["name"]
            assert skill_dir.exists()

            # Verify SKILL.md exists and has correct content
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.exists()
            assert "Runbooks Manager" in skill_md.read_text()

            # Verify nested structure for references
            reference = skill_dir / "references" / "matching" / "confidence.md"
            assert reference.exists()
            assert "Confidence Rubric" in reference.read_text()

            # Verify repository directory
            repo_doc = skill_dir / "repository" / "sql-injection.md"
            assert repo_doc.exists()
            assert "SQL Injection Runbook" in repo_doc.read_text()

    async def test_baseline_manifest_tracks_synced_files(
        self, session_factory, tenant_id, seeded_skill
    ):
        """Baseline manifest correctly tracks all synced files."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".claude" / "skills"

            await syncer.sync_skills(target_dir, [seeded_skill["name"]])

            # Verify baseline was recorded
            assert syncer.baseline_timestamp is not None
            assert len(syncer._baseline_manifest) == 3  # 3 documents

            # Verify manifest contains correct paths
            skill_name = seeded_skill["name"]
            assert f"{skill_name}/SKILL.md" in syncer._baseline_manifest
            assert (
                f"{skill_name}/references/matching/confidence.md"
                in syncer._baseline_manifest
            )
            assert (
                f"{skill_name}/repository/sql-injection.md" in syncer._baseline_manifest
            )

    async def test_detect_new_files_after_agent_creates(
        self, session_factory, tenant_id, seeded_skill
    ):
        """Detect new files created by agent after sync."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".claude" / "skills"

            await syncer.sync_skills(target_dir, [seeded_skill["name"]])

            # Simulate agent creating a new runbook
            new_runbook = (
                target_dir / seeded_skill["name"] / "repository" / "phishing-alert.md"
            )
            new_runbook.write_text(
                "# Phishing Alert Runbook\n\n## Steps\n1. Check email"
            )

            # Detect new files
            new_files = syncer.detect_new_files(target_dir)

            assert len(new_files) == 1
            assert new_files[0].name == "phishing-alert.md"

    async def test_detect_modified_files(
        self, session_factory, tenant_id, seeded_skill
    ):
        """Detect files modified by agent after sync."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".claude" / "skills"

            await syncer.sync_skills(target_dir, [seeded_skill["name"]])

            # Simulate agent modifying an existing file
            skill_md = target_dir / seeded_skill["name"] / "SKILL.md"
            skill_md.write_text("# Modified Runbooks Manager\n\nUpdated description.")

            # Detect modified files
            new_files = syncer.detect_new_files(target_dir)

            assert len(new_files) == 1
            assert new_files[0].name == "SKILL.md"

    async def test_parallel_execution_isolation(
        self, session_factory, tenant_id, seeded_skill
    ):
        """Parallel syncers have isolated baselines."""
        syncer1 = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )
        syncer2 = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                target1 = Path(tmpdir1) / ".claude" / "skills"
                target2 = Path(tmpdir2) / ".claude" / "skills"

                # Sync both
                await syncer1.sync_skills(target1, [seeded_skill["name"]])
                await syncer2.sync_skills(target2, [seeded_skill["name"]])

                # Create different files in each workspace
                new_file1 = (
                    target1 / seeded_skill["name"] / "repository" / "workspace1.md"
                )
                new_file1.write_text("# From workspace 1")

                new_file2 = (
                    target2 / seeded_skill["name"] / "repository" / "workspace2.md"
                )
                new_file2.write_text("# From workspace 2")

                # Each syncer should only see its own new file
                new_files1 = syncer1.detect_new_files(target1)
                new_files2 = syncer2.detect_new_files(target2)

                assert len(new_files1) == 1
                assert new_files1[0].name == "workspace1.md"

                assert len(new_files2) == 1
                assert new_files2[0].name == "workspace2.md"

    async def test_skill_not_found_raises(self, session_factory, tenant_id):
        """SkillNotFoundError raised for missing skill with no fallback."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".claude" / "skills"

            with pytest.raises(SkillNotFoundError) as exc_info:
                await syncer.sync_skills(target_dir, ["nonexistent-skill"])

            assert "nonexistent-skill" in str(exc_info.value)

    async def test_sync_all_skills(self, session_factory, tenant_id, seeded_skill):
        """sync_all_skills syncs ALL tenant skills from DB."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".claude" / "skills"

            result = await syncer.sync_all_skills(target_dir)

            # Should sync the seeded skill
            assert seeded_skill["name"] in result
            assert result[seeded_skill["name"]] == "db"

            # Verify file exists
            skill_dir = target_dir / seeded_skill["name"]
            assert skill_dir.exists()
            assert (skill_dir / "SKILL.md").exists()

    async def test_sync_all_skills_empty_tenant(self, session_factory):
        """sync_all_skills returns empty dict for tenant with no skills."""
        empty_tenant = f"empty-tenant-{uuid4().hex[:8]}"
        syncer = TenantSkillsSyncer(
            tenant_id=empty_tenant,
            session_factory=session_factory,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".claude" / "skills"

            result = await syncer.sync_all_skills(target_dir)

            assert result == {}
            assert syncer.baseline_timestamp is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentWorkspaceSkillsIntegration:
    """Integration tests for AgentWorkspace with skills syncer."""

    @pytest.fixture
    def tenant_id(self) -> str:
        return f"test-ws-{uuid4().hex[:8]}"

    @pytest.fixture
    async def session_factory(self, integration_test_engine):
        """Create a session factory."""
        return async_sessionmaker(
            integration_test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @pytest.fixture
    async def seeded_skill(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Create a skill in DB."""
        session = integration_test_session
        km_repo = KnowledgeModuleRepository(session)
        ku_repo = KnowledgeUnitRepository(session)

        skill_cy_name = f"test_skill_{uuid4().hex[:6]}"

        skill = await km_repo.create_skill(
            tenant_id,
            {
                "name": "test-skill",
                "description": "Test skill for workspace integration",
                "cy_name": skill_cy_name,
            },
        )

        skill_md = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "SKILL.md",
                "doc_format": "markdown",
                "markdown_content": "# Test Skill\n\nFor testing workspace integration.",
                "content": None,
            },
        )

        await km_repo.add_document_to_skill(
            tenant_id, skill.component_id, skill_md.component_id, "SKILL.md"
        )

        return {"name": skill.component.name, "cy_name": skill_cy_name}

    async def test_workspace_setup_skills_specific(
        self, session_factory, tenant_id, seeded_skill
    ):
        """AgentWorkspace.setup_skills with specific skills syncs from DB."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        workspace = AgentWorkspace(
            run_id=str(uuid4()),
            tenant_id=tenant_id,
            skills_syncer=syncer,
        )

        try:
            result = await workspace.setup_skills([seeded_skill["name"]])

            # Verify skills were synced
            assert result == {seeded_skill["name"]: "db"}

            # Verify file exists in workspace
            skill_md = workspace.skills_dir / seeded_skill["name"] / "SKILL.md"
            assert skill_md.exists()
            assert "Test Skill" in skill_md.read_text()

        finally:
            workspace.cleanup()

    async def test_workspace_setup_skills_all(
        self, session_factory, tenant_id, seeded_skill
    ):
        """AgentWorkspace.setup_skills() without arguments syncs ALL skills."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        workspace = AgentWorkspace(
            run_id=str(uuid4()),
            tenant_id=tenant_id,
            skills_syncer=syncer,
        )

        try:
            # Call without arguments - should sync all tenant skills
            result = await workspace.setup_skills()

            # Should include the seeded skill
            assert seeded_skill["name"] in result

            # Verify file exists in workspace
            skill_md = workspace.skills_dir / seeded_skill["name"] / "SKILL.md"
            assert skill_md.exists()

        finally:
            workspace.cleanup()

    async def test_workspace_detect_new_files(
        self, session_factory, tenant_id, seeded_skill
    ):
        """AgentWorkspace.detect_new_files finds agent-created files."""
        syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        workspace = AgentWorkspace(
            run_id=str(uuid4()),
            tenant_id=tenant_id,
            skills_syncer=syncer,
        )

        try:
            await workspace.setup_skills([seeded_skill["name"]])

            # Simulate agent creating a file
            new_file = workspace.skills_dir / seeded_skill["name"] / "output.md"
            new_file.write_text("# Agent Output")

            new_files = workspace.detect_new_files()

            assert len(new_files) == 1
            assert new_files[0].name == "output.md"

        finally:
            workspace.cleanup()

    async def test_workspace_isolation_between_runs(
        self, session_factory, tenant_id, seeded_skill
    ):
        """Each workspace has isolated skills directory."""
        syncer1 = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )
        syncer2 = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=session_factory,
        )

        workspace1 = AgentWorkspace(
            run_id=str(uuid4()),
            tenant_id=tenant_id,
            skills_syncer=syncer1,
        )
        workspace2 = AgentWorkspace(
            run_id=str(uuid4()),
            tenant_id=tenant_id,
            skills_syncer=syncer2,
        )

        try:
            await workspace1.setup_skills([seeded_skill["name"]])
            await workspace2.setup_skills([seeded_skill["name"]])

            # Workspaces are different
            assert workspace1.work_dir != workspace2.work_dir
            assert workspace1.skills_dir != workspace2.skills_dir

            # Both have the skill
            assert (workspace1.skills_dir / seeded_skill["name"] / "SKILL.md").exists()
            assert (workspace2.skills_dir / seeded_skill["name"] / "SKILL.md").exists()

        finally:
            workspace1.cleanup()
            workspace2.cleanup()
