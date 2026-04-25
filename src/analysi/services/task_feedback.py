"""Task Feedback Service — Project Zakynthos.

Orchestrates feedback CRUD using existing KU infrastructure.
Each feedback entry = Component + KnowledgeUnit + KUDocument,
connected to a task via a 'feedback_for' KDG edge.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from analysi.config.logging import get_logger
from analysi.models.component import Component, ComponentKind, ComponentStatus
from analysi.models.kdg_edge import EdgeType, KDGEdge
from analysi.models.knowledge_unit import KnowledgeUnit, KUDocument, KUType
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.repositories.component import merge_classification_into_categories
from analysi.schemas.audit_context import AuditContext

logger = get_logger(__name__)


class TaskFeedbackService:
    """Service for managing task feedback as KUDocuments with KDG edges."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _log_audit(
        self,
        tenant_id: str,
        action: str,
        resource_id: str,
        audit_context: AuditContext | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit event if audit_context is provided."""
        if audit_context is None or audit_context.actor_user_id is None:
            return
        try:
            repo = ActivityAuditRepository(self.session)
            await repo.create(
                tenant_id=tenant_id,
                actor_id=audit_context.actor_user_id,
                actor_type=audit_context.actor_type,
                source=audit_context.source,
                action=action,
                resource_type="task_feedback",
                resource_id=resource_id,
                details=details,
                ip_address=audit_context.ip_address,
                user_agent=audit_context.user_agent,
                request_id=audit_context.request_id,
            )
        except Exception:
            logger.warning(
                "task_feedback_audit_log_failed", action=action, resource_id=resource_id
            )

    async def _generate_title(self, tenant_id: str, feedback_text: str) -> str:
        """Generate a short title for feedback using the tenant's primary LLM.

        Falls back to truncation if no LLM is configured or the call fails.
        """
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from analysi.repositories.integration_repository import (
                IntegrationRepository,
            )
            from analysi.services.integration_service import IntegrationService
            from analysi.services.llm_factory import LangChainFactory

            integration_repo = IntegrationRepository(self.session)
            integration_service = IntegrationService(
                integration_repo=integration_repo,
            )
            llm_factory = LangChainFactory(integration_service)
            llm = await llm_factory.get_primary_llm(tenant_id, self.session)
            llm = llm.bind(max_tokens=50)

            system_prompt = (
                "You generate short titles (5-8 words) for analyst feedback entries. "
                "Feedback is operational guidance that analysts attach to automated "
                "security tasks to steer LLM decision-making — e.g. which tools to "
                "prefer, what thresholds to use, or when to escalate.\n\n"
                "Rules:\n"
                "- Return ONLY the title, no quotes, no punctuation at the end\n"
                "- Capture the actionable intent, not just the topic\n"
                "- If the feedback is very short or vague, still produce a clear title\n\n"
                "Examples:\n"
                'Feedback: "Always check VirusTotal before closing an alert as benign"\n'
                "Title: Require VirusTotal Check Before Benign Closure\n\n"
                'Feedback: "use abuseipdb"\n'
                "Title: Prefer AbuseIPDB for IP Lookups\n\n"
                'Feedback: "When the severity is critical, skip the enrichment step '
                'and escalate directly to the SOC team via Slack"\n'
                "Title: Escalate Critical Alerts Directly to SOC\n\n"
                "Feedback: \"Don't trust DNS results from internal resolvers for "
                'external domains — always use public DNS"\n'
                "Title: Use Public DNS for External Domains\n\n"
                'Feedback: "too many false positives"\n'
                "Title: Reduce False Positive Rate"
            )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=feedback_text),
            ]
            response = await llm.ainvoke(messages)
            title = response.content if hasattr(response, "content") else str(response)
            title = title.strip().strip('"').strip("'")

            if title:
                return title
        except Exception as e:
            logger.warning("feedback_title_generation_failed", error=str(e))

        # Fallback: truncate feedback text
        short = feedback_text[:60].replace("\n", " ")
        return short if len(feedback_text) <= 60 else f"{short}..."

    async def create_feedback(
        self,
        tenant_id: str,
        task_component_id: UUID,
        feedback_text: str,
        created_by: UUID,
        metadata: dict[str, Any] | None = None,
        audit_context: AuditContext | None = None,
    ) -> KUDocument:
        """Create a feedback entry as a KUDocument linked to a task via KDG edge.

        Args:
            tenant_id: Tenant identifier.
            task_component_id: The component ID of the target task.
            feedback_text: The feedback content.
            created_by: UUID of the user creating the feedback.
            metadata: Optional structured metadata (priority, category, etc.).

        Returns:
            The created KUDocument.

        Raises:
            ValueError: If the target task component does not exist.
        """
        # Verify target task exists
        target = await self.session.get(Component, task_component_id)
        if target is None or target.tenant_id != tenant_id:
            raise ValueError(
                f"Task component {task_component_id} not found for tenant {tenant_id}"
            )

        # Generate a short LLM title for the component name
        name = await self._generate_title(tenant_id, feedback_text)

        # 1. Create Component with auto-populated categories
        categories = merge_classification_into_categories(
            [],
            document_type="feedback",
            doc_format="raw",
        )
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name=name,
            description="Task feedback entry",
            status=ComponentStatus.ENABLED,
            created_by=created_by,
            categories=categories,
        )
        self.session.add(component)
        await self.session.flush()  # Get component.id

        # 2. Create KnowledgeUnit
        ku = KnowledgeUnit(
            component_id=component.id,
            ku_type=KUType.DOCUMENT,
        )
        self.session.add(ku)

        # 3. Create KUDocument
        doc = KUDocument(
            component_id=component.id,
            content=feedback_text,
            document_type="feedback",
            doc_metadata=metadata or {},
            doc_format="raw",
        )
        self.session.add(doc)

        # 4. Create KDG edge: feedback -> task
        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=component.id,
            target_id=task_component_id,
            relationship_type=EdgeType.FEEDBACK_FOR,
        )
        self.session.add(edge)

        await self.session.flush()
        # Attach component for response building
        doc.component = component

        logger.info(
            "task_feedback_created",
            feedback_id=str(component.id),
            task_component_id=str(task_component_id),
            tenant_id=tenant_id,
        )

        # Project Zakynthos — audit trail
        await self._log_audit(
            tenant_id=tenant_id,
            action="task_feedback.create",
            resource_id=str(component.id),
            audit_context=audit_context,
            details={
                "task_component_id": str(task_component_id),
                "feedback_preview": feedback_text[:100],
            },
        )

        return doc

    async def list_active_feedback(
        self,
        tenant_id: str,
        task_component_id: UUID,
    ) -> list[KUDocument]:
        """List all active (enabled) feedback entries for a task.

        Returns KUDocuments with their Component relationship loaded.
        """
        stmt = (
            select(KUDocument)
            .join(Component, KUDocument.component_id == Component.id)
            .join(KnowledgeUnit, KnowledgeUnit.component_id == Component.id)
            .join(
                KDGEdge,
                and_(
                    KDGEdge.source_id == Component.id,
                    KDGEdge.relationship_type == EdgeType.FEEDBACK_FOR,
                    KDGEdge.target_id == task_component_id,
                ),
            )
            .where(
                Component.tenant_id == tenant_id,
                Component.status == ComponentStatus.ENABLED,
                KUDocument.document_type == "feedback",
            )
            .options(joinedload(KUDocument.component))
            .order_by(Component.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_feedback(
        self,
        tenant_id: str,
        feedback_component_id: UUID,
    ) -> KUDocument | None:
        """Get a single active feedback entry by its component ID."""
        stmt = (
            select(KUDocument)
            .join(Component, KUDocument.component_id == Component.id)
            .where(
                KUDocument.component_id == feedback_component_id,
                KUDocument.document_type == "feedback",
                Component.tenant_id == tenant_id,
                Component.status == ComponentStatus.ENABLED,
            )
            .options(joinedload(KUDocument.component))
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().first()

    async def deactivate_feedback(
        self,
        tenant_id: str,
        feedback_component_id: UUID,
        audit_context: AuditContext | None = None,
    ) -> bool:
        """Soft-delete a feedback entry by setting Component.status = 'disabled'.

        Returns True if the entry was found and deactivated, False otherwise.
        """
        stmt = (
            update(Component)
            .where(
                Component.id == feedback_component_id,
                Component.tenant_id == tenant_id,
                Component.status == ComponentStatus.ENABLED,
            )
            .values(
                status=ComponentStatus.DISABLED,
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        if result.rowcount > 0:
            # Remove the FEEDBACK_FOR edge so the node no longer appears in KDG graphs
            edge_stmt = delete(KDGEdge).where(
                KDGEdge.source_id == feedback_component_id,
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.relationship_type == EdgeType.FEEDBACK_FOR,
            )
            await self.session.execute(edge_stmt)

            logger.info(
                "task_feedback_deactivated",
                feedback_id=str(feedback_component_id),
                tenant_id=tenant_id,
            )
            # Project Zakynthos — audit trail
            await self._log_audit(
                tenant_id=tenant_id,
                action="task_feedback.delete",
                resource_id=str(feedback_component_id),
                audit_context=audit_context,
            )
            return True
        return False

    async def update_feedback(
        self,
        tenant_id: str,
        feedback_component_id: UUID,
        feedback_text: str | None = None,
        metadata: dict[str, Any] | None = None,
        audit_context: AuditContext | None = None,
    ) -> KUDocument | None:
        """Update feedback text and/or metadata.

        Returns the updated KUDocument, or None if not found.
        """
        doc = await self.get_feedback(tenant_id, feedback_component_id)
        if doc is None:
            return None

        if feedback_text is not None:
            doc.content = feedback_text
            # Regenerate the LLM title from the new text
            doc.component.name = await self._generate_title(tenant_id, feedback_text)
        if metadata is not None:
            doc.doc_metadata = metadata

        doc.updated_at = datetime.now(UTC)
        doc.component.updated_at = datetime.now(UTC)
        await self.session.flush()

        logger.info(
            "task_feedback_updated",
            feedback_id=str(feedback_component_id),
            tenant_id=tenant_id,
        )

        # Project Zakynthos — audit trail
        updated_fields = []
        if feedback_text is not None:
            updated_fields.append("feedback_text")
        if metadata is not None:
            updated_fields.append("metadata")
        await self._log_audit(
            tenant_id=tenant_id,
            action="task_feedback.update",
            resource_id=str(feedback_component_id),
            audit_context=audit_context,
            details={"updated_fields": updated_fields},
        )

        return doc
