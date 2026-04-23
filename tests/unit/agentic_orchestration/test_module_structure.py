"""
Unit tests for agentic orchestration module structure.

Tests validate that the module is properly structured and importable.
"""


class TestModuleImports:
    """Tests for module importability."""

    def test_module_imports(self):
        """Verify all module files can be imported without errors."""
        # Import the main module

        # Import submodules
        from analysi.agentic_orchestration import observability, sdk_wrapper

        assert observability is not None
        assert sdk_wrapper is not None

    def test_public_api_exports(self):
        """Verify __init__.py exports the correct public classes."""
        from analysi.agentic_orchestration import (
            AgentOrchestrationExecutor,
            ProgressCallback,
            StageExecutionMetrics,
            ToolCallTrace,
            WorkflowGenerationStage,
            WorkflowGenerationStatus,
        )

        # Verify all exports are the correct types
        assert WorkflowGenerationStage.RUNBOOK_GENERATION is not None
        assert WorkflowGenerationStatus.PENDING is not None
        assert ToolCallTrace is not None
        assert StageExecutionMetrics is not None
        assert ProgressCallback is not None
        assert AgentOrchestrationExecutor is not None
