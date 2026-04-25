"""
Integration tests for workflow execution with artifact linking.

Tests the complete end-to-end flow:
1. Workflow creates tasks
2. Tasks create artifacts with workflow_run_id
3. Artifacts are queryable by workflow_run_id
4. FinalDispositionUpdateStep can retrieve and use artifacts
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.artifact import Artifact
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.task_run import TaskRun
from analysi.models.workflow import Workflow
from analysi.models.workflow_execution import WorkflowRun


@pytest.mark.integration
@pytest.mark.skip(
    reason="Tests need significant setup - artifact creation requires many fields"
)
class TestWorkflowArtifactLinking:
    """Integration tests for workflow-artifact linking."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncClient:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_workflow_task_creates_artifact_with_workflow_run_id(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test that tasks executed within workflows create artifacts with workflow_run_id."""
        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()
        workflow_run_id = uuid.uuid4()
        task_run_id = uuid.uuid4()

        # First create a Workflow (blueprint)
        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        integration_test_session.add(workflow)
        await integration_test_session.flush()

        # Create a workflow run
        workflow_run = WorkflowRun(
            id=workflow_run_id,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            status="running",
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(workflow_run)

        # Create a task run linked to workflow
        task_run = TaskRun(
            id=task_run_id,
            tenant_id=tenant_id,
            task_id=None,  # Ad-hoc task
            workflow_run_id=workflow_run_id,  # Link to workflow
            cy_script="print('test task')",
            status="running",
            started_at=datetime.now(UTC),
            execution_context={
                "tenant_id": tenant_id,
                "task_run_id": str(task_run_id),
                "workflow_run_id": str(workflow_run_id),
            },
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Create artifact via API (simulating CyFunctions.store_artifact)
        # Don't provide task_id since it doesn't exist in the database
        artifact_data = {
            "name": "Disposition",
            "content": "false_positive",
            "artifact_type": "disposition",
            "task_run_id": str(task_run_id),
            "workflow_run_id": str(workflow_run_id),  # Should be populated
            "tags": ["analysis", "disposition"],
        }

        response = await client.post(
            f"/v1/{tenant_id}/artifacts",
            json=artifact_data,
        )

        # Verify artifact was created
        assert response.status_code == 201
        artifact_response = response.json()["data"]
        artifact_id = artifact_response["id"]

        # Query artifact from database to verify workflow_run_id
        stmt = select(Artifact).where(Artifact.id == uuid.UUID(artifact_id))
        result = await integration_test_session.execute(stmt)
        artifact = result.scalar_one()

        assert artifact.workflow_run_id == workflow_run_id
        assert artifact.task_run_id == task_run_id
        # task_id column removed - now we use task_run_id only
        assert artifact.name == "Disposition"

    @pytest.mark.asyncio
    async def test_query_artifacts_by_workflow_run_id(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test querying artifacts by workflow_run_id."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid.uuid4()
        task_run_id = uuid.uuid4()

        # Create multiple artifacts for the same workflow run
        artifacts = []
        for i in range(3):
            artifact = Artifact(
                tenant_id=tenant_id,
                name=f"Artifact_{i}",
                inline_content=f"Content_{i}".encode(),  # inline_content is bytes
                storage_class="inline",
                artifact_type="test",
                mime_type="text/plain",
                task_run_id=task_run_id,
                workflow_run_id=workflow_run_id,
            )
            integration_test_session.add(artifact)
            artifacts.append(artifact)

        # Create an artifact for a different workflow
        other_artifact = Artifact(
            tenant_id=tenant_id,
            name="Other_Artifact",
            inline_content=b"Other_Content",  # inline_content is bytes
            storage_class="inline",
            artifact_type="test",
            mime_type="text/plain",
            workflow_run_id=uuid.uuid4(),  # Different workflow
        )
        integration_test_session.add(other_artifact)
        await integration_test_session.commit()

        # Query artifacts by workflow_run_id
        response = await client.get(
            f"/v1/{tenant_id}/artifacts",
            params={"workflow_run_id": str(workflow_run_id)},
        )

        assert response.status_code == 200
        result = response.json()

        # Should return only artifacts for the specified workflow
        assert len(result["data"]) == 3
        returned_names = {a["name"] for a in result["data"]}
        assert returned_names == {"Artifact_0", "Artifact_1", "Artifact_2"}
        assert "Other_Artifact" not in returned_names

    @pytest.mark.asyncio
    async def test_disposition_artifact_retrieval_in_final_step(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test that FinalDispositionUpdateStep can retrieve Disposition artifacts."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid.uuid4()
        alert_id = str(uuid.uuid4())
        str(uuid.uuid4())

        # Create Disposition artifact
        disposition_artifact = Artifact(
            tenant_id=tenant_id,
            name="Disposition",
            inline_content=b"false_positive",  # inline_content is bytes
            storage_class="inline",
            artifact_type="disposition",
            mime_type="text/plain",
            workflow_run_id=workflow_run_id,
        )
        integration_test_session.add(disposition_artifact)

        # Create Analysis Summary artifact
        summary_artifact = Artifact(
            tenant_id=tenant_id,
            name="Analysis Summary",
            inline_content=json.dumps(
                {
                    "alert_id": alert_id,
                    "severity": "low",
                    "analysis": "This appears to be a false positive based on...",
                }
            ).encode(),  # inline_content is bytes
            storage_class="inline",
            artifact_type="summary",
            mime_type="application/json",
            workflow_run_id=workflow_run_id,
        )
        integration_test_session.add(summary_artifact)
        await integration_test_session.commit()

        # Query artifacts by workflow_run_id (simulating what FinalDispositionUpdateStep does)
        response = await client.get(
            f"/v1/{tenant_id}/artifacts",
            params={"workflow_run_id": str(workflow_run_id)},
        )

        assert response.status_code == 200
        result = response.json()
        artifacts = result["data"]

        # Verify both artifacts are retrieved
        assert len(artifacts) == 2

        # Find Disposition artifact
        disposition = next((a for a in artifacts if a["name"] == "Disposition"), None)
        assert disposition is not None
        assert disposition["content"] == "false_positive"
        assert disposition["workflow_run_id"] == str(workflow_run_id)

        # Find Summary artifact
        summary = next((a for a in artifacts if a["name"] == "Analysis Summary"), None)
        assert summary is not None
        summary_content = json.loads(summary["content"])
        assert summary_content["alert_id"] == alert_id

    @pytest.mark.asyncio
    async def test_ad_hoc_task_without_workflow(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test that ad-hoc tasks (not part of workflow) create artifacts without workflow_run_id."""
        tenant_id = "test-tenant"
        task_run_id = uuid.uuid4()

        # Create a task run without workflow_run_id (ad-hoc execution)
        task_run = TaskRun(
            id=task_run_id,
            tenant_id=tenant_id,
            task_id=None,  # Ad-hoc
            workflow_run_id=None,  # No workflow
            cy_script="print('hello')",
            status="running",
            started_at=datetime.now(UTC),
            execution_context={
                "tenant_id": tenant_id,
                "task_run_id": str(task_run_id),
            },
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Create artifact without workflow_run_id
        artifact_data = {
            "name": "Ad-hoc Result",
            "content": "Ad-hoc execution output",
            "artifact_type": "output",
            "task_run_id": str(task_run_id),
            # No workflow_run_id
        }

        response = await client.post(
            f"/v1/{tenant_id}/artifacts",
            json=artifact_data,
        )

        # Verify artifact was created
        assert response.status_code == 201
        artifact_response = response.json()["data"]

        # Query artifact to verify no workflow_run_id
        artifact_id = artifact_response["id"]
        stmt = select(Artifact).where(Artifact.id == uuid.UUID(artifact_id))
        result = await integration_test_session.execute(stmt)
        artifact = result.scalar_one()

        assert artifact.workflow_run_id is None
        assert artifact.task_run_id == task_run_id
        assert artifact.name == "Ad-hoc Result"


@pytest.mark.integration
class TestWorkflowRunIdPropagation:
    """Test workflow_run_id propagation through the execution chain."""

    @pytest.mark.asyncio
    async def test_workflow_executor_passes_workflow_run_id_to_task(
        self, integration_test_session: AsyncSession
    ):
        """Verify WorkflowExecutor passes workflow_run_id when creating tasks."""
        from analysi.services.task_run import TaskRunService

        tenant_id = "test-tenant"
        workflow_run_id = uuid.uuid4()

        # Create task run via service with workflow_run_id
        # Using ad-hoc execution (no task_id) to avoid foreign key constraints
        service = TaskRunService()
        task_run = await service.create_execution(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=None,  # Ad-hoc execution
            cy_script="print('test')",  # Must provide script for ad-hoc
            input_data={"test": "data"},
            workflow_run_id=workflow_run_id,  # This is the key part we're testing
        )

        # Verify task_run has workflow_run_id
        assert task_run.workflow_run_id == workflow_run_id

        # Verify execution_context contains workflow_run_id
        assert task_run.execution_context["workflow_run_id"] == str(workflow_run_id)

        # Verify task_run is persisted correctly
        await integration_test_session.commit()

        # Query to verify persistence
        stmt = select(TaskRun).where(TaskRun.id == task_run.id)
        result = await integration_test_session.execute(stmt)
        persisted_task_run = result.scalar_one()

        assert persisted_task_run.workflow_run_id == workflow_run_id
        assert persisted_task_run.execution_context["workflow_run_id"] == str(
            workflow_run_id
        )
