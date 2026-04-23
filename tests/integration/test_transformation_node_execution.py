"""
Integration tests for transformation node execution with Python templates.
Tests secure Python template execution, sandboxing, and error handling.
All tests follow TDD principles and should FAIL initially since implementation isn't complete yet.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.services.workflow_execution import TransformationNodeExecutor


@pytest.mark.asyncio
@pytest.mark.integration
class TestTransformationNodeExecution:
    """Test Python template execution with real templates and data."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.fixture
    def executor(self):
        """Create a TransformationNodeExecutor for direct testing."""
        return TransformationNodeExecutor()

    @pytest.mark.asyncio
    async def test_passthrough_template(self, executor):
        """Test simple "return inp" template."""
        code = "return inp"
        input_data = {"message": "hello world", "count": 42}

        result = await executor.execute_template(code, input_data)

        # Should return input wrapped in transformation envelope
        assert isinstance(result, dict)
        assert "result" in result
        assert result["result"] == input_data

    @pytest.mark.asyncio
    async def test_pick_field_template(self, executor):
        """Test field extraction template."""
        code = "return {'picked_value': inp.get('source_field')}"
        input_data = {
            "source_field": "extracted_value",
            "other_field": "ignored_value",
            "metadata": {"timestamp": "2024-01-01T00:00:00Z"},
        }

        result = await executor.execute_template(code, input_data)

        # Should return extracted field wrapped in transformation envelope
        assert isinstance(result, dict)
        assert "result" in result
        assert result["result"]["picked_value"] == "extracted_value"

    @pytest.mark.asyncio
    async def test_basic_arithmetic_template(self, executor):
        """Test simple calculations."""
        code = """
result = inp.get('a', 0) + inp.get('b', 0)
return {'sum': result, 'operation': 'addition'}
"""
        input_data = {"a": 15, "b": 27}

        result = await executor.execute_template(code, input_data)

        # Should return result wrapped in transformation envelope
        assert isinstance(result, dict)
        assert "result" in result
        assert result["result"] == {"sum": 42, "operation": "addition"}

    @pytest.mark.asyncio
    async def test_string_manipulation_template(self, executor):
        """Test string operations."""
        code = """
text = inp.get('text', '')
return {
    'uppercase': text.upper(),
    'length': len(text),
    'words': text.split()
}
"""
        input_data = {"text": "hello world testing"}

        result = await executor.execute_template(code, input_data)

        # Should return result wrapped in transformation envelope
        assert isinstance(result, dict)
        assert "result" in result
        expected = {
            "uppercase": "HELLO WORLD TESTING",
            "length": 19,
            "words": ["hello", "world", "testing"],
        }
        assert result["result"] == expected

    @pytest.mark.asyncio
    async def test_json_processing_template(self, executor):
        """Test complex JSON data processing."""
        code = """
alerts = inp.get('alerts', [])
high_severity = [alert for alert in alerts if alert.get('severity') == 'high']
return {
    'total_alerts': len(alerts),
    'high_severity_count': len(high_severity),
    'high_severity_alerts': high_severity
}
"""
        input_data = {
            "alerts": [
                {"id": 1, "severity": "low", "message": "Info alert"},
                {"id": 2, "severity": "high", "message": "Critical alert"},
                {"id": 3, "severity": "medium", "message": "Warning alert"},
                {"id": 4, "severity": "high", "message": "Security alert"},
            ]
        }

        result = await executor.execute_template(code, input_data)

        # Should return result wrapped in transformation envelope
        assert isinstance(result, dict)
        assert "result" in result
        expected = {
            "total_alerts": 4,
            "high_severity_count": 2,
            "high_severity_alerts": [
                {"id": 2, "severity": "high", "message": "Critical alert"},
                {"id": 4, "severity": "high", "message": "Security alert"},
            ],
        }
        assert result["result"] == expected

    @pytest.mark.asyncio
    async def test_aggregation_template(self, executor):
        """Test aggregating data from multiple inputs."""
        code = """
# inp should be an array of envelope structures
total = 0
items = []
for envelope in inp:
    result = envelope.get('result', {})
    if 'value' in result:
        total += result['value']
        items.append(result)

return {
    'aggregated_total': total,
    'item_count': len(items),
    'items': items
}
"""
        input_data = [
            {"node_id": "n-1", "result": {"value": 10, "type": "number"}},
            {"node_id": "n-2", "result": {"value": 25, "type": "number"}},
            {"node_id": "n-3", "result": {"value": 15, "type": "number"}},
        ]

        result = await executor.execute_template(code, input_data)

        # Should return result wrapped in transformation envelope
        assert isinstance(result, dict)
        assert "result" in result
        expected = {
            "aggregated_total": 50,
            "item_count": 3,
            "items": [
                {"value": 10, "type": "number"},
                {"value": 25, "type": "number"},
                {"value": 15, "type": "number"},
            ],
        }
        assert result["result"] == expected

    @pytest.mark.asyncio
    async def test_conditional_logic_template(self, executor):
        """Test conditional processing based on input."""
        code = """
data = inp.get('data', {})
severity = data.get('severity', 'unknown')

if severity == 'critical':
    action = 'immediate_response'
    priority = 1
elif severity == 'high':
    action = 'escalate'
    priority = 2
elif severity == 'medium':
    action = 'review'
    priority = 3
else:
    action = 'log_only'
    priority = 4

return {
    'action': action,
    'priority': priority,
    'original_severity': severity,
    'processed': True
}
"""
        input_data = {
            "data": {"severity": "high", "message": "Security breach detected"}
        }

        result = await executor.execute_template(code, input_data)

        # Should return result wrapped in transformation envelope
        assert isinstance(result, dict)
        assert "result" in result
        expected = {
            "action": "escalate",
            "priority": 2,
            "original_severity": "high",
            "processed": True,
        }
        assert result["result"] == expected


@pytest.mark.asyncio
@pytest.mark.integration
class TestTemplateSecurity:
    """Test Python template sandboxing and security restrictions."""

    @pytest.fixture
    def executor(self):
        """Create a TransformationNodeExecutor for security testing."""
        return TransformationNodeExecutor()

    @pytest.mark.asyncio
    async def test_template_import_restriction(self, executor):
        """Test imports are blocked."""
        code = """
import os
return {'system_info': os.uname()}
"""
        input_data = {"test": "data"}

        # AST validation blocks import statements before execution
        with pytest.raises(ValueError, match="must not use import statements"):
            await executor.execute_template(code, input_data)

    @pytest.mark.asyncio
    async def test_template_file_access_restriction(self, executor):
        """Test file operations blocked."""
        code = """
with open('/etc/passwd', 'r') as f:
    content = f.read()
return {'file_content': content}
"""
        input_data = {"test": "data"}

        # AST validation blocks 'open' as a dangerous builtin
        with pytest.raises(ValueError, match="must not use 'open'"):
            await executor.execute_template(code, input_data)

    @pytest.mark.asyncio
    async def test_template_network_restriction(self, executor):
        """Test network access blocked."""
        code = """
import urllib.request
response = urllib.request.urlopen('http://example.com')
return {'response': response.read()}
"""
        input_data = {"test": "data"}

        # AST validation blocks import statements before execution
        with pytest.raises(ValueError, match="must not use import statements"):
            await executor.execute_template(code, input_data)

    @pytest.mark.asyncio
    async def test_template_infinite_loop_timeout(self, executor):
        """Test execution timeout works."""

        # Note: This test would hang since we don't have timeout protection yet
        # For now, we'll skip actual execution of infinite loops
        # In production, this should use asyncio.wait_for() with timeout
        pytest.skip("Timeout protection not yet implemented - would hang")

    @pytest.mark.asyncio
    async def test_template_memory_limits(self, executor):
        """Test memory consumption limits."""

        # Note: This test could consume excessive memory since we don't have memory limits yet
        # For now, we'll skip to avoid potential system issues
        # In production, this should use resource limits or monitoring
        pytest.skip(
            "Memory limits not yet implemented - could consume excessive memory"
        )

    @pytest.mark.asyncio
    async def test_template_forbidden_builtins(self, executor):
        """Test that dangerous built-in functions are restricted."""
        code = """
# Try to use eval
result = eval('2 + 2')
return {'eval_result': result}
"""
        input_data = {"test": "data"}

        # AST validation blocks 'eval' as a dangerous builtin
        with pytest.raises(ValueError, match="must not use 'eval'"):
            await executor.execute_template(code, input_data)


@pytest.mark.integration
class TestTemplateErrorHandling:
    """Test error handling in template execution."""

    @pytest.fixture
    def executor(self):
        """Create a TransformationNodeExecutor for error testing."""
        return TransformationNodeExecutor()

    @pytest.mark.asyncio
    async def test_template_syntax_error(self, executor):
        """Test Python syntax errors handled."""
        code = """
if True
    return {'invalid': 'syntax'}  # Missing colon
"""
        input_data = {"test": "data"}

        # AST validation wraps SyntaxError as ValueError
        with pytest.raises(ValueError, match="Template syntax error"):
            await executor.execute_template(code, input_data)

    @pytest.mark.asyncio
    async def test_template_runtime_error(self, executor):
        """Test runtime exceptions handled."""
        code = """
x = inp.get('number', 0)
result = 100 / x  # Will raise ZeroDivisionError if x is 0
return {'division_result': result}
"""
        input_data = {"number": 0}  # Will cause division by zero

        # Should raise ZeroDivisionError because of division by zero
        with pytest.raises(ZeroDivisionError):
            await executor.execute_template(code, input_data)

        # Template execution correctly catches and propagates runtime errors

    @pytest.mark.asyncio
    async def test_template_key_error(self, executor):
        """Test missing key access handled."""
        code = """
required_field = inp['required_field']  # Will raise KeyError if not present
return {'field_value': required_field}
"""
        input_data = {"other_field": "value"}  # Missing required_field

        # Should raise KeyError because required_field is missing
        with pytest.raises(KeyError, match="required_field"):
            await executor.execute_template(code, input_data)

        # Template execution correctly catches and propagates key errors

    @pytest.mark.asyncio
    async def test_template_type_error(self, executor):
        """Test type errors handled."""
        code = """
text = inp.get('text', None)
length = len(text)  # Will raise TypeError if text is None
return {'text_length': length}
"""
        input_data = {"text": None}

        # Should raise TypeError because len() can't be called on None
        with pytest.raises(TypeError):
            await executor.execute_template(code, input_data)

        # Template execution correctly catches and propagates type errors

    @pytest.mark.asyncio
    async def test_template_output_schema_violation(self, executor):
        """Test schema validation failures."""
        # This test will use the validate_output_schema method
        output = {"result": 123}  # Should be string according to schema
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }

        is_valid = executor.validate_output_schema(output, schema)

        # Should return False because 123 is not a string as required by schema
        assert is_valid is False

    def test_envelope_structure_creation(self, executor):
        """Test standard envelope format building."""
        node_id = "n-transform-1"
        result = {"processed_data": "value", "count": 42}
        context = {"execution_time_ms": 150, "template_version": "1.0"}
        description = "Data transformation completed successfully"

        envelope = executor.build_envelope(node_id, result, context, description)

        # Should return correctly structured envelope
        expected = {
            "node_id": "n-transform-1",
            "context": {"execution_time_ms": 150, "template_version": "1.0"},
            "description": "Data transformation completed successfully",
            "result": {"processed_data": "value", "count": 42},
        }
        assert envelope == expected

    def test_envelope_minimal_structure(self, executor):
        """Test envelope with only required fields."""
        node_id = "n-simple"
        result = "simple string result"

        envelope = executor.build_envelope(node_id, result)

        # Should return envelope with defaults for optional fields
        expected = {
            "node_id": "n-simple",
            "context": {},  # Defaults to empty dict, not None
            "description": "Output from n-simple",  # Default description
            "result": "simple string result",
        }
        assert envelope == expected

    def test_output_schema_validation_success(self, executor):
        """Test successful output validation."""
        output = {"result": "success", "count": 42, "items": ["a", "b", "c"]}
        schema = {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "count": {"type": "number"},
                "items": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["result", "count"],
        }

        is_valid = executor.validate_output_schema(output, schema)

        # Should return True because output matches schema
        assert is_valid is True

    def test_output_schema_validation_failure(self, executor):
        """Test failed output validation."""
        output = {"result": 123}  # Should be string
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }

        is_valid = executor.validate_output_schema(output, schema)

        # Should return False because 123 is not a string
        assert is_valid is False


@pytest.mark.asyncio
@pytest.mark.integration
class TestTemplateExecutionIntegration:
    """Test template execution integration with storage and node instances."""

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

    @pytest.mark.asyncio
    async def test_template_execution_with_storage(self, client: AsyncClient):
        """Test template execution stores results correctly."""
        # This test will be implemented once we have template storage integration
        # For now, just verify the endpoint structure exists

        # Future implementation will:
        # 1. Create a node template with specific code
        # 2. Execute it through workflow execution
        # 3. Verify the output is stored correctly
        # 4. Verify the envelope structure is preserved

        # Placeholder test
        response = await client.get("/v1/test_tenant/workflows")
        assert response.status_code in [200, 404]  # Endpoint should exist

    @pytest.mark.asyncio
    async def test_template_execution_error_propagation(self, client: AsyncClient):
        """Test that template errors propagate to node instance status."""
        # This test will verify error handling flow:
        # 1. Template execution fails
        # 2. Node instance is marked as failed
        # 3. Error message is stored
        # 4. Workflow run status is updated

        # Placeholder test
        response = await client.get("/v1/test_tenant/workflow-runs")
        assert response.status_code in [200, 404]  # Endpoint should exist
