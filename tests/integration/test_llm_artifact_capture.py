"""
Integration test for LLM artifact capture - verifies model name is captured.

Requires OPENAI_API_KEY — these tests make real LLM calls.
"""

import json
import os
import zlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("ANALYSI_LLM_INTEGRATION_TESTS"),
        reason="Requires tenant LLM integration setup — set ANALYSI_LLM_INTEGRATION_TESTS=1 to enable",
    ),
]

from analysi.models.component import Component  # noqa: E402
from analysi.models.task import Task  # noqa: E402
from analysi.models.task_run import TaskRun  # noqa: E402
from analysi.repositories.artifact_repository import ArtifactRepository  # noqa: E402
from analysi.services.task_execution import TaskExecutionService  # noqa: E402


@pytest.mark.asyncio
@pytest.mark.integration
class TestLLMArtifactCapture:
    """Test that LLM calls capture model name in artifacts."""

    @pytest.fixture
    async def setup_for_llm_test(self, integration_test_session: AsyncSession):
        """Create minimal setup for LLM tests (no OpenAI integration - uses env fallback)."""
        tenant_id = f"llm-test-{uuid4().hex[:8]}"
        component_id = uuid4()
        task_id = uuid4()

        # No OpenAI integration created - LangChainFactory will fall back to
        # OPENAI_API_KEY environment variable (see llm_factory.py lines 107-137)

        # Create Component for the Task
        component = Component(
            id=component_id,
            tenant_id=tenant_id,
            name="LLM Test Task Component",
            description="Component for LLM artifact capture test",
            categories=["test"],
            status="enabled",
            kind="task",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create Task record
        task = Task(
            id=task_id,
            component_id=component_id,
            function="processing",
            scope="processing",
            script="return {}",
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        return {
            "tenant_id": tenant_id,
            "task_id": component_id,  # TaskRun.task_id FK references task(component_id)
            "session": integration_test_session,
        }

    @pytest.mark.asyncio
    async def test_llm_run_captures_model_name(
        self, integration_test_session: AsyncSession, setup_for_llm_test
    ):
        """
        Test that llm_run() captures the model name in the artifact.

        This verifies the fix for the bug where model was always null.
        Requires OPENAI_API_KEY environment variable to be set.
        """
        tenant_id = setup_for_llm_test["tenant_id"]
        task_id = setup_for_llm_test["task_id"]

        # Simple Cy script that calls llm_run
        cy_script = """result = llm_run("Echo: Hi")
return {"response": result}
"""
        task_run_id = uuid4()

        # Create TaskRun
        task_run = TaskRun(
            id=task_run_id,
            task_id=task_id,
            tenant_id=tenant_id,
            cy_script=cy_script,
            status="running",
            input_type="inline",
            input_location=json.dumps({}),
            execution_context={},
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Execute the task using the new API (task_run_id, tenant_id)
        execution_service = TaskExecutionService()
        await execution_service.execute_single_task(task_run_id, tenant_id)

        # Query for LLM execution artifact
        artifact_repo = ArtifactRepository(integration_test_session)
        artifacts_list, _ = await artifact_repo.list(
            tenant_id,
            filters={
                "artifact_type": "llm_execution",
                "task_run_id": str(task_run_id),
            },
        )

        assert len(artifacts_list) > 0, (
            f"Expected at least one llm_execution artifact. "
            f"Found {len(artifacts_list)} artifacts."
        )

        artifact = artifacts_list[0]

        # Verify artifact fields
        assert artifact.artifact_type == "llm_execution"
        assert artifact.source == "auto_capture"
        assert artifact.name == "llm_run"

        # Parse content and verify model is captured
        content = json.loads(zlib.decompress(artifact.inline_content).decode("utf-8"))

        assert "model" in content, f"Artifact content missing 'model': {content}"
        assert content["model"] is not None, (
            f"Model should not be null. Content: {content}"
        )
        assert len(content["model"]) > 0, (
            f"Model should not be empty. Content: {content}"
        )

        # Model should be something like "gpt-4o", "gpt-4-turbo-preview", etc.
        assert "gpt" in content["model"].lower() or "o1" in content["model"].lower(), (
            f"Expected OpenAI model name, got: {content['model']}"
        )

        # Verify other expected fields
        assert "prompt" in content
        assert "completion" in content
        assert "duration_ms" in content
        assert content["prompt"] == "Echo: Hi"
