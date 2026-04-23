"""
Repository layer for workflow execution data access.
Handles partition-aware queries and CRUD operations.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.constants import WorkflowConstants
from analysi.models.workflow_execution import (
    WorkflowEdgeInstance,
    WorkflowNodeInstance,
    WorkflowRun,
)


class WorkflowRunRepository:
    """
    Repository for workflow run operations.
    Handles partitioned table queries.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_workflow_run(
        self,
        tenant_id: str,
        workflow_id: UUID,
        input_type: str,
        input_location: str,
        execution_context: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        """
        Create a new workflow run.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow to execute
            input_type: Storage type for input (inline, s3)
            input_location: Location of input data
            execution_context: Optional context (e.g., analysis_id for artifact linking)
        """
        workflow_run = WorkflowRun(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            status=WorkflowConstants.Status.PENDING,
            input_type=input_type,
            input_location=input_location,
            execution_context=execution_context,
        )
        self.session.add(workflow_run)
        await self.session.flush()
        return workflow_run

    async def get_workflow_run(
        self, tenant_id: str, workflow_run_id: UUID
    ) -> WorkflowRun | None:
        """
        Get workflow run by ID with tenant filtering.
        """
        from analysi.constants import WorkflowConstants
        from analysi.models.workflow import Workflow

        # Query with LEFT JOIN to get workflow name from Workflow table
        stmt = (
            select(WorkflowRun, Workflow.name)
            .outerjoin(
                Workflow,
                (WorkflowRun.workflow_id == Workflow.id)
                & (Workflow.tenant_id == tenant_id),
            )
            .where(
                WorkflowRun.id == workflow_run_id,
                WorkflowRun.tenant_id == tenant_id,
            )
        )
        result = await self.session.execute(stmt)
        row = result.first()

        if not row:
            return None

        workflow_run = row[0]  # WorkflowRun object
        workflow_name = row[1]  # Workflow.name or None

        # Set workflow_name: use workflow name or "Ad Hoc Workflow" for None
        workflow_run.workflow_name = (
            workflow_name or WorkflowConstants.AD_HOC_WORKFLOW_NAME
        )

        return workflow_run

    async def get_workflow_run_by_id(self, workflow_run_id: UUID) -> WorkflowRun | None:
        """
        Get workflow run by ID only (no tenant filtering).
        Used when we need to get tenant_id from the workflow_run itself.
        """
        stmt = select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_workflow_run_status(
        self,
        workflow_run_id: UUID,
        status: str,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        output_type: str | None = None,
        output_location: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """
        Update workflow run status and timing.
        """
        update_data = {"status": status}
        if error_message is not None:
            update_data["error_message"] = error_message
        if started_at is not None:
            update_data["started_at"] = started_at
        if completed_at is not None:
            update_data["completed_at"] = completed_at
        if output_type is not None:
            update_data["output_type"] = output_type
        if output_location is not None:
            update_data["output_location"] = output_location

        stmt = update(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        if tenant_id is not None:
            stmt = stmt.where(WorkflowRun.tenant_id == tenant_id)
        stmt = stmt.values(**update_data)
        await self.session.execute(stmt)
        await self.session.flush()

    async def merge_execution_context(
        self, workflow_run_id: UUID, extra: dict, tenant_id: str | None = None
    ) -> None:
        """
        Merge extra keys into workflow_run.execution_context.
        No new column or migration needed — reuses the existing JSONB column.

        Read-merge-write in Python to avoid SQLAlchemy/asyncpg expression
        complexity with JSONB operator casting.
        """
        current_stmt = select(WorkflowRun.execution_context).where(
            WorkflowRun.id == workflow_run_id
        )
        if tenant_id is not None:
            current_stmt = current_stmt.where(WorkflowRun.tenant_id == tenant_id)
        result = await self.session.execute(current_stmt)
        current = result.scalar_one_or_none() or {}

        merged = {**current, **extra}

        update_stmt = update(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        if tenant_id is not None:
            update_stmt = update_stmt.where(WorkflowRun.tenant_id == tenant_id)
        update_stmt = update_stmt.values(execution_context=merged)
        await self.session.execute(update_stmt)
        await self.session.flush()

    async def list_workflow_runs(
        self,
        tenant_id: str,
        workflow_id: UUID | None = None,
        status: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[WorkflowRun], int]:
        """
        List workflow runs with filtering, sorting, and pagination.
        Returns tuple of (workflow_runs, total_count).
        """
        from sqlalchemy import asc, desc, func

        from analysi.constants import WorkflowConstants
        from analysi.models.workflow import Workflow

        # Query with LEFT JOIN to get workflow names from Workflow table
        query = (
            select(WorkflowRun, Workflow.name)
            .outerjoin(
                Workflow,
                (WorkflowRun.workflow_id == Workflow.id)
                & (Workflow.tenant_id == tenant_id),
            )
            .where(WorkflowRun.tenant_id == tenant_id)
        )

        # Apply filters
        if workflow_id is not None:
            query = query.where(WorkflowRun.workflow_id == workflow_id)
        if status is not None:
            query = query.where(WorkflowRun.status == status)

        # Count total before pagination (use simpler query for counting)
        count_query = select(func.count(WorkflowRun.id)).where(
            WorkflowRun.tenant_id == tenant_id
        )

        # Apply same filters to count query
        if workflow_id is not None:
            count_query = count_query.where(WorkflowRun.workflow_id == workflow_id)
        if status is not None:
            count_query = count_query.where(WorkflowRun.status == status)

        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Build sort column
        sort_column = getattr(WorkflowRun, sort, WorkflowRun.created_at)
        order_by = asc(sort_column) if order == "asc" else desc(sort_column)

        # Apply sorting and pagination
        query = query.order_by(order_by).offset(skip).limit(limit)

        # Execute query
        result = await self.session.execute(query)
        rows = result.all()

        # Process results to set workflow_name
        workflow_runs = []
        for row in rows:
            workflow_run = row[0]  # WorkflowRun object
            workflow_name = row[1]  # Workflow.name or None

            # Set workflow_name: use workflow name or "Ad Hoc Workflow" for None
            workflow_run.workflow_name = (
                workflow_name or WorkflowConstants.AD_HOC_WORKFLOW_NAME
            )
            workflow_runs.append(workflow_run)

        return workflow_runs, total


class WorkflowNodeInstanceRepository:
    """
    Repository for workflow node instance operations.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_node_instance(
        self,
        workflow_run_id: UUID,
        node_id: str,
        node_uuid: UUID,
        parent_instance_id: UUID | None = None,
        loop_context: dict[str, Any] | None = None,
        template_id: UUID | None = None,
    ) -> WorkflowNodeInstance:
        """
        Create a node instance with pending status.
        """
        node_instance = WorkflowNodeInstance(
            workflow_run_id=workflow_run_id,
            node_id=node_id,
            node_uuid=node_uuid,
            parent_instance_id=parent_instance_id,
            loop_context=loop_context,
            template_id=template_id,
            status=WorkflowConstants.Status.PENDING,
        )
        self.session.add(node_instance)
        await self.session.flush()
        return node_instance

    async def get_node_instance(
        self, node_instance_id: UUID
    ) -> WorkflowNodeInstance | None:
        """
        Get node instance by ID.
        """
        stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.id == node_instance_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_node_instance_by_node_id(
        self, workflow_run_id: UUID, node_id: str
    ) -> WorkflowNodeInstance | None:
        """
        Get node instance by workflow run ID and node ID.
        """
        stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == workflow_run_id,
            WorkflowNodeInstance.node_id == node_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_node_instances(
        self,
        workflow_run_id: UUID,
        status: str | None = None,
        parent_instance_id: UUID | None = None,
    ) -> list[WorkflowNodeInstance]:
        """
        List node instances for a workflow run.
        """
        stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == workflow_run_id
        )

        if status is not None:
            stmt = stmt.where(WorkflowNodeInstance.status == status)
        if parent_instance_id is not None:
            stmt = stmt.where(
                WorkflowNodeInstance.parent_instance_id == parent_instance_id
            )

        stmt = stmt.order_by(WorkflowNodeInstance.created_at)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_predecessor_instances(
        self, workflow_run_id: UUID, node_id: str
    ) -> list[WorkflowNodeInstance]:
        """
        Get all predecessor node instances for a given node based on workflow definition.
        """
        # Get the workflow run to find the workflow definition
        from analysi.models.workflow import Workflow
        from analysi.models.workflow_execution import WorkflowRun

        # Get workflow run
        run_stmt = select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        run_result = await self.session.execute(run_stmt)
        workflow_run = run_result.scalar_one_or_none()

        if not workflow_run:
            return []

        # Get workflow definition with edges
        from analysi.models.workflow import WorkflowEdge

        workflow_stmt = (
            select(Workflow)
            .options(
                selectinload(Workflow.edges).selectinload(WorkflowEdge.from_node),
                selectinload(Workflow.edges).selectinload(WorkflowEdge.to_node),
            )
            .where(Workflow.id == workflow_run.workflow_id)
        )
        workflow_result = await self.session.execute(workflow_stmt)
        workflow = workflow_result.scalar_one_or_none()

        if not workflow:
            return []

        # Find incoming edges to this node in the workflow definition
        incoming_edges = [
            edge for edge in workflow.edges if edge.to_node.node_id == node_id
        ]

        if not incoming_edges:
            return []

        # Get predecessor node IDs from the workflow definition
        predecessor_node_ids = [edge.from_node.node_id for edge in incoming_edges]

        # Find corresponding completed node instances
        pred_stmt = select(WorkflowNodeInstance).where(
            WorkflowNodeInstance.workflow_run_id == workflow_run_id,
            WorkflowNodeInstance.node_id.in_(predecessor_node_ids),
            WorkflowNodeInstance.status == WorkflowConstants.Status.COMPLETED,
        )
        pred_result = await self.session.execute(pred_stmt)
        return list(pred_result.scalars().all())

    _UNSET = object()  # sentinel: "not provided" (distinct from None)

    async def update_node_instance_status(
        self,
        node_instance_id: UUID,
        status: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None | object = _UNSET,
        task_run_id: UUID | None = None,
    ) -> None:
        """
        Update node instance execution status.

        Pass ``error_message=None`` to explicitly set the column to NULL
        (e.g., clearing stale HITL context on completion).  Omit to leave
        the existing value unchanged.
        """
        update_data = {"status": status}
        if started_at is not None:
            update_data["started_at"] = started_at
        if completed_at is not None:
            update_data["completed_at"] = completed_at
        if error_message is not self._UNSET:
            update_data["error_message"] = error_message
        if task_run_id is not None:
            update_data["task_run_id"] = task_run_id

        stmt = (
            update(WorkflowNodeInstance)
            .where(WorkflowNodeInstance.id == node_instance_id)
            .values(**update_data)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def save_node_instance_output(
        self,
        node_instance_id: UUID,
        output_type: str,
        output_location: str,
    ) -> None:
        """
        Save node instance output location.
        """
        stmt = (
            update(WorkflowNodeInstance)
            .where(WorkflowNodeInstance.id == node_instance_id)
            .values(output_type=output_type, output_location=output_location)
        )
        await self.session.execute(stmt)
        await self.session.flush()


class WorkflowEdgeInstanceRepository:
    """
    Repository for workflow edge instance operations.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_edge_instance(
        self,
        workflow_run_id: UUID,
        edge_id: str,
        edge_uuid: UUID,
        from_instance_id: UUID,
        to_instance_id: UUID,
    ) -> WorkflowEdgeInstance:
        """
        Create an edge instance when data flows.
        """
        edge_instance = WorkflowEdgeInstance(
            workflow_run_id=workflow_run_id,
            edge_id=edge_id,
            edge_uuid=edge_uuid,
            from_instance_id=from_instance_id,
            to_instance_id=to_instance_id,
        )
        self.session.add(edge_instance)
        await self.session.flush()
        return edge_instance

    async def mark_edge_delivered(
        self, edge_instance_id: UUID, delivered_at: datetime
    ) -> None:
        """
        Mark edge as having delivered data.
        """
        stmt = (
            update(WorkflowEdgeInstance)
            .where(WorkflowEdgeInstance.id == edge_instance_id)
            .values(delivered_at=delivered_at)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_incoming_edges(
        self, workflow_run_id: UUID, to_instance_id: UUID
    ) -> list[WorkflowEdgeInstance]:
        """
        Get all incoming edges to a node instance.
        """
        stmt = select(WorkflowEdgeInstance).where(
            WorkflowEdgeInstance.workflow_run_id == workflow_run_id,
            WorkflowEdgeInstance.to_instance_id == to_instance_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_outgoing_edges(
        self, workflow_run_id: UUID, from_instance_id: UUID
    ) -> list[WorkflowEdgeInstance]:
        """
        Get all outgoing edges from a node instance.
        """
        stmt = select(WorkflowEdgeInstance).where(
            WorkflowEdgeInstance.workflow_run_id == workflow_run_id,
            WorkflowEdgeInstance.from_instance_id == from_instance_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
