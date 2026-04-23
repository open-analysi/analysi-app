"""Knowledge Extraction service — Hydra project.

Orchestrates the extraction lifecycle:
  start_extraction → (pipeline) → preview → apply | reject
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.knowledge_extraction import KnowledgeExtraction
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.repositories.kdg import KDGRepository
from analysi.repositories.knowledge_extraction_repository import (
    KnowledgeExtractionRepository,
)
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.knowledge_extraction import ExtractionStatus

logger = get_logger(__name__)

MAX_CONTENT_LENGTH = 50_000


class KnowledgeExtractionService:
    """Service for knowledge extraction lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = KnowledgeExtractionRepository(session)
        self.ku_repo = KnowledgeUnitRepository(session)
        self.skill_repo = KnowledgeModuleRepository(session)
        self.kdg_repo = KDGRepository(session)

    async def _log_audit(
        self,
        tenant_id: str,
        action: str,
        resource_id: str,
        audit_context: AuditContext | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit event if audit_context is provided."""
        if audit_context is None:
            return

        try:
            repo = ActivityAuditRepository(self.session)
            await repo.create(
                tenant_id=tenant_id,
                actor_id=audit_context.actor_user_id,
                actor_type=audit_context.actor_type,
                source=audit_context.source,
                action=action,
                resource_type="extraction",
                resource_id=resource_id,
                details=details,
                ip_address=audit_context.ip_address,
                user_agent=audit_context.user_agent,
                request_id=audit_context.request_id,
            )
        except Exception:
            logger.exception("Failed to log audit event for %s", action)

    async def start_extraction(
        self,
        tenant_id: str,
        skill_id: UUID,
        document_id: UUID,
        audit_context: AuditContext | None = None,
    ) -> KnowledgeExtraction:
        """Start a knowledge extraction from a source document into a skill.

        Validates the skill and document exist, creates an extraction record,
        runs the pipeline, and returns the result.
        """
        # Validate skill exists
        skill = await self.skill_repo.get_skill_by_id(skill_id, tenant_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # Validate source document exists
        doc = await self.ku_repo.get_document_by_id(document_id, tenant_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        # Validate content
        content = doc.content or ""
        if not content.strip():
            raise ContentValidationError("Source document has empty content")
        if len(content) > MAX_CONTENT_LENGTH:
            raise ContentValidationError(
                f"Source document exceeds {MAX_CONTENT_LENGTH:,} characters ({len(content):,} chars)"
            )

        # Create extraction record
        extraction = await self.repo.create(
            tenant_id=tenant_id,
            skill_id=skill_id,
            document_id=document_id,
        )

        logger.info(
            "Extraction started",
            extra={"extraction_id": str(extraction.id), "tenant_id": tenant_id},
        )

        # Run extraction pipeline
        try:
            pipeline_result = await self._run_pipeline(doc, tenant_id, skill_id)
            status = pipeline_result.pop("status")
            await self.repo.update_pipeline_outputs(
                extraction, status=status, **pipeline_result
            )
        except Exception as e:
            logger.exception(
                "Extraction pipeline failed",
                extra={"extraction_id": str(extraction.id)},
            )
            await self.repo.update_pipeline_outputs(
                extraction, status=ExtractionStatus.FAILED, error_message=str(e)
            )

        await self.session.commit()
        await self.session.refresh(extraction)

        await self._log_audit(
            tenant_id=tenant_id,
            action="extraction.start",
            resource_id=str(extraction.id),
            audit_context=audit_context,
            details={"document_id": str(document_id), "status": extraction.status},
        )

        return extraction

    async def apply_extraction(
        self,
        tenant_id: str,
        skill_id: UUID,
        extraction_id: UUID,
        overrides: dict[str, Any] | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        """Apply an extraction: create/update skill document + KDG edges.

        Returns dict with document_id, skill_id, namespace_path, extraction_id.
        """
        # SELECT FOR UPDATE prevents race conditions on concurrent apply/reject
        extraction = await self.repo.get_by_id_for_update(tenant_id, extraction_id)
        if not extraction:
            raise ValueError("Extraction not found")
        if str(extraction.skill_id) != str(skill_id):
            raise ValueError("Extraction does not belong to this skill")
        if extraction.status != ExtractionStatus.COMPLETED:
            raise ExtractionStateError(
                f"Cannot apply extraction with status '{extraction.status}'"
            )

        overrides = overrides or {}
        content = overrides.get("content") or extraction.transformed_content
        placement = extraction.placement or {}
        target_namespace = overrides.get("target_namespace") or placement.get(
            "target_namespace", "repository/"
        )
        target_filename = overrides.get("target_filename") or placement.get(
            "target_filename", "extracted-document.md"
        )
        if target_namespace and not target_namespace.endswith("/"):
            target_namespace += "/"
        namespace_path = f"{target_namespace}{target_filename}"

        # Determine create vs merge
        merge_strategy = placement.get("merge_strategy", "create_new")

        if merge_strategy == "merge_with_existing" and extraction.merge_info:
            # Merge path: update existing document content
            merge_target = placement.get("merge_target")
            if merge_target:
                applied_doc = await self._update_existing_document(
                    tenant_id, skill_id, merge_target, content
                )
            else:
                applied_doc = await self._create_new_document(
                    tenant_id, skill_id, namespace_path, content
                )
        else:
            # Create path
            applied_doc = await self._create_new_document(
                tenant_id, skill_id, namespace_path, content
            )

        applied_doc_id = applied_doc.component_id

        # KDG edges
        await self._create_provenance_edges(
            tenant_id=tenant_id,
            skill_id=skill_id,
            extracted_doc_id=applied_doc_id,
            source_doc_id=extraction.document_id,
            extraction=extraction,
            merge_strategy=merge_strategy,
        )

        # Remove STAGED_FOR edge if source doc was staged
        from analysi.repositories.knowledge_module import KnowledgeModuleRepository

        km_repo = KnowledgeModuleRepository(self.session)
        await km_repo.remove_staged_edge(tenant_id, skill_id, extraction.document_id)

        # Update extraction record
        await self.repo.apply(extraction, applied_document_id=applied_doc_id)
        await self.session.commit()

        await self._log_audit(
            tenant_id=tenant_id,
            action="extraction.apply",
            resource_id=str(extraction_id),
            audit_context=audit_context,
            details={
                "document_id": str(applied_doc_id),
                "namespace_path": namespace_path,
            },
        )

        return {
            "document_id": applied_doc_id,
            "skill_id": skill_id,
            "namespace_path": namespace_path,
            "extraction_id": extraction_id,
        }

    async def reject_extraction(
        self,
        tenant_id: str,
        skill_id: UUID,
        extraction_id: UUID,
        reason: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> KnowledgeExtraction:
        """Reject an extraction. No documents or edges created."""
        # SELECT FOR UPDATE prevents race conditions on concurrent apply/reject
        extraction = await self.repo.get_by_id_for_update(tenant_id, extraction_id)
        if not extraction:
            raise ValueError("Extraction not found")
        if str(extraction.skill_id) != str(skill_id):
            raise ValueError("Extraction does not belong to this skill")
        if extraction.status != ExtractionStatus.COMPLETED:
            raise ExtractionStateError(
                f"Cannot reject extraction with status '{extraction.status}'"
            )

        await self.repo.reject(extraction, reason=reason)
        await self.session.commit()
        await self.session.refresh(extraction)

        await self._log_audit(
            tenant_id=tenant_id,
            action="extraction.reject",
            resource_id=str(extraction_id),
            audit_context=audit_context,
            details={"reason": reason},
        )

        return extraction

    async def list_extractions(
        self,
        tenant_id: str,
        skill_id: UUID,
        status: str | None = None,
        document_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[KnowledgeExtraction], int]:
        """List extractions for a skill."""
        return await self.repo.list_by_skill(
            tenant_id=tenant_id,
            skill_id=skill_id,
            status=status,
            document_id=document_id,
            limit=limit,
            offset=offset,
        )

    async def get_extraction(
        self,
        tenant_id: str,
        skill_id: UUID,
        extraction_id: UUID,
    ) -> KnowledgeExtraction | None:
        """Get a single extraction."""
        extraction = await self.repo.get_by_id(tenant_id, extraction_id)
        if extraction and str(extraction.skill_id) != str(skill_id):
            return None
        return extraction

    # --- Private helpers ---

    async def _run_pipeline(
        self, doc: Any, tenant_id: str, skill_id: UUID
    ) -> dict[str, Any]:
        """Run the extraction pipeline.

        Uses LangChainFactory to get LLM from OpenAI integration.
        Falls back to a deterministic stub when no integration configured.
        """
        from analysi.repositories.integration_repository import IntegrationRepository
        from analysi.services.integration_service import IntegrationService
        from analysi.services.llm_factory import LangChainFactory

        # Get LLM from OpenAI integration
        integration_repo = IntegrationRepository(self.session)
        integration_service = IntegrationService(
            integration_repo=integration_repo,
        )
        llm_factory = LangChainFactory(integration_service)

        try:
            llm = await llm_factory.get_primary_llm(tenant_id, self.session)
            logger.info(
                "hydra_using_openai_llm",
                tenant_id=tenant_id,
            )
        except ValueError as e:
            logger.error(
                "hydra_no_openai_integration_using_stub",
                tenant_id=tenant_id,
                error=str(e),
            )
            return self._run_pipeline_stub(doc)

        from analysi.agentic_orchestration.langgraph.config import get_db_skills_store
        from analysi.agentic_orchestration.langgraph.knowledge_extraction.graph import (
            run_extraction,
        )

        content = doc.content or ""
        source_format = getattr(doc, "doc_format", "markdown") or "markdown"
        source_description = doc.component.name if doc.component else "unknown"

        store = get_db_skills_store(tenant_id)

        result = await run_extraction(
            content=content,
            source_format=source_format,
            source_description=source_description,
            skill_id=str(skill_id),
            tenant_id=tenant_id,
            llm=llm,
            store=store,
        )

        return result

    def _run_pipeline_stub(self, doc: Any) -> dict[str, Any]:
        """Deterministic stub pipeline for integration tests without LLM."""
        content = doc.content or ""
        doc_name = doc.component.name if doc.component else "unknown"

        return {
            "status": "completed",
            "classification": {
                "doc_type": "new_runbook",
                "confidence": "medium",
                "reasoning": f"Stub classification for '{doc_name}'",
            },
            "relevance": {
                "is_relevant": True,
                "applicable_namespaces": ["repository/"],
                "reasoning": "Stub: assumed relevant",
            },
            "placement": {
                "target_namespace": "repository/",
                "target_filename": "extracted-document.md",
                "merge_strategy": "create_new",
                "merge_target": None,
                "reasoning": "Stub: default placement",
            },
            "transformed_content": content,
            "validation": {
                "valid": True,
                "errors": [],
                "warnings": ["Stub pipeline — no real validation performed"],
            },
            "extraction_summary": f"Extracted knowledge from '{doc_name}' as a new runbook for security investigation.",
        }

    async def _create_new_document(
        self,
        tenant_id: str,
        skill_id: UUID,
        namespace_path: str,
        content: str,
    ) -> Any:
        """Create a new KUDocument and link it to the skill."""
        # Get skill for namespace scoping
        skill = await self.skill_repo.get_skill_by_id(skill_id, tenant_id)
        skill_cy_name = (
            skill.component.cy_name if skill and skill.component else "unknown"
        )
        skill_namespace = f"/{skill_cy_name}/"

        doc = await self.ku_repo.create_document_ku(
            tenant_id=tenant_id,
            data={
                "name": namespace_path.rsplit("/", 1)[-1].replace(".md", ""),
                "content": content,
                "doc_format": "markdown",
                "document_type": "extracted_knowledge",
                "content_source": "knowledge_extraction",
                "created_by": SYSTEM_USER_ID,
            },
            namespace=skill_namespace,
        )

        # Link document to skill via CONTAINS edge
        from analysi.services.knowledge_module import KnowledgeModuleService

        km_service = KnowledgeModuleService(self.session)
        await km_service.add_document(
            tenant_id=tenant_id,
            skill_id=skill_id,
            document_id=doc.component_id,
            namespace_path=namespace_path,
        )

        return doc

    async def _update_existing_document(
        self,
        tenant_id: str,
        skill_id: UUID,
        merge_target_path: str,
        content: str,
    ) -> Any:
        """Update an existing document's content (merge path)."""
        from analysi.services.knowledge_module import KnowledgeModuleService

        km_service = KnowledgeModuleService(self.session)
        file_info = await km_service.read_skill_file(
            tenant_id, skill_id, merge_target_path
        )
        if not file_info:
            raise ValueError(f"Merge target '{merge_target_path}' not found in skill")

        doc_id = UUID(file_info["document_id"])
        doc = await self.ku_repo.get_document_by_id(doc_id, tenant_id)
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        doc.content = content
        await self.session.flush()
        return doc

    async def _create_provenance_edges(
        self,
        tenant_id: str,
        skill_id: UUID,
        extracted_doc_id: UUID,
        source_doc_id: UUID,
        extraction: KnowledgeExtraction,
        merge_strategy: str,
    ) -> None:
        """Create KDG provenance edges on apply."""
        classification = extraction.classification or {}
        edge_metadata = {
            "extraction_id": str(extraction.id),
            "extraction_method": "knowledge_extraction_v1",
            "classification": classification.get("doc_type", "unknown"),
            "confidence": classification.get("confidence", "unknown"),
            "merge_strategy": merge_strategy,
        }

        # DERIVED_FROM: extracted doc → source doc
        await self.kdg_repo.create_edge(
            tenant_id=tenant_id,
            source_id=extracted_doc_id,
            target_id=source_doc_id,
            relationship_type="derived_from",
            metadata=edge_metadata,
        )

        # CONTAINS edge (skill → extracted doc) is already created by
        # KnowledgeModuleService.add_document() for create_new path.
        # For merge path, the edge already existed. No action needed here.


class ExtractionStateError(Exception):
    """Raised when an extraction state transition is invalid."""

    pass


class ContentValidationError(ValueError):
    """Raised when source document content fails validation."""

    pass
