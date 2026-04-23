"""Integration tests for Chat Conversation CRUD API.

Tests conversation create, list, get, update, delete, and ownership isolation.
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import User

TENANT = f"test-chat-{uuid4().hex[:8]}"
BASE = f"/v1/{TENANT}/chat/conversations"


@pytest.mark.asyncio
@pytest.mark.integration
class TestChatConversationAPI:
    """Integration tests for conversation CRUD endpoints."""

    @pytest.fixture
    async def user_a(self, integration_test_session: AsyncSession) -> User:
        """Create user A in the database."""
        user = User(
            keycloak_id=f"keycloak-a-{uuid4().hex[:8]}",
            email=f"user-a-{uuid4().hex[:8]}@test.local",
            display_name="User A",
        )
        integration_test_session.add(user)
        await integration_test_session.flush()
        return user

    @pytest.fixture
    async def user_b(self, integration_test_session: AsyncSession) -> User:
        """Create user B in the database."""
        user = User(
            keycloak_id=f"keycloak-b-{uuid4().hex[:8]}",
            email=f"user-b-{uuid4().hex[:8]}@test.local",
            display_name="User B",
        )
        integration_test_session.add(user)
        await integration_test_session.flush()
        return user

    @pytest.fixture
    async def client_a(self, integration_test_session: AsyncSession, user_a: User):
        """HTTP client authenticated as user A."""

        async def override_get_db():
            yield integration_test_session

        def override_user():
            return CurrentUser(
                user_id=user_a.keycloak_id,
                email=user_a.email,
                tenant_id=TENANT,
                roles=["analyst"],
                actor_type="user",
                db_user_id=user_a.id,
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture
    async def client_b(self, integration_test_session: AsyncSession, user_b: User):
        """HTTP client authenticated as user B."""

        async def override_get_db():
            yield integration_test_session

        def override_user():
            return CurrentUser(
                user_id=user_b.keycloak_id,
                email=user_b.email,
                tenant_id=TENANT,
                roles=["analyst"],
                actor_type="user",
                db_user_id=user_b.id,
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture
    async def admin_client_a(
        self, integration_test_session: AsyncSession, user_a: User
    ):
        """HTTP client authenticated as user A with admin role (for delete tests)."""

        async def override_get_db():
            yield integration_test_session

        def override_user():
            return CurrentUser(
                user_id=user_a.keycloak_id,
                email=user_a.email,
                tenant_id=TENANT,
                roles=["admin"],
                actor_type="user",
                db_user_id=user_a.id,
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    # --- Create ---

    async def test_create_conversation_returns_201(self, client_a: AsyncClient):
        """Creating a conversation with page_context returns 201."""
        response = await client_a.post(
            BASE,
            json={
                "page_context": {
                    "route": "/alerts/ALT-42",
                    "entity_type": "alert",
                    "entity_id": "ALT-42",
                },
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["tenant_id"] == TENANT
        assert data["page_context"]["route"] == "/alerts/ALT-42"
        assert data["token_count_total"] == 0
        assert "id" in data
        assert "created_at" in data

    async def test_create_conversation_without_page_context(
        self, client_a: AsyncClient
    ):
        """Creating a conversation without page_context succeeds."""
        response = await client_a.post(BASE, json={})
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["page_context"] is None

    async def test_create_conversation_with_title(self, client_a: AsyncClient):
        """Creating a conversation with a title stores it."""
        response = await client_a.post(BASE, json={"title": "Alert Investigation"})
        assert response.status_code == 201
        assert response.json()["data"]["title"] == "Alert Investigation"

    async def test_create_conversation_metadata_key_not_leaked(
        self, client_a: AsyncClient
    ):
        """Response JSON uses 'metadata' key, not 'metadata_' (internal alias)."""
        response = await client_a.post(BASE, json={})
        assert response.status_code == 201
        data = response.json()["data"]

        # The key MUST be "metadata" in the API contract, not "metadata_"
        # (metadata_ is the SQLAlchemy attribute name to avoid shadowing Python's
        # built-in metadata; it should not leak into the REST API).
        assert "metadata" in data, (
            f"Expected 'metadata' key in response, got keys: {list(data.keys())}"
        )
        assert "metadata_" not in data, (
            "Internal alias 'metadata_' leaked into API response"
        )
        assert data["metadata"] == {}

    async def test_get_conversation_detail_metadata_key_not_leaked(
        self, client_a: AsyncClient
    ):
        """ConversationDetailResponse also uses 'metadata' key, not 'metadata_'."""
        create_resp = await client_a.post(BASE, json={"title": "Detail Meta Test"})
        conv_id = create_resp.json()["data"]["id"]

        response = await client_a.get(f"{BASE}/{conv_id}")
        assert response.status_code == 200
        data = response.json()["data"]

        assert "metadata" in data, (
            f"Expected 'metadata' key in detail response, got keys: {list(data.keys())}"
        )
        assert "metadata_" not in data, (
            "Internal alias 'metadata_' leaked into detail API response"
        )

    # --- List ---

    async def test_list_conversations_returns_user_conversations(
        self, client_a: AsyncClient
    ):
        """List returns only the current user's conversations."""
        # Create two conversations
        await client_a.post(BASE, json={"title": "Conv 1"})
        await client_a.post(BASE, json={"title": "Conv 2"})

        response = await client_a.get(BASE)
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] >= 2
        assert len(body["data"]) >= 2

    # --- Get ---

    async def test_get_conversation_returns_detail(self, client_a: AsyncClient):
        """GET returns conversation detail."""
        create_resp = await client_a.post(BASE, json={"title": "Detail Test"})
        conv_id = create_resp.json()["data"]["id"]

        response = await client_a.get(f"{BASE}/{conv_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == conv_id
        assert data["title"] == "Detail Test"
        assert "messages" in data

    async def test_get_nonexistent_conversation_returns_404(
        self, client_a: AsyncClient
    ):
        """Unknown UUID returns 404."""
        response = await client_a.get(f"{BASE}/{uuid4()}")
        assert response.status_code == 404

    # --- Update ---

    async def test_update_conversation_title(self, client_a: AsyncClient):
        """PATCH updates title."""
        create_resp = await client_a.post(BASE, json={"title": "Old Title"})
        conv_id = create_resp.json()["data"]["id"]

        response = await client_a.patch(
            f"{BASE}/{conv_id}", json={"title": "New Title"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["title"] == "New Title"

    # --- Delete ---

    async def test_analyst_cannot_delete_conversation(self, client_a: AsyncClient):
        """Analyst role gets 403 on DELETE (admin+ required)."""
        create_resp = await client_a.post(BASE, json={"title": "Protected"})
        conv_id = create_resp.json()["data"]["id"]

        response = await client_a.delete(f"{BASE}/{conv_id}")
        assert response.status_code == 403

    async def test_delete_conversation_returns_204(
        self, client_a: AsyncClient, admin_client_a: AsyncClient
    ):
        """Admin DELETE soft-deletes conversation."""
        create_resp = await client_a.post(BASE, json={"title": "To Delete"})
        conv_id = create_resp.json()["data"]["id"]

        response = await admin_client_a.delete(f"{BASE}/{conv_id}")
        assert response.status_code == 204

    async def test_deleted_conversation_not_in_list(
        self, client_a: AsyncClient, admin_client_a: AsyncClient
    ):
        """Soft-deleted conversation is hidden from list."""
        create_resp = await client_a.post(BASE, json={"title": "Hidden"})
        conv_id = create_resp.json()["data"]["id"]

        await admin_client_a.delete(f"{BASE}/{conv_id}")

        # The deleted conversation should not appear in the list
        list_resp = await client_a.get(BASE)
        ids = [c["id"] for c in list_resp.json()["data"]]
        assert conv_id not in ids

    async def test_deleted_conversation_returns_404_on_get(
        self, client_a: AsyncClient, admin_client_a: AsyncClient
    ):
        """Soft-deleted conversation returns 404 on GET."""
        create_resp = await client_a.post(BASE, json={"title": "Ghost"})
        conv_id = create_resp.json()["data"]["id"]

        await admin_client_a.delete(f"{BASE}/{conv_id}")

        response = await client_a.get(f"{BASE}/{conv_id}")
        assert response.status_code == 404

    # --- Ownership Isolation ---

    async def test_conversation_ownership_isolation(
        self,
        integration_test_session: AsyncSession,
        user_a: User,
        user_b: User,
    ):
        """User A cannot access User B's conversation (and vice versa).

        Uses inline overrides to avoid fixture interaction with shared
        app.dependency_overrides dict.
        """

        async def override_get_db():
            yield integration_test_session

        # Step 1: User A creates a conversation
        def override_as_user_a():
            return CurrentUser(
                user_id=user_a.keycloak_id,
                email=user_a.email,
                tenant_id=TENANT,
                roles=["analyst"],
                actor_type="user",
                db_user_id=user_a.id,
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_as_user_a

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            create_resp = await client.post(BASE, json={"title": "A's Secret"})
            assert create_resp.status_code == 201
            conv_id_a = create_resp.json()["data"]["id"]

        # Step 2: Switch to User B and verify isolation
        def override_as_user_b():
            return CurrentUser(
                user_id=user_b.keycloak_id,
                email=user_b.email,
                tenant_id=TENANT,
                roles=["analyst"],
                actor_type="user",
                db_user_id=user_b.id,
            )

        app.dependency_overrides[get_current_user] = override_as_user_b

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # User B cannot GET User A's conversation
            get_resp = await client.get(f"{BASE}/{conv_id_a}")
            assert get_resp.status_code == 404

            # User B cannot PATCH User A's conversation
            patch_resp = await client.patch(
                f"{BASE}/{conv_id_a}", json={"title": "Hacked"}
            )
            assert patch_resp.status_code == 404

            # User B cannot DELETE User A's conversation (403 — analyst lacks delete)
            delete_resp = await client.delete(f"{BASE}/{conv_id_a}")
            assert delete_resp.status_code == 403

            # User B's list does not include User A's conversation
            list_resp = await client.get(BASE)
            ids = [c["id"] for c in list_resp.json()["data"]]
            assert conv_id_a not in ids

        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
