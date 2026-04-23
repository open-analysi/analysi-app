"""Tests for task proposal schemas."""

import json

import pytest
from pydantic import ValidationError

from analysi.agentic_orchestration.schemas import (
    TaskDesignation,
    TaskProposal,
    TaskProposalList,
)


class TestTaskDesignationEnum:
    """Tests for TaskDesignation enum."""

    def test_task_designation_enum_values(self):
        """Verify TaskDesignation has EXISTING, MODIFICATION, NEW values."""
        assert TaskDesignation.EXISTING == "existing"
        assert TaskDesignation.MODIFICATION == "modification"
        assert TaskDesignation.NEW == "new"

    def test_task_designation_has_three_values(self):
        """Verify TaskDesignation has exactly three values."""
        assert len(TaskDesignation) == 3

    def test_task_designation_string_values(self):
        """Verify TaskDesignation values are lowercase strings."""
        for designation in TaskDesignation:
            assert designation.value.islower()


class TestTaskProposal:
    """Tests for TaskProposal model."""

    def test_task_proposal_required_fields(self):
        """Verify TaskProposal requires name, description, designation, required_integrations."""
        # Should succeed with all required fields
        proposal = TaskProposal(
            name="Check IP Reputation",
            description="Look up IP in threat intel",
            designation=TaskDesignation.NEW,
            required_integrations=["virustotal"],
        )
        assert proposal.name == "Check IP Reputation"

    def test_task_proposal_missing_name_raises(self):
        """Verify TaskProposal raises error when name is missing."""
        with pytest.raises(ValidationError) as exc_info:
            TaskProposal(
                description="Test",
                designation=TaskDesignation.NEW,
                required_integrations=[],
            )
        assert "name" in str(exc_info.value)

    def test_task_proposal_missing_description_raises(self):
        """Verify TaskProposal raises error when description is missing."""
        with pytest.raises(ValidationError) as exc_info:
            TaskProposal(
                name="Test",
                designation=TaskDesignation.NEW,
                required_integrations=[],
            )
        assert "description" in str(exc_info.value)

    def test_task_proposal_missing_designation_raises(self):
        """Verify TaskProposal raises error when designation is missing."""
        with pytest.raises(ValidationError) as exc_info:
            TaskProposal(
                name="Test",
                description="Test",
                required_integrations=[],
            )
        assert "designation" in str(exc_info.value)

    def test_task_proposal_missing_integrations_raises(self):
        """Verify TaskProposal raises error when required_integrations is missing."""
        with pytest.raises(ValidationError) as exc_info:
            TaskProposal(
                name="Test",
                description="Test",
                designation=TaskDesignation.NEW,
            )
        assert "required_integrations" in str(exc_info.value)

    def test_task_proposal_optional_fields(self):
        """Verify existing_task_id, input_schema, output_schema are optional."""
        # Should succeed without optional fields
        proposal = TaskProposal(
            name="Test",
            description="Test",
            designation=TaskDesignation.NEW,
            required_integrations=[],
        )
        assert proposal.existing_task_id is None
        assert proposal.input_schema is None
        assert proposal.output_schema is None

    def test_task_proposal_with_optional_fields(self):
        """Verify TaskProposal accepts optional fields."""
        proposal = TaskProposal(
            name="Update IP Check",
            description="Modify existing IP check task",
            designation=TaskDesignation.MODIFICATION,
            existing_task_id="task-123",
            required_integrations=["virustotal", "abuseipdb"],
            input_schema={"type": "object", "properties": {"ip": {"type": "string"}}},
            output_schema={
                "type": "object",
                "properties": {"score": {"type": "number"}},
            },
        )
        assert proposal.existing_task_id == "task-123"
        assert proposal.input_schema["properties"]["ip"]["type"] == "string"

    def test_task_proposal_serialization(self):
        """Verify TaskProposal serializes to JSON correctly."""
        proposal = TaskProposal(
            name="Test Task",
            description="A test task",
            designation=TaskDesignation.EXISTING,
            existing_task_id="existing-123",
            required_integrations=["splunk"],
        )

        json_str = proposal.model_dump_json()
        data = json.loads(json_str)

        assert data["name"] == "Test Task"
        assert data["designation"] == "existing"
        assert data["existing_task_id"] == "existing-123"

    def test_task_proposal_designation_string_conversion(self):
        """Verify designation can be set from string."""
        proposal = TaskProposal(
            name="Test",
            description="Test",
            designation="new",  # String instead of enum
            required_integrations=[],
        )
        assert proposal.designation == TaskDesignation.NEW

    def test_task_proposal_invalid_designation_raises(self):
        """Verify invalid designation raises error."""
        with pytest.raises(ValidationError):
            TaskProposal(
                name="Test",
                description="Test",
                designation="invalid",
                required_integrations=[],
            )


class TestTaskProposalList:
    """Tests for TaskProposalList model."""

    def test_task_proposal_list_structure(self):
        """Verify TaskProposalList contains proposals and analysis_summary."""
        proposal_list = TaskProposalList(
            proposals=[
                TaskProposal(
                    name="Task 1",
                    description="First task",
                    designation=TaskDesignation.NEW,
                    required_integrations=["virustotal"],
                ),
            ],
            analysis_summary="Found 1 new task needed",
        )
        assert len(proposal_list.proposals) == 1
        assert proposal_list.analysis_summary == "Found 1 new task needed"

    def test_task_proposal_list_empty_proposals(self):
        """Verify TaskProposalList accepts empty proposals list."""
        proposal_list = TaskProposalList(
            proposals=[],
            analysis_summary="No tasks needed",
        )
        assert len(proposal_list.proposals) == 0

    def test_task_proposal_list_multiple_proposals(self):
        """Verify TaskProposalList handles multiple proposals."""
        proposal_list = TaskProposalList(
            proposals=[
                TaskProposal(
                    name="Task 1",
                    description="First",
                    designation=TaskDesignation.NEW,
                    required_integrations=[],
                ),
                TaskProposal(
                    name="Task 2",
                    description="Second",
                    designation=TaskDesignation.EXISTING,
                    existing_task_id="task-456",
                    required_integrations=["splunk"],
                ),
                TaskProposal(
                    name="Task 3",
                    description="Third",
                    designation=TaskDesignation.MODIFICATION,
                    existing_task_id="task-789",
                    required_integrations=["virustotal"],
                ),
            ],
            analysis_summary="Found 3 tasks: 1 new, 1 existing, 1 to modify",
        )
        assert len(proposal_list.proposals) == 3
        assert proposal_list.proposals[0].designation == TaskDesignation.NEW
        assert proposal_list.proposals[1].designation == TaskDesignation.EXISTING
        assert proposal_list.proposals[2].designation == TaskDesignation.MODIFICATION

    def test_task_proposal_list_serialization(self):
        """Verify TaskProposalList serializes to JSON correctly."""
        proposal_list = TaskProposalList(
            proposals=[
                TaskProposal(
                    name="Test",
                    description="Test",
                    designation=TaskDesignation.NEW,
                    required_integrations=["test"],
                ),
            ],
            analysis_summary="Summary",
        )

        json_str = proposal_list.model_dump_json()
        data = json.loads(json_str)

        assert "proposals" in data
        assert "analysis_summary" in data
        assert len(data["proposals"]) == 1
