"""
Integration tests for system_merge smart template with conflict detection.

Tests extensive corner cases for the new smart merge logic that:
1. Tracks field-level modifications vs inherited values
2. Detects conflicts when multiple branches modify the same field
3. Produces deterministic output regardless of execution order
"""

from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]

DEFAULT_TENANT = "test_tenant"


@pytest.mark.asyncio
@pytest.mark.integration
class TestSystemMergeSmartTemplate:
    """Test smart merge template with comprehensive corner cases."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, integration_test_session

        app.dependency_overrides.clear()

    async def create_template(
        self,
        client: AsyncClient,
        name: str,
        code: str,
        input_schema: dict,
        output_schema: dict,
        description: str = None,
    ) -> str:
        """Helper to create a transformation template."""
        template_data = {
            "name": name,
            "description": description or name,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "code": code,
            "language": "python",
            "type": "static",
        }
        response = await client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201, (
            f"Failed to create template: {response.text}"
        )
        return response.json()["data"]["id"]

    async def create_and_execute_merge_workflow(
        self,
        client: AsyncClient,
        session,
        base_value: dict,
        branch_a_code: str,
        branch_b_code: str,
    ) -> dict:
        """
        Helper to create and execute a workflow with merge pattern: base → [A, B] → merge.

        Args:
            client: HTTP client
            session: Database session
            base_value: Initial input value
            branch_a_code: Python code for branch A transformation
            branch_b_code: Python code for branch B transformation

        Returns:
            Workflow execution result
        """
        http_client, db_session = client

        # Create identity template for base node
        identity_template_id = await self.create_template(
            http_client,
            "identity_for_merge",
            "return inp",
            {"type": "object"},
            {"type": "object"},
            "Pass through input unchanged",
        )

        # Create branch A template
        branch_a_template_id = await self.create_template(
            http_client,
            "branch_a",
            branch_a_code,
            {"type": "object"},
            {"type": "object"},
            "Branch A transformation",
        )

        # Create branch B template
        branch_b_template_id = await self.create_template(
            http_client,
            "branch_b",
            branch_b_code,
            {"type": "object"},
            {"type": "object"},
            "Branch B transformation",
        )

        # Get system_merge template ID
        templates_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflows/node-templates"
        )
        assert templates_response.status_code == 200
        templates = templates_response.json()["data"]
        merge_template = next(
            (t for t in templates if t["name"] == "system_merge"), None
        )
        assert merge_template is not None, "system_merge template not found"
        merge_template_id = merge_template["id"]

        # Create workflow: base → [A, B] → merge
        workflow_data = {
            "name": "Smart Merge Test Workflow",
            "description": "Test smart merge with field-level conflict detection",
            "is_dynamic": False,
            "data_samples": [{"input": base_value}],
            "created_by": str(SYSTEM_USER_ID),
            "io_schema": {
                "input": {"type": "object", "properties": {"base": {"type": "object"}}},
                "output": {"type": "object"},
            },
            "nodes": [
                {
                    "node_id": "base",
                    "kind": "transformation",
                    "name": "Base",
                    "is_start_node": True,
                    "node_template_id": identity_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "branch_a",
                    "kind": "transformation",
                    "name": "Branch A",
                    "node_template_id": branch_a_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "branch_b",
                    "kind": "transformation",
                    "name": "Branch B",
                    "node_template_id": branch_b_template_id,
                    "schemas": {
                        "input": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "merge",
                    "kind": "transformation",
                    "name": "Merge",
                    "node_template_id": merge_template_id,
                    "schemas": {
                        "input": {"type": "array"},
                        "output_result": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {"edge_id": "e1", "from_node_id": "base", "to_node_id": "branch_a"},
                {"edge_id": "e2", "from_node_id": "base", "to_node_id": "branch_b"},
                {"edge_id": "e3", "from_node_id": "branch_a", "to_node_id": "merge"},
                {"edge_id": "e4", "from_node_id": "branch_b", "to_node_id": "merge"},
            ],
        }

        # Create workflow
        create_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows", json=workflow_data
        )
        assert create_response.status_code == 201, (
            f"Failed to create workflow: {create_response.text}"
        )
        workflow_id = create_response.json()["data"]["id"]

        # Commit test data
        await db_session.commit()

        # Execute workflow
        start_response = await http_client.post(
            f"/v1/{DEFAULT_TENANT}/workflows/{workflow_id}/run",
            json={"input_data": base_value},
        )
        assert start_response.status_code == 202, (
            f"Failed to start workflow: {start_response.text}"
        )
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Manually trigger execution
        from analysi.services.workflow_execution import WorkflowExecutor

        executor = WorkflowExecutor(db_session)
        await executor.monitor_execution(UUID(workflow_run_id))
        await db_session.commit()

        # Get result
        details_response = await http_client.get(
            f"/v1/{DEFAULT_TENANT}/workflow-runs/{workflow_run_id}"
        )
        assert details_response.status_code == 200
        return details_response.json()["data"]

    # ==================== SUCCESS CASES ====================

    @pytest.mark.asyncio
    async def test_merge_both_branches_add_different_fields(self, client):
        """
        Test: Base {a:1}, Branch A adds b, Branch B adds c
        Expected: {a:1, b:2, c:3}
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": 1},
            branch_a_code="result = inp.copy(); result['b'] = 2; return result",
            branch_b_code="result = inp.copy(); result['c'] = 3; return result",
        )

        assert result["status"] == "completed"
        # Check merge node output
        # TODO: Extract actual result from workflow run details

    @pytest.mark.asyncio
    async def test_merge_one_branch_modifies_one_adds(self, client):
        """
        Test: Base {a:1}, Branch A modifies a, Branch B adds b
        Expected: CONFLICT (branches have different values for 'a')
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": 1},
            branch_a_code="return {'a': 2}",  # Modifies a
            branch_b_code="result = inp.copy(); result['b'] = 3; return result",  # Adds b, keeps a:1
        )

        # Should fail with conflict error
        assert result["status"] in ["failed", "error"]

    @pytest.mark.asyncio
    async def test_merge_one_branch_inactive_other_modifies(self, client):
        """
        Test: Base {a:1}, Branch A keeps unchanged, Branch B modifies a
        Expected: CONFLICT (branches have different values for 'a')
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": 1},
            branch_a_code="return inp",  # Pass through a:1
            branch_b_code="return {'a': 2}",  # Modifies a to 2
        )

        # Should fail with conflict error
        assert result["status"] in ["failed", "error"]

    @pytest.mark.asyncio
    async def test_merge_empty_base(self, client):
        """
        Test: Base {}, Branch A adds a, Branch B adds b
        Expected: {a:1, b:2}
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={},
            branch_a_code="return {'a': 1}",
            branch_b_code="return {'b': 2}",
        )

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_merge_nested_objects(self, client):
        """
        Test: Base {x: {y: 1}}, Branch A modifies nested, Branch B adds top-level
        Expected: CONFLICT (Branch A changes 'x', Branch B keeps original 'x')
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"x": {"y": 1}},
            branch_a_code="return {'x': {'y': 2}}",  # Modifies nested object
            branch_b_code="result = inp.copy(); result['z'] = 3; return result",  # Adds z, keeps x
        )

        # Should fail with conflict error
        assert result["status"] in ["failed", "error"]

    @pytest.mark.asyncio
    async def test_merge_with_arrays(self, client):
        """
        Test: Base {arr: [1]}, Branch A modifies array, Branch B adds field
        Expected: CONFLICT (Branch A changes 'arr', Branch B keeps original 'arr')
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"arr": [1]},
            branch_a_code="result = inp.copy(); result['arr'] = inp['arr'] + [2]; return result",
            branch_b_code="result = inp.copy(); result['b'] = 3; return result",
        )

        # Should fail with conflict error
        assert result["status"] in ["failed", "error"]

    @pytest.mark.asyncio
    async def test_merge_with_null_values(self, client):
        """
        Test: Base {a: null}, Branch A sets a to value, Branch B adds b
        Expected: CONFLICT (Branch A changes 'a' to 1, Branch B keeps 'a' as null)
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": None},
            branch_a_code="return {'a': 1}",  # Changes null to 1
            branch_b_code="result = inp.copy(); result['b'] = 2; return result",
        )

        # Should fail with conflict error
        assert result["status"] in ["failed", "error"]

    @pytest.mark.asyncio
    async def test_merge_with_boolean_fields(self, client):
        """
        Test: Base {enabled: False}, Branch A flips boolean, Branch B adds field
        Expected: CONFLICT (Branch A changes 'enabled' to True, Branch B keeps 'enabled' as False)
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"enabled": False},
            branch_a_code="return {'enabled': True}",
            branch_b_code="result = inp.copy(); result['status'] = 'active'; return result",
        )

        # Should fail with conflict error
        assert result["status"] in ["failed", "error"]

    @pytest.mark.asyncio
    async def test_merge_large_object(self, client):
        """
        Test: Base with 10 fields, Branch A modifies 2, Branch B modifies 3 different ones
        Expected: CONFLICT (Both branches change fields to different values than base)
        """
        base = {f"field_{i}": i for i in range(10)}

        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value=base,
            branch_a_code="result = inp.copy(); result['field_0'] = 100; result['field_1'] = 101; return result",
            branch_b_code="result = inp.copy(); result['field_5'] = 500; result['field_6'] = 600; result['field_7'] = 700; return result",
        )

        # Should fail with conflict error (branches have different values for multiple fields)
        assert result["status"] in ["failed", "error"]

    # ==================== CONFLICT CASES (SHOULD ERROR) ====================

    @pytest.mark.asyncio
    async def test_merge_conflict_both_modify_same_field(self, client):
        """
        Test: Base {a:1}, Branch A modifies a to 2, Branch B modifies a to 3
        Expected: ERROR - conflict detected
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": 1},
            branch_a_code="return {'a': 2}",
            branch_b_code="return {'a': 3}",
        )

        # Should fail with conflict error
        assert result["status"] in ["failed", "error"]
        # TODO: Verify error message mentions "conflict"

    @pytest.mark.asyncio
    async def test_merge_conflict_multiple_fields(self, client):
        """
        Test: Both branches modify different subset of same fields
        Expected: ERROR - conflict on overlapping fields
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": 1, "b": 2, "c": 3},
            branch_a_code="return {'a': 10, 'b': 20, 'd': 4}",  # Modifies a,b, adds d
            branch_b_code="return {'b': 30, 'c': 40, 'e': 5}",  # Modifies b,c, adds e
        )

        # Should fail - both modify 'b'
        assert result["status"] in ["failed", "error"]

    # ==================== EDGE CASES ====================

    @pytest.mark.asyncio
    async def test_merge_one_branch_empty_dict(self, client):
        """
        Test: Base {a:1}, Branch A returns {}, Branch B adds b
        Expected: {a:1, b:2} (empty dict from A means no modifications)
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": 1},
            branch_a_code="return {}",  # Clears all fields - is this a modification?
            branch_b_code="result = inp.copy(); result['b'] = 2; return result",
        )

        # This is ambiguous: is {} a modification or "no changes"?
        # Current implementation: {} is a modification (clears fields)
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_merge_both_branches_no_changes(self, client):
        """
        Test: Base {a:1}, Both branches pass through unchanged
        Expected: {a:1}
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": 1},
            branch_a_code="return inp",
            branch_b_code="return inp",
        )

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_merge_one_branch_deletes_field(self, client):
        """
        Test: Base {a:1, b:2}, Branch A deletes b, Branch B adds c
        Expected: {a:1, c:3} (deletion is a modification)
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": 1, "b": 2},
            branch_a_code="return {'a': inp['a']}",  # Omits b (deletion)
            branch_b_code="result = inp.copy(); result['c'] = 3; return result",
        )

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_merge_string_to_number_type_change(self, client):
        """
        Test: Base {a: "1"}, Branch A changes type to number, Branch B adds field
        Expected: CONFLICT (Branch A changes 'a' to 1, Branch B keeps 'a' as "1")
        """
        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value={"a": "1"},
            branch_a_code="return {'a': 1}",  # Type change string → number
            branch_b_code="result = inp.copy(); result['b'] = 2; return result",
        )

        # Should fail with conflict error (type change means different values)
        assert result["status"] in ["failed", "error"]

    @pytest.mark.asyncio
    async def test_merge_very_deep_nesting(self, client):
        """
        Test: Deeply nested object modifications
        Expected: CONFLICT (Branch A changes nested 'level1' structure, Branch B keeps original)
        """
        base = {"level1": {"level2": {"level3": {"value": 1}}}}

        result = await self.create_and_execute_merge_workflow(
            client,
            client[1],
            base_value=base,
            branch_a_code="return {'level1': {'level2': {'level3': {'value': 2}}}}",
            branch_b_code="result = inp.copy(); result['other'] = 'data'; return result",
        )

        # Should fail with conflict error (different values for 'level1' field)
        assert result["status"] in ["failed", "error"]
