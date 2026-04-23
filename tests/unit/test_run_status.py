"""Unit tests for RunStatus enum (Project Leros)."""

import pytest

from analysi.constants import RunStatus


@pytest.mark.unit
class TestRunStatus:
    """RunStatus is the unified job lifecycle enum for tracked jobs."""

    def test_run_status_has_six_values(self):
        """Exactly 6 lifecycle states: pending, running, completed, failed, paused, cancelled."""
        assert len(RunStatus) == 6

    def test_run_status_values_are_lowercase_strings(self):
        """All values are lowercase strings (StrEnum contract)."""
        for member in RunStatus:
            assert member.value == member.value.lower()
            assert isinstance(member.value, str)

    def test_run_status_string_equality(self):
        """StrEnum values compare equal to plain strings."""
        assert RunStatus.PENDING == "pending"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.PAUSED == "paused"
        assert RunStatus.CANCELLED == "cancelled"

    def test_run_status_terminal_states(self):
        """completed, failed, cancelled are terminal — no further transitions."""
        terminal = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
        assert len(terminal) == 3
        for state in terminal:
            assert state in RunStatus

    def test_run_status_active_states(self):
        """pending, running, paused are non-terminal — work may continue."""
        active = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.PAUSED}
        assert len(active) == 3
        # Active and terminal are disjoint and cover all values
        terminal = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
        assert active | terminal == set(RunStatus)
        assert active & terminal == set()
