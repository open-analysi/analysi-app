"""
Test TransformationNodeExecutor in complete isolation.
Verifies the core template execution logic works without any workflow context.
"""

import pytest

from analysi.services.workflow_execution import TransformationNodeExecutor


@pytest.mark.integration
class TestTransformationExecutorIsolated:
    """Test TransformationNodeExecutor without workflow context."""

    @pytest.fixture
    def executor(self):
        """Create a TransformationNodeExecutor for testing."""
        return TransformationNodeExecutor()

    @pytest.mark.asyncio
    async def test_simple_passthrough_execution(self, executor):
        """Test basic passthrough template execution."""

        code = "return inp"
        input_data = {"message": "hello", "value": 42}

        result = await executor.execute_template(code, input_data)

        # Should return wrapped in envelope
        assert isinstance(result, dict)
        assert "result" in result
        assert result["result"] == input_data
        print(f"✅ Passthrough execution: {input_data} → {result['result']}")

    @pytest.mark.asyncio
    async def test_simple_transformation_execution(self, executor):
        """Test basic mathematical transformation."""

        code = "return {'result': inp.get('value', 0) + 10}"
        input_data = {"value": 15}

        result = await executor.execute_template(code, input_data)

        # Should return wrapped in envelope
        assert isinstance(result, dict)
        assert "result" in result
        assert result["result"]["result"] == 25  # 15 + 10
        print(f"✅ Math transformation: {input_data} → {result['result']}")

    @pytest.mark.asyncio
    async def test_string_transformation_execution(self, executor):
        """Test string manipulation."""

        code = """
text = inp.get('text', '')
return {
    'uppercase': text.upper(),
    'length': len(text),
    'reversed': text[::-1]
}
"""
        input_data = {"text": "hello"}

        result = await executor.execute_template(code, input_data)

        # Should return wrapped in envelope
        assert isinstance(result, dict)
        assert "result" in result

        output = result["result"]
        assert output["uppercase"] == "HELLO"
        assert output["length"] == 5
        assert output["reversed"] == "olleh"
        print(f"✅ String transformation: {input_data} → {output}")

    @pytest.mark.asyncio
    async def test_complex_data_processing(self, executor):
        """Test processing complex nested data."""

        code = """
alerts = inp.get('alerts', [])
high_severity = [alert for alert in alerts if alert.get('severity') == 'high']
return {
    'total_count': len(alerts),
    'high_severity_count': len(high_severity),
    'high_severity_alerts': high_severity
}
"""
        input_data = {
            "alerts": [
                {"id": 1, "severity": "low", "message": "Info"},
                {"id": 2, "severity": "high", "message": "Critical"},
                {"id": 3, "severity": "medium", "message": "Warning"},
                {"id": 4, "severity": "high", "message": "Security"},
            ]
        }

        result = await executor.execute_template(code, input_data)

        assert isinstance(result, dict)
        assert "result" in result

        output = result["result"]
        assert output["total_count"] == 4
        assert output["high_severity_count"] == 2
        assert len(output["high_severity_alerts"]) == 2
        print(
            f"✅ Complex data processing: {len(input_data['alerts'])} alerts → {output['high_severity_count']} high severity"
        )

    @pytest.mark.asyncio
    async def test_envelope_structure(self, executor):
        """Test that envelope structure is correctly created."""

        code = "return {'test': 'value'}"
        input_data = {"input": "data"}

        result = await executor.execute_template(code, input_data)

        # Check envelope structure
        assert isinstance(result, dict)
        assert "node_id" in result
        assert "context" in result
        assert "description" in result
        assert "result" in result

        assert result["node_id"] == "transformation"
        assert isinstance(result["context"], dict)
        assert isinstance(result["description"], str)
        assert result["result"]["test"] == "value"
        print(f"✅ Envelope structure: {list(result.keys())}")

    @pytest.mark.asyncio
    async def test_error_handling_execution(self, executor):
        """Test that execution errors are properly handled."""

        # Test division by zero
        code = "return {'result': 10 / 0}"
        input_data = {"test": "data"}

        with pytest.raises(ZeroDivisionError):
            await executor.execute_template(code, input_data)

        print("✅ Error handling: Division by zero properly raises exception")

    @pytest.mark.asyncio
    async def test_syntax_error_handling(self, executor):
        """Test that syntax errors are properly handled."""

        # Invalid Python syntax
        code = "if True return {'invalid': 'syntax'}"  # Missing colon
        input_data = {"test": "data"}

        # AST validation wraps SyntaxError as ValueError
        with pytest.raises(ValueError, match="Template syntax error"):
            await executor.execute_template(code, input_data)

        print("✅ Syntax error handling: Invalid syntax properly raises exception")

    def test_schema_validation_success(self, executor):
        """Test successful schema validation."""

        output = {"name": "test", "value": 42}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "value": {"type": "number"}},
            "required": ["name", "value"],
        }

        is_valid = executor.validate_output_schema(output, schema)
        assert is_valid is True
        print("✅ Schema validation success")

    def test_schema_validation_failure(self, executor):
        """Test failed schema validation."""

        output = {"name": 123, "value": "not_a_number"}  # Wrong types
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "value": {"type": "number"}},
            "required": ["name", "value"],
        }

        is_valid = executor.validate_output_schema(output, schema)
        assert is_valid is False
        print("✅ Schema validation failure detected correctly")
