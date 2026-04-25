"""
Type propagation service for Rodos (Typed Workflows).

This module implements the type propagation algorithm that infers types throughout
a workflow DAG, validates type compatibility, and reports errors with actionable suggestions.
"""

from analysi.services.type_propagation.errors import (
    DeprecatedMultiInputWarning,
    InvalidTemplateInputError,
    MergeConflictError,
    TypeMismatchError,
    TypePropagationError,
)
from analysi.services.type_propagation.propagator import (
    NodeTypeInfo,
    PropagationResult,
    WorkflowTypePropagator,
)
from analysi.services.type_propagation.task_inference import (
    infer_task_output_schema,
    validate_task_input,
)
from analysi.services.type_propagation.template_handlers import (
    create_union_schema,
    handle_collect_template,
    handle_identity_template,
    handle_merge_template,
    merge_object_schemas,
)

__all__ = [
    "DeprecatedMultiInputWarning",
    "InvalidTemplateInputError",
    "MergeConflictError",
    "NodeTypeInfo",
    "PropagationResult",
    "TypeMismatchError",
    # Errors
    "TypePropagationError",
    # Propagator
    "WorkflowTypePropagator",
    "create_union_schema",
    "handle_collect_template",
    # Template handlers
    "handle_identity_template",
    "handle_merge_template",
    # Task inference
    "infer_task_output_schema",
    "merge_object_schemas",
    "validate_task_input",
]
