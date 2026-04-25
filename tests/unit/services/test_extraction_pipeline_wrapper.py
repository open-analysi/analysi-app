"""Unit tests for extraction pipeline wrapper."""

from analysi.agentic_orchestration.langgraph.content_review.extraction_pipeline import (
    ExtractionReviewPipeline,
)


class TestExtractionReviewPipeline:
    def test_pipeline_name(self):
        pipeline = ExtractionReviewPipeline()
        assert pipeline.name == "extraction"

    def test_pipeline_mode_is_review_transform(self):
        pipeline = ExtractionReviewPipeline()
        assert pipeline.mode == "review_transform"

    def test_content_gates_include_empty_and_length(self):
        from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
            content_length_gate,
            empty_content_gate,
        )

        pipeline = ExtractionReviewPipeline()
        gates = pipeline.content_gates()
        assert empty_content_gate in gates
        assert content_length_gate in gates

    def test_extract_results_maps_completed_to_approved(self):
        pipeline = ExtractionReviewPipeline()
        result = pipeline.extract_results(
            {"status": "completed", "transformed_content": "text"}
        )
        assert result["_status"] == "approved"
        assert result["_transformed_content"] == "text"

    def test_extract_results_maps_rejected(self):
        pipeline = ExtractionReviewPipeline()
        result = pipeline.extract_results({"status": "rejected"})
        assert result["_status"] == "rejected"

    def test_extract_results_maps_failed(self):
        pipeline = ExtractionReviewPipeline()
        result = pipeline.extract_results({"status": "failed"})
        assert result["_status"] == "failed"

    def test_initial_state_has_required_keys(self):
        pipeline = ExtractionReviewPipeline()
        state = pipeline.initial_state(content="test", skill_id="abc", tenant_id="t1")
        assert state["content"] == "test"
        assert state["skill_id"] == "abc"
        assert state["tenant_id"] == "t1"
