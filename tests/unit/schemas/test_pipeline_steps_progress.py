"""Unit tests for PipelineStepsProgress schema."""

from datetime import UTC, datetime, timedelta

from analysi.schemas.alert import (
    PIPELINE_STEPS,
    PipelineStep,
    PipelineStepProgress,
    PipelineStepsProgress,
    StepStatus,
)


class TestPipelineStepEnum:
    """Test PipelineStep enum values."""

    def test_enum_has_four_steps(self):
        """Should have exactly 4 pipeline steps."""
        assert len(PipelineStep) == 4

    def test_enum_values_match_expected(self):
        """Enum values should match expected step names."""
        expected = [
            "pre_triage",
            "workflow_builder",
            "workflow_execution",
            "final_disposition_update",
        ]
        actual = [step.value for step in PipelineStep]
        assert actual == expected


class TestStepStatusEnum:
    """Test StepStatus enum values."""

    def test_enum_has_five_statuses(self):
        """Should have exactly 5 status values."""
        assert len(StepStatus) == 5

    def test_enum_values_match_expected(self):
        """Enum values should match expected statuses."""
        expected = ["not_started", "in_progress", "completed", "failed", "skipped"]
        actual = [status.value for status in StepStatus]
        assert actual == expected


class TestPipelineStepProgress:
    """Test PipelineStepProgress model."""

    def test_defaults_to_not_started(self):
        """New step should default to not_started status."""
        step = PipelineStepProgress(step=PipelineStep.PRE_TRIAGE)

        assert step.status == StepStatus.NOT_STARTED
        assert step.started_at is None
        assert step.completed_at is None
        assert step.error is None
        assert step.retries == 0
        assert step.result is None

    def test_all_fields_can_be_set(self):
        """All fields should be settable."""
        now = datetime.now(UTC)
        step = PipelineStepProgress(
            step=PipelineStep.WORKFLOW_BUILDER,
            status=StepStatus.COMPLETED,
            started_at=now - timedelta(minutes=5),
            completed_at=now,
            error=None,
            retries=2,
            result={"workflow_id": "abc123"},
        )

        assert step.step == PipelineStep.WORKFLOW_BUILDER
        assert step.status == StepStatus.COMPLETED
        assert step.retries == 2
        assert step.result == {"workflow_id": "abc123"}


class TestPipelineStepsProgressInitialization:
    """Test PipelineStepsProgress initialization."""

    def test_initialize_all_steps_creates_four_steps(self):
        """initialize_all_steps should create all 4 steps."""
        progress = PipelineStepsProgress.initialize_all_steps()

        assert len(progress.steps) == 4

    def test_initialize_all_steps_in_correct_order(self):
        """Steps should be in pipeline execution order."""
        progress = PipelineStepsProgress.initialize_all_steps()

        expected_order = [
            PipelineStep.PRE_TRIAGE,
            PipelineStep.WORKFLOW_BUILDER,
            PipelineStep.WORKFLOW_EXECUTION,
            PipelineStep.FINAL_DISPOSITION,
        ]
        actual_order = [step.step for step in progress.steps]
        assert actual_order == expected_order

    def test_initialize_all_steps_all_not_started(self):
        """All steps should start as not_started."""
        progress = PipelineStepsProgress.initialize_all_steps()

        for step in progress.steps:
            assert step.status == StepStatus.NOT_STARTED


class TestPipelineStepsProgressGetStep:
    """Test get_step method."""

    def test_get_step_returns_correct_step(self):
        """get_step should return the correct step."""
        progress = PipelineStepsProgress.initialize_all_steps()

        step = progress.get_step(PipelineStep.WORKFLOW_BUILDER)

        assert step is not None
        assert step.step == PipelineStep.WORKFLOW_BUILDER

    def test_get_step_returns_none_for_unknown(self):
        """get_step should return None if step not found."""
        progress = PipelineStepsProgress(steps=[])  # Empty

        step = progress.get_step(PipelineStep.PRE_TRIAGE)

        assert step is None


class TestPipelineStepsProgressMarkMethods:
    """Test mark_step_* methods."""

    def test_mark_step_in_progress_sets_status_and_started_at(self):
        """mark_step_in_progress should set status and started_at."""
        progress = PipelineStepsProgress.initialize_all_steps()

        progress.mark_step_in_progress(PipelineStep.PRE_TRIAGE)

        step = progress.get_step(PipelineStep.PRE_TRIAGE)
        assert step.status == StepStatus.IN_PROGRESS
        assert step.started_at is not None

    def test_mark_step_completed_sets_status_and_completed_at(self):
        """mark_step_completed should set status and completed_at."""
        progress = PipelineStepsProgress.initialize_all_steps()
        progress.mark_step_in_progress(PipelineStep.PRE_TRIAGE)

        progress.mark_step_completed(
            PipelineStep.PRE_TRIAGE, result={"verdict": "malicious"}
        )

        step = progress.get_step(PipelineStep.PRE_TRIAGE)
        assert step.status == StepStatus.COMPLETED
        assert step.completed_at is not None
        assert step.result == {"verdict": "malicious"}

    def test_mark_step_failed_sets_status_and_error(self):
        """mark_step_failed should set status, completed_at, and error."""
        progress = PipelineStepsProgress.initialize_all_steps()
        progress.mark_step_in_progress(PipelineStep.WORKFLOW_BUILDER)

        progress.mark_step_failed(
            PipelineStep.WORKFLOW_BUILDER, error="Connection timeout"
        )

        step = progress.get_step(PipelineStep.WORKFLOW_BUILDER)
        assert step.status == StepStatus.FAILED
        assert step.completed_at is not None
        assert step.error == "Connection timeout"


class TestPipelineStepsProgressSerialization:
    """Test to_dict and from_dict methods."""

    def test_to_dict_produces_json_serializable_output(self):
        """to_dict should produce JSON-serializable output."""
        import json

        progress = PipelineStepsProgress.initialize_all_steps()
        progress.mark_step_in_progress(PipelineStep.PRE_TRIAGE)

        result = progress.to_dict()

        # Should not raise
        json_str = json.dumps(result)
        assert '"steps"' in json_str
        assert '"pre_triage"' in json_str
        assert '"in_progress"' in json_str

    def test_to_dict_enums_serialized_as_strings(self):
        """Enums should be serialized as string values."""
        progress = PipelineStepsProgress.initialize_all_steps()
        progress.mark_step_completed(PipelineStep.PRE_TRIAGE)

        result = progress.to_dict()

        first_step = result["steps"][0]
        assert first_step["step"] == "pre_triage"
        assert first_step["status"] == "completed"
        # Should be strings, not enum objects
        assert isinstance(first_step["step"], str)
        assert isinstance(first_step["status"], str)

    def test_from_dict_round_trip_preserves_data(self):
        """from_dict should preserve data from to_dict."""
        original = PipelineStepsProgress.initialize_all_steps()
        original.mark_step_in_progress(PipelineStep.PRE_TRIAGE)
        original.mark_step_completed(PipelineStep.PRE_TRIAGE)
        original.mark_step_in_progress(PipelineStep.WORKFLOW_BUILDER)

        serialized = original.to_dict()
        restored = PipelineStepsProgress.from_dict(serialized)

        assert restored.get_step(PipelineStep.PRE_TRIAGE).status == StepStatus.COMPLETED
        assert (
            restored.get_step(PipelineStep.WORKFLOW_BUILDER).status
            == StepStatus.IN_PROGRESS
        )
        assert (
            restored.get_step(PipelineStep.WORKFLOW_EXECUTION).status
            == StepStatus.NOT_STARTED
        )

    def test_from_dict_handles_empty_dict(self):
        """from_dict with empty dict should initialize all steps."""
        progress = PipelineStepsProgress.from_dict({})

        assert len(progress.steps) == 4
        for step in progress.steps:
            assert step.status == StepStatus.NOT_STARTED

    def test_from_dict_handles_none(self):
        """from_dict with None should initialize all steps."""
        progress = PipelineStepsProgress.from_dict(None)

        assert len(progress.steps) == 4


class TestPipelineStepsProgressBackwardCompatibility:
    """Test backward compatibility with old format."""

    def test_from_dict_converts_old_format_completed(self):
        """from_dict should convert old format with completed=True to COMPLETED status."""
        old_format = {
            "pre_triage": {
                "completed": True,
                "started_at": "2025-01-01T00:00:00Z",
                "completed_at": "2025-01-01T00:01:00Z",
            }
        }

        progress = PipelineStepsProgress.from_dict(old_format)

        step = progress.get_step(PipelineStep.PRE_TRIAGE)
        assert step.status == StepStatus.COMPLETED

    def test_from_dict_converts_old_format_in_progress(self):
        """from_dict should convert old format with started_at but no completed to IN_PROGRESS."""
        old_format = {
            "pre_triage": {
                "completed": False,
                "started_at": "2025-01-01T00:00:00Z",
            }
        }

        progress = PipelineStepsProgress.from_dict(old_format)

        step = progress.get_step(PipelineStep.PRE_TRIAGE)
        assert step.status == StepStatus.IN_PROGRESS

    def test_from_dict_converts_old_format_failed(self):
        """from_dict should convert old format with error to FAILED status."""
        old_format = {
            "workflow_builder": {
                "completed": False,
                "started_at": "2025-01-01T00:00:00Z",
                "error": "Connection timeout",
            }
        }

        progress = PipelineStepsProgress.from_dict(old_format)

        step = progress.get_step(PipelineStep.WORKFLOW_BUILDER)
        assert step.status == StepStatus.FAILED
        assert step.error == "Connection timeout"

    def test_from_dict_converts_old_format_not_started(self):
        """from_dict should convert missing steps to NOT_STARTED."""
        old_format = {
            "pre_triage": {"completed": True},
            # Other steps missing = not_started
        }

        progress = PipelineStepsProgress.from_dict(old_format)

        assert progress.get_step(PipelineStep.PRE_TRIAGE).status == StepStatus.COMPLETED
        assert (
            progress.get_step(PipelineStep.WORKFLOW_BUILDER).status
            == StepStatus.NOT_STARTED
        )
        assert (
            progress.get_step(PipelineStep.WORKFLOW_EXECUTION).status
            == StepStatus.NOT_STARTED
        )

    def test_from_dict_preserves_retries_from_old_format(self):
        """from_dict should preserve retries count from old format."""
        old_format = {
            "workflow_builder": {
                "completed": False,
                "error": "Timeout",
                "retries": 3,
            }
        }

        progress = PipelineStepsProgress.from_dict(old_format)

        step = progress.get_step(PipelineStep.WORKFLOW_BUILDER)
        assert step.retries == 3

    def test_from_dict_preserves_result_from_old_format(self):
        """from_dict should preserve result data from old format."""
        old_format = {
            "pre_triage": {
                "completed": True,
                "result": {"verdict": "suspicious"},
            }
        }

        progress = PipelineStepsProgress.from_dict(old_format)

        step = progress.get_step(PipelineStep.PRE_TRIAGE)
        assert step.result == {"verdict": "suspicious"}

    def test_from_dict_creates_all_four_steps_from_partial_old_format(self):
        """from_dict should create all 4 steps even if old format only has some."""
        old_format = {
            "pre_triage": {"completed": True},
        }

        progress = PipelineStepsProgress.from_dict(old_format)

        # Should have all 4 steps
        assert len(progress.steps) == 4

        # Check each step exists
        for pipeline_step in PIPELINE_STEPS:
            assert progress.get_step(pipeline_step) is not None


class TestPipelineStepsProgressNewFormatDetection:
    """Test detection between old and new formats."""

    def test_from_dict_detects_new_format_by_steps_key(self):
        """from_dict should detect new format by presence of 'steps' key."""
        new_format = {
            "steps": [
                {"step": "pre_triage", "status": "completed"},
                {"step": "workflow_builder", "status": "in_progress"},
            ]
        }

        progress = PipelineStepsProgress.from_dict(new_format)

        # Should have the 2 steps from new format, not 4
        assert len(progress.steps) == 2
        assert progress.steps[0].status == StepStatus.COMPLETED
        assert progress.steps[1].status == StepStatus.IN_PROGRESS
