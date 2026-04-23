"""Unit tests for provision_system_api_key."""

import hashlib
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.auth.api_key import provision_system_api_key
from analysi.models.auth import ApiKey


def _make_api_key_row(key_hash: str) -> ApiKey:
    row = MagicMock(spec=ApiKey)
    row.id = uuid4()
    row.key_hash = key_hash
    row.user_id = None
    row.tenant_id = "default"
    return row


class TestProvisionSystemApiKey:
    @pytest.mark.asyncio
    async def test_provision_creates_key_when_not_exists(self):
        """Provision inserts a new system key if hash not found in DB."""
        raw_key = "dev-system-api-key"
        session = AsyncMock()

        # Simulate no existing key (execute returns sync result object)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute.return_value = execute_result

        await provision_system_api_key(raw_key, "default", session)

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        assert added.key_hash == expected_hash
        assert added.user_id is None
        assert added.tenant_id == "default"

    @pytest.mark.asyncio
    async def test_provision_skips_when_key_already_exists(self):
        """Provision is a no-op if the key hash already exists."""
        raw_key = "dev-system-api-key"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        session = AsyncMock()

        existing = _make_api_key_row(key_hash)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = existing
        session.execute.return_value = execute_result

        await provision_system_api_key(raw_key, "default", session)

        # No new row added
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_provision_uses_null_user_id(self):
        """Provisioned system key has user_id=None (system key, not user key)."""
        raw_key = "some-system-key-abc"
        session = AsyncMock()

        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute.return_value = execute_result

        await provision_system_api_key(raw_key, "default", session)

        added = session.add.call_args[0][0]
        assert added.user_id is None

    @pytest.mark.asyncio
    async def test_provision_stores_correct_hash(self):
        """Provision stores SHA-256 hash of the raw key."""
        raw_key = "my-test-key-xyz"
        session = AsyncMock()

        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute.return_value = execute_result

        await provision_system_api_key(raw_key, "default", session)

        added = session.add.call_args[0][0]
        expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        assert added.key_hash == expected_hash
