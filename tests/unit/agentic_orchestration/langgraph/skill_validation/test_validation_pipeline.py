"""Unit tests for skill validation pipeline."""

import pytest

from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
    python_ast_gate,
)
from analysi.agentic_orchestration.langgraph.skill_validation.pipeline import (
    SkillValidationPipeline,
)


class TestSkillValidationPipeline:
    @pytest.fixture
    def pipeline(self):
        return SkillValidationPipeline()

    def test_pipeline_name(self, pipeline):
        assert pipeline.name == "skill_validation"

    def test_pipeline_mode(self, pipeline):
        assert pipeline.mode == "review"

    def test_content_gates_include_ast(self, pipeline):
        gate_names = [c.__name__ for c in pipeline.content_gates()]
        assert "python_ast_gate" in gate_names

    def test_content_gates_include_policy(self, pipeline):
        gate_names = [c.__name__ for c in pipeline.content_gates()]
        assert "content_policy_gate" in gate_names

    def test_content_gates_include_format(self, pipeline):
        gate_names = [c.__name__ for c in pipeline.content_gates()]
        assert "format_gate" in gate_names

    def test_content_gates_include_empty(self, pipeline):
        gate_names = [c.__name__ for c in pipeline.content_gates()]
        assert "empty_content_gate" in gate_names

    def test_extract_results_maps_correctly(self, pipeline):
        final_state = {
            "status": "flagged",
            "validation_summary": "Content flagged for safety concerns.",
            "relevance": {"relevant": True, "confidence": "high", "reasoning": "ok"},
            "safety": {
                "safe": False,
                "concerns": ["prompt injection"],
                "reasoning": "bad",
            },
        }
        result = pipeline.extract_results(final_state)
        assert result["_status"] == "flagged"
        assert result["_summary"] == "Content flagged for safety concerns."
        assert result["relevance"]["relevant"] is True
        assert result["safety"]["safe"] is False

    def test_extract_results_pending_becomes_approved(self, pipeline):
        """If status is still 'pending' after pipeline, treat as approved."""
        final_state = {
            "status": "pending",
            "validation_summary": "All good.",
            "relevance": None,
            "safety": None,
        }
        result = pipeline.extract_results(final_state)
        assert result["_status"] == "approved"


class TestPythonAstGate:
    def test_catches_unsafe_py(self):
        """Python file with os import should produce errors."""
        errors = python_ast_gate("import os\nos.system('ls')", "script.py")
        assert len(errors) > 0
        assert any("os" in e.lower() for e in errors)

    def test_passes_safe_py(self):
        """Python file with json import should pass."""
        errors = python_ast_gate("import json\ndata = json.loads('{}')", "safe.py")
        assert errors == []

    def test_ignores_md(self):
        """Markdown files should passthrough — no AST analysis."""
        errors = python_ast_gate("import os\nos.system('rm -rf /')", "readme.md")
        assert errors == []

    def test_ignores_txt(self):
        errors = python_ast_gate("import subprocess", "notes.txt")
        assert errors == []
