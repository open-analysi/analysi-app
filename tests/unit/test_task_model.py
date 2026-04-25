"""
Unit tests for Task model structure and validation.
These tests don't require a database - they test model structure only.
"""

from uuid import uuid4

import pytest

from analysi.models.task import Task, TaskFunction, TaskScope


@pytest.mark.unit
class TestTaskModel:
    """Test Task model structure and validation."""

    def test_task_model_attributes(self):
        """Test that Task model has expected attributes."""
        # Test required attributes exist
        assert hasattr(Task, "id")
        assert hasattr(Task, "component_id")
        assert hasattr(Task, "directive")
        assert hasattr(Task, "script")
        assert hasattr(Task, "function")
        assert hasattr(Task, "scope")
        assert hasattr(Task, "schedule")
        assert hasattr(Task, "llm_config")
        assert hasattr(Task, "created_at")
        assert hasattr(Task, "updated_at")

        # Test relationship attributes exist
        assert hasattr(Task, "component")

    def test_task_function_enum(self):
        """Test TaskFunction enum values."""
        expected_functions = [
            "DATA_CONVERSION",
            "EXTRACTION",
            "PLANNING",
            "REASONING",
            "SEARCH",
            "SUMMARIZATION",
            "VISUALIZATION",
        ]

        for func_name in expected_functions:
            assert hasattr(TaskFunction, func_name)

        # Test some specific values
        assert TaskFunction.DATA_CONVERSION == "data_conversion"
        assert TaskFunction.EXTRACTION == "extraction"
        assert TaskFunction.REASONING == "reasoning"

    def test_task_scope_enum(self):
        """Test TaskScope enum values."""
        expected_scopes = ["INPUT", "PROCESSING", "OUTPUT"]

        for scope_name in expected_scopes:
            assert hasattr(TaskScope, scope_name)

        # Test specific values
        assert TaskScope.INPUT == "input"
        assert TaskScope.PROCESSING == "processing"
        assert TaskScope.OUTPUT == "output"

    def test_task_initialization_minimal(self):
        """Test Task model initialization with minimal fields."""
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Test directive",
            function=TaskFunction.EXTRACTION,
        )

        # Verify basic attributes are set
        assert task.component_id == component_id
        assert task.directive == "Test directive"
        assert task.function == TaskFunction.EXTRACTION

        # Optional fields should be None or default
        assert task.script is None
        assert task.schedule is None

    def test_task_initialization_full(self):
        """Test Task with all fields."""
        component_id = uuid4()
        llm_config = {"default_model": "gpt-4", "temperature": 0.2, "max_tokens": 1000}

        task = Task(
            component_id=component_id,
            directive="Complex analysis directive",
            script="process_data(input)",
            function=TaskFunction.DATA_CONVERSION,
            scope=TaskScope.PROCESSING,
            schedule="0 */6 * * *",
            llm_config=llm_config,
        )

        # Verify all fields are set
        assert task.component_id == component_id
        assert task.directive == "Complex analysis directive"
        assert task.script == "process_data(input)"
        assert task.function == TaskFunction.DATA_CONVERSION
        assert task.scope == TaskScope.PROCESSING
        assert task.schedule == "0 */6 * * *"
        assert task.llm_config == llm_config

    def test_task_llm_config_types(self):
        """Test LLM config can handle different data types."""
        component_id = uuid4()

        # Test complex config with nested structures
        complex_config = {
            "default_model": "gpt-4",
            "fallback_models": ["gpt-3.5-turbo", "claude-3"],
            "temperature": 0.1,
            "max_tokens": 4000,
            "timeout_seconds": 60,
            "custom_parameters": {
                "top_p": 0.9,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
            },
            "system_prompt_template": "You are analyzing: {input_type}",
            "enabled": True,
            "retry_count": 3,
        }

        task = Task(
            component_id=component_id,
            directive="LLM config test",
            function=TaskFunction.EXTRACTION,
            llm_config=complex_config,
        )

        # Verify complex config is preserved
        assert task.llm_config == complex_config
        assert task.llm_config["default_model"] == "gpt-4"
        assert task.llm_config["custom_parameters"]["top_p"] == 0.9
        assert task.llm_config["enabled"] is True
        assert task.llm_config["retry_count"] == 3

    def test_task_repr(self):
        """Test Task string representation."""
        component_id = uuid4()
        task_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Test task",
            function=TaskFunction.EXTRACTION,
        )

        # Manually set ID for testing
        task.id = task_id

        repr_str = repr(task)
        assert "Task" in repr_str
        assert str(task_id) in repr_str
        assert str(component_id) in repr_str
        assert TaskFunction.EXTRACTION in repr_str

    def test_task_table_name(self):
        """Test that Task has correct table name."""
        assert Task.__tablename__ == "tasks"

    def test_task_field_types(self):
        """Test that task fields have expected Python types."""
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Type test task",
            script="print('hello')",
            function=TaskFunction.VISUALIZATION,
            scope=TaskScope.INPUT,
            schedule="0 0 * * *",
            llm_config={"model": "gpt-4"},
        )

        # Test field types
        assert isinstance(task.directive, str)
        assert isinstance(task.script, str)
        assert isinstance(task.function, str)
        assert isinstance(task.scope, str)
        assert isinstance(task.schedule, str)
        assert isinstance(task.llm_config, dict)

        # Test UUID field
        from uuid import UUID

        assert isinstance(task.component_id, UUID)

    def test_task_enum_values_are_strings(self):
        """Test that all enum values are strings."""
        # Test TaskFunction members
        for member in TaskFunction:
            assert isinstance(member.value, str), (
                f"TaskFunction.{member.name} should be string"
            )

        # Test TaskScope members
        for member in TaskScope:
            assert isinstance(member.value, str), (
                f"TaskScope.{member.name} should be string"
            )

    def test_task_directive_and_script_content(self):
        """Test directive and script can contain various content."""
        component_id = uuid4()

        # Test with multiline directive and script
        multiline_directive = """
        Perform comprehensive security analysis of the network traffic data.
        Look for suspicious patterns and anomalies.
        Generate detailed report with recommendations.
        """

        multiline_script = """
        #!cy 2.1
        # Security analysis script
        def analyze_traffic(data):
            patterns = detect_patterns(data)
            anomalies = find_anomalies(patterns)
            return generate_report(anomalies)

        result = analyze_traffic(input_data)
        """

        task = Task(
            component_id=component_id,
            directive=multiline_directive.strip(),
            script=multiline_script.strip(),
            function=TaskFunction.EXTRACTION,
        )

        assert "comprehensive security analysis" in task.directive
        assert "#!cy 2.1" in task.script
        assert "def analyze_traffic" in task.script

    def test_task_empty_llm_config(self):
        """Test task with empty LLM config."""
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Task with empty config",
            function=TaskFunction.SEARCH,
            llm_config={},
        )

        assert task.llm_config == {}
        assert isinstance(task.llm_config, dict)
