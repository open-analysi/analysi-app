"""Unit tests for LLM-generated feedback titles.

Tests that TaskFeedbackService._generate_title uses the tenant's primary LLM
to create short titles, and falls back to truncation on failure.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.task_feedback import TaskFeedbackService

TENANT = "test-tenant"


def _mock_llm_pipeline(response_content: str):
    """Create mock LLM factory + bound LLM that returns the given content.

    Returns (mock_factory_class, mock_bound_llm) so tests can assert on calls.
    """
    mock_response = MagicMock()
    mock_response.content = response_content

    mock_bound = AsyncMock()
    mock_bound.ainvoke = AsyncMock(return_value=mock_response)

    mock_llm = MagicMock()
    mock_llm.bind = MagicMock(return_value=mock_bound)

    mock_factory_instance = AsyncMock()
    mock_factory_instance.get_primary_llm = AsyncMock(return_value=mock_llm)

    mock_factory_class = MagicMock(return_value=mock_factory_instance)
    return mock_factory_class, mock_bound


class TestGenerateTitle:
    """Tests for _generate_title LLM call and fallback."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_llm_generated_title(self):
        """Should call the primary LLM and return the generated title."""
        session = AsyncMock()
        svc = TaskFeedbackService(session)

        mock_factory_cls, mock_bound = _mock_llm_pipeline("Check VirusTotal for Hashes")

        with (
            patch("analysi.services.llm_factory.LangChainFactory", mock_factory_cls),
            patch("analysi.services.integration_service.IntegrationService"),
        ):
            title = await svc._generate_title(TENANT, "Always check VirusTotal hashes")

        assert title == "Check VirusTotal for Hashes"
        mock_bound.ainvoke.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_strips_quotes_from_title(self):
        """Should strip surrounding quotes from LLM response."""
        session = AsyncMock()
        svc = TaskFeedbackService(session)

        mock_factory_cls, _ = _mock_llm_pipeline('"Verify Source IP Reputation"')

        with (
            patch("analysi.services.llm_factory.LangChainFactory", mock_factory_cls),
            patch("analysi.services.integration_service.IntegrationService"),
        ):
            title = await svc._generate_title(TENANT, "Check the source IP")

        assert title == "Verify Source IP Reputation"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_falls_back_to_truncation_on_llm_failure(self):
        """Should return truncated text when LLM call fails."""
        session = AsyncMock()
        svc = TaskFeedbackService(session)

        mock_factory_instance = AsyncMock()
        mock_factory_instance.get_primary_llm = AsyncMock(
            side_effect=ValueError("No LLM configured")
        )
        mock_factory_cls = MagicMock(return_value=mock_factory_instance)

        with (
            patch("analysi.services.llm_factory.LangChainFactory", mock_factory_cls),
            patch("analysi.services.integration_service.IntegrationService"),
        ):
            title = await svc._generate_title(TENANT, "Short feedback")

        assert title == "Short feedback"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_falls_back_to_truncation_on_empty_response(self):
        """Should fall back to truncation when LLM returns empty string."""
        session = AsyncMock()
        svc = TaskFeedbackService(session)

        mock_factory_cls, _ = _mock_llm_pipeline("   ")

        with (
            patch("analysi.services.llm_factory.LangChainFactory", mock_factory_cls),
            patch("analysi.services.integration_service.IntegrationService"),
        ):
            title = await svc._generate_title(TENANT, "Some feedback text")

        assert title == "Some feedback text"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_truncation_fallback_adds_ellipsis_for_long_text(self):
        """Should add ellipsis when falling back with text > 60 chars."""
        session = AsyncMock()
        svc = TaskFeedbackService(session)

        long_text = "A" * 100

        mock_factory_instance = AsyncMock()
        mock_factory_instance.get_primary_llm = AsyncMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        mock_factory_cls = MagicMock(return_value=mock_factory_instance)

        with (
            patch("analysi.services.llm_factory.LangChainFactory", mock_factory_cls),
            patch("analysi.services.integration_service.IntegrationService"),
        ):
            title = await svc._generate_title(TENANT, long_text)

        assert title == "A" * 60 + "..."


class TestCreateFeedbackUsesLLMTitle:
    """Verify create_feedback uses _generate_title for the component name."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_feedback_uses_generated_title(self):
        """create_feedback should use _generate_title for component name."""
        session = AsyncMock()
        task_component_id = uuid4()
        feedback_component_id = uuid4()

        # Mock the target component lookup
        mock_component = MagicMock()
        mock_component.tenant_id = TENANT
        session.get = AsyncMock(return_value=mock_component)

        # Mock flush to assign component.id
        async def capture_flush():
            for call in session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "kind") and not hasattr(obj, "component_id"):
                    obj.id = feedback_component_id

        session.flush = AsyncMock(side_effect=capture_flush)

        svc = TaskFeedbackService(session)

        with (
            patch.object(
                svc,
                "_generate_title",
                new_callable=AsyncMock,
                return_value="LLM Generated Title",
            ) as mock_gen,
            patch.object(svc, "_log_audit", new_callable=AsyncMock),
        ):
            doc = await svc.create_feedback(
                tenant_id=TENANT,
                task_component_id=task_component_id,
                feedback_text="Always check VirusTotal for suspicious hashes",
                created_by=uuid4(),
            )

            mock_gen.assert_called_once_with(
                TENANT, "Always check VirusTotal for suspicious hashes"
            )
            assert doc.component.name == "LLM Generated Title"


class TestUpdateFeedbackUsesLLMTitle:
    """Verify update_feedback regenerates title via _generate_title."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_feedback_regenerates_title(self):
        """update_feedback should regenerate title when feedback_text changes."""
        feedback_id = uuid4()

        mock_doc = MagicMock()
        mock_doc.content = "Old text"
        mock_doc.doc_metadata = {}
        mock_doc.component = MagicMock()
        mock_doc.component.name = "Old Title"

        session = AsyncMock()
        svc = TaskFeedbackService(session)

        with (
            patch.object(
                svc, "get_feedback", new_callable=AsyncMock, return_value=mock_doc
            ),
            patch.object(
                svc,
                "_generate_title",
                new_callable=AsyncMock,
                return_value="New LLM Title",
            ) as mock_gen,
            patch.object(svc, "_log_audit", new_callable=AsyncMock),
        ):
            result = await svc.update_feedback(
                tenant_id=TENANT,
                feedback_component_id=feedback_id,
                feedback_text="Updated feedback text",
            )

            mock_gen.assert_called_once_with(TENANT, "Updated feedback text")
            assert result.component.name == "New LLM Title"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_metadata_only_does_not_regenerate_title(self):
        """update_feedback should NOT call _generate_title when only metadata changes."""
        feedback_id = uuid4()

        mock_doc = MagicMock()
        mock_doc.content = "Same text"
        mock_doc.doc_metadata = {}
        mock_doc.component = MagicMock()
        mock_doc.component.name = "Existing Title"

        session = AsyncMock()
        svc = TaskFeedbackService(session)

        with (
            patch.object(
                svc, "get_feedback", new_callable=AsyncMock, return_value=mock_doc
            ),
            patch.object(
                svc,
                "_generate_title",
                new_callable=AsyncMock,
            ) as mock_gen,
            patch.object(svc, "_log_audit", new_callable=AsyncMock),
        ):
            await svc.update_feedback(
                tenant_id=TENANT,
                feedback_component_id=feedback_id,
                metadata={"priority": "high"},
            )

            mock_gen.assert_not_called()
            assert mock_doc.component.name == "Existing Title"
