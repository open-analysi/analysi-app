"""Unit tests for TenantSkillsSyncer and skills sync utilities.

Updated for DB-only skills - removed filesystem fallback tests.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from analysi.agentic_orchestration.skills_sync import (
    SkillNotFoundError,
    TenantSkillsSyncer,
)


class TestTenantSkillsSyncer:
    """Tests for TenantSkillsSyncer class."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        def factory():
            return session

        return factory

    @pytest.mark.asyncio
    async def test_sync_all_skills(self, mock_session_factory, tmp_path):
        """Test syncing ALL tenant skills from database."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"

        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            # Simulate 2 skills available for tenant
            mock_store.list_skills_async.return_value = {
                "runbooks-manager": "Runbook management",
                "cybersecurity-analyst": "Security analysis",
            }
            mock_store.tree_async.side_effect = [
                ["SKILL.md"],
                ["SKILL.md", "references/guide.md"],
            ]
            mock_store.read_async.side_effect = [
                "# Runbooks Manager",
                "# Cybersecurity Analyst",
                "# Guide Content",
            ]

            result = await syncer.sync_all_skills(target_dir)

            assert result == {"runbooks-manager": "db", "cybersecurity-analyst": "db"}
            assert (target_dir / "runbooks-manager" / "SKILL.md").exists()
            assert (target_dir / "cybersecurity-analyst" / "SKILL.md").exists()

    @pytest.mark.asyncio
    async def test_sync_all_skills_empty_tenant(self, mock_session_factory, tmp_path):
        """Test sync_all_skills with tenant that has no skills."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"

        syncer = TenantSkillsSyncer(
            tenant_id="empty-tenant",
            session_factory=mock_session_factory,
        )

        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store
            mock_store.list_skills_async.return_value = {}  # No skills

            result = await syncer.sync_all_skills(target_dir)

            assert result == {}
            assert syncer.baseline_timestamp is not None  # Baseline still set

    @pytest.mark.asyncio
    async def test_sync_skills_from_db(self, mock_session_factory, tmp_path):
        """Test syncing specific skills from database."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"

        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        # Mock the DatabaseResourceStore
        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            # Simulate DB skill exists
            mock_store.tree_async.return_value = ["SKILL.md", "references/guide.md"]
            mock_store.read_async.side_effect = [
                "# Skill Content",
                "# Guide Content",
            ]

            result = await syncer.sync_skills(target_dir, ["db-skill"])

            assert result == {"db-skill": "db"}
            assert (target_dir / "db-skill" / "SKILL.md").exists()
            assert (target_dir / "db-skill" / "references" / "guide.md").exists()

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, mock_session_factory, tmp_path):
        """Paths with ../ must not escape the skill directory."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"
        # This file should NOT be writable via traversal
        escape_target = tmp_path / "workspace" / "pwned.txt"

        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            # DB returns a path with ../ traversal
            mock_store.tree_async.return_value = [
                "SKILL.md",
                "../../pwned.txt",
            ]
            mock_store.read_async.side_effect = [
                "# Legit skill",
                "# I escaped the sandbox!",
            ]

            with pytest.raises(ValueError, match="path traversal"):
                await syncer.sync_skills(target_dir, ["evil-skill"])

        # Verify the escape target was NOT created
        assert not escape_target.exists(), (
            "Path traversal allowed file write outside skill dir"
        )

    @pytest.mark.asyncio
    async def test_absolute_path_blocked(self, mock_session_factory, tmp_path):
        """Absolute paths from DB must be rejected."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"

        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store

            mock_store.tree_async.return_value = ["/etc/passwd"]
            mock_store.read_async.return_value = "malicious"

            with pytest.raises(ValueError, match="path traversal"):
                await syncer.sync_skills(target_dir, ["evil-skill"])

    @pytest.mark.asyncio
    async def test_sync_skills_not_found_raises(self, mock_session_factory, tmp_path):
        """Test that missing skill raises SkillNotFoundError."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"

        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store
            mock_store.tree_async.return_value = []  # Not in DB

            with pytest.raises(SkillNotFoundError) as exc_info:
                await syncer.sync_skills(target_dir, ["nonexistent-skill"])

            assert "nonexistent-skill" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_baseline_manifest_creation(self, mock_session_factory, tmp_path):
        """Test that baseline manifest is created after sync."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"

        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store
            mock_store.tree_async.return_value = ["SKILL.md"]
            mock_store.read_async.return_value = "# Content"

            await syncer.sync_skills(target_dir, ["test-skill"])

            assert syncer.baseline_timestamp is not None
            assert syncer._baseline_manifest  # Has entries

    @pytest.mark.asyncio
    async def test_detect_new_files(self, mock_session_factory, tmp_path):
        """Test detecting new files created by agent."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"

        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store
            mock_store.tree_async.return_value = ["SKILL.md"]
            mock_store.read_async.return_value = "# Original Content"

            await syncer.sync_skills(target_dir, ["test-skill"])

            # Simulate agent creating a new file
            new_file = target_dir / "test-skill" / "repository" / "new-runbook.md"
            new_file.parent.mkdir(parents=True, exist_ok=True)
            new_file.write_text("# New Runbook")

            new_files = syncer.detect_new_files(target_dir)

            assert len(new_files) == 1
            assert new_files[0].name == "new-runbook.md"

    @pytest.mark.asyncio
    async def test_detect_modified_files(self, mock_session_factory, tmp_path):
        """Test detecting modified files."""
        target_dir = tmp_path / "workspace" / ".claude" / "skills"

        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        with patch(
            "analysi.agentic_orchestration.skills_sync.DatabaseResourceStore"
        ) as MockStore:
            mock_store = AsyncMock()
            MockStore.return_value = mock_store
            mock_store.tree_async.return_value = ["SKILL.md"]
            mock_store.read_async.return_value = "# Original Content"

            await syncer.sync_skills(target_dir, ["test-skill"])

            # Simulate agent modifying an existing file
            skill_md = target_dir / "test-skill" / "SKILL.md"
            skill_md.write_text("# Modified Content")

            new_files = syncer.detect_new_files(target_dir)

            assert len(new_files) == 1
            assert new_files[0].name == "SKILL.md"

    @pytest.mark.asyncio
    async def test_detect_new_files_without_sync_raises(self, mock_session_factory):
        """Test that detect_new_files raises if sync not called."""
        syncer = TenantSkillsSyncer(
            tenant_id="test-tenant",
            session_factory=mock_session_factory,
        )

        with pytest.raises(RuntimeError) as exc_info:
            syncer.detect_new_files(Path("/some/path"))

        assert "sync_skills()" in str(exc_info.value)


class TestAgentUtils:
    """Tests for agent utility functions."""

    def test_extract_skills_from_agent(self, tmp_path):
        """Test extracting skills from agent frontmatter."""
        from analysi.agentic_orchestration.agent_utils import (
            extract_skills_from_agent,
        )

        agent_file = tmp_path / "test-agent.md"
        agent_file.write_text(
            """---
name: test-agent
description: Test agent
skills: skill-one, skill-two
---

# Agent Content
"""
        )

        skills = extract_skills_from_agent(agent_file)

        assert skills == ["skill-one", "skill-two"]

    def test_extract_skills_no_frontmatter(self, tmp_path):
        """Test extracting skills when no frontmatter."""
        from analysi.agentic_orchestration.agent_utils import (
            extract_skills_from_agent,
        )

        agent_file = tmp_path / "test-agent.md"
        agent_file.write_text("# Agent Content\nNo frontmatter here.")

        skills = extract_skills_from_agent(agent_file)

        assert skills == []

    def test_extract_skills_no_skills_field(self, tmp_path):
        """Test extracting skills when no skills field in frontmatter."""
        from analysi.agentic_orchestration.agent_utils import (
            extract_skills_from_agent,
        )

        agent_file = tmp_path / "test-agent.md"
        agent_file.write_text(
            """---
name: test-agent
description: Test agent
---

# Agent Content
"""
        )

        skills = extract_skills_from_agent(agent_file)

        assert skills == []

    def test_extract_skills_file_not_found(self, tmp_path):
        """Test extracting skills when file doesn't exist."""
        from analysi.agentic_orchestration.agent_utils import (
            extract_skills_from_agent,
        )

        agent_file = tmp_path / "nonexistent.md"

        skills = extract_skills_from_agent(agent_file)

        assert skills == []

    def test_extract_agent_metadata(self, tmp_path):
        """Test extracting full metadata from agent frontmatter."""
        from analysi.agentic_orchestration.agent_utils import (
            extract_agent_metadata,
        )

        agent_file = tmp_path / "test-agent.md"
        agent_file.write_text(
            """---
name: test-agent
description: Test agent for testing
model: sonnet
skills: skill-one, skill-two
---

# Agent Content
"""
        )

        metadata = extract_agent_metadata(agent_file)

        assert metadata["name"] == "test-agent"
        assert metadata["description"] == "Test agent for testing"
        assert metadata["model"] == "sonnet"
        assert metadata["skills"] == ["skill-one", "skill-two"]
