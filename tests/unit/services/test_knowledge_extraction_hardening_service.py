"""Unit tests for Knowledge Extraction hardening.

Tests input validation, audit logging, and error handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.schemas.audit_context import AuditContext
from analysi.services.knowledge_extraction import (
    ExtractionStateError,
    KnowledgeExtractionService,
)


@pytest.mark.asyncio
class TestInputValidation:
    """Test input validation for content length and emptiness."""

    async def test_rejects_content_exceeding_15k_chars(self):
        """T10: Content > 15K chars → ValueError."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        # Mock skill and document lookups
        mock_skill = MagicMock()
        service.skill_repo.get_skill_by_id = AsyncMock(return_value=mock_skill)

        mock_doc = MagicMock()
        mock_doc.content = "x" * 50_001  # Exceeds 50K
        service.ku_repo.get_document_by_id = AsyncMock(return_value=mock_doc)

        with pytest.raises(ValueError, match="50,000 characters.*chars"):
            await service.start_extraction(
                tenant_id="test-tenant",
                skill_id=uuid4(),
                document_id=uuid4(),
            )

    async def test_rejects_empty_content(self):
        """T11: Empty content → ValueError."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_skill = MagicMock()
        service.skill_repo.get_skill_by_id = AsyncMock(return_value=mock_skill)

        mock_doc = MagicMock()
        mock_doc.content = ""
        service.ku_repo.get_document_by_id = AsyncMock(return_value=mock_doc)

        with pytest.raises(ValueError, match="empty content"):
            await service.start_extraction(
                tenant_id="test-tenant",
                skill_id=uuid4(),
                document_id=uuid4(),
            )

    async def test_rejects_none_content(self):
        """Empty content includes None."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_skill = MagicMock()
        service.skill_repo.get_skill_by_id = AsyncMock(return_value=mock_skill)

        mock_doc = MagicMock()
        mock_doc.content = None
        service.ku_repo.get_document_by_id = AsyncMock(return_value=mock_doc)

        with pytest.raises(ValueError, match="empty content"):
            await service.start_extraction(
                tenant_id="test-tenant",
                skill_id=uuid4(),
                document_id=uuid4(),
            )


@pytest.mark.asyncio
class TestAuditLogging:
    """Test audit trail logging on extraction lifecycle events."""

    def _make_service_with_audit(self):
        """Create service with mocked _log_audit."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)
        service._log_audit = AsyncMock()
        return service

    def _make_audit_context(self):
        return AuditContext(
            actor_id="test-user",
            actor_type="user",
            source="rest_api",
        )

    async def test_start_extraction_logs_audit(self):
        """T12: start_extraction calls _log_audit with extraction.start."""
        service = self._make_service_with_audit()
        audit_ctx = self._make_audit_context()

        mock_skill = MagicMock()
        service.skill_repo.get_skill_by_id = AsyncMock(return_value=mock_skill)

        mock_doc = MagicMock()
        mock_doc.content = "Valid content here"
        service.ku_repo.get_document_by_id = AsyncMock(return_value=mock_doc)

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        service.repo.create = AsyncMock(return_value=mock_extraction)
        service._run_pipeline = AsyncMock(
            return_value={"status": "completed", "classification": {}}
        )
        service.repo.update_pipeline_outputs = AsyncMock()

        await service.start_extraction(
            tenant_id="test-tenant",
            skill_id=uuid4(),
            document_id=uuid4(),
            audit_context=audit_ctx,
        )

        service._log_audit.assert_called_once()
        call_kwargs = service._log_audit.call_args
        assert (
            call_kwargs[1]["action"] == "extraction.start"
            or call_kwargs[0][1] == "extraction.start"
        )

    async def test_apply_extraction_logs_audit(self):
        """T13: apply_extraction calls _log_audit with extraction.apply."""
        service = self._make_service_with_audit()
        audit_ctx = self._make_audit_context()

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        mock_extraction.skill_id = uuid4()
        mock_extraction.status = "completed"
        mock_extraction.transformed_content = "content"
        mock_extraction.placement = {
            "target_namespace": "repository/",
            "target_filename": "test.md",
            "merge_strategy": "create_new",
        }
        mock_extraction.document_id = uuid4()
        mock_extraction.classification = {"doc_type": "new_runbook"}

        service.repo.get_by_id_for_update = AsyncMock(return_value=mock_extraction)

        mock_doc = MagicMock()
        mock_doc.component_id = uuid4()
        service._create_new_document = AsyncMock(return_value=mock_doc)
        service._create_provenance_edges = AsyncMock()
        service.repo.apply = AsyncMock()

        await service.apply_extraction(
            tenant_id="test-tenant",
            skill_id=mock_extraction.skill_id,
            extraction_id=mock_extraction.id,
            audit_context=audit_ctx,
        )

        service._log_audit.assert_called_once()
        args = service._log_audit.call_args
        assert "extraction.apply" in str(args)

    async def test_reject_extraction_logs_audit(self):
        """T14: reject_extraction calls _log_audit with extraction.reject."""
        service = self._make_service_with_audit()
        audit_ctx = self._make_audit_context()

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        mock_extraction.skill_id = uuid4()
        mock_extraction.status = "completed"

        service.repo.get_by_id_for_update = AsyncMock(return_value=mock_extraction)
        service.repo.reject = AsyncMock()

        await service.reject_extraction(
            tenant_id="test-tenant",
            skill_id=mock_extraction.skill_id,
            extraction_id=mock_extraction.id,
            reason="Not useful",
            audit_context=audit_ctx,
        )

        service._log_audit.assert_called_once()
        args = service._log_audit.call_args
        assert "extraction.reject" in str(args)

    async def test_log_audit_skips_when_no_context(self):
        """T15: _log_audit does nothing when audit_context is None."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        # Call the real _log_audit with None context — should not raise
        await service._log_audit(
            tenant_id="test-tenant",
            action="extraction.start",
            resource_id="fake-id",
            audit_context=None,
        )
        # No error = success. No repo call made.


@pytest.mark.asyncio
class TestErrorHandling:
    """Test pipeline error handling and partial state persistence."""

    async def test_pipeline_exception_sets_failed_status(self):
        """T16: Pipeline exception → status=failed with error_message."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_skill = MagicMock()
        service.skill_repo.get_skill_by_id = AsyncMock(return_value=mock_skill)

        mock_doc = MagicMock()
        mock_doc.content = "Valid content"
        service.ku_repo.get_document_by_id = AsyncMock(return_value=mock_doc)

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        service.repo.create = AsyncMock(return_value=mock_extraction)
        service.repo.update_pipeline_outputs = AsyncMock()

        # Simulate pipeline failure
        service._run_pipeline = AsyncMock(
            side_effect=RuntimeError("LLM timeout after 60s")
        )

        await service.start_extraction(
            tenant_id="test-tenant",
            skill_id=uuid4(),
            document_id=uuid4(),
        )

        # Verify update_pipeline_outputs called with failed status
        service.repo.update_pipeline_outputs.assert_called_once()
        call_kwargs = service.repo.update_pipeline_outputs.call_args[1]
        assert call_kwargs["status"] == "failed"
        assert "LLM timeout" in call_kwargs["error_message"]

    async def test_partial_pipeline_state_preserved(self):
        """T17: Mid-pipeline failure preserves partial results."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_skill = MagicMock()
        service.skill_repo.get_skill_by_id = AsyncMock(return_value=mock_skill)

        mock_doc = MagicMock()
        mock_doc.content = "Valid content"
        service.ku_repo.get_document_by_id = AsyncMock(return_value=mock_doc)

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        service.repo.create = AsyncMock(return_value=mock_extraction)
        service.repo.update_pipeline_outputs = AsyncMock()

        # Pipeline returns partial results with failed status
        service._run_pipeline = AsyncMock(
            return_value={
                "status": "failed",
                "classification": {"doc_type": "new_runbook", "confidence": "high"},
                "error_message": "Relevance node failed: API error",
            }
        )

        await service.start_extraction(
            tenant_id="test-tenant",
            skill_id=uuid4(),
            document_id=uuid4(),
        )

        call_kwargs = service.repo.update_pipeline_outputs.call_args[1]
        assert call_kwargs["status"] == "failed"
        assert call_kwargs["classification"]["doc_type"] == "new_runbook"
        assert "Relevance node" in call_kwargs["error_message"]


@pytest.mark.asyncio
class TestRaceConditionPrevention:
    """Test that apply/reject use row-level locking to prevent race conditions."""

    async def test_apply_uses_for_update_locking(self):
        """Apply calls get_by_id_for_update (not get_by_id) to lock the row."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        mock_extraction.skill_id = uuid4()
        mock_extraction.status = "completed"
        mock_extraction.transformed_content = "content"
        mock_extraction.placement = {
            "target_namespace": "repository/",
            "target_filename": "test.md",
            "merge_strategy": "create_new",
        }
        mock_extraction.document_id = uuid4()
        mock_extraction.classification = {"doc_type": "new_runbook"}

        service.repo.get_by_id_for_update = AsyncMock(return_value=mock_extraction)
        service.repo.get_by_id = AsyncMock(
            side_effect=AssertionError("Should use get_by_id_for_update, not get_by_id")
        )

        mock_doc = MagicMock()
        mock_doc.component_id = uuid4()
        service._create_new_document = AsyncMock(return_value=mock_doc)
        service._create_provenance_edges = AsyncMock()
        service.repo.apply = AsyncMock()
        service._log_audit = AsyncMock()

        await service.apply_extraction(
            tenant_id="test-tenant",
            skill_id=mock_extraction.skill_id,
            extraction_id=mock_extraction.id,
        )

        service.repo.get_by_id_for_update.assert_called_once()

    async def test_reject_uses_for_update_locking(self):
        """Reject calls get_by_id_for_update (not get_by_id) to lock the row."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        mock_extraction.skill_id = uuid4()
        mock_extraction.status = "completed"

        service.repo.get_by_id_for_update = AsyncMock(return_value=mock_extraction)
        service.repo.get_by_id = AsyncMock(
            side_effect=AssertionError("Should use get_by_id_for_update, not get_by_id")
        )
        service.repo.reject = AsyncMock()
        service._log_audit = AsyncMock()

        await service.reject_extraction(
            tenant_id="test-tenant",
            skill_id=mock_extraction.skill_id,
            extraction_id=mock_extraction.id,
            reason="Not useful",
        )

        service.repo.get_by_id_for_update.assert_called_once()

    async def test_apply_already_applied_with_locking(self):
        """Even with locking, status check still rejects double-apply."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        mock_extraction.skill_id = uuid4()
        mock_extraction.status = "applied"  # Already applied

        service.repo.get_by_id_for_update = AsyncMock(return_value=mock_extraction)

        with pytest.raises(ExtractionStateError, match="Cannot apply"):
            await service.apply_extraction(
                tenant_id="test-tenant",
                skill_id=mock_extraction.skill_id,
                extraction_id=mock_extraction.id,
            )


@pytest.mark.asyncio
class TestExtractionSummary:
    """Test extraction_summary field in pipeline results."""

    async def test_pipeline_passes_extraction_summary(self):
        """T7: Service passes extraction_summary to update_pipeline_outputs."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_skill = MagicMock()
        service.skill_repo.get_skill_by_id = AsyncMock(return_value=mock_skill)

        mock_doc = MagicMock()
        mock_doc.content = "Valid content here"
        service.ku_repo.get_document_by_id = AsyncMock(return_value=mock_doc)

        mock_extraction = MagicMock()
        mock_extraction.id = uuid4()
        service.repo.create = AsyncMock(return_value=mock_extraction)
        service.repo.update_pipeline_outputs = AsyncMock()

        service._run_pipeline = AsyncMock(
            return_value={
                "status": "completed",
                "classification": {"doc_type": "new_runbook"},
                "extraction_summary": "Extracted a new runbook for brute force investigation.",
            }
        )

        await service.start_extraction(
            tenant_id="test-tenant",
            skill_id=uuid4(),
            document_id=uuid4(),
        )

        call_kwargs = service.repo.update_pipeline_outputs.call_args[1]
        assert (
            call_kwargs["extraction_summary"]
            == "Extracted a new runbook for brute force investigation."
        )

    async def test_stub_pipeline_returns_extraction_summary(self):
        """T8: Stub pipeline returns extraction_summary field."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_doc = MagicMock()
        mock_doc.content = "Some content"
        mock_component = MagicMock()
        mock_component.name = "Test Doc"
        mock_doc.component = mock_component

        result = service._run_pipeline_stub(mock_doc)

        assert "extraction_summary" in result
        assert result["extraction_summary"] is not None
        assert len(result["extraction_summary"]) > 0


@pytest.mark.asyncio
class TestLLMFactoryIntegration:
    """Test LLM factory integration for knowledge extraction.

    These tests verify that _run_pipeline uses LangChainFactory instead of
    the deprecated get_langgraph_llm() which used ANTHROPIC_API_KEY.
    """

    async def test_pipeline_uses_llm_factory(self):
        """T5: Test pipeline uses LangChainFactory.get_primary_llm() for LLM."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_doc = MagicMock()
        mock_doc.content = "Valid content"
        mock_doc.doc_format = "markdown"
        mock_component = MagicMock()
        mock_component.name = "Test Doc"
        mock_doc.component = mock_component

        mock_llm = MagicMock()
        mock_store = MagicMock()

        with (
            patch(
                "analysi.services.llm_factory.LangChainFactory"
            ) as mock_factory_class,
            patch("analysi.services.integration_service.IntegrationService"),
            patch(
                "analysi.agentic_orchestration.langgraph.config.get_db_skills_store"
            ) as mock_get_store,
            patch(
                "analysi.agentic_orchestration.langgraph.knowledge_extraction.graph.run_extraction"
            ) as mock_run_extraction,
        ):
            mock_factory = AsyncMock()
            mock_factory.get_primary_llm.return_value = mock_llm
            mock_factory_class.return_value = mock_factory

            mock_get_store.return_value = mock_store
            mock_run_extraction.return_value = {
                "status": "completed",
                "classification": {"doc_type": "new_runbook"},
            }

            result = await service._run_pipeline(mock_doc, "test-tenant", uuid4())

            # Verify LangChainFactory was used
            mock_factory.get_primary_llm.assert_called_once()
            assert result["status"] == "completed"

    async def test_pipeline_no_integration_uses_stub(self):
        """T7: Test pipeline falls back to stub when no OpenAI integration configured."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_doc = MagicMock()
        mock_doc.content = "Valid content"
        mock_doc.doc_format = "markdown"
        mock_component = MagicMock()
        mock_component.name = "Test Doc"
        mock_doc.component = mock_component

        with (
            patch(
                "analysi.services.llm_factory.LangChainFactory"
            ) as mock_factory_class,
            patch("analysi.services.integration_service.IntegrationService"),
        ):
            mock_factory = AsyncMock()
            mock_factory.get_primary_llm.side_effect = ValueError(
                "No primary LLM integration configured"
            )
            mock_factory_class.return_value = mock_factory

            result = await service._run_pipeline(mock_doc, "test-tenant", uuid4())

            # Should fall back to stub pipeline
            assert result["status"] == "completed"
            assert result["classification"]["doc_type"] == "new_runbook"
            assert "Stub" in result["classification"]["reasoning"]

    async def test_pipeline_logs_error_no_integration(self):
        """T6: Test pipeline logs ERROR level when no integration available."""
        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_doc = MagicMock()
        mock_doc.content = "Valid content"
        mock_doc.doc_format = "markdown"
        mock_component = MagicMock()
        mock_component.name = "Test Doc"
        mock_doc.component = mock_component

        with (
            patch(
                "analysi.services.llm_factory.LangChainFactory"
            ) as mock_factory_class,
            patch("analysi.services.integration_service.IntegrationService"),
            patch("analysi.services.knowledge_extraction.logger") as mock_logger,
        ):
            mock_factory = AsyncMock()
            mock_factory.get_primary_llm.side_effect = ValueError(
                "No primary LLM integration configured"
            )
            mock_factory_class.return_value = mock_factory

            await service._run_pipeline(mock_doc, "test-tenant", uuid4())

            # Verify ERROR was logged (not INFO)
            mock_logger.error.assert_called_once()
            error_msg = mock_logger.error.call_args[0][0]
            assert "OpenAI" in error_msg or "integration" in error_msg.lower()

    async def test_pipeline_no_longer_checks_anthropic_key(self):
        """T8: Test pipeline no longer checks ANTHROPIC_API_KEY env var."""
        import os

        session = AsyncMock()
        service = KnowledgeExtractionService(session)

        mock_doc = MagicMock()
        mock_doc.content = "Valid content"
        mock_doc.doc_format = "markdown"
        mock_component = MagicMock()
        mock_component.name = "Test Doc"
        mock_doc.component = mock_component

        # Ensure ANTHROPIC_API_KEY is NOT set
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "analysi.services.llm_factory.LangChainFactory"
            ) as mock_factory_class,
            patch("analysi.services.integration_service.IntegrationService"),
            patch("analysi.agentic_orchestration.langgraph.config.get_db_skills_store"),
            patch(
                "analysi.agentic_orchestration.langgraph.knowledge_extraction.graph.run_extraction"
            ) as mock_run_extraction,
        ):
            mock_factory = AsyncMock()
            mock_factory.get_primary_llm.return_value = MagicMock()
            mock_factory_class.return_value = mock_factory

            mock_run_extraction.return_value = {
                "status": "completed",
                "classification": {},
            }

            # Should NOT fall back to stub just because ANTHROPIC_API_KEY is missing
            # It should try LangChainFactory first
            await service._run_pipeline(mock_doc, "test-tenant", uuid4())

            # LangChainFactory should have been called
            mock_factory.get_primary_llm.assert_called_once()
