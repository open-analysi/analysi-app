"""Unit tests for hydra_tenant_lock context manager.

Note: submit_new_files_to_hydra() and submit_content_to_hydra() have
internal imports that make unit testing complex. These functions are
tested via integration tests in test_sdk_hydra_integration.py.
"""

import hashlib
from unittest.mock import AsyncMock

import pytest


class TestHydraTenantLock:
    """Tests for hydra_tenant_lock context manager."""

    @pytest.mark.asyncio
    async def test_lock_acquires_advisory_lock(self):
        """Advisory lock is acquired on entry."""
        from analysi.agentic_orchestration.skills_sync import hydra_tenant_lock

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async with hydra_tenant_lock(mock_session, "test-tenant"):
            pass

        # Verify pg_advisory_xact_lock was called
        mock_session.execute.assert_called_once()
        # Get the TextClause object from the call
        call_args = mock_session.execute.call_args
        text_clause = call_args[0][0]
        # Access the text of the SQL statement
        sql_text = str(text_clause)
        assert "pg_advisory_xact_lock" in sql_text

    @pytest.mark.asyncio
    async def test_lock_uses_tenant_specific_id(self):
        """Different tenants get different lock IDs."""
        from analysi.agentic_orchestration.skills_sync import hydra_tenant_lock

        mock_session1 = AsyncMock()
        mock_session1.execute = AsyncMock()

        mock_session2 = AsyncMock()
        mock_session2.execute = AsyncMock()

        async with hydra_tenant_lock(mock_session1, "tenant-a"):
            pass

        async with hydra_tenant_lock(mock_session2, "tenant-b"):
            pass

        # Lock id is now bound as a SQL parameter, not interpolated into the
        # statement string — check the bind dict.
        params1 = mock_session1.execute.call_args[0][1]
        params2 = mock_session2.execute.call_args[0][1]

        assert params1["lock_id"] != params2["lock_id"]

    @pytest.mark.asyncio
    async def test_lock_same_tenant_same_id(self):
        """Same tenant always gets same lock ID."""
        from analysi.agentic_orchestration.skills_sync import hydra_tenant_lock

        mock_session1 = AsyncMock()
        mock_session1.execute = AsyncMock()

        mock_session2 = AsyncMock()
        mock_session2.execute = AsyncMock()

        async with hydra_tenant_lock(mock_session1, "same-tenant"):
            pass

        async with hydra_tenant_lock(mock_session2, "same-tenant"):
            pass

        params1 = mock_session1.execute.call_args[0][1]
        params2 = mock_session2.execute.call_args[0][1]

        # Same tenant_id produces same lock ID.
        assert params1["lock_id"] == params2["lock_id"]

    @pytest.mark.asyncio
    async def test_lock_id_is_deterministic(self):
        """Lock ID for a tenant is deterministic (based on hash)."""
        from analysi.agentic_orchestration.skills_sync import hydra_tenant_lock

        tenant_id = "test-tenant-abc"
        expected_lock_id = int(
            hashlib.sha256(f"hydra:{tenant_id}".encode()).hexdigest()[:15], 16
        )

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async with hydra_tenant_lock(mock_session, tenant_id):
            pass

        # Lock id is bound as a parameter — check the bind dict.
        params = mock_session.execute.call_args[0][1]
        assert params["lock_id"] == expected_lock_id

    @pytest.mark.asyncio
    async def test_lock_releases_on_exception(self):
        """Lock is released even when exception occurs in block."""
        from analysi.agentic_orchestration.skills_sync import hydra_tenant_lock

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        with pytest.raises(ValueError):
            async with hydra_tenant_lock(mock_session, "test-tenant"):
                raise ValueError("Something went wrong")

        # Lock was still acquired (executed once)
        mock_session.execute.assert_called_once()
