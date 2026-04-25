"""Unit tests for QuestionGenerator."""

from uuid import uuid4

import pytest

from analysi.services.workflow_composer.models import (
    Question,
    ResolvedTask,
)
from analysi.services.workflow_composer.questions import QuestionGenerator


class TestQuestionGenerator:
    """Test QuestionGenerator business logic."""

    @pytest.fixture
    def generator(self):
        """Create a QuestionGenerator instance."""
        return QuestionGenerator()

    # ============================================================================
    # Positive Tests
    # ============================================================================

    def test_generate_missing_aggregation_question(self, generator):
        """
        Verify generator creates actionable question for missing aggregation.

        Expected:
        - Question with question_type="missing_aggregation"
        - Options include "add merge", "add collect", "skip"
        - Suggested option based on output schemas
        """
        parallel_node_ids = ["n2", "n3"]
        layer = 2
        resolved_nodes = {
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                data_samples=[],
            ),
            "n3": ResolvedTask(
                task_id=uuid4(),
                cy_name="task3",
                name="Task 3",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                data_samples=[],
            ),
        }

        question = generator.generate_missing_aggregation_question(
            parallel_node_ids, layer, resolved_nodes
        )

        assert isinstance(question, Question)
        assert question.question_type == "missing_aggregation"
        assert len(question.options) >= 2  # At least merge and collect options
        assert question.suggested is not None
        assert (
            "merge" in str(question.options).lower()
            or "collect" in str(question.options).lower()
        )

    def test_suggest_merge_for_uniform_outputs(self, generator):
        """
        Verify generator suggests "merge" when parallel nodes have same output schema.

        Expected:
        - suggested = "add merge" or similar
        """
        parallel_node_ids = ["n2", "n3"]
        resolved_nodes = {
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                data_samples=[],
            ),
            "n3": ResolvedTask(
                task_id=uuid4(),
                cy_name="task3",
                name="Task 3",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                data_samples=[],
            ),
        }

        suggested = generator._suggest_aggregation_node(
            parallel_node_ids, resolved_nodes
        )

        assert suggested == "merge"

    def test_suggest_collect_for_varied_outputs(self, generator):
        """
        Verify generator suggests "collect" when parallel nodes have different output schemas.

        Expected:
        - suggested = "collect"
        """
        parallel_node_ids = ["n2", "n3"]
        resolved_nodes = {
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                data_samples=[],
            ),
            "n3": ResolvedTask(
                task_id=uuid4(),
                cy_name="task3",
                name="Task 3",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"score": {"type": "number"}},
                },
                data_samples=[],
            ),
        }

        suggested = generator._suggest_aggregation_node(
            parallel_node_ids, resolved_nodes
        )

        assert suggested == "collect"

    def test_generate_ambiguous_resolution_question(self, generator):
        """
        Verify generator creates question when multiple tasks match.

        Expected:
        - Question with question_type="ambiguous_resolution"
        - Options include all candidate task names
        - Context includes task descriptions
        """
        reference = "ambiguous_task"
        candidates = [
            {
                "id": str(uuid4()),
                "cy_name": "ambiguous_task",
                "name": "Task Option 1",
                "description": "First matching task",
            },
            {
                "id": str(uuid4()),
                "cy_name": "ambiguous_task",
                "name": "Task Option 2",
                "description": "Second matching task",
            },
        ]

        question = generator.generate_ambiguous_resolution_question(
            reference, candidates
        )

        assert isinstance(question, Question)
        assert question.question_type == "ambiguous_resolution"
        assert len(question.options) == 2
        assert "Task Option 1" in str(question.options) or "Task Option 1" in str(
            question.context
        )
        assert "Task Option 2" in str(question.options) or "Task Option 2" in str(
            question.context
        )
