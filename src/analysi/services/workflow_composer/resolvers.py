"""
Task and Template Resolvers.

Resolve cy_names to tasks and shortcuts to templates.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.config.logging import get_logger
from analysi.models.task import Task
from analysi.models.workflow import NodeTemplate
from analysi.services.type_propagation.data_sample_validator import (
    generate_schema_from_samples,
)
from analysi.services.type_propagation.task_inference import (
    TypePropagationError,
    infer_task_output_schema,
)

from .models import ResolvedTask, ResolvedTemplate

# Template shortcut mappings
TEMPLATE_SHORTCUTS = {
    "identity": "system_identity",
    "merge": "system_merge",
    "collect": "system_collect",
}


class TaskResolver:
    """Resolve task cy_names to task objects."""

    def __init__(self, session: AsyncSession):
        """
        Initialize TaskResolver.

        Args:
            session: Database session
        """
        self.session = session
        self._cache: dict[str, ResolvedTask] = {}

    async def resolve(self, cy_name: str, tenant_id: str) -> ResolvedTask:
        """
        Resolve cy_name to task.

        Args:
            cy_name: Task canonical name
            tenant_id: Tenant ID

        Returns:
            ResolvedTask with full task details

        Raises:
            ValueError: If task not found, disabled, or ambiguous
        """
        # Check cache first
        cache_key = f"{tenant_id}:{cy_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Lookup task
        tasks = await self._lookup_task(cy_name, tenant_id)

        if not tasks:
            raise ValueError(f"Task not found: {cy_name}")

        if len(tasks) > 1:
            raise ValueError(
                f"Ambiguous task resolution: multiple tasks found with cy_name '{cy_name}'"
            )

        task_data = tasks[0]

        # Check if task is enabled
        if task_data.get("status") != "enabled":
            raise ValueError(
                f"Task '{cy_name}' is disabled (status: {task_data.get('status')})"
            )

        # Infer schemas
        task_id = task_data["id"]
        input_schema, output_schema = await self._infer_schemas(task_id, tenant_id)

        # Create ResolvedTask
        resolved = ResolvedTask(
            task_id=task_id,
            cy_name=cy_name,
            name=task_data["name"],
            input_schema=input_schema,
            output_schema=output_schema,
            data_samples=task_data.get("data_samples") or [],
        )

        # Cache result
        self._cache[cache_key] = resolved

        return resolved

    async def _lookup_task(self, cy_name: str, tenant_id: str) -> list[dict[str, Any]]:
        """
        Lookup task by cy_name in database.

        Args:
            cy_name: Task canonical name
            tenant_id: Tenant ID

        Returns:
            List of matching tasks (should be 0 or 1 for unique cy_names)
        """
        from analysi.models.component import Component

        # Join Task with Component to filter by tenant_id and cy_name
        stmt = (
            select(Task)
            .join(Component, Task.component_id == Component.id)
            .options(selectinload(Task.component))  # Eagerly load component
            .where(
                Component.tenant_id == tenant_id,
                Component.cy_name == cy_name,
                Component.status == "enabled",
            )
        )
        result = await self.session.execute(stmt)
        tasks = result.scalars().all()

        return [
            {
                "id": task.component_id,  # Use component_id, not task.id (FK to component.id)
                "cy_name": task.component.cy_name,
                "name": task.component.name,
                "status": task.component.status,
                "data_samples": task.data_samples,
                "script": task.script,
            }
            for task in tasks
        ]

    async def _infer_schemas(
        self, task_id: UUID, tenant_id: str
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """
        Infer input/output schemas from task using type propagation.

        Args:
            task_id: Task ID (actually component_id)
            tenant_id: Tenant ID

        Returns:
            Tuple of (input_schema, output_schema)
        """
        # Get task from database by component_id (tenant-scoped)
        from analysi.models.component import Component

        stmt = (
            select(Task)
            .join(Component, Task.component_id == Component.id)
            .where(
                Task.component_id == task_id,
                Component.tenant_id == tenant_id,
            )
        )
        db_result = await self.session.execute(stmt)
        task = db_result.scalar_one_or_none()

        if not task:
            return None, None

        # Infer input schema from data_samples (Finding #6)
        # For workflows: Extract 'input' field from data_samples wrapper structure
        # Tasks use {name, input, description, expected_output} but workflows should use direct input
        input_schema = None
        if task.data_samples and len(task.data_samples) > 0:
            try:
                # Extract 'input' field from each sample if present
                # This handles the Task convention: {name, input, description, expected_output}
                # For workflows, we want to infer schema from the actual input data, not the wrapper
                input_samples = []
                for sample in task.data_samples:
                    if isinstance(sample, dict) and "input" in sample:
                        # Extract the actual input data from the wrapper
                        input_samples.append(sample["input"])
                    else:
                        # Fallback: use sample as-is if no wrapper structure
                        input_samples.append(sample)

                # Generate schema from the extracted input samples
                if input_samples:
                    input_schema = generate_schema_from_samples(input_samples)
            except Exception as e:
                # Log schema generation failure for debugging
                logger = get_logger(__name__)
                logger.warning(
                    "schema_generation_failed",
                    task_id=str(task.id),
                    error=str(e),
                    data_samples=task.data_samples,
                )
                # If schema generation fails, leave as None
                pass

        # Infer output schema using type propagation
        output_schema = None
        if input_schema:
            try:
                result_or_error = await infer_task_output_schema(
                    task, input_schema, session=self.session, tenant_id=tenant_id
                )
                if not isinstance(result_or_error, TypePropagationError):
                    output_schema = result_or_error
            except Exception:
                # If inference fails, leave as None
                pass

        return input_schema, output_schema


class TemplateResolver:
    """Resolve template shortcuts to template objects."""

    def __init__(self, session: AsyncSession):
        """
        Initialize TemplateResolver.

        Args:
            session: Database session
        """
        self.session = session
        self._cache: dict[str, ResolvedTemplate] = {}

    async def resolve(self, shortcut: str) -> ResolvedTemplate:
        """
        Resolve shortcut to template.

        Args:
            shortcut: Lowercase shortcut (identity, merge, collect)

        Returns:
            ResolvedTemplate with template details

        Raises:
            ValueError: If shortcut unknown or template not found
        """
        # Check cache first
        if shortcut in self._cache:
            return self._cache[shortcut]

        # Validate shortcut
        if shortcut not in TEMPLATE_SHORTCUTS:
            raise ValueError(
                f"Unknown template shortcut: '{shortcut}'. "
                f"Valid shortcuts are: {', '.join(TEMPLATE_SHORTCUTS.keys())}"
            )

        # Get template name from mapping
        template_name = TEMPLATE_SHORTCUTS[shortcut]

        # Lookup template
        template_data = await self._lookup_template(template_name)

        if not template_data:
            raise ValueError(
                f"Template not found in database: '{template_name}' "
                f"(shortcut: '{shortcut}')"
            )

        # Create ResolvedTemplate
        resolved = ResolvedTemplate(
            template_id=template_data["id"],
            shortcut=shortcut,
            name=template_data["name"],
            kind=template_data["kind"],
            input_schema=template_data["input_schema"],
            output_schema=template_data["output_schema"],
        )

        # Cache result
        self._cache[shortcut] = resolved

        return resolved

    async def _lookup_template(self, template_name: str) -> dict[str, Any] | None:
        """
        Lookup template by name in database.

        Args:
            template_name: System template name

        Returns:
            Template dict or None if not found
        """
        stmt = select(NodeTemplate).where(
            NodeTemplate.name == template_name,
            NodeTemplate.tenant_id.is_(None),  # System templates only
            NodeTemplate.enabled.is_(True),
        )
        result = await self.session.execute(stmt)
        template = result.scalar_one_or_none()

        if not template:
            return None

        return {
            "id": template.id,
            "name": template.name,
            "kind": template.kind,
            "input_schema": template.input_schema,
            "output_schema": template.output_schema,
        }
