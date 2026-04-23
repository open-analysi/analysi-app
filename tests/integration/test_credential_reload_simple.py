"""
Integration test for credential reload fix.

Tests that IntegrationService raises ValueError when credential is not found,
which triggers the reload logic in TaskExecutionService.
"""

from uuid import uuid4

import pytest

from analysi.models.integration import Integration
from analysi.repositories.credential_repository import CredentialRepository
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.services.credential_service import CredentialService
from analysi.services.integration_service import IntegrationService

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestCredentialReloadFix:
    """Test that missing credentials trigger ValueError for reload logic."""

    @pytest.mark.asyncio
    async def test_missing_credential_raises_value_error(
        self, integration_test_session, sample_tenant_id
    ):
        """
        Test that when IntegrationService tries to use a non-existent credential,
        it raises ValueError (not silently using empty credentials).

        This ValueError is caught by the reload logic in task_execution.py
        which then reloads the integration and credential from the database.
        """
        int_repo = IntegrationRepository(integration_test_session)

        cred_repo = CredentialRepository(integration_test_session)

        integration_service = IntegrationService(
            integration_repo=int_repo, credential_repo=cred_repo
        )

        # Create integration without any credentials
        integration_id = f"test-error-{uuid4().hex[:8]}"
        integration = Integration(
            integration_id=integration_id,
            tenant_id=sample_tenant_id,
            integration_type="echo_edr",
            name="Test Integration",
            description="Test that missing credentials raise ValueError",
            enabled=True,
            settings={"base_url": "http://localhost:8003"},
        )
        integration_test_session.add(integration)
        await integration_test_session.commit()

        # Try to execute an action with a non-existent credential ID
        non_existent_cred_id = uuid4()

        with pytest.raises(ValueError) as exc_info:
            await integration_service.execute_action(
                tenant_id=sample_tenant_id,
                integration_id=integration_id,
                integration_type="echo_edr",
                action_id="pull_processes",
                credential_id=non_existent_cred_id,
                params={"ip": "192.168.1.100"},  # Required parameter
            )

        # Verify the error message contains expected text
        error_msg = str(exc_info.value)
        assert "Credential" in error_msg
        assert "not found" in error_msg
        assert str(non_existent_cred_id) in error_msg or sample_tenant_id in error_msg

    @pytest.mark.asyncio
    async def test_valid_credential_does_not_raise(
        self, integration_test_session, sample_tenant_id
    ):
        """
        Test that when a valid credential exists, no ValueError is raised.
        (The action itself might fail for other reasons, but credential lookup succeeds)
        """
        int_repo = IntegrationRepository(integration_test_session)

        cred_repo = CredentialRepository(integration_test_session)
        cred_service = CredentialService(integration_test_session)

        integration_service = IntegrationService(
            integration_repo=int_repo, credential_repo=cred_repo
        )

        # Create integration
        integration_id = f"test-valid-{uuid4().hex[:8]}"
        integration = Integration(
            integration_id=integration_id,
            tenant_id=sample_tenant_id,
            integration_type="echo_edr",
            name="Test Valid Cred Integration",
            description="Test that valid credentials work",
            enabled=True,
            settings={"base_url": "http://localhost:8003"},
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()

        # Create valid credential
        cred_data = {"api_key": "test-key-123"}
        cred_id, _ = await cred_service.store_credential(
            tenant_id=sample_tenant_id,
            provider="echo_edr",
            secret=cred_data,
            account="test-account",
            credential_metadata={"name": "Test Credential"},
        )

        # Associate credential
        await cred_service.associate_with_integration(
            tenant_id=sample_tenant_id,
            integration_id=integration_id,
            credential_id=cred_id,
            is_primary=True,
        )
        await integration_test_session.commit()

        # Execute action - should not raise ValueError for missing credential
        # (might fail for other reasons like network, but credential lookup succeeds)
        result = await integration_service.execute_action(
            tenant_id=sample_tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
            action_id="pull_processes",
            credential_id=cred_id,
            params={"ip": "192.168.1.100"},  # Required parameter
        )

        # Verify we got a result (even if it's an error result, not a ValueError)
        assert result is not None
        assert isinstance(result, dict)
        # The action might fail due to network, but not due to missing credentials
        # So we just verify we got past the credential loading phase
