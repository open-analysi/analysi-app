"""
Integration tests for CheckpointRepository.

Cross-run checkpoint state for Tasks and Workflows.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.checkpoint_repository import CheckpointRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestCheckpointRepository:
    """Test CheckpointRepository with PostgreSQL."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    async def repo(self, integration_test_session: AsyncSession):
        return CheckpointRepository(integration_test_session)

    # ── Positive tests ──────────────────────────────────────────────

    async def test_upsert_creates_new_checkpoint(
        self, repo: CheckpointRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        owner_id = uuid4()

        cp = await repo.upsert(
            tenant, owner_id, "last_pull", {"ts": "2026-03-27T10:00:00Z"}
        )
        assert cp.id is not None
        assert cp.tenant_id == tenant
        assert cp.owner_id == owner_id
        assert cp.owner_type == "task"  # default
        assert cp.key == "last_pull"
        assert cp.value == {"ts": "2026-03-27T10:00:00Z"}

    async def test_upsert_updates_existing_checkpoint(
        self, repo: CheckpointRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        owner_id = uuid4()

        await repo.upsert(tenant, owner_id, "cursor", {"offset": 0})
        updated = await repo.upsert(tenant, owner_id, "cursor", {"offset": 100})

        assert updated.value == {"offset": 100}

    async def test_get_returns_value(self, repo: CheckpointRepository, unique_id: str):
        tenant = f"t-{unique_id}"
        owner_id = uuid4()
        await repo.upsert(tenant, owner_id, "last_pull", {"ts": "2026-03-27"})

        value = await repo.get(tenant, owner_id, "last_pull")
        assert value == {"ts": "2026-03-27"}

    async def test_get_returns_none_for_missing(
        self, repo: CheckpointRepository, unique_id: str
    ):
        value = await repo.get(f"t-{unique_id}", uuid4(), "nonexistent")
        assert value is None

    async def test_delete_by_owner_removes_all_keys(
        self, repo: CheckpointRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        owner_id = uuid4()
        await repo.upsert(tenant, owner_id, "key_a", {"v": 1})
        await repo.upsert(tenant, owner_id, "key_b", {"v": 2})

        await repo.delete_by_owner(tenant, owner_id)

        assert await repo.get(tenant, owner_id, "key_a") is None
        assert await repo.get(tenant, owner_id, "key_b") is None

    async def test_delete_by_owner_returns_count(
        self, repo: CheckpointRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        owner_id = uuid4()
        await repo.upsert(tenant, owner_id, "k1", {"v": 1})
        await repo.upsert(tenant, owner_id, "k2", {"v": 2})

        count = await repo.delete_by_owner(tenant, owner_id)
        assert count == 2

    async def test_multiple_keys_per_owner(
        self, repo: CheckpointRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        owner_id = uuid4()
        await repo.upsert(tenant, owner_id, "cursor_time", {"ts": "2026-01-01"})
        await repo.upsert(tenant, owner_id, "cursor_id", {"id": 42})

        assert await repo.get(tenant, owner_id, "cursor_time") == {"ts": "2026-01-01"}
        assert await repo.get(tenant, owner_id, "cursor_id") == {"id": 42}

    # ── owner_type isolation ────────────────────────────────────────

    async def test_workflow_owner_type(
        self, repo: CheckpointRepository, unique_id: str
    ):
        """Checkpoints with owner_type='workflow' are stored and retrieved."""
        tenant = f"t-{unique_id}"
        wf_id = uuid4()

        cp = await repo.upsert(
            tenant, wf_id, "batch_offset", {"offset": 50}, owner_type="workflow"
        )
        assert cp.owner_type == "workflow"

        value = await repo.get(tenant, wf_id, "batch_offset", owner_type="workflow")
        assert value == {"offset": 50}

    async def test_same_owner_id_different_type_isolated(
        self, repo: CheckpointRepository, unique_id: str
    ):
        """Same owner_id with different owner_types are independent checkpoints."""
        tenant = f"t-{unique_id}"
        shared_id = uuid4()

        await repo.upsert(tenant, shared_id, "cursor", {"v": "task"}, owner_type="task")
        await repo.upsert(
            tenant, shared_id, "cursor", {"v": "workflow"}, owner_type="workflow"
        )

        task_val = await repo.get(tenant, shared_id, "cursor", owner_type="task")
        wf_val = await repo.get(tenant, shared_id, "cursor", owner_type="workflow")

        assert task_val == {"v": "task"}
        assert wf_val == {"v": "workflow"}

    async def test_delete_by_owner_scoped_to_type(
        self, repo: CheckpointRepository, unique_id: str
    ):
        """delete_by_owner only removes checkpoints for the specified owner_type."""
        tenant = f"t-{unique_id}"
        shared_id = uuid4()

        await repo.upsert(tenant, shared_id, "k1", {"v": 1}, owner_type="task")
        await repo.upsert(tenant, shared_id, "k1", {"v": 2}, owner_type="workflow")

        count = await repo.delete_by_owner(tenant, shared_id, owner_type="task")
        assert count == 1

        # Workflow checkpoint untouched
        assert await repo.get(tenant, shared_id, "k1", owner_type="workflow") == {
            "v": 2
        }
        # Task checkpoint gone
        assert await repo.get(tenant, shared_id, "k1", owner_type="task") is None

    # ── Negative tests ──────────────────────────────────────────────

    async def test_get_wrong_tenant_returns_none(
        self, repo: CheckpointRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        owner_id = uuid4()
        await repo.upsert(tenant, owner_id, "key", {"v": 1})

        value = await repo.get("wrong-tenant", owner_id, "key")
        assert value is None

    async def test_get_wrong_owner_type_returns_none(
        self, repo: CheckpointRepository, unique_id: str
    ):
        """Requesting with wrong owner_type returns None even if owner_id matches."""
        tenant = f"t-{unique_id}"
        owner_id = uuid4()
        await repo.upsert(tenant, owner_id, "key", {"v": 1}, owner_type="task")

        value = await repo.get(tenant, owner_id, "key", owner_type="workflow")
        assert value is None

    async def test_delete_by_owner_returns_zero_when_none(
        self, repo: CheckpointRepository, unique_id: str
    ):
        count = await repo.delete_by_owner(f"t-{unique_id}", uuid4())
        assert count == 0
