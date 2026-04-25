"""Unit tests for tenant-scoped user resolution.

Verifies that /resolve only returns users who are members of the
requesting tenant (plus well-known sentinel users like SYSTEM_USER_ID).
Cross-tenant UUIDs must not be resolvable.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.db.session import get_db
from analysi.models.auth import SYSTEM_USER_ID


def _make_current_user(tenant_id: str = "acme") -> CurrentUser:
    return CurrentUser(
        user_id="kc-test",
        email="test@acme.com",
        tenant_id=tenant_id,
        roles=["analyst"],
        actor_type="user",
        db_user_id=uuid4(),
    )


@pytest.fixture
def app():
    """Create FastAPI test app with the users router under v1."""
    from fastapi import FastAPI

    from analysi.routers.v1 import router as v1_router

    test_app = FastAPI()
    test_app.include_router(v1_router, prefix="/v1")
    return test_app


class TestResolveEndpointTenantScope:
    """Verify /resolve scopes queries to the caller's tenant."""

    def test_resolve_calls_tenant_scoped_query(self, app):
        """The resolve endpoint must use get_by_ids_in_tenant, not get_by_ids."""
        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.email = "alice@acme.com"
        mock_user.display_name = "Alice"

        current_user = _make_current_user(tenant_id="acme")

        # Override auth + DB dependencies
        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        try:
            with patch("analysi.routers.users.UserRepository") as MockRepoClass:
                mock_repo = MockRepoClass.return_value
                mock_repo.get_by_ids_in_tenant = AsyncMock(return_value=[mock_user])

                client = TestClient(app, raise_server_exceptions=False)
                response = client.get(f"/v1/acme/users/resolve?ids={user_id}")

            assert response.status_code == 200
            # Verify the tenant-scoped method was called with the URL tenant
            mock_repo.get_by_ids_in_tenant.assert_called_once_with([user_id], "acme")
        finally:
            app.dependency_overrides.clear()

    def test_resolve_does_not_call_global_get_by_ids(self, app):
        """The resolve endpoint must NOT use the unscoped get_by_ids."""
        current_user = _make_current_user(tenant_id="acme")

        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        try:
            with patch("analysi.routers.users.UserRepository") as MockRepoClass:
                mock_repo = MockRepoClass.return_value
                mock_repo.get_by_ids_in_tenant = AsyncMock(return_value=[])
                mock_repo.get_by_ids = AsyncMock(return_value=[])

                client = TestClient(app, raise_server_exceptions=False)
                response = client.get(f"/v1/acme/users/resolve?ids={uuid4()}")

            assert response.status_code == 200
            mock_repo.get_by_ids.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    def test_resolve_sentinel_users_always_resolvable(self, app):
        """SYSTEM_USER_ID must be resolvable regardless of tenant membership."""
        mock_system_user = MagicMock()
        mock_system_user.id = SYSTEM_USER_ID
        mock_system_user.email = "system@internal"
        mock_system_user.display_name = "System"

        current_user = _make_current_user(tenant_id="acme")

        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        try:
            with patch("analysi.routers.users.UserRepository") as MockRepoClass:
                mock_repo = MockRepoClass.return_value
                # get_by_ids_in_tenant should include sentinel users
                mock_repo.get_by_ids_in_tenant = AsyncMock(
                    return_value=[mock_system_user]
                )

                client = TestClient(app, raise_server_exceptions=False)
                response = client.get(f"/v1/acme/users/resolve?ids={SYSTEM_USER_ID}")

            assert response.status_code == 200
            body = response.json()
            assert len(body["data"]) == 1
            assert body["data"][0]["id"] == str(SYSTEM_USER_ID)
        finally:
            app.dependency_overrides.clear()
