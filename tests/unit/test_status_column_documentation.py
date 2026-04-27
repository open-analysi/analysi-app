"""Inline comments on status columns must match the canonical enum values.

Why this test exists: developers reading a model file should be able to trust the
inline `# ...` comment next to the `status` column. Drift is silent and easy: an
enum value gets renamed or added, the comment stays. This test parses the comment
out of the model source and asserts the listed values match the enum the runtime
actually uses.

Failure messages will tell you exactly what to update.
"""

from __future__ import annotations

import inspect
import re
from typing import Any

import pytest

from analysi.constants import TaskConstants, WorkflowConstants
from analysi.models.alert import AlertAnalysis
from analysi.models.task_run import TaskRun
from analysi.models.workflow_execution import WorkflowNodeInstance, WorkflowRun
from analysi.schemas.alert import AnalysisStatus


def _extract_status_comment(model_cls: type, column_name: str = "status") -> set[str]:
    """Pull the inline comment that follows the status column declaration.

    Handles both supported comment shapes:
      )  # See FooConstants.Status: a, b, c
      )  # Enum: a, b, c
      )  # a, b, c
    Returns the set of comma-separated tokens.
    """
    source = inspect.getsource(model_cls)
    # Find the column declaration block, then the trailing comment after the closing `)`.
    pattern = (
        rf"{column_name}:\s*Mapped\[[^\]]*\]\s*=\s*mapped_column\(.*?\)\s*"
        rf"#\s*(?:See\s+\w+(?:\.\w+)*\s*:\s*)?(?:Enum:\s*)?([^\n]+)"
    )
    match = re.search(pattern, source, re.DOTALL)
    assert match, (
        f"Could not parse the inline `# ...` comment on {model_cls.__name__}.{column_name}. "
        f"This test expects the comment to follow `mapped_column(...)` on the same closing-`)` line "
        f"and to list status values comma-separated, optionally prefixed by 'See <Enum>:' or 'Enum:'."
    )
    return {v.strip() for v in match.group(1).split(",") if v.strip()}


def _enum_values(enum_cls: Any) -> set[str]:
    return {member.value for member in enum_cls}


@pytest.mark.parametrize(
    ("model_cls", "enum_cls", "enum_label"),
    [
        (TaskRun, TaskConstants.Status, "TaskConstants.Status"),
        (WorkflowRun, WorkflowConstants.Status, "WorkflowConstants.Status"),
        (WorkflowNodeInstance, WorkflowConstants.Status, "WorkflowConstants.Status"),
        (AlertAnalysis, AnalysisStatus, "AnalysisStatus"),
    ],
)
def test_status_column_comment_matches_enum(
    model_cls: type, enum_cls: Any, enum_label: str
) -> None:
    documented = _extract_status_comment(model_cls)
    real = _enum_values(enum_cls)
    assert documented == real, (
        f"\n{model_cls.__name__}.status inline comment is out of sync with {enum_label}.\n"
        f"  Comment lists: {sorted(documented)}\n"
        f"  Enum values  : {sorted(real)}\n"
        f"  Missing from comment   : {sorted(real - documented)}\n"
        f"  Extra (fictional) in comment: {sorted(documented - real)}\n"
    )
