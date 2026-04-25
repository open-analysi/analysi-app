"""
Task type inference integration with Cy language.

Provides functions to infer task output schemas and validate task inputs
using Cy's type inference API with strict input validation.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.task import Task
from analysi.services.cy_tool_registry import load_tool_registry_async
from analysi.services.type_propagation.errors import TypePropagationError


def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a schema to proper JSON Schema format.

    Cy's analyze_types returns {} for scripts without return statements,
    but {} doesn't trigger strict_input validation. We need to normalize
    this to {type: object, properties: {}} for proper validation.

    Args:
        schema: Schema that might be empty {}

    Returns:
        Normalized JSON Schema with at least type and properties
    """
    if not schema or schema == {}:
        return {"type": "object", "properties": {}}

    # If schema has properties but no type, add type
    if "properties" in schema and "type" not in schema:
        return {"type": "object", **schema}

    return schema


async def infer_task_output_schema(
    task: Task,
    input_schema: dict[str, Any],
    strict_input: bool = True,
    session: AsyncSession | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any] | TypePropagationError:
    """
    Infer task output schema using Cy type inference.

    If task.output_schema is explicitly set, returns it directly.
    Otherwise, calls Cy's analyze_types() API with configurable strictness.

    Args:
        task: Task model instance
        input_schema: Input JSON Schema for the task
        strict_input: If True, enforce that all input field accesses exist in input_schema.
                     If False, allow accessing fields not in schema (permissive mode).

                     Use strict_input=True (default) for:
                     - Workflow composition validation (Task A → Task B)
                     - Known, well-defined APIs
                     - Catching field name typos early

                     Use strict_input=False for:
                     - API responses where schema isn't fully known
                     - Dynamic data from external systems
                     - Exploratory development
        session: Optional database session for loading integration tool schemas
        tenant_id: Optional tenant ID for loading tenant-specific integration tools

    Returns:
        Inferred output schema, or TypePropagationError on failure

    Example:
        >>> task = Task(script="return input.ip", output_schema=None)
        >>> input_schema = {"type": "object", "properties": {"ip": {"type": "string"}}}
        >>> await infer_task_output_schema(task, input_schema)
        {"type": "string"}
    """
    # If script is empty, return error
    if not task.script or task.script.strip() == "":
        return TypePropagationError(
            node_id=str(task.id) if task.id else "unknown",
            error_type="type_inference_error",
            message="Cannot infer output schema from empty script",
            suggestion="Add script content",
        )

    # Load integration tool schemas if session and tenant_id provided
    tool_registry = None
    if session and tenant_id:
        tool_registry_dict = await load_tool_registry_async(session, tenant_id)

        # Convert dict to ToolRegistry object
        # Native tools are automatically included by analyze_types() internally
        if tool_registry_dict:
            from cy_language.tool_signature import ToolRegistry

            tool_registry = ToolRegistry.from_dict(tool_registry_dict)

    # Normalize input_schema to proper JSON Schema format
    # Empty dict {} doesn't trigger validation; {type: object, properties: {}} does
    normalized_input = _normalize_schema(input_schema)

    # Use Cy 0.19.0 type analysis API with configurable strictness
    try:
        from cy_language import analyze_types

        # analyze_types with strict_input=True enforces field existence validation
        # It raises TypeError when script accesses fields not in input_schema
        # This catches workflow composition errors at validation time
        # NOTE: Native tools (len, str, etc.) are automatically included internally
        inferred_schema = analyze_types(
            task.script,
            input_schema=normalized_input,
            tool_registry=tool_registry,  # ToolRegistry object with app tools only
            strict_input=strict_input,
        )

        # Normalize output schema (empty {} from no-return → proper schema)
        return _normalize_schema(inferred_schema)
    except TypeError as e:
        # Type validation error (e.g., accessing missing field, type mismatch)
        return TypePropagationError(
            node_id=str(task.id) if task.id else "unknown",
            error_type="type_validation_error",
            message=f"Type validation failed: {e!s}",
            suggestion="Check that script uses fields provided by input schema",
        )
    except SyntaxError as e:
        # Syntax error in Cy code
        return TypePropagationError(
            node_id=str(task.id) if task.id else "unknown",
            error_type="syntax_error",
            message=f"Syntax error in Cy script: {e!s}",
            suggestion="Fix Cy syntax errors (check for return statement, proper variable declarations)",
        )
    except Exception as e:
        # Other errors (ValueError for invalid schemas, etc.)
        return TypePropagationError(
            node_id=str(task.id) if task.id else "unknown",
            error_type="type_inference_error",
            message=f"Failed to infer output schema: {e!s}",
            suggestion="Check script syntax and ensure return statement is used",
        )


async def validate_task_input(
    task: Task,
    input_schema: dict[str, Any],
    strict_input: bool = True,
    session: AsyncSession | None = None,
    tenant_id: str | None = None,
) -> bool | TypePropagationError:
    """
    Validate task input compatibility using Cy inference.

    Uses duck typing - if Cy can infer output from input, input is compatible.

    Args:
        task: Task model instance
        input_schema: Input JSON Schema to validate
        strict_input: If True, enforce strict field validation. See infer_task_output_schema() docs.
        session: Optional database session for loading integration tool schemas
        tenant_id: Optional tenant ID for loading tenant-specific integration tools

    Returns:
        True if compatible, TypePropagationError otherwise

    Example:
        >>> task = Task(script="return input.ip")
        >>> input_schema = {"type": "object", "properties": {"ip": {"type": "string"}}}
        >>> await validate_task_input(task, input_schema)
        True
    """
    # Try to infer output schema - if it succeeds, input is compatible
    result = await infer_task_output_schema(
        task,
        input_schema,
        strict_input=strict_input,
        session=session,
        tenant_id=tenant_id,
    )

    if isinstance(result, TypePropagationError):
        # Inference failed - input is incompatible
        return TypePropagationError(
            node_id=str(task.id) if task.id else "unknown",
            error_type="type_validation_error",
            message=f"Task input validation failed: {result.message}",
            suggestion="Ensure input schema provides required fields for task script",
        )

    # Inference succeeded - input is compatible
    return True
