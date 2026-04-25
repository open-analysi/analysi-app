"""Test that workspace run_id matches generation_id for troubleshooting.

Workspace paths should use generation_id as run_id for easier
troubleshooting and correlation with database records.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from analysi.agentic_orchestration.orchestrator import run_full_orchestration
from analysi.schemas.alert import AlertBase


@pytest.mark.asyncio
async def test_orchestration_uses_provided_run_id_for_workspace():
    """Test that run_id parameter is used for workspace creation, not randomly generated.

    This ensures workspace paths contain the generation_id, making it easy to:
    1. Correlate workspace directories with database records
    2. Debug issues by checking /tmp/kea-{tenant}-{generation_id}-*
    3. Clean up workspaces using database queries
    """
    # Arrange
    generation_id = str(uuid4())
    tenant_id = "test-tenant"

    alert = AlertBase(
        title="Test Alert",
        severity="high",
        triggering_event_time="2025-01-01T00:00:00Z",
        raw_alert='{"test": "data"}',
    )

    mock_executor = MagicMock()

    # Mock the first subgraph to capture run_id used for workspace
    captured_run_id = None

    async def mock_first_subgraph(
        alert,
        executor,
        run_id,
        callback=None,
        tenant_id=None,
        created_by=None,
        skills_syncer=None,
        session=None,
    ):
        nonlocal captured_run_id
        captured_run_id = run_id
        return {
            "runbook": "test runbook",
            "task_proposals": [],
            "run_id": captured_run_id,
            "metrics": [],
        }

    async def mock_second_subgraph(
        task_proposals,
        runbook,
        alert,
        executor,
        run_id,
        callback=None,
        tenant_id=None,
        created_by=None,
        max_tasks_to_build=None,
    ):
        return {
            "workflow_id": str(uuid4()),
            "workspace_path": f"/tmp/kea-{tenant_id}-{run_id}-test",
            "tasks_built": [],
            "workflow_composition": [],
            "metrics": [],
        }

    with (
        patch(
            "analysi.agentic_orchestration.orchestrator.run_first_subgraph",
            side_effect=mock_first_subgraph,
        ),
        patch(
            "analysi.agentic_orchestration.orchestrator.run_second_subgraph",
            side_effect=mock_second_subgraph,
        ),
    ):
        # Act
        result = await run_full_orchestration(
            alert=alert,
            executor=mock_executor,
            tenant_id=tenant_id,
            run_id=generation_id,  # Pass generation_id as run_id
        )

    # Assert - workspace should use the provided generation_id
    assert captured_run_id == generation_id, (
        f"Expected workspace to use generation_id={generation_id}, "
        f"but got run_id={captured_run_id}"
    )

    # Verify workspace_path contains the generation_id
    assert generation_id in result["workspace_path"], (
        f"Workspace path should contain generation_id={generation_id}, "
        f"but got: {result['workspace_path']}"
    )


@pytest.mark.asyncio
async def test_orchestration_requires_run_id():
    """Test that orchestration requires run_id parameter (no auto-generation)."""
    # Arrange
    tenant_id = "test-tenant"

    alert = AlertBase(
        title="Test Alert",
        severity="high",
        triggering_event_time="2025-01-01T00:00:00Z",
        raw_alert='{"test": "data"}',
    )

    mock_executor = MagicMock()

    # Act & Assert - should raise TypeError when run_id is missing
    with pytest.raises(
        TypeError, match="missing 1 required positional argument: 'run_id'"
    ):
        await run_full_orchestration(
            alert=alert,
            executor=mock_executor,
            tenant_id=tenant_id,
            # run_id deliberately omitted to test requirement
        )
