"""Integration tests for content review apply → KUDocument creation.

Verifies that _create_and_link_document creates real DB entries:
- KUDocument with correct name, content, namespace, and document_type
- CONTAINS edge linking the document to the skill
- Skill tree reflects the new document with correct path
"""

import uuid
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.kdg_edge import EdgeType, KDGEdge
from analysi.models.knowledge_unit import KUDocument
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.schemas.skill import SkillCreate
from analysi.services.content_review import ContentReviewService
from analysi.services.knowledge_module import KnowledgeModuleService


async def _create_test_skill(
    session: AsyncSession, tenant_id: str, suffix: str
) -> UUID:
    """Create a skill and return its component_id."""
    km_service = KnowledgeModuleService(session)
    skill = await km_service.create_skill(
        tenant_id,
        SkillCreate(
            name=f"Test Skill {suffix}",
            cy_name=f"test_skill_{suffix}",
            description="Skill for content review apply tests",
        ),
    )
    await session.flush()
    return skill.component.id


@pytest.mark.asyncio
@pytest.mark.integration
class TestCreateAndLinkDocument:
    """Integration tests for _create_and_link_document hitting real PostgreSQL."""

    @pytest_asyncio.fixture
    async def setup(self, integration_test_session: AsyncSession):
        suffix = uuid.uuid4().hex[:8]
        tenant_id = f"test-cr-apply-{suffix}"
        skill_id = await _create_test_skill(integration_test_session, tenant_id, suffix)
        await integration_test_session.commit()
        return {
            "session": integration_test_session,
            "tenant_id": tenant_id,
            "skill_id": skill_id,
            "suffix": suffix,
        }

    async def test_creates_ku_document_with_correct_fields(self, setup):
        """KUDocument has correct name, content, namespace, and type."""
        session = setup["session"]
        service = ContentReviewService(session)

        doc_id = await service._create_and_link_document(
            tenant_id=setup["tenant_id"],
            skill_id=setup["skill_id"],
            filename="investigation.md",
            content="# Investigation Guide\n\nStep 1: Triage the alert.",
        )
        await session.commit()

        # Fetch the created document
        doc = await session.execute(
            select(KUDocument).where(KUDocument.component_id == doc_id)
        )
        ku_doc = doc.scalar_one()

        assert ku_doc.content == "# Investigation Guide\n\nStep 1: Triage the alert."
        assert ku_doc.doc_format == "markdown"
        assert ku_doc.document_type == "skill_content"
        assert ku_doc.content_source == "content_review"

        # Check component name and namespace
        await session.refresh(ku_doc, ["component"])
        assert ku_doc.component.name == "investigation"
        assert ku_doc.component.namespace == f"/test_skill_{setup['suffix']}/"

    async def test_creates_contains_edge(self, setup):
        """A CONTAINS edge links the skill to the new document."""
        session = setup["session"]
        service = ContentReviewService(session)

        doc_id = await service._create_and_link_document(
            tenant_id=setup["tenant_id"],
            skill_id=setup["skill_id"],
            filename="playbook.md",
            content="# Playbook",
        )
        await session.commit()

        # Check CONTAINS edge exists
        edge_result = await session.execute(
            select(KDGEdge).where(
                KDGEdge.tenant_id == setup["tenant_id"],
                KDGEdge.source_id == setup["skill_id"],
                KDGEdge.target_id == doc_id,
                KDGEdge.relationship_type == EdgeType.CONTAINS,
            )
        )
        edge = edge_result.scalar_one()
        assert edge.edge_metadata["namespace_path"] == "playbook.md"

    async def test_nested_path_preserved_in_edge(self, setup):
        """Directory paths like 'docs/guide.md' stored in edge metadata."""
        session = setup["session"]
        service = ContentReviewService(session)

        doc_id = await service._create_and_link_document(
            tenant_id=setup["tenant_id"],
            skill_id=setup["skill_id"],
            filename="procedures/containment.md",
            content="# Containment\n\nIsolate the host.",
        )
        await session.commit()

        edge_result = await session.execute(
            select(KDGEdge).where(
                KDGEdge.source_id == setup["skill_id"],
                KDGEdge.target_id == doc_id,
                KDGEdge.relationship_type == EdgeType.CONTAINS,
            )
        )
        edge = edge_result.scalar_one()
        assert edge.edge_metadata["namespace_path"] == "procedures/containment.md"

    async def test_nested_path_document_name_includes_directory(self, setup):
        """Document name derived from full path: 'procedures/containment'."""
        session = setup["session"]
        service = ContentReviewService(session)

        doc_id = await service._create_and_link_document(
            tenant_id=setup["tenant_id"],
            skill_id=setup["skill_id"],
            filename="queries/splunk/lateral_movement.md",
            content="# Lateral Movement Detection",
        )
        await session.commit()

        doc = await session.execute(
            select(KUDocument).where(KUDocument.component_id == doc_id)
        )
        ku_doc = doc.scalar_one()
        await session.refresh(ku_doc, ["component"])
        assert ku_doc.component.name == "queries/splunk/lateral_movement"

    async def test_skill_tree_shows_document(self, setup):
        """Skill tree API returns the linked document with correct path."""
        session = setup["session"]
        service = ContentReviewService(session)

        await service._create_and_link_document(
            tenant_id=setup["tenant_id"],
            skill_id=setup["skill_id"],
            filename="docs/evidence.md",
            content="# Evidence Collection",
        )
        await session.commit()

        km_repo = KnowledgeModuleRepository(session)
        tree = await km_repo.get_skill_tree(setup["tenant_id"], setup["skill_id"])

        paths = [entry["path"] for entry in tree]
        assert "docs/evidence.md" in paths

    async def test_multiple_files_in_tree(self, setup):
        """Multiple documents from different directories all appear in tree."""
        session = setup["session"]
        service = ContentReviewService(session)

        files = {
            "SKILL.md": "# Skill Root",
            "docs/triage.md": "# Triage Guide",
            "queries/hunting.md": "# Hunting Queries",
            "procedures/response.md": "# Response Steps",
        }

        for filename, content in files.items():
            await service._create_and_link_document(
                tenant_id=setup["tenant_id"],
                skill_id=setup["skill_id"],
                filename=filename,
                content=content,
            )
        await session.commit()

        km_repo = KnowledgeModuleRepository(session)
        tree = await km_repo.get_skill_tree(setup["tenant_id"], setup["skill_id"])
        paths = sorted(entry["path"] for entry in tree)

        assert paths == [
            "SKILL.md",
            "docs/triage.md",
            "procedures/response.md",
            "queries/hunting.md",
        ]

    async def test_upsert_existing_document(self, setup):
        """Calling twice with same filename updates content, not duplicates."""
        session = setup["session"]
        service = ContentReviewService(session)

        doc_id_1 = await service._create_and_link_document(
            tenant_id=setup["tenant_id"],
            skill_id=setup["skill_id"],
            filename="runbook.md",
            content="# Version 1",
        )
        await session.commit()

        doc_id_2 = await service._create_and_link_document(
            tenant_id=setup["tenant_id"],
            skill_id=setup["skill_id"],
            filename="runbook.md",
            content="# Version 2 — Updated",
        )
        await session.commit()

        # Should update same document (upsert by name+namespace)
        assert doc_id_1 == doc_id_2

        doc = await session.execute(
            select(KUDocument).where(KUDocument.component_id == doc_id_2)
        )
        ku_doc = doc.scalar_one()
        assert ku_doc.content == "# Version 2 — Updated"
