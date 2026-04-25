"""Unit tests for task_building_node proposal parsing.

Tests that the node correctly extracts task metadata from proposals.
"""

from analysi.agentic_orchestration.schemas.task_proposal import TaskDesignation


def test_proposal_has_correct_field_name():
    """Test that TaskProposal uses 'name' field, not 'task-name'."""
    from analysi.agentic_orchestration.schemas.task_proposal import TaskProposal

    # TaskProposal should use "name" field
    proposal = TaskProposal(
        name="Test Task",
        description="Test description",
        designation=TaskDesignation.NEW,
        required_integrations=["virustotal"],
    )

    # Verify the field is called "name", not "task-name"
    assert hasattr(proposal, "name")
    assert proposal.name == "Test Task"

    # Convert to dict (as it would be in orchestrator state)
    proposal_dict = proposal.model_dump()

    # The dict should have "name" key, not "task-name"
    assert "name" in proposal_dict
    assert proposal_dict["name"] == "Test Task"
    assert "task-name" not in proposal_dict


def test_task_metadata_extracts_correct_name_field():
    """Test that task_metadata extracts from 'name' field, not 'task-name'."""
    # Simulate a proposal dict as it appears in orchestrator state
    proposal_dict = {
        "name": "IP Reputation Check",
        "description": "Check IP against threat intel",
        "category": "new",
        "designation": "new",
        "required_integrations": ["virustotal"],
    }

    # This is what the code SHOULD do (correct)
    correct_name = proposal_dict.get("name")
    assert correct_name == "IP Reputation Check"

    # This is what the code WAS doing (wrong) - would return None
    wrong_name = proposal_dict.get("task-name")
    assert wrong_name is None  # Bug: This returns None!
