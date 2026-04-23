"""Integration tests for workspace cleanup in reconciliation job."""

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from analysi.alert_analysis.db import AlertAnalysisDB
from analysi.alert_analysis.jobs.reconciliation import cleanup_orphaned_workspaces
from analysi.repositories.kea_coordination_repository import (
    AnalysisGroupRepository,
    WorkflowGenerationRepository,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_orphaned_workspaces_removes_terminal_workspaces(db):
    """Test that cleanup_orphaned_workspaces removes workspace directories for terminal generations."""
    # Arrange
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"

    # Create analysis group and workflow generation
    group_repo = AnalysisGroupRepository(db.session)
    generation_repo = WorkflowGenerationRepository(db.session)

    group = await group_repo.create(tenant_id=tenant_id, title="Test Group")
    generation = await generation_repo.create(
        tenant_id=tenant_id,
        analysis_group_id=group.id,
    )

    # Create real workspace directory
    workspace_dir = Path(tempfile.mkdtemp(prefix="kea-test-cleanup-"))
    test_file = workspace_dir / "test.txt"
    test_file.write_text("test content")

    # Mark generation as completed with workspace_path
    await generation_repo.update_with_results(
        tenant_id=tenant_id,
        generation_id=generation.id,
        workflow_id=None,
        status="completed",
        orchestration_results={"test": "data"},
        workspace_path=str(workspace_dir),
    )

    # Verify workspace exists before cleanup
    assert workspace_dir.exists()
    assert test_file.exists()

    # Act
    cleaned_count = await cleanup_orphaned_workspaces(db)

    # Assert
    assert cleaned_count == 1
    assert not workspace_dir.exists()  # Workspace should be deleted


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_skips_placeholder_paths(db):
    """Test that cleanup skips generations with placeholder workspace_path='/tmp/unknown'."""
    # Arrange
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"

    # Create analysis group and workflow generation
    group_repo = AnalysisGroupRepository(db.session)
    generation_repo = WorkflowGenerationRepository(db.session)

    group = await group_repo.create(tenant_id=tenant_id, title="Test Group")
    generation = await generation_repo.create(
        tenant_id=tenant_id,
        analysis_group_id=group.id,
    )

    # Mark generation as completed with placeholder path (legacy generations)
    await generation_repo.update_with_results(
        tenant_id=tenant_id,
        generation_id=generation.id,
        workflow_id=None,
        status="completed",
        orchestration_results={"test": "data"},
        workspace_path="/tmp/unknown",  # Placeholder path
    )

    # Act
    cleaned_count = await cleanup_orphaned_workspaces(db)

    # Assert
    assert cleaned_count == 0  # Should skip placeholder paths


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_handles_nonexistent_paths_gracefully(db):
    """Test that cleanup handles non-existent workspace paths without errors."""
    # Arrange
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"

    # Create analysis group and workflow generation
    group_repo = AnalysisGroupRepository(db.session)
    generation_repo = WorkflowGenerationRepository(db.session)

    group = await group_repo.create(tenant_id=tenant_id, title="Test Group")
    generation = await generation_repo.create(
        tenant_id=tenant_id,
        analysis_group_id=group.id,
    )

    # Mark generation as completed with non-existent workspace path
    nonexistent_path = f"/tmp/kea-test-nonexistent-{uuid4().hex}"
    await generation_repo.update_with_results(
        tenant_id=tenant_id,
        generation_id=generation.id,
        workflow_id=None,
        status="completed",
        orchestration_results={"test": "data"},
        workspace_path=nonexistent_path,
    )

    # Act - should not raise exception
    cleaned_count = await cleanup_orphaned_workspaces(db)

    # Assert
    assert cleaned_count == 0  # Nothing to clean since path doesn't exist


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cleanup_only_affects_terminal_generations(db):
    """Test that cleanup only processes completed/failed generations, not running ones."""
    # Arrange
    tenant_id = f"test-tenant-{uuid4().hex[:8]}"

    # Create analysis group
    group_repo = AnalysisGroupRepository(db.session)
    generation_repo = WorkflowGenerationRepository(db.session)

    group = await group_repo.create(tenant_id=tenant_id, title="Test Group")

    # Create running generation with workspace
    running_generation = await generation_repo.create(
        tenant_id=tenant_id,
        analysis_group_id=group.id,
    )
    running_workspace = Path(tempfile.mkdtemp(prefix="kea-test-running-"))
    await generation_repo.update_with_results(
        tenant_id=tenant_id,
        generation_id=running_generation.id,
        workflow_id=None,
        status="running",  # Still running
        workspace_path=str(running_workspace),
    )

    # Create completed generation with workspace
    completed_generation = await generation_repo.create(
        tenant_id=tenant_id,
        analysis_group_id=group.id,
    )
    completed_workspace = Path(tempfile.mkdtemp(prefix="kea-test-completed-"))
    await generation_repo.update_with_results(
        tenant_id=tenant_id,
        generation_id=completed_generation.id,
        workflow_id=None,
        status="completed",  # Terminal
        workspace_path=str(completed_workspace),
    )

    # Verify both exist before cleanup
    assert running_workspace.exists()
    assert completed_workspace.exists()

    # Act
    cleaned_count = await cleanup_orphaned_workspaces(db)

    # Assert
    assert cleaned_count == 1
    assert running_workspace.exists()  # Running workspace preserved
    assert not completed_workspace.exists()  # Completed workspace deleted

    # Cleanup
    if running_workspace.exists():
        shutil.rmtree(running_workspace)


@pytest.fixture
async def db():
    """Create AlertAnalysisDB instance for integration tests."""
    db_instance = AlertAnalysisDB()
    await db_instance.initialize()
    try:
        yield db_instance
    finally:
        await db_instance.close()
