"""
Integration tests for workflow execution storage integration.
Tests storage strategy (512KB threshold), inline vs MinIO storage, and retrieval.
All tests follow TDD principles and should FAIL initially since implementation isn't complete yet.
"""

import json
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowStorageStrategy:
    """Test storage strategy based on payload size (512KB threshold)."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.fixture
    def small_input_data(self) -> dict:
        """Create input data under 512KB for inline storage."""
        return {
            "alert": {
                "id": "alert_123",
                "type": "security",
                "severity": "high",
                "message": "Suspicious activity detected",
                "metadata": {
                    "source": "firewall",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "details": ["blocked connection", "repeated attempts"],
                },
            }
        }

    @pytest.fixture
    def large_input_data(self) -> dict:
        """Create input data over 512KB for MinIO storage."""
        # Create data that exceeds 512KB (524,288 bytes)
        large_list = []

        # Each item is roughly 100 bytes, so 6000 items ≈ 600KB
        for i in range(6000):
            large_list.append(
                {
                    "id": f"item_{i:04d}",
                    "data": f"This is test data item number {i} with some additional content to make it larger",
                    "metadata": {
                        "index": i,
                        "category": f"category_{i % 10}",
                        "timestamp": f"2024-01-01T{i % 24:02d}:00:00Z",
                    },
                }
            )

        return {
            "massive_dataset": large_list,
            "summary": f"Dataset with {len(large_list)} items",
        }

    @pytest.fixture
    async def sample_workflow_id(self, client: AsyncClient) -> str:
        """Create a sample workflow for storage testing."""
        # First create a template
        template_data = {
            "name": "storage_passthrough",
            "description": "Simple passthrough template for storage testing",
            "input_schema": {
                "type": "object",
                "properties": {"data": {"type": "object"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"result": {"type": "object"}},
            },
            "code": "return inp",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201, (
            f"Failed to create template: {template_response.text}"
        )
        template_id = template_response.json()["data"]["id"]

        workflow_data = {
            "name": "Storage Test Workflow",
            "description": "Tests storage strategy integration",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {"type": "object"}}},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            "data_samples": [{"data": {"test": "sample"}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-passthrough",
                    "kind": "transformation",
                    "name": "Passthrough Node",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"data": {"type": "object"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {"result": {"type": "object"}},
                        },
                    },
                }
            ],
            "edges": [],
        }

        response = await client.post("/v1/test_tenant/workflows", json=workflow_data)
        assert response.status_code == 201
        return response.json()["data"]["id"]

    @pytest.mark.asyncio
    async def test_small_workflow_input_inline(
        self, client: AsyncClient, sample_workflow_id: str, small_input_data: dict
    ):
        """Test <512KB input stored inline."""
        # Start workflow with small input
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run",
            json={"input_data": small_input_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Get workflow run details
        details_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}"
        )
        assert details_response.status_code == 200

        workflow_details = details_response.json()["data"]

        # Verify input was stored inline (when implementation is complete)
        # Should have input_data directly in response, not a storage reference
        assert "input_data" in workflow_details

        # In real implementation, would verify:
        # 1. input_type = "inline" in database
        # 2. input_location contains the actual JSON data
        # 3. No MinIO storage operation occurred
        # 4. Data can be retrieved directly from database

    @pytest.mark.asyncio
    async def test_large_workflow_input_minio(
        self, client: AsyncClient, sample_workflow_id: str, large_input_data: dict
    ):
        """Test ≥512KB input stored in MinIO."""
        # Verify the test data is actually large enough
        data_size = len(json.dumps(large_input_data).encode("utf-8"))
        assert data_size > 512 * 1024, (
            f"Test data is only {data_size} bytes, should be > 524288"
        )

        # Start workflow with large input
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run",
            json={"input_data": large_input_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Get workflow run details
        details_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}"
        )
        assert details_response.status_code == 200

        workflow_details = details_response.json()["data"]

        # Verify input was retrieved (implementation will handle storage transparently)
        assert "input_data" in workflow_details

        # In real implementation, would verify:
        # 1. input_type = "s3" in database
        # 2. input_location contains S3 path
        # 3. MinIO storage operation occurred
        # 4. Data can be retrieved from MinIO and returned to user

    @pytest.mark.asyncio
    async def test_small_workflow_output_inline(
        self, client: AsyncClient, sample_workflow_id: str, small_input_data: dict
    ):
        """Test <512KB output stored inline."""
        # Start workflow that will produce small output
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{sample_workflow_id}/run",
            json={"input_data": small_input_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # In real implementation, would:
        # 1. Wait for workflow completion
        # 2. Verify output_type = "inline" in database
        # 3. Verify output_location contains JSON data
        # 4. Verify output can be retrieved directly

        # For now, just verify the workflow was started
        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200

    @pytest.mark.asyncio
    async def test_large_workflow_output_minio(
        self, client: AsyncClient, sample_workflow_id: str
    ):
        """Test ≥512KB output stored in MinIO."""
        # First create a template for large output generation
        template_data = {
            "name": "large_output_generator",
            "description": "Template for generating large output data",
            "input_schema": {
                "type": "object",
                "properties": {"generate": {"type": "string"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"large_data": {"type": "array"}},
            },
            "code": "return {'large_data': ['item_' + str(i) for i in range(10000)]}",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201, (
            f"Failed to create template: {template_response.text}"
        )
        template_id = template_response.json()["data"]["id"]

        # Create workflow that will generate large output
        large_output_workflow = {
            "name": "Large Output Workflow",
            "description": "Generates output over 512KB",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"generate": {"type": "string"}},
                },
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            "data_samples": [{"generate": "sample"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-large-output",
                    "kind": "transformation",
                    "name": "Large Output Generator",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"generate": {"type": "string"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {"result": {"type": "object"}},
                        },
                    },
                }
            ],
            "edges": [],
        }

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=large_output_workflow
        )
        assert create_response.status_code == 201
        large_workflow_id = create_response.json()["data"]["id"]

        # Start workflow
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{large_workflow_id}/run",
            json={"input_data": {"generate": "large_data"}},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # In real implementation, would:
        # 1. Template would generate >512KB output
        # 2. System would store in MinIO automatically
        # 3. output_type = "s3" in database
        # 4. output_location contains S3 path
        # 5. API would retrieve from MinIO transparently

        status_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/status"
        )
        assert status_response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.integration
class TestNodeInstanceStorage:
    """Test storage integration for individual node instances."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    async def create_templates(self, client: AsyncClient) -> dict[str, str]:
        """Helper method to create templates for this test class."""
        templates = {}

        # Basic passthrough template
        basic_data = {
            "name": "basic_passthrough",
            "description": "Simple passthrough template",
            "input_schema": {
                "type": "object",
                "properties": {"data": {"type": "object"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"result": {"type": "object"}},
            },
            "code": "return inp",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=basic_data
        )
        assert response.status_code == 201
        templates["basic_passthrough"] = response.json()["data"]["id"]

        # Data producer template
        producer_data = {
            "name": "data_producer",
            "description": "Produces data for workflow testing",
            "input_schema": {
                "type": "object",
                "properties": {"data": {"type": "object"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "produced": {"type": "object"},
                    "timestamp": {"type": "string"},
                },
            },
            "code": "return {'produced': inp, 'timestamp': '2026-04-26'}",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=producer_data
        )
        assert response.status_code == 201
        templates["data_producer"] = response.json()["data"]["id"]

        # Data consumer template
        consumer_data = {
            "name": "data_consumer",
            "description": "Consumes data from previous nodes",
            "input_schema": {
                "type": "object",
                "properties": {"data": {"type": "object"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "consumed": {"type": "object"},
                    "result": {"type": "string"},
                },
            },
            "code": "return {'consumed': inp, 'result': 'processed'}",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=consumer_data
        )
        assert response.status_code == 201
        templates["data_consumer"] = response.json()["data"]["id"]

        return templates

    @pytest.mark.asyncio
    async def test_node_small_io_inline(self, client: AsyncClient):
        """Test node I/O under threshold."""
        # First create a template for small data processing
        template_data = {
            "name": "small_data_processor",
            "description": "Template for processing small data",
            "input_schema": {
                "type": "object",
                "properties": {"data": {"type": "object"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "processed": {"type": "object"},
                    "size": {"type": "string"},
                },
            },
            "code": "return {'processed': inp, 'size': 'small'}",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201, (
            f"Failed to create template: {template_response.text}"
        )
        template_id = template_response.json()["data"]["id"]

        # Create workflow with node that processes small data
        workflow_data = {
            "name": "Small Node I/O Workflow",
            "description": "Tests small node input/output storage",
            "io_schema": {
                "input": {"type": "object", "properties": {"data": {"type": "object"}}},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            "data_samples": [{"data": {"test": "sample"}}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-small-processor",
                    "kind": "transformation",
                    "is_start_node": True,
                    "name": "Small Data Processor",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"data": {"type": "object"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {"result": {"type": "object"}},
                        },
                    },
                }
            ],
            "edges": [],
        }

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Start execution with small data
        small_data = {"message": "small test data", "count": 100}
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": small_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Get node instances
        nodes_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200

        # In real implementation, would verify:
        # 1. Node input/output stored inline
        # 2. input_type/output_type = "inline" in database
        # 3. Data directly accessible in node instance records

    @pytest.mark.asyncio
    async def test_node_large_io_minio(self, client: AsyncClient):
        """Test node I/O over threshold."""
        # First create a template for large data processing
        template_data = {
            "name": "large_data_processor",
            "description": "Template for processing large data",
            "input_schema": {
                "type": "object",
                "properties": {"massive_array": {"type": "array"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "expanded_data": {"type": "array"},
                    "processed": {"type": "boolean"},
                },
            },
            "code": "return {'expanded_data': inp.get('massive_array', []) * 2, 'processed': True}",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }

        template_response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert template_response.status_code == 201, (
            f"Failed to create template: {template_response.text}"
        )
        template_id = template_response.json()["data"]["id"]

        # Create workflow with node that processes large data
        workflow_data = {
            "name": "Large Node I/O Workflow",
            "description": "Tests large node input/output storage",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"massive_array": {"type": "array"}},
                },
                "output": {
                    "type": "object",
                    "properties": {"expanded_data": {"type": "array"}},
                },
            },
            "data_samples": [{"massive_array": ["sample"]}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-large-processor",
                    "kind": "transformation",
                    "is_start_node": True,
                    "name": "Large Data Processor",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"massive_array": {"type": "array"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {"expanded_data": {"type": "array"}},
                        },
                    },
                }
            ],
            "edges": [],
        }

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Create large input data - make it definitely over 512KB (524,288 bytes)
        large_array = [
            f"item_{i:05d}_with_lots_of_data_to_exceed_threshold_padding_text_to_make_it_larger"
            for i in range(12000)
        ]
        large_data = {"massive_array": large_array}

        # Verify it's actually large
        data_size = len(json.dumps(large_data).encode("utf-8"))
        assert data_size > 512 * 1024, f"Data size {data_size} should be > {512 * 1024}"

        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": large_data},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Get node instances
        nodes_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/nodes"
        )
        assert nodes_response.status_code == 200

        # In real implementation, would verify:
        # 1. Node input/output stored in MinIO
        # 2. input_type/output_type = "s3" in database
        # 3. input_location/output_location contains S3 paths
        # 4. Data retrieved from MinIO when requested

    @pytest.mark.asyncio
    async def test_storage_retrieval_workflow(self, client: AsyncClient):
        """Test end-to-end storage/retrieval."""
        # Create templates
        templates = await self.create_templates(client)

        # Create multi-node workflow to test data flow through storage
        workflow_data = {
            "name": "Storage Retrieval Test",
            "description": "Tests data flow through storage system",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {
                    "type": "object",
                    "properties": {"consumed": {"type": "object"}},
                },
            },
            "data_samples": [{"test": "sample"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-producer",
                    "kind": "transformation",
                    "is_start_node": True,
                    "name": "Data Producer",
                    "node_template_id": templates["data_producer"],
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"test": {"type": "string"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {"result": {"type": "object"}},
                        },
                    },
                },
                {
                    "node_id": "n-consumer",
                    "kind": "transformation",
                    "name": "Data Consumer",
                    "node_template_id": templates["data_consumer"],
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"result": {"type": "object"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {"consumed": {"type": "object"}},
                        },
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "n-producer",
                    "to_node_id": "n-consumer",
                }
            ],
        }

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Start execution
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": {"test": "storage_flow"}},
        )

        assert start_response.status_code == 202
        workflow_run_id = start_response.json()["data"]["workflow_run_id"]

        # Monitor execution graph
        graph_response = await client.get(
            f"/v1/test_tenant/workflow-runs/{workflow_run_id}/graph"
        )
        assert graph_response.status_code == 200

        # In real implementation, would verify:
        # 1. Producer node stores output (inline or MinIO based on size)
        # 2. Consumer node retrieves producer output correctly
        # 3. Data integrity maintained through storage layer
        # 4. Appropriate storage type chosen based on data size

    @pytest.mark.asyncio
    async def test_storage_tenant_isolation(self, client: AsyncClient):
        """Test storage paths include tenant_id."""
        # Create templates for tenant-a and tenant-b (templates are tenant-scoped)
        basic_data = {
            "name": f"isolation_test_template_{uuid4().hex[:8]}",
            "description": "Template for tenant isolation testing",
            "input_schema": {
                "type": "object",
                "properties": {"tenant_isolation": {"type": "string"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"result": {"type": "object"}},
            },
            "code": "return inp",
            "language": "python",
            "type": "static",
            "enabled": True,
        }
        resp_a = await client.post(
            "/v1/tenant-a/workflows/node-templates", json=basic_data
        )
        assert resp_a.status_code == 201
        template_a_id = resp_a.json()["data"]["id"]

        resp_b = await client.post(
            "/v1/tenant-b/workflows/node-templates", json=basic_data
        )
        assert resp_b.status_code == 201
        template_b_id = resp_b.json()["data"]["id"]

        # Create workflows in different tenants (each uses its own tenant's template)
        def make_workflow_data(template_id: str) -> dict:
            return {
                "name": "Tenant Isolation Test",
                "description": "Tests storage tenant isolation",
                "io_schema": {
                    "input": {
                        "type": "object",
                        "properties": {"tenant_isolation": {"type": "string"}},
                    },
                    "output": {
                        "type": "object",
                        "properties": {"result": {"type": "object"}},
                    },
                },
                "data_samples": [{"tenant_isolation": "sample"}],
                "created_by": str(SYSTEM_USER_ID),
                "nodes": [
                    {
                        "node_id": "n-storage-test",
                        "kind": "transformation",
                        "is_start_node": True,
                        "name": "Storage Test Node",
                        "node_template_id": template_id,
                        "schemas": {
                            "input": {
                                "type": "object",
                                "properties": {"tenant_isolation": {"type": "string"}},
                            },
                            "output_result": {
                                "type": "object",
                                "properties": {"result": {"type": "object"}},
                            },
                        },
                    }
                ],
                "edges": [],
            }

        # Create workflow in tenant-a using tenant-a's template
        create_a = await client.post(
            "/v1/tenant-a/workflows", json=make_workflow_data(template_a_id)
        )
        assert create_a.status_code == 201
        workflow_a_id = create_a.json()["data"]["id"]

        # Create workflow in tenant-b using tenant-b's template
        create_b = await client.post(
            "/v1/tenant-b/workflows", json=make_workflow_data(template_b_id)
        )
        assert create_b.status_code == 201
        workflow_b_id = create_b.json()["data"]["id"]

        # Start executions with same data
        test_data = {"tenant_isolation": "test_data"}

        start_a = await client.post(
            f"/v1/tenant-a/workflows/{workflow_a_id}/run",
            json={"input_data": test_data},
        )
        assert start_a.status_code == 202

        start_b = await client.post(
            f"/v1/tenant-b/workflows/{workflow_b_id}/run",
            json={"input_data": test_data},
        )
        assert start_b.status_code == 202

        # In real implementation, would verify:
        # 1. Storage paths contain tenant ID (e.g., s3://bucket/tenant-a/...)
        # 2. Tenants cannot access each other's stored data
        # 3. MinIO paths are properly segregated by tenant
        # 4. Database records maintain tenant isolation


@pytest.mark.asyncio
@pytest.mark.integration
class TestStorageErrorHandling:
    """Test storage error handling and recovery."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    async def create_basic_template(self, client: AsyncClient) -> str:
        """Helper method to create a basic template."""
        template_data = {
            "name": "basic_passthrough",
            "description": "Simple passthrough template",
            "input_schema": {
                "type": "object",
                "properties": {"test": {"type": "string"}},
            },
            "output_schema": {
                "type": "object",
                "properties": {"result": {"type": "object"}},
            },
            "code": "return inp",
            "language": "python",
            "type": "static",
            "enabled": True,
            "revision_num": 1,
        }
        response = await client.post(
            "/v1/test_tenant/workflows/node-templates", json=template_data
        )
        assert response.status_code == 201
        return response.json()["data"]["id"]

    @pytest.mark.asyncio
    async def test_storage_failure_handling(self, client: AsyncClient):
        """Test storage operation failures."""
        # This test would simulate storage failures and verify graceful handling
        # For now, create a basic workflow to test the framework
        template_id = await self.create_basic_template(client)

        workflow_data = {
            "name": "Storage Failure Test",
            "description": "Tests storage failure scenarios",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            "data_samples": [{"test": "sample"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-storage-fail",
                    "kind": "transformation",
                    "is_start_node": True,
                    "name": "Storage Failure Node",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"test": {"type": "string"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {"result": {"type": "object"}},
                        },
                    },
                }
            ],
            "edges": [],
        }

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Start execution (in real implementation, would simulate storage failure)
        start_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/run",
            json={"input_data": {"test": "storage_failure"}},
        )

        assert start_response.status_code == 202

        # In real implementation, would:
        # 1. Simulate MinIO connection failure
        # 2. Verify workflow handles error gracefully
        # 3. Verify appropriate error messages
        # 4. Verify fallback behavior (if any)
        # 5. Test retry mechanisms

    @pytest.mark.asyncio
    async def test_storage_recovery_scenarios(self, client: AsyncClient):
        """Test recovery from storage issues."""
        # This would test scenarios like:
        # 1. Temporary storage unavailability
        # 2. Partial write failures
        # 3. Retrieval failures during execution

        # For now, basic framework test
        template_id = await self.create_basic_template(client)

        workflow_data = {
            "name": "Storage Recovery Test",
            "description": "Tests storage recovery scenarios",
            "io_schema": {
                "input": {"type": "object", "properties": {"test": {"type": "string"}}},
                "output": {
                    "type": "object",
                    "properties": {"result": {"type": "object"}},
                },
            },
            "data_samples": [{"test": "sample"}],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-recovery-test",
                    "kind": "transformation",
                    "is_start_node": True,
                    "name": "Recovery Test Node",
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"test": {"type": "string"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {"result": {"type": "object"}},
                        },
                    },
                }
            ],
            "edges": [],
        }

        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_data
        )
        assert create_response.status_code == 201

        # In real implementation, would test:
        # 1. Retry mechanisms for transient failures
        # 2. Circuit breaker patterns for persistent failures
        # 3. Graceful degradation options
        # 4. Error reporting and alerting
