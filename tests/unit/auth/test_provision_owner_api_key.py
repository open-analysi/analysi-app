"""Unit tests for dev API key provisioning.

Project Mikonos — Idempotent bootstrapping of dev API keys on startup.
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.auth.api_key import DevApiKeySpec, provision_dev_api_keys
from analysi.models.auth import SYSTEM_USER_ID, ApiKey, Membership, User


def _make_execute_result(scalar_value):
    """Create a mock execute result that returns scalar_value from scalar_one_or_none."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    return result


def _owner_spec(raw_key: str = "dev-owner-api-key") -> DevApiKeySpec:
    return DevApiKeySpec(
        raw_key=raw_key,
        role="owner",
        email="system@analysi.internal",
        key_name="Owner API Key",
        user_id=SYSTEM_USER_ID,
    )


def _admin_spec(raw_key: str = "dev-admin-api-key") -> DevApiKeySpec:
    return DevApiKeySpec(
        raw_key=raw_key,
        role="admin",
        email="dev-admin@analysi.local",
        key_name="Admin API Key",
    )


class TestProvisionDevApiKeys:
    @pytest.mark.asyncio
    async def test_creates_user_membership_and_key(self):
        """First run: creates user, membership, and API key."""
        session = AsyncMock()

        # Query 1: ApiKey lookup → not found
        # Query 2: User lookup → not found
        # Query 3: Membership lookup → not found
        session.execute = AsyncMock(
            side_effect=[
                _make_execute_result(None),  # no existing key
                _make_execute_result(None),  # no existing user
                _make_execute_result(None),  # no existing membership
            ]
        )

        await provision_dev_api_keys([_owner_spec()], "default", session)

        # Should add user, membership, and API key
        assert session.add.call_count == 3
        added = [call[0][0] for call in session.add.call_args_list]

        user = next(o for o in added if isinstance(o, User))
        assert user.id == SYSTEM_USER_ID

        membership = next(o for o in added if isinstance(o, Membership))
        assert membership.user_id == SYSTEM_USER_ID
        assert membership.role == "owner"

        api_key = next(o for o in added if isinstance(o, ApiKey))
        assert api_key.key_hash == hashlib.sha256(b"dev-owner-api-key").hexdigest()
        assert api_key.user_id == SYSTEM_USER_ID

    @pytest.mark.asyncio
    async def test_skips_when_key_already_exists(self):
        """Idempotent: no-op if key hash already exists."""
        session = AsyncMock()

        existing_key = MagicMock(spec=ApiKey)
        session.execute = AsyncMock(return_value=_make_execute_result(existing_key))

        await provision_dev_api_keys([_owner_spec()], "default", session)

        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_user_and_membership_when_exist(self):
        """If user and membership exist, only creates the API key."""
        session = AsyncMock()

        existing_user = MagicMock(spec=User)
        existing_membership = MagicMock(spec=Membership)

        session.execute = AsyncMock(
            side_effect=[
                _make_execute_result(None),  # no existing key
                _make_execute_result(existing_user),  # user exists
                _make_execute_result(existing_membership),  # membership exists
            ]
        )

        await provision_dev_api_keys([_owner_spec()], "default", session)

        assert session.add.call_count == 1
        added = session.add.call_args[0][0]
        assert isinstance(added, ApiKey)

    @pytest.mark.asyncio
    async def test_admin_key_uses_deterministic_uuid(self):
        """Admin key derives user_id from email via uuid5."""
        import uuid

        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _make_execute_result(None),  # no existing key
                _make_execute_result(None),  # no existing user
                _make_execute_result(None),  # no existing membership
            ]
        )

        spec = _admin_spec()
        await provision_dev_api_keys([spec], "default", session)

        added = [call[0][0] for call in session.add.call_args_list]
        user = next(o for o in added if isinstance(o, User))
        expected_id = uuid.uuid5(uuid.NAMESPACE_URL, "dev-admin@analysi.local")
        assert user.id == expected_id

        membership = next(o for o in added if isinstance(o, Membership))
        assert membership.role == "admin"

    @pytest.mark.asyncio
    async def test_provisions_multiple_keys_in_one_call(self):
        """Multiple specs are processed in a single session."""
        session = AsyncMock()

        # 3 queries per spec (key, user, membership) × 2 specs = 6
        session.execute = AsyncMock(
            side_effect=[
                _make_execute_result(None),  # owner: no key
                _make_execute_result(None),  # owner: no user
                _make_execute_result(None),  # owner: no membership
                _make_execute_result(None),  # admin: no key
                _make_execute_result(None),  # admin: no user
                _make_execute_result(None),  # admin: no membership
            ]
        )

        await provision_dev_api_keys([_owner_spec(), _admin_spec()], "default", session)

        # 3 adds per spec (user + membership + key) × 2 = 6
        assert session.add.call_count == 6
        added = [call[0][0] for call in session.add.call_args_list]
        api_keys = [o for o in added if isinstance(o, ApiKey)]
        assert len(api_keys) == 2
        assert {k.name for k in api_keys} == {"Owner API Key", "Admin API Key"}

    @pytest.mark.asyncio
    async def test_stores_correct_hash(self):
        """Key is stored as SHA-256 hash."""
        raw_key = "my-owner-key-xyz"
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _make_execute_result(None),
                _make_execute_result(None),
                _make_execute_result(None),
            ]
        )

        await provision_dev_api_keys([_owner_spec(raw_key)], "default", session)

        added = [call[0][0] for call in session.add.call_args_list]
        api_key = next(o for o in added if isinstance(o, ApiKey))
        assert api_key.key_hash == hashlib.sha256(raw_key.encode()).hexdigest()

    @pytest.mark.asyncio
    async def test_empty_specs_is_noop(self):
        """Empty list should not touch the database."""
        session = AsyncMock()
        await provision_dev_api_keys([], "default", session)
        session.execute.assert_not_called()
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_short_key_prefix(self):
        """Keys shorter than 8 chars use the full key as prefix."""
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _make_execute_result(None),
                _make_execute_result(None),
                _make_execute_result(None),
            ]
        )

        await provision_dev_api_keys([_owner_spec("abc")], "default", session)

        added = [call[0][0] for call in session.add.call_args_list]
        api_key = next(o for o in added if isinstance(o, ApiKey))
        assert api_key.key_prefix == "abc"

    @pytest.mark.asyncio
    async def test_second_spec_reuses_existing_user(self):
        """Two specs with the same user_id don't create duplicate users."""
        import uuid

        session = AsyncMock()
        existing_user = MagicMock(spec=User)

        admin_user_id = uuid.uuid5(uuid.NAMESPACE_URL, "dev-admin@analysi.local")

        session.execute = AsyncMock(
            side_effect=[
                # First spec (admin key #1)
                _make_execute_result(None),  # no existing key
                _make_execute_result(existing_user),  # user already exists
                _make_execute_result(None),  # no membership
                # Second spec (admin key #2, same email → same user_id)
                _make_execute_result(None),  # no existing key
                _make_execute_result(existing_user),  # user already exists
                _make_execute_result(
                    MagicMock(spec=Membership)
                ),  # membership now exists
            ]
        )

        spec1 = DevApiKeySpec(
            raw_key="admin-key-1",
            role="admin",
            email="dev-admin@analysi.local",
            key_name="Admin Key 1",
        )
        spec2 = DevApiKeySpec(
            raw_key="admin-key-2",
            role="admin",
            email="dev-admin@analysi.local",
            key_name="Admin Key 2",
        )
        await provision_dev_api_keys([spec1, spec2], "default", session)

        added = [call[0][0] for call in session.add.call_args_list]
        users = [o for o in added if isinstance(o, User)]
        assert len(users) == 0  # user existed both times, never created

        memberships = [o for o in added if isinstance(o, Membership)]
        assert len(memberships) == 1  # created first time, skipped second

        api_keys = [o for o in added if isinstance(o, ApiKey)]
        assert len(api_keys) == 2
        assert api_keys[0].user_id == admin_user_id
        assert api_keys[1].user_id == admin_user_id

    def test_spec_is_immutable(self):
        """DevApiKeySpec is a frozen dataclass."""
        spec = _admin_spec()
        with pytest.raises(AttributeError):
            spec.role = "owner"

    def test_spec_rejects_invalid_role(self):
        """DevApiKeySpec validates role against VALID_DEV_ROLES."""
        with pytest.raises(ValueError, match="Invalid role"):
            DevApiKeySpec(
                raw_key="key",
                role="superadmin",
                email="x@test.com",
                key_name="Bad",
            )

    def test_spec_rejects_typo_role(self):
        with pytest.raises(ValueError, match="Invalid role.*ownerr"):
            DevApiKeySpec(
                raw_key="key",
                role="ownerr",
                email="x@test.com",
                key_name="Bad",
            )
