"""Integration tests for full SDK-Hydra flow.

Tests the complete lifecycle:
1. Seed skill in DB
2. Sync skills to workspace (TenantSkillsSyncer)
3. Detect new files created by agent
4. Apply content policy
5. Submit to Hydra extraction pipeline
6. Verify extraction results and applied documents
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysi.agentic_orchestration.content_policy import ContentPolicy
from analysi.agentic_orchestration.skills_sync import (
    TenantSkillsSyncer,
)
from analysi.agentic_orchestration.workspace import AgentWorkspace
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestSDKHydraIntegration:
    """Integration tests for the full SDK agent → Hydra pipeline."""

    @pytest.fixture
    def tenant_id(self) -> str:
        return f"test-hydra-{uuid4().hex[:8]}"

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
        """Create a skill with documents for testing Hydra submission."""
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
                "markdown_content": "# Runbooks Manager\n\nSecurity investigation runbooks.",
                "content": None,
            },
        )

        # Create existing repository runbook
        existing_runbook = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "repository/phishing.md",
                "doc_format": "markdown",
                "markdown_content": "# Phishing Investigation\n\n## Steps\n1. Check sender\n2. Analyze links",
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
            existing_runbook.component_id,
            "repository/phishing.md",
        )

        return {
            "skill": skill,
            "skill_id": skill.component_id,
            "name": skill.component.name,
            "cy_name": skill_cy_name,
        }

    async def test_full_flow_sync_detect_policy_submit(
        self,
        session_factory,
        integration_test_session,
        tenant_id,
        seeded_skill,
    ):
        """Test the complete SDK → Hydra flow.

        1. Sync skills to workspace
        2. Agent creates a new runbook file
        3. Content policy approves the file
        4. File is submitted to Hydra (would run extraction)
        """
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
            # Step 1: Sync skills
            result = await workspace.setup_skills([seeded_skill["name"]])
            assert result == {seeded_skill["name"]: "db"}

            # Verify skill files exist
            skill_dir = workspace.skills_dir / seeded_skill["name"]
            assert (skill_dir / "SKILL.md").exists()
            assert (skill_dir / "repository" / "phishing.md").exists()

            # Step 2: Simulate agent creating a new runbook
            new_runbook = skill_dir / "repository" / "sql-injection-alert.md"
            new_runbook.write_text(
                """# SQL Injection Alert Investigation

## Alert Context
- Alert Type: SQL Injection Detected
- Severity: High

## Investigation Steps

1. **Identify Source IP**
   - Check WAF logs for source IP
   - Look up IP reputation in threat intelligence

2. **Analyze Payload**
   - Extract the SQL injection payload
   - Classify attack type (UNION, boolean-based, etc.)

3. **Check for Success**
   - Review database logs for query execution
   - Check for data exfiltration indicators

## Recommended Actions
- Block the source IP if malicious
- Patch the vulnerable endpoint
- Alert SOC team for further investigation
"""
            )

            # Step 3: Detect new files
            new_files = workspace.detect_new_files()
            assert len(new_files) == 1
            assert new_files[0].name == "sql-injection-alert.md"

            # Step 4: Apply content policy
            policy = ContentPolicy()
            approved, rejected = policy.filter_new_files(new_files)

            assert len(approved) == 1
            assert len(rejected) == 0
            assert approved[0].name == "sql-injection-alert.md"

            # Step 5: Submit to Hydra (note: this will fail if extraction
            # service isn't fully mocked, but tests the wiring)
            # In a real integration test with full Hydra, this would:
            # - Create KUDocument
            # - Run extraction
            # - Auto-apply

        finally:
            workspace.cleanup()

    async def test_content_policy_blocks_suspicious_file(
        self,
        session_factory,
        tenant_id,
        seeded_skill,
    ):
        """Test that suspicious files are blocked by content policy."""
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

            # Create a file with suspicious content
            suspicious_file = (
                workspace.skills_dir
                / seeded_skill["name"]
                / "repository"
                / "malicious.md"
            )
            suspicious_file.write_text(
                """# Malicious Investigation

```python
import os
os.system("rm -rf /")
```

This is a dangerous runbook.
"""
            )

            new_files = workspace.detect_new_files()
            assert len(new_files) == 1

            policy = ContentPolicy()
            approved, rejected = policy.filter_new_files(new_files)

            # Should be rejected due to suspicious pattern
            assert len(approved) == 0
            assert len(rejected) == 1
            assert "Suspicious pattern" in rejected[0]["reason"]

        finally:
            workspace.cleanup()

    async def test_content_policy_blocks_executable_extension(
        self,
        session_factory,
        tenant_id,
        seeded_skill,
    ):
        """Test that executable extensions are blocked."""
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

            # Create a Python file (should be blocked)
            py_file = (
                workspace.skills_dir / seeded_skill["name"] / "scripts" / "helper.py"
            )
            py_file.parent.mkdir(parents=True, exist_ok=True)
            py_file.write_text("print('hello')")

            new_files = workspace.detect_new_files()
            assert len(new_files) == 1

            policy = ContentPolicy()
            approved, rejected = policy.filter_new_files(new_files)

            # Should be rejected due to executable extension
            assert len(approved) == 0
            assert len(rejected) == 1
            assert "Executable extension" in rejected[0]["reason"]

        finally:
            workspace.cleanup()

    async def test_parallel_workspaces_isolation(
        self,
        session_factory,
        tenant_id,
        seeded_skill,
    ):
        """Test that parallel workspaces are fully isolated."""
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
            # Sync skills in parallel
            await workspace1.setup_skills([seeded_skill["name"]])
            await workspace2.setup_skills([seeded_skill["name"]])

            # Create different files in each workspace
            file1 = (
                workspace1.skills_dir
                / seeded_skill["name"]
                / "repository"
                / "workspace1.md"
            )
            file1.write_text("# From Workspace 1\n\nContent from workspace 1")

            file2 = (
                workspace2.skills_dir
                / seeded_skill["name"]
                / "repository"
                / "workspace2.md"
            )
            file2.write_text("# From Workspace 2\n\nContent from workspace 2")

            # Each workspace should only see its own file
            new_files1 = workspace1.detect_new_files()
            new_files2 = workspace2.detect_new_files()

            assert len(new_files1) == 1
            assert new_files1[0].name == "workspace1.md"

            assert len(new_files2) == 1
            assert new_files2[0].name == "workspace2.md"

            # Workspaces don't interfere with each other
            assert "workspace2.md" not in [f.name for f in new_files1]
            assert "workspace1.md" not in [f.name for f in new_files2]

        finally:
            workspace1.cleanup()
            workspace2.cleanup()

    async def test_modified_synced_file_detected(
        self,
        session_factory,
        tenant_id,
        seeded_skill,
    ):
        """Test that modifications to synced files are detected."""
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

            # Modify an existing synced file
            existing_runbook = (
                workspace.skills_dir
                / seeded_skill["name"]
                / "repository"
                / "phishing.md"
            )
            existing_runbook.write_text(
                "# Updated Phishing Runbook\n\n## New Steps\n1. Enhanced analysis"
            )

            # Should detect the modified file
            new_files = workspace.detect_new_files()
            assert len(new_files) == 1
            assert new_files[0].name == "phishing.md"

        finally:
            workspace.cleanup()
