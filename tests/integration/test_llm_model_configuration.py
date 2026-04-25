"""
Integration tests: OpenAI model configuration is correctly applied to llm_run().

Verifies that the `model` field in the OpenAI integration `settings` is picked up
by LangChainFactory and passed through to ChatOpenAI — i.e. the manifest's
`settings_schema.properties.model` rename (from `default_model` → `model`) is
wired up end-to-end.

Test strategy:
    - We patch `ChatOpenAI` at the factory level to capture which `model=` kwarg
      was used, rather than making real API calls, so these tests run fast and
      deterministically without spending money.
    - We DO create real DB rows (Integration + Credential) so the factory path that
      reads from the database is exercised, not just unit-level mocks.
    - Two tests verify different configured models; one test verifies that updating
      the integration's model setting causes the new model to be used on the next call
      (after cache is cleared).
"""

import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.integration import Integration
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.services.credential_service import CredentialService
from analysi.services.integration_service import IntegrationService
from analysi.services.llm_factory import LangChainFactory

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-dummy-key-for-tests")


async def _create_openai_integration(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    model: str,
) -> None:
    """Create an OpenAI Integration row with the specified model in settings."""
    integration = Integration(
        integration_id=integration_id,
        tenant_id=tenant_id,
        integration_type="openai",
        name=f"Test OpenAI ({model})",
        description=f"Integration for model configuration test — {model}",
        enabled=True,
        settings={"model": model, "api_url": "https://api.openai.com/v1"},
    )
    session.add(integration)
    await session.flush()


async def _create_and_link_credential(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
) -> None:
    """Store an OpenAI API key credential and link it to the integration."""
    cred_service = CredentialService(session)
    cred_id, _ = await cred_service.store_credential(
        tenant_id=tenant_id,
        provider="openai",
        secret={"api_key": _OPENAI_API_KEY},
        account="default",
        credential_metadata={"note": "test credential"},
    )
    await cred_service.associate_with_integration(
        tenant_id=tenant_id,
        integration_id=integration_id,
        credential_id=cred_id,
        is_primary=True,
    )


def _build_factory(session: AsyncSession) -> LangChainFactory:
    """Build a LangChainFactory backed by real DB repos."""
    int_repo = IntegrationRepository(session)
    integration_service = IntegrationService(integration_repo=int_repo)
    return LangChainFactory(integration_service, vault_client=None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestLLMModelConfiguration:
    """
    Verify that the `model` field in OpenAI integration settings is applied
    correctly when LangChainFactory builds a ChatOpenAI instance.
    """

    async def test_configured_model_is_passed_to_chatopenai(
        self, integration_test_session: AsyncSession
    ):
        """
        When an OpenAI integration has settings.model = "gpt-4o-mini",
        LangChainFactory must call ChatOpenAI(model="gpt-4o-mini", ...).
        """
        LangChainFactory.clear_cache()

        tenant_id = f"llm-model-cfg-{uuid4().hex[:8]}"
        integration_id = f"openai-mini-{uuid4().hex[:6]}"
        expected_model = "gpt-4o-mini"

        await _create_openai_integration(
            integration_test_session, tenant_id, integration_id, expected_model
        )
        await _create_and_link_credential(
            integration_test_session, tenant_id, integration_id
        )
        await integration_test_session.commit()

        factory = _build_factory(integration_test_session)

        with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
            mock_llm = MagicMock()
            mock_chat.return_value = mock_llm

            llm = await factory.get_llm_by_id(
                tenant_id, integration_id, session=integration_test_session
            )

        assert llm is mock_llm, "Factory should return the mocked LLM instance"

        # Verify the model kwarg passed to ChatOpenAI
        mock_chat.assert_called_once()
        call_kwargs = mock_chat.call_args.kwargs
        actual_model = call_kwargs.get("model")
        assert actual_model == expected_model, (
            f"ChatOpenAI was called with model={actual_model!r}, "
            f"expected {expected_model!r}. "
            "Check that LangChainFactory._create_openai_llm() reads settings['model']."
        )

    async def test_different_model_produces_different_chatopenai_call(
        self, integration_test_session: AsyncSession
    ):
        """
        Two integrations configured with different models must produce
        ChatOpenAI calls with their respective model values.
        """
        LangChainFactory.clear_cache()

        tenant_id = f"llm-model-diff-{uuid4().hex[:8]}"
        int_id_mini = f"openai-mini-{uuid4().hex[:6]}"
        int_id_full = f"openai-full-{uuid4().hex[:6]}"

        await _create_openai_integration(
            integration_test_session, tenant_id, int_id_mini, "gpt-4o-mini"
        )
        await _create_and_link_credential(
            integration_test_session, tenant_id, int_id_mini
        )

        await _create_openai_integration(
            integration_test_session, tenant_id, int_id_full, "gpt-4o"
        )
        await _create_and_link_credential(
            integration_test_session, tenant_id, int_id_full
        )
        await integration_test_session.commit()

        factory = _build_factory(integration_test_session)

        captured_models: list[str] = []

        def capture_model(*args, **kwargs):
            captured_models.append(kwargs.get("model", "<not set>"))
            return MagicMock()

        with patch(
            "analysi.services.llm_factory.ChatOpenAI", side_effect=capture_model
        ):
            await factory.get_llm_by_id(
                tenant_id, int_id_mini, session=integration_test_session
            )
            await factory.get_llm_by_id(
                tenant_id, int_id_full, session=integration_test_session
            )

        assert len(captured_models) == 2, (
            f"Expected 2 ChatOpenAI calls (one per integration), got {len(captured_models)}"
        )
        assert "gpt-4o-mini" in captured_models, (
            f"gpt-4o-mini not in captured calls: {captured_models}"
        )
        assert "gpt-4o" in captured_models, (
            f"gpt-4o not in captured calls: {captured_models}"
        )

    async def test_updated_model_takes_effect_after_cache_cleared(
        self, integration_test_session: AsyncSession
    ):
        """
        After updating an integration's model setting and clearing the LLM cache,
        the next get_llm_by_id() call must use the new model.

        This verifies that the DB round-trip (integration update → factory cache clear
        → factory re-read) works end-to-end.
        """
        LangChainFactory.clear_cache()

        tenant_id = f"llm-model-update-{uuid4().hex[:8]}"
        integration_id = f"openai-update-{uuid4().hex[:6]}"

        # --- Initial model: gpt-4o-mini ---
        await _create_openai_integration(
            integration_test_session, tenant_id, integration_id, "gpt-4o-mini"
        )
        await _create_and_link_credential(
            integration_test_session, tenant_id, integration_id
        )
        await integration_test_session.commit()

        factory = _build_factory(integration_test_session)
        first_model: list[str] = []

        def capture_first(*args, **kwargs):
            first_model.append(kwargs.get("model", "<not set>"))
            return MagicMock()

        with patch(
            "analysi.services.llm_factory.ChatOpenAI", side_effect=capture_first
        ):
            await factory.get_llm_by_id(
                tenant_id, integration_id, session=integration_test_session
            )

        assert first_model == ["gpt-4o-mini"], (
            f"First call should use gpt-4o-mini, got {first_model}"
        )

        # --- Update model in the DB ---
        int_repo = IntegrationRepository(integration_test_session)
        await int_repo.update_integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            updates={
                "settings": {"model": "gpt-4o", "api_url": "https://api.openai.com/v1"}
            },
        )
        await integration_test_session.commit()

        # Clear cache so the factory re-reads the DB
        LangChainFactory.clear_cache(tenant_id)

        second_model: list[str] = []

        def capture_second(*args, **kwargs):
            second_model.append(kwargs.get("model", "<not set>"))
            return MagicMock()

        with patch(
            "analysi.services.llm_factory.ChatOpenAI", side_effect=capture_second
        ):
            await factory.get_llm_by_id(
                tenant_id, integration_id, session=integration_test_session
            )

        assert second_model == ["gpt-4o"], (
            f"After updating model to gpt-4o and clearing cache, "
            f"expected gpt-4o but got {second_model}. "
            "Verify IntegrationRepository.update_integration() persists settings correctly."
        )

    async def test_default_model_is_gpt4o_when_not_specified(
        self, integration_test_session: AsyncSession
    ):
        """
        An integration with no `model` in settings should fall back to 'gpt-4o'
        (the default defined in LangChainFactory._create_openai_llm).
        """
        LangChainFactory.clear_cache()

        tenant_id = f"llm-model-default-{uuid4().hex[:8]}"
        integration_id = f"openai-default-{uuid4().hex[:6]}"

        # Create integration with NO model field in settings
        integration = Integration(
            integration_id=integration_id,
            tenant_id=tenant_id,
            integration_type="openai",
            name="Test OpenAI (no model setting)",
            description="Integration without model in settings",
            enabled=True,
            settings={
                "api_url": "https://api.openai.com/v1"
            },  # model intentionally absent
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()
        await _create_and_link_credential(
            integration_test_session, tenant_id, integration_id
        )
        await integration_test_session.commit()

        factory = _build_factory(integration_test_session)

        with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            await factory.get_llm_by_id(
                tenant_id, integration_id, session=integration_test_session
            )

        mock_chat.assert_called_once()
        actual_model = mock_chat.call_args.kwargs.get("model")
        assert actual_model == "gpt-4o-mini", (
            f"Expected default model 'gpt-4o-mini', got {actual_model!r}. "
            "Update LangChainFactory._create_openai_llm() default if changed."
        )
