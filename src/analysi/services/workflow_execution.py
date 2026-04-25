"""
Workflow execution service with progressive execution algorithm.
Handles transformation nodes, aggregation, and workflow state management.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.auth.context_sanitizer import sanitize_execution_context
from analysi.config.logging import get_logger
from analysi.constants import TaskConstants, WorkflowConstants
from analysi.models.task_run import TaskRun
from analysi.models.workflow import NodeTemplate, Workflow, WorkflowNode
from analysi.models.workflow_execution import (
    WorkflowNodeInstance,
    WorkflowRun,
)
from analysi.repositories.workflow_execution import (
    WorkflowEdgeInstanceRepository,
    WorkflowNodeInstanceRepository,
    WorkflowRunRepository,
)
from analysi.services.storage import StorageManager

logger = get_logger(__name__)


class WorkflowExecutor:
    """
    Base workflow executor implementing progressive execution algorithm.
    Creates node instances dynamically as workflow unfolds.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.polling_interval = 0.1  # 100ms
        self.run_repo = WorkflowRunRepository(session)
        self.node_repo = WorkflowNodeInstanceRepository(session)
        self.edge_repo = WorkflowEdgeInstanceRepository(session)
        self.storage = StorageManager()
        self.tenant_id: str | None = None  # Set lazily by entry points

    # ------------------------------------------------------------------
    # Helpers: shared between execute_node_instance and continue_after_hitl
    # ------------------------------------------------------------------

    @staticmethod
    def _build_llm_usage_dict(llm_usage: Any) -> dict:
        """Extract LLM usage stats into a plain dict for the output envelope."""
        return {
            "input_tokens": llm_usage.input_tokens,
            "output_tokens": llm_usage.output_tokens,
            "total_tokens": llm_usage.total_tokens,
            "cost_usd": llm_usage.cost_usd,
        }

    @staticmethod
    def _build_task_output_envelope(
        node_id: str,
        task_output: Any | None,
        llm_usage: Any | None,
        description: str = "Output from task execution",
    ) -> dict:
        """Build the standard node-output envelope.

        Used after both first-run and HITL-resumed task executions.
        """
        node_context: dict = {}
        if llm_usage is not None:
            node_context["llm_usage"] = WorkflowExecutor._build_llm_usage_dict(
                llm_usage
            )

        if task_output is not None:
            return {
                "node_id": node_id,
                "context": node_context,
                "description": description,
                "result": task_output,
            }
        return {
            "node_id": node_id,
            "context": node_context,
            "description": "Task produced no output",
            "result": {},
        }

    async def _handle_hitl_pause(
        self,
        session: AsyncSession,
        task_result: Any,
        node_instance: WorkflowNodeInstance,
        tenant_id: str,
        workflow_run_id: UUID | None = None,
        analysis_id_str: str | None = None,
    ) -> None:
        """Create a hitl_questions row and send a Slack message for a PAUSED task.

        Shared between execute_node_instance (first pause) and
        continue_after_hitl (re-pause after HITL resume).
        """
        checkpoint_data = (task_result.output_data or {}).get("_hitl_checkpoint", {})
        if not checkpoint_data:
            return

        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        hitl_question = await create_question_from_checkpoint(
            session=session,
            tenant_id=tenant_id,
            task_run_id=task_result.task_run_id,
            checkpoint_data=checkpoint_data,
            workflow_run_id=workflow_run_id or node_instance.workflow_run_id,
            node_instance_id=node_instance.id,
            analysis_id=(UUID(analysis_id_str) if analysis_id_str else None),
        )
        if hitl_question is not None:
            from analysi.slack_listener.sender import send_hitl_question

            await send_hitl_question(
                session=session,
                hitl_question=hitl_question,
                pending_tool_args=checkpoint_data.get("pending_tool_args", {}),
                tenant_id=tenant_id,
            )

    async def create_workflow_run(
        self,
        tenant_id: str,
        workflow_id: UUID,
        input_data: Any,
        execution_context: dict[str, Any] | None = None,
    ) -> UUID:
        """
        Create a WorkflowRun record without starting execution.

        Use this when the caller will drive execution directly (e.g., the
        analysis worker running synchronously via an ARQ job).  The caller
        is responsible for committing the session and then calling
        ``_execute_workflow_synchronously(workflow_run_id)`` to start
        the execution loop.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow to execute
            input_data: Initial input for workflow
            execution_context: Optional context (e.g., analysis_id for artifact linking)

        Returns:
            workflow_run_id (UUID) for the newly created run
        """
        self.tenant_id = tenant_id
        # Store input data
        input_json = json.dumps(input_data)
        input_type = self.storage.select_storage_type(input_json)

        storage_result = await self.storage.store(
            content=input_json,
            content_type="application/json",
            tenant_id=tenant_id,
            task_run_id=str(workflow_id),
            storage_purpose="workflow-input",
        )

        input_location = storage_result["location"]

        # Create workflow run
        # SECURITY: Strip protected identity/runtime keys from user-supplied context
        workflow_run = await self.run_repo.create_workflow_run(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            input_type=input_type,
            input_location=input_location,
            execution_context=sanitize_execution_context(execution_context),
        )

        return workflow_run.id

    async def execute_workflow(
        self,
        tenant_id: str,
        workflow_id: UUID,
        input_data: Any,
        execution_context: dict[str, Any] | None = None,
    ) -> UUID:
        """
        Start workflow execution by creating the run and enqueuing an ARQ job.

        The caller must commit the session after this returns so the
        ARQ worker can see the WorkflowRun row.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow to execute
            input_data: Initial input for workflow
            execution_context: Optional context (e.g., analysis_id for artifact linking)

        Returns:
            workflow_run_id for tracking
        """
        workflow_run_id = await self.create_workflow_run(
            tenant_id, workflow_id, input_data, execution_context=execution_context
        )

        # Execution is handled by an ARQ job (enqueued by the caller
        # after session.commit).

        return workflow_run_id

    async def create_node_instance(
        self,
        workflow_run_id: UUID,
        node_id: str,
        node_uuid: UUID,
        parent_instance_id: UUID | None = None,
        template_id: UUID | None = None,
    ) -> WorkflowNodeInstance:
        """
        Create a node instance when all predecessors exist.
        """
        node_instance = await self.node_repo.create_node_instance(
            workflow_run_id=workflow_run_id,
            node_id=node_id,
            node_uuid=node_uuid,
            parent_instance_id=parent_instance_id,
            template_id=template_id,
        )
        await self.session.commit()
        return node_instance

    async def execute_node_instance(self, node_instance: WorkflowNodeInstance) -> None:
        """
        Execute a node instance when all predecessors complete.
        """
        try:
            # Update status to running
            await self.node_repo.update_node_instance_status(
                node_instance.id,
                status=WorkflowConstants.Status.RUNNING,
                started_at=datetime.now(UTC),
            )
            await self.session.commit()

            # Get node details
            node_stmt = select(WorkflowNode).where(
                WorkflowNode.id == node_instance.node_uuid
            )
            node_result = await self.session.execute(node_stmt)
            node = node_result.scalar_one()

            # Execute based on node type
            if node.kind == "task":
                # For task nodes, delegate to task execution system
                from analysi.services.task_execution import TaskExecutionService
                from analysi.services.task_run import TaskRunService

                # Get input data from predecessors
                input_data = await self.aggregate_predecessor_outputs(
                    node_instance.workflow_run_id, node_instance.node_id
                )

                # Extract actual data from envelope for task execution (same as transformation nodes)
                logger.debug("task_inputdata_before_extraction", input_data=input_data)
                task_input = input_data
                if isinstance(input_data, dict) and "result" in input_data:
                    task_input = input_data["result"]
                    logger.debug(
                        "extracted_taskinput_from_envelope", task_input=task_input
                    )
                    logger.debug(
                        "extracted_task_input_type", input_type=str(type(task_input))
                    )
                else:
                    logger.debug(
                        "no_result_field_in_inputdata_using_raw", task_input=task_input
                    )

                # Get tenant_id and execution_context from workflow run
                workflow_run = await self.run_repo.get_workflow_run_by_id(
                    node_instance.workflow_run_id
                )
                tenant_id = workflow_run.tenant_id if workflow_run else "default"

                # Create a task run with node instance link and execution context
                task_run_service = TaskRunService()
                task_run = await task_run_service.create_execution(
                    session=self.session,
                    tenant_id=tenant_id,
                    task_id=node.task_id,
                    cy_script=None,  # Will be loaded from task
                    input_data=task_input,
                    executor_config=None,
                    workflow_run_id=node_instance.workflow_run_id,  # Link to workflow
                    workflow_node_instance_id=node_instance.id,  # Link to node instance
                    execution_context=(
                        workflow_run.execution_context if workflow_run else None
                    ),
                )

                # Store task_run_id in node instance for tracking
                await self.node_repo.update_node_instance_status(
                    node_instance.id,
                    WorkflowConstants.Status.RUNNING,
                    task_run_id=task_run.id,
                )
                await self.session.commit()

                # Execute the task with its own isolated session; get result back directly
                from analysi.schemas.task_execution import TaskExecutionStatus

                execution_service = TaskExecutionService()
                task_result = await execution_service.execute_single_task(
                    task_run.id, tenant_id
                )

                # Persist execution outcome to DB using our own session
                if task_result.status == TaskExecutionStatus.COMPLETED:
                    await task_run_service.update_status(
                        self.session,
                        task_result.task_run_id,
                        TaskConstants.Status.COMPLETED,
                        output_data=task_result.output_data,
                        llm_usage=task_result.llm_usage,
                    )
                elif task_result.status == TaskExecutionStatus.PAUSED:
                    # HITL: task awaiting human input.
                    # Suspend the branch: mark node instance as PAUSED so the
                    # monitor loop neither retries it nor treats it as a failure.
                    logger.info(
                        "task_run_returned_paused_suspending_branch", id=task_run.id
                    )
                    await task_run_service.update_status(
                        self.session,
                        task_result.task_run_id,
                        TaskConstants.Status.PAUSED,
                        output_data=task_result.output_data,
                        llm_usage=task_result.llm_usage,
                    )
                    # Extract HITL context for UI display (stored as
                    # error_message so the existing API carries it without
                    # schema changes — the UI renders it as an amber panel
                    # when status is "paused").
                    hitl_ctx = (task_result.output_data or {}).get(
                        "_hitl_checkpoint", {}
                    )
                    hitl_args = hitl_ctx.get("pending_tool_args", {})
                    hitl_question_text = hitl_args.get(
                        "question",
                        hitl_args.get("text", hitl_args.get("question_text", "")),
                    )
                    hitl_channel = hitl_args.get(
                        "channel", hitl_args.get("destination", "")
                    )
                    hitl_responses = hitl_args.get("responses", "")
                    hitl_detail = json.dumps(
                        {
                            "hitl": True,
                            "question": hitl_question_text[:500],
                            "channel": hitl_channel,
                            "options": hitl_responses,
                        }
                    )

                    await self.node_repo.update_node_instance_status(
                        node_instance.id,
                        WorkflowConstants.Status.PAUSED,
                        error_message=hitl_detail,
                    )
                    # R20/R21: create hitl_questions row + send Slack message
                    analysis_id_str = (workflow_run.execution_context or {}).get(
                        "analysis_id"
                    )
                    await self._handle_hitl_pause(
                        session=self.session,
                        task_result=task_result,
                        node_instance=node_instance,
                        tenant_id=tenant_id,
                        analysis_id_str=analysis_id_str,
                    )
                    await self.session.commit()
                    return
                else:
                    error_msg = task_result.error_message or "Task execution failed"
                    logger.error("task_run_failed", id=task_run.id, error_msg=error_msg)
                    await task_run_service.update_status(
                        self.session,
                        task_result.task_run_id,
                        TaskConstants.Status.FAILED,
                        error_info={"error": error_msg},
                        llm_usage=task_result.llm_usage,
                    )
                    await self.node_repo.update_node_instance_status(
                        node_instance.id,
                        WorkflowConstants.Status.FAILED,
                        error_message=error_msg,
                    )
                    await self.session.commit()
                    return

                # Build output envelope from task result
                output_data = self._build_task_output_envelope(
                    node_id=node_instance.node_id,
                    task_output=task_result.output_data,
                    llm_usage=task_result.llm_usage,
                )
                logger.debug("final_task_envelope", output_data=output_data)
            elif node.kind == "transformation":
                # Execute transformation
                transformation_executor = TransformationNodeExecutor()

                # Get input data from predecessors
                input_data = await self.aggregate_predecessor_outputs(
                    node_instance.workflow_run_id, node_instance.node_id
                )

                # Execute template if available
                if node_instance.template_id:
                    from sqlalchemy import or_

                    # Get tenant_id for ownership check
                    wf_run = await self.run_repo.get_workflow_run_by_id(
                        node_instance.workflow_run_id
                    )
                    run_tenant = wf_run.tenant_id if wf_run else None

                    # Scope template load to tenant-owned or system templates
                    template_stmt = select(NodeTemplate.code).where(
                        NodeTemplate.id == node_instance.template_id,
                        or_(
                            NodeTemplate.tenant_id == run_tenant,
                            NodeTemplate.tenant_id.is_(None),
                        ),
                    )
                    template_result = await self.session.execute(template_stmt)
                    template_code = template_result.scalar_one_or_none()

                    if template_code:
                        # Templates receive simplified input by default, with optional envelope access
                        # inp = content of result field, workflow_input = full envelope
                        template_input = (
                            input_data.get("result", input_data)
                            if isinstance(input_data, dict) and "result" in input_data
                            else input_data
                        )

                        output_data = await transformation_executor.execute_template(
                            template_code, template_input, envelope=input_data
                        )
                    else:
                        output_data = input_data  # Pass through
                else:
                    output_data = input_data  # Pass through
            else:
                # Default: pass through input
                input_data = await self.aggregate_predecessor_outputs(
                    node_instance.workflow_run_id, node_instance.node_id
                )
                output_data = input_data

            # Store output
            output_json = json.dumps(output_data)
            output_type = self.storage.select_storage_type(output_json)

            # Get workflow run to extract tenant_id
            workflow_run = await self.run_repo.get_workflow_run(
                "", node_instance.workflow_run_id
            )

            storage_result = await self.storage.store(
                content=output_json,
                content_type="application/json",
                tenant_id=workflow_run.tenant_id if workflow_run else "unknown",
                task_run_id=str(node_instance.id),
                storage_purpose="node-output",
            )

            output_location = storage_result["location"]

            await self.node_repo.save_node_instance_output(
                node_instance.id, output_type, output_location
            )

            # Update status to completed
            await self.node_repo.update_node_instance_status(
                node_instance.id,
                status=WorkflowConstants.Status.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            await self.session.commit()

        except Exception as e:
            # Update status to failed
            await self.node_repo.update_node_instance_status(
                node_instance.id,
                status=WorkflowConstants.Status.FAILED,
                completed_at=datetime.now(UTC),
                error_message=str(e),
            )
            await self.session.commit()
            raise

    async def _execute_node_with_isolated_session(
        self,
        node_instance_id: UUID,
        workflow_run_id: UUID,
        workflow_id: UUID,
    ) -> None:
        """
        Execute a single node instance using its own isolated AsyncSession.

        This is the concurrent-safe execution wrapper.
        SQLAlchemy's AsyncSession does not support concurrent operations on the
        same session.  By creating a fresh session per node we can safely
        asyncio.gather() multiple nodes at once while each node reads and writes
        its own transactional scope.

        The caller (monitor_execution) holds the main session for read-only
        predecessor checks; all node-level writes happen inside this method.

        IMPORTANT: We take workflow_id (a plain UUID) rather than a Workflow ORM
        object.  ORM objects are bound to a specific session/greenlet; passing
        them across asyncio.create_task() boundaries triggers MissingGreenlet
        errors when their lazy-loaded relationships are accessed.  Instead each
        isolated execution reloads the workflow definition from its own session.
        """
        from analysi.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as node_session:
            # Reconstruct a WorkflowExecutor that uses this node's own session
            node_executor = WorkflowExecutor(node_session)

            # Load the node instance by ID from this fresh session
            stmt = select(WorkflowNodeInstance).where(
                WorkflowNodeInstance.id == node_instance_id
            )
            result = await node_session.execute(stmt)
            node_instance = result.scalar_one()

            # Load the workflow from THIS session — do not reuse the caller's ORM object
            # Scope by tenant_id from the workflow run for defense-in-depth
            run_stmt = select(WorkflowRun.tenant_id).where(
                WorkflowRun.id == workflow_run_id
            )
            run_result = await node_session.execute(run_stmt)
            run_tenant = run_result.scalar_one()

            workflow_stmt = (
                select(Workflow)
                .options(selectinload(Workflow.edges), selectinload(Workflow.nodes))
                .where(Workflow.id == workflow_id, Workflow.tenant_id == run_tenant)
            )
            workflow_result = await node_session.execute(workflow_stmt)
            workflow = workflow_result.scalar_one()

            logger.debug(
                "executing_node_isolated_session", node_id=node_instance.node_id
            )
            await node_executor.execute_node_instance(node_instance)
            logger.debug("successfully_executed_node", node_id=node_instance.node_id)

            # Create successor instances within the same isolated session
            logger.debug(
                "creating_successor_instances_for", node_id=node_instance.node_id
            )
            await node_executor._create_successor_instances(
                workflow_run_id, node_instance, workflow
            )
            logger.debug("created_successors_for", node_id=node_instance.node_id)
            # node_session commits are handled by execute_node_instance internally

    async def check_predecessors_complete(
        self, workflow_run_id: UUID, node_id: str
    ) -> bool:
        """
        Check if all predecessor nodes have completed.
        First checks the workflow definition for required predecessors,
        then checks if those predecessors have completed instances.
        """
        # Get the workflow run first (simplified query without tenant filter)
        workflow_run_stmt = select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        workflow_run_result = await self.session.execute(workflow_run_stmt)
        workflow_run = workflow_run_result.scalar_one_or_none()

        if not workflow_run:
            return False

        # Get the workflow definition — scoped to tenant for defense-in-depth
        workflow_stmt = (
            select(Workflow)
            .options(selectinload(Workflow.edges), selectinload(Workflow.nodes))
            .where(
                Workflow.id == workflow_run.workflow_id,
                Workflow.tenant_id == workflow_run.tenant_id,
            )
        )
        workflow_result = await self.session.execute(workflow_stmt)
        workflow = workflow_result.scalar_one_or_none()

        if not workflow:
            return False

        # Find incoming edges to this node in the workflow definition
        incoming_edges = [
            edge for edge in workflow.edges if edge.to_node.node_id == node_id
        ]

        if not incoming_edges:
            return True  # No predecessors defined, ready to execute

        # Get predecessor node IDs from the workflow definition
        predecessor_node_ids = [edge.from_node.node_id for edge in incoming_edges]

        # Check if all predecessor nodes have completed instances
        for pred_node_id in predecessor_node_ids:
            pred_instance = await self.node_repo.get_node_instance_by_node_id(
                workflow_run_id, pred_node_id
            )
            if (
                not pred_instance
                or pred_instance.status != WorkflowConstants.Status.COMPLETED
            ):
                return False

        return True  # All predecessors completed

    async def aggregate_predecessor_outputs(
        self, workflow_run_id: UUID, node_id: str
    ) -> dict[str, Any]:
        """
        Aggregate outputs from multiple predecessors for fan-in.
        """

        predecessors = await self.node_repo.get_predecessor_instances(
            workflow_run_id, node_id
        )

        if not predecessors:
            # No predecessors, return workflow input
            logger.debug(
                "no_predecessors_for_node_getting_workflow_input_da", node_id=node_id
            )

            # First get the workflow run to extract tenant_id
            from sqlalchemy import select

            from analysi.models.workflow_execution import WorkflowRun

            workflow_run_stmt = select(WorkflowRun).where(
                WorkflowRun.id == workflow_run_id
            )
            workflow_run_result = await self.session.execute(workflow_run_stmt)
            workflow_run = workflow_run_result.scalar_one_or_none()

            # Now use the proper repository method with tenant_id
            if workflow_run:
                logger.debug(
                    "found_workflowrun_with_tenantid", tenant_id=workflow_run.tenant_id
                )
                workflow_run = await self.run_repo.get_workflow_run(
                    workflow_run.tenant_id, workflow_run_id
                )

            if workflow_run:
                logger.debug(
                    "workflow_run_found",
                    input_type=workflow_run.input_type,
                    has_input_location=workflow_run.input_location is not None,
                )

                if workflow_run.input_location:
                    logger.debug(
                        "reading_input_from_location",
                        location_preview=workflow_run.input_location[:100],
                    )

                    if workflow_run.input_type == "inline":
                        # For inline storage, input_location contains the JSON directly
                        input_data = json.loads(workflow_run.input_location)
                        logger.debug("parsed_input_data", input_data=input_data)
                        return input_data
                    # For S3 storage, use storage service
                    input_content = await self.storage.retrieve(
                        storage_type=workflow_run.input_type,
                        location=workflow_run.input_location,
                        content_type="application/json",
                    )
                    input_data = json.loads(input_content)
                    logger.debug("retrieved_input_data", input_data=input_data)
                    return input_data
                logger.error("no_input_location_found")
            else:
                logger.error("no_workflow_run_found")

            logger.warning("returning_empty_dict_as_fallback")
            return {}

        # Single predecessor: return consistent envelope format
        if len(predecessors) == 1:
            pred = predecessors[0]
            if pred.output_location:
                logger.debug(
                    "single_predecessor_extracting_result_with_envelope",
                    node_id=pred.node_id,
                )
                output_content = await self.storage.retrieve(
                    storage_type=pred.output_type,
                    location=pred.output_location,
                    content_type="application/json",
                )
                output_data = json.loads(output_content)

                # Extract actual result from envelope if it exists
                if isinstance(output_data, dict) and "result" in output_data:
                    actual_result = output_data["result"]
                    logger.debug("extracted_result", actual_result=actual_result)
                else:
                    actual_result = output_data
                    logger.debug(
                        "debug_no_result_field_using_raw_outputdata",
                        actual_result=actual_result,
                    )

                # Return standard envelope contract (consistent with multi-predecessor)
                return {
                    "node_id": f"single-{node_id}",
                    "context": {},
                    "description": f"Single predecessor result from {pred.node_id}",
                    "result": actual_result,
                }
            logger.warning(
                "single_predecessor_has_no_output_location", node_id=pred.node_id
            )
            return {
                "node_id": f"single-{node_id}",
                "context": {},
                "description": "Empty result - no output location",
                "result": {},
            }

        # Multiple predecessors: return structured dict with predecessors array
        predecessor_outputs = []
        for pred in predecessors:
            if pred.output_location:
                output_content = await self.storage.retrieve(
                    storage_type=pred.output_type,
                    location=pred.output_location,
                    content_type="application/json",
                )
                output_data = json.loads(output_content)

                # Extract actual result from envelope if it exists
                if isinstance(output_data, dict) and "result" in output_data:
                    actual_result = output_data["result"]
                else:
                    actual_result = output_data

                # Add just the result to array (no envelope wrapper)
                # Node identification preserved in execution metadata, not passed to next node
                predecessor_outputs.append(actual_result)

        logger.debug(
            "fanin_aggregation_predecessor_outputs",
            predecessor_outputs_count=len(predecessor_outputs),
        )

        # Return standard envelope contract with aggregated results in 'result' field
        return {
            "node_id": f"aggregation-{node_id}",
            "context": {},
            "description": f"Fan-in aggregation of {len(predecessor_outputs)} predecessors",
            "result": predecessor_outputs,
        }

    async def update_workflow_status(
        self,
        workflow_run_id: UUID,
        status: str,
        error_message: str | None = None,
        llm_usage: dict | None = None,
    ) -> None:
        """
        Update workflow run status.

        When llm_usage is provided it is merged into execution_context under
        key "_llm_usage" — no extra column or migration required.
        """
        update_kwargs = {"status": status}
        if status == WorkflowConstants.Status.RUNNING:
            update_kwargs["started_at"] = datetime.now(UTC)
        elif status in [
            WorkflowConstants.Status.COMPLETED,
            WorkflowConstants.Status.FAILED,
            WorkflowConstants.Status.CANCELLED,
        ]:
            update_kwargs["completed_at"] = datetime.now(UTC)
        # HITL: PAUSED does NOT set completed_at or started_at.
        # It's a suspended state, not a terminal one.
        if error_message:
            update_kwargs["error_message"] = error_message

        await self.run_repo.update_workflow_run_status(
            workflow_run_id, **update_kwargs, tenant_id=self.tenant_id
        )

        if llm_usage is not None:
            await self.run_repo.merge_execution_context(
                workflow_run_id, {"_llm_usage": llm_usage}, tenant_id=self.tenant_id
            )

        await self.session.commit()

    async def _aggregate_llm_usage(self, workflow_run_id: UUID) -> dict | None:
        """
        Sum LLM token/cost data from all task_runs belonging to this workflow run.

        Returns a dict for storing in execution_context["_llm_usage"], or None if
        no task runs used LLM calls.
        """
        stmt = select(TaskRun.execution_context).where(
            TaskRun.workflow_run_id == workflow_run_id
        )
        result = await self.session.execute(stmt)
        total_input = 0
        total_output = 0
        total_tokens = 0
        total_cost: float | None = None
        found_any = False
        for (ctx,) in result:
            raw = (ctx or {}).get("_llm_usage")
            if raw and isinstance(raw, dict):
                found_any = True
                total_input += raw.get("input_tokens", 0)
                total_output += raw.get("output_tokens", 0)
                total_tokens += raw.get("total_tokens", 0)
                cost = raw.get("cost_usd")
                if cost is not None:
                    total_cost = (total_cost or 0.0) + cost
        if not found_any:
            return None
        return {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_tokens": total_tokens,
            "cost_usd": total_cost,
        }

    async def resume_paused_workflow(self, workflow_run_id: UUID) -> None:
        """
        Resume a paused workflow (HITL).

        Resets all paused node instances to PENDING, updates the workflow
        to RUNNING, and re-enters monitor_execution() so the now-pending
        nodes can be picked up and executed.

        The caller (handle_human_responded control event handler) is
        responsible for injecting the human answer into the paused
        TaskRun's checkpoint before calling this method.

        Raises:
            ValueError: If workflow_run_id does not exist or is not paused.
        """
        # Load workflow run
        stmt = select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        result = await self.session.execute(stmt)
        wf_run = result.scalar_one_or_none()

        if wf_run is None:
            raise ValueError(f"WorkflowRun {workflow_run_id} not found")
        if wf_run.status != WorkflowConstants.Status.PAUSED:
            raise ValueError(
                f"WorkflowRun {workflow_run_id} is not paused (status={wf_run.status})"
            )

        # Find all paused nodes and reset them to PENDING
        paused_nodes = await self.node_repo.list_node_instances(
            workflow_run_id, status=WorkflowConstants.Status.PAUSED
        )
        for node in paused_nodes:
            await self.node_repo.update_node_instance_status(
                node.id, WorkflowConstants.Status.PENDING
            )
        await self.session.flush()

        logger.info(
            "workflow_resuming_from_pause",
            workflow_run_id=str(workflow_run_id),
            resumed_nodes=[n.node_id for n in paused_nodes],
        )

        # Re-enter the monitor loop — it will pick up the now-pending nodes
        await self.monitor_execution(workflow_run_id)

    @staticmethod
    async def continue_after_hitl(
        workflow_run_id: UUID,
        node_instance_id: UUID,
        task_result: Any,
    ) -> None:
        """Continue a workflow after a HITL node's task has been resumed.

        HITL: called by ``handle_human_responded`` after
        ``resume_paused_task`` completes.  The task has already re-executed and
        the ``task_result`` holds the outcome.  This method:

        1. Persists the task result (TaskRun status + output).
        2. Updates the node instance (COMPLETED / FAILED / stays PAUSED).
        3. If COMPLETED: stores node output, creates successor instances.
        4. Re-enters ``monitor_execution`` so the remaining DAG continues.

        If the task paused **again** (another HITL in the same script), the
        node and workflow stay PAUSED and a new ``hitl_questions`` row is
        created — the next human answer will trigger another cycle.

        Args:
            workflow_run_id: The paused WorkflowRun UUID.
            node_instance_id: The paused WorkflowNodeInstance UUID.
            task_result: ``TaskExecutionResult`` from ``resume_paused_task``.
        """
        from analysi.db.session import AsyncSessionLocal
        from analysi.schemas.task_execution import TaskExecutionStatus
        from analysi.services.task_run import TaskRunService

        async with AsyncSessionLocal() as session:
            executor = WorkflowExecutor(session)
            task_run_service = TaskRunService()

            # --- Load node instance + workflow definition -----------------
            stmt = select(WorkflowNodeInstance).where(
                WorkflowNodeInstance.id == node_instance_id
            )
            result = await session.execute(stmt)
            node_instance = result.scalar_one()

            wf_run = await executor.run_repo.get_workflow_run_by_id(workflow_run_id)
            executor.tenant_id = wf_run.tenant_id

            # Bug #14 fix: Check workflow is still PAUSED before resuming.
            # If the workflow was cancelled while paused, we should not continue.
            if wf_run.status not in (
                WorkflowConstants.Status.PAUSED,
                WorkflowConstants.Status.RUNNING,
            ):
                logger.warning(
                    "continue_after_hitl_workflow_not_resumable",
                    workflow_run_id=str(workflow_run_id),
                    current_status=wf_run.status,
                )
                # Bug #29 fix: Persist the task result before returning.
                # resume_paused_task already executed the task (setting it to
                # running), so the task_run is stranded in a non-terminal state
                # if we return without persisting.
                final_status = (
                    TaskConstants.Status.COMPLETED
                    if task_result.status == TaskExecutionStatus.COMPLETED
                    else TaskConstants.Status.FAILED
                )
                await task_run_service.update_status(
                    session,
                    task_result.task_run_id,
                    final_status,
                    output_data=task_result.output_data,
                    error_info=(
                        {"error": f"Workflow {wf_run.status}, result discarded"}
                        if final_status == TaskConstants.Status.FAILED
                        else None
                    ),
                    llm_usage=task_result.llm_usage,
                )
                node_instance.status = WorkflowConstants.Status.FAILED
                node_instance.error_message = (
                    f"Workflow was '{wf_run.status}' when HITL resumed — "
                    f"task result discarded"
                )
                node_instance.completed_at = datetime.now(UTC)
                await session.commit()
                return

            workflow_stmt = (
                select(Workflow)
                .options(
                    selectinload(Workflow.edges),
                    selectinload(Workflow.nodes),
                )
                .where(
                    Workflow.id == wf_run.workflow_id,
                    Workflow.tenant_id == wf_run.tenant_id,
                )
            )
            wf_result = await session.execute(workflow_stmt)
            workflow = wf_result.scalar_one()

            # --- Persist the task result ----------------------------------
            if task_result.status == TaskExecutionStatus.COMPLETED:
                await task_run_service.update_status(
                    session,
                    task_result.task_run_id,
                    TaskConstants.Status.COMPLETED,
                    output_data=task_result.output_data,
                    llm_usage=task_result.llm_usage,
                )

                # Build output envelope (via instance to avoid test mock issues)
                output_data = executor._build_task_output_envelope(
                    node_id=node_instance.node_id,
                    task_output=task_result.output_data,
                    llm_usage=task_result.llm_usage,
                    description="Output from HITL-resumed task",
                )

                # Store output
                output_json = json.dumps(output_data)
                output_type = executor.storage.select_storage_type(output_json)
                storage_result = await executor.storage.store(
                    content=output_json,
                    content_type="application/json",
                    tenant_id=wf_run.tenant_id,
                    task_run_id=str(node_instance.id),
                    storage_purpose="node-output",
                )
                await executor.node_repo.save_node_instance_output(
                    node_instance.id,
                    output_type,
                    storage_result["location"],
                )

                # Mark node COMPLETED — clear error_message to remove stale
                # HITL context JSON that was stored when the node paused.
                await executor.node_repo.update_node_instance_status(
                    node_instance.id,
                    WorkflowConstants.Status.COMPLETED,
                    completed_at=datetime.now(UTC),
                    error_message=None,
                )
                await session.commit()

                # Create successor instances (commits internally)
                await executor._create_successor_instances(
                    workflow_run_id, node_instance, workflow
                )

            elif task_result.status == TaskExecutionStatus.PAUSED:
                # Task hit another HITL tool — node + workflow stay PAUSED.
                await task_run_service.update_status(
                    session,
                    task_result.task_run_id,
                    TaskConstants.Status.PAUSED,
                    output_data=task_result.output_data,
                    llm_usage=task_result.llm_usage,
                )
                # Node stays PAUSED (was not reset)

                # Create a new hitl_questions row for the next question
                analysis_id_str = (wf_run.execution_context or {}).get("analysis_id")
                await executor._handle_hitl_pause(
                    session=session,
                    task_result=task_result,
                    node_instance=node_instance,
                    tenant_id=wf_run.tenant_id,
                    workflow_run_id=workflow_run_id,
                    analysis_id_str=analysis_id_str,
                )
                await session.commit()
                logger.info(
                    "continue_after_hitl_task_paused_again",
                    workflow_run_id=str(workflow_run_id),
                    node_instance_id=str(node_instance_id),
                )
                return  # Workflow stays PAUSED — next human answer resumes

            else:
                # Task failed
                error_msg = task_result.error_message or "Task execution failed"
                await task_run_service.update_status(
                    session,
                    task_result.task_run_id,
                    TaskConstants.Status.FAILED,
                    error_info={"error": error_msg},
                    llm_usage=task_result.llm_usage,
                )
                await executor.node_repo.update_node_instance_status(
                    node_instance.id,
                    WorkflowConstants.Status.FAILED,
                    completed_at=datetime.now(UTC),
                    error_message=error_msg,
                )
                await session.commit()

            # Re-enter monitor_execution for remaining nodes.
            # monitor_execution sets workflow to RUNNING and continues the DAG.
            await executor.monitor_execution(workflow_run_id)

    async def monitor_execution(self, workflow_run_id: UUID) -> None:  # noqa: C901
        """
        Main execution monitoring loop.
        Polls for state changes and triggers node execution.
        """
        try:
            logger.info(
                "monitorexecution_starting_for_workflowrunid",
                workflow_run_id=workflow_run_id,
            )
            await self.update_workflow_status(
                workflow_run_id, WorkflowConstants.Status.RUNNING
            )
            logger.debug("updated_workflow_status_to_running")

            # Get workflow blueprint
            logger.debug(
                "getting_workflow_run_with_id", workflow_run_id=workflow_run_id
            )
            # First get the workflow run without tenant filtering - query directly
            workflow_run_stmt = select(WorkflowRun).where(
                WorkflowRun.id == workflow_run_id
            )
            workflow_run_result = await self.session.execute(workflow_run_stmt)
            workflow_run = workflow_run_result.scalar_one_or_none()

            if not workflow_run:
                logger.error(
                    "error_workflowrun_not_found", workflow_run_id=workflow_run_id
                )
                return
            self.tenant_id = workflow_run.tenant_id
            logger.debug(
                "found_workflowrun_workflowid_tenantid",
                workflow_id=workflow_run.workflow_id,
                tenant_id=workflow_run.tenant_id,
            )

            workflow_stmt = (
                select(Workflow)
                .options(
                    selectinload(Workflow.nodes),
                    selectinload(Workflow.edges),
                )
                .where(
                    Workflow.id == workflow_run.workflow_id,
                    Workflow.tenant_id == workflow_run.tenant_id,
                )
            )
            workflow_result = await self.session.execute(workflow_stmt)
            workflow = workflow_result.scalar_one()
            logger.debug("found_workflow", name=workflow.name)

            # Pre-compute plain-data view of the workflow graph so we can reference
            # node IDs after SQLAlchemy expire_all() invalidates the ORM relationships.
            # (After asyncio.create_task + expire_all, lazy-loading ORM relationships
            # in the main session triggers MissingGreenlet errors.)
            nodes_with_outgoing = {edge.from_node.node_id for edge in workflow.edges}
            terminal_node_ids: list[str] = [
                node.node_id
                for node in workflow.nodes
                if node.node_id not in nodes_with_outgoing
            ]

            # Create initial node instances for nodes with no predecessors
            logger.debug(
                "workflow_topology",
                nodes_count=len(workflow.nodes),
                edges_count=len(workflow.edges),
            )

            try:
                for node in workflow.nodes:
                    # Check if node has predecessors
                    has_predecessors = any(
                        edge.to_node.node_id == node.node_id for edge in workflow.edges
                    )
                    logger.debug(
                        "node_haspredecessors",
                        node_id=node.node_id,
                        has_predecessors=has_predecessors,
                    )

                    if not has_predecessors:
                        logger.debug(
                            "creating_initial_instance_for_node", node_id=node.node_id
                        )
                        try:
                            # Check if node instance already exists (prevent duplicates from concurrent execution)
                            existing_instance = (
                                await self.node_repo.get_node_instance_by_node_id(
                                    workflow_run_id, node.node_id
                                )
                            )
                            if existing_instance:
                                logger.debug(
                                    "node_instance_for_already_exists_skipping_creation",
                                    node_id=node.node_id,
                                )
                                continue

                            await self.create_node_instance(
                                workflow_run_id,
                                node.node_id,
                                node.id,
                                template_id=node.node_template_id,
                            )
                            logger.debug(
                                "successfully_created_node_instance_for",
                                node_id=node.node_id,
                            )
                        except Exception as e:
                            # Check if this might be a duplicate key error (race condition)
                            # Even if creation fails, verify if instance now exists
                            existing_after_error = (
                                await self.node_repo.get_node_instance_by_node_id(
                                    workflow_run_id, node.node_id
                                )
                            )
                            if existing_after_error:
                                logger.warning(
                                    "node_instance_for_was_created_by_concurrent_execut",
                                    node_id=node.node_id,
                                )
                                continue
                            logger.error(
                                "error_creating_node_instance_for",
                                node_id=node.node_id,
                                error=str(e),
                            )
                            import traceback

                            traceback.print_exc()
                            raise
            except Exception as e:
                logger.error("error_in_initial_node_creation_phase", error=str(e))
                import traceback

                traceback.print_exc()
                raise

            # Progressive execution loop
            max_iterations = 1000  # Prevent infinite loops
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                logger.debug("execution_loop_iteration", iteration=iteration)

                # Check if any nodes have failed - if so, stop immediately
                failed_nodes = await self.node_repo.list_node_instances(
                    workflow_run_id, status=WorkflowConstants.Status.FAILED
                )
                if failed_nodes:
                    logger.error(
                        "workflow_stopped_failed_nodes",
                        failed_count=len(failed_nodes),
                        failed_nodes=[n.node_id for n in failed_nodes],
                    )
                    llm_usage_on_fail = await self._aggregate_llm_usage(workflow_run_id)
                    # Include the first failed node's error message for better diagnostics
                    first_error = failed_nodes[0].error_message or ""
                    if first_error:
                        fail_msg = f"Failed nodes: {[n.node_id for n in failed_nodes]}. Error: {first_error}"
                    else:
                        fail_msg = f"Failed nodes: {[n.node_id for n in failed_nodes]}"
                    await self.update_workflow_status(
                        workflow_run_id,
                        WorkflowConstants.Status.FAILED,
                        fail_msg,
                        llm_usage=llm_usage_on_fail,
                    )
                    break

                # Get pending node instances
                pending_nodes = await self.node_repo.list_node_instances(
                    workflow_run_id, status=WorkflowConstants.Status.PENDING
                )
                logger.debug(
                    "found_pending_nodes", pending_nodes_count=len(pending_nodes)
                )

                if not pending_nodes:
                    # Check if all nodes are in a terminal state
                    all_nodes = await self.node_repo.list_node_instances(
                        workflow_run_id
                    )
                    if all(
                        node.status
                        in [
                            WorkflowConstants.Status.COMPLETED,
                            WorkflowConstants.Status.FAILED,
                            WorkflowConstants.Status.PAUSED,
                        ]
                        for node in all_nodes
                    ):
                        llm_usage_final = await self._aggregate_llm_usage(
                            workflow_run_id
                        )
                        failed_nodes = [
                            node
                            for node in all_nodes
                            if node.status == WorkflowConstants.Status.FAILED
                        ]
                        paused_nodes = [
                            node
                            for node in all_nodes
                            if node.status == WorkflowConstants.Status.PAUSED
                        ]
                        if failed_nodes:
                            # FAILED takes precedence over PAUSED
                            first_error = failed_nodes[0].error_message or ""
                            if first_error:
                                fail_msg = f"Failed nodes: {[n.node_id for n in failed_nodes]}. Error: {first_error}"
                            else:
                                fail_msg = (
                                    f"Failed nodes: {[n.node_id for n in failed_nodes]}"
                                )
                            await self.update_workflow_status(
                                workflow_run_id,
                                WorkflowConstants.Status.FAILED,
                                fail_msg,
                                llm_usage=llm_usage_final,
                            )
                        elif paused_nodes:
                            # HITL: some nodes paused, none failed.
                            # Workflow suspends until human responds.
                            logger.info(
                                "workflow_paused_for_hitl",
                                workflow_run_id=str(workflow_run_id),
                                paused_nodes=[n.node_id for n in paused_nodes],
                            )
                            await self.update_workflow_status(
                                workflow_run_id,
                                WorkflowConstants.Status.PAUSED,
                                llm_usage=llm_usage_final,
                            )
                        else:
                            # All nodes completed — capture output and mark done
                            await self._capture_workflow_output(
                                workflow_run_id, terminal_node_ids
                            )
                            await self.update_workflow_status(
                                workflow_run_id,
                                WorkflowConstants.Status.COMPLETED,
                                llm_usage=llm_usage_final,
                            )
                        break

                # Identify ready nodes (sequential read-only predecessor checks)
                ready_nodes = []
                for node_instance in pending_nodes:
                    logger.debug(
                        "checking_node_for_execution_readiness",
                        node_id=node_instance.node_id,
                    )
                    if await self.check_predecessors_complete(
                        workflow_run_id, node_instance.node_id
                    ):
                        ready_nodes.append(node_instance)
                    else:
                        logger.debug(
                            "node_not_ready_predecessors_not_complete",
                            node_id=node_instance.node_id,
                        )

                if ready_nodes:
                    # Launch all ready nodes concurrently.
                    # Each node executes with its own isolated AsyncSession so that
                    # SQLAlchemy's AsyncSession constraint (no concurrent operations on
                    # one session) is respected.  The main session is used only for the
                    # read-only predecessor checks above and the post-gather state reads.
                    #
                    # We use asyncio.create_task() + asyncio.gather() rather than
                    # plain gather() on bare coroutines.  asyncio.create_task() schedules
                    # each coroutine as a proper Task, giving each one its own asyncio
                    # execution context — required by SQLAlchemy/asyncpg whose greenlet
                    # machinery expects each async database connection to run in a Task
                    # context, not as an inline coroutine nested inside gather().
                    logger.debug(
                        "launching_ready_nodes_concurrently",
                        ready_nodes_count=len(ready_nodes),
                    )
                    tasks = [
                        asyncio.create_task(
                            self._execute_node_with_isolated_session(
                                node_instance.id, workflow_run_id, workflow.id
                            )
                        )
                        for node_instance in ready_nodes
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Process gather results: log errors and mark failed nodes.
                    # Partial failure: other branches complete normally; the loop will
                    # detect failed nodes on the next iteration and stop the workflow.
                    for node_instance, result in zip(
                        ready_nodes, results, strict=False
                    ):
                        if isinstance(result, BaseException):
                            logger.error(
                                "error_executing_node",
                                node_id=node_instance.node_id,
                                result=result,
                            )
                            import traceback

                            traceback.print_exc()
                            # Mark node as failed in DB so the loop picks it up
                            try:
                                await self.node_repo.update_node_instance_status(
                                    node_instance.id,
                                    WorkflowConstants.Status.FAILED,
                                    error_message=str(result),
                                )
                                await self.session.commit()
                            except Exception:
                                pass  # Best-effort; loop will catch the failure state
                        else:
                            logger.debug(
                                "node_completed_successfully",
                                node_id=node_instance.node_id,
                            )

                    # Expire so next iteration sees fresh DB state written by isolated sessions
                    self.session.expire_all()
                else:
                    # No ready nodes but pending nodes exist — check for stall.
                    # If nothing is RUNNING, the workflow is stalled.
                    # HITL: stall caused by paused predecessors
                    # means the workflow should pause, not spin forever.
                    running_nodes = await self.node_repo.list_node_instances(
                        workflow_run_id, status=WorkflowConstants.Status.RUNNING
                    )
                    if not running_nodes:
                        # Nothing running, nothing ready — workflow is stalled.
                        # Check if any nodes are paused (HITL cause).
                        all_nodes = await self.node_repo.list_node_instances(
                            workflow_run_id
                        )
                        paused_nodes = [
                            n
                            for n in all_nodes
                            if n.status == WorkflowConstants.Status.PAUSED
                        ]
                        if paused_nodes:
                            logger.info(
                                "workflow_stalled_by_paused_nodes",
                                workflow_run_id=str(workflow_run_id),
                                paused_nodes=[n.node_id for n in paused_nodes],
                                pending_nodes=[n.node_id for n in pending_nodes],
                            )
                            llm_usage_stall = await self._aggregate_llm_usage(
                                workflow_run_id
                            )
                            await self.update_workflow_status(
                                workflow_run_id,
                                WorkflowConstants.Status.PAUSED,
                                llm_usage=llm_usage_stall,
                            )
                            break
                    await asyncio.sleep(self.polling_interval)

        except Exception as e:
            await self.update_workflow_status(
                workflow_run_id, WorkflowConstants.Status.FAILED, str(e)
            )

    async def _create_successor_instances(
        self,
        workflow_run_id: UUID,
        completed_node: WorkflowNodeInstance,
        workflow: Workflow,
    ) -> None:
        """Create instances for successor nodes.

        Race-safety:
          When multiple fan-out branches complete concurrently, they each call
          this method from isolated sessions.  Without protection, both sessions
          could see "no successor exists" and both INSERT a duplicate node
          instance for the same successor (TOCTOU race).

          We prevent this with a PostgreSQL advisory lock keyed on
          (workflow_run_id, successor_node_id).  Advisory locks serialise
          the check-then-create sequence across concurrent sessions without
          blocking unrelated work.  The lock is transaction-scoped and
          released automatically on commit/rollback.
        """
        from sqlalchemy import text

        # Find edges from this node
        outgoing_edges = [
            edge
            for edge in workflow.edges
            if edge.from_node.node_id == completed_node.node_id
        ]

        for edge in outgoing_edges:
            successor_node_id = edge.to_node.node_id

            # Acquire a transaction-scoped advisory lock to serialise
            # successor creation across concurrent sessions.
            # pg_advisory_xact_lock takes a bigint key; we derive one
            # from the workflow_run_id and successor node_id.
            lock_key = hash((str(workflow_run_id), successor_node_id)) % (2**63)
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": lock_key},
            )

            # Now, within the lock, check if the successor already exists.
            # Because the lock serialises this section, only ONE session
            # can reach the INSERT for a given (workflow_run_id, node_id).
            existing_instance = await self.node_repo.get_node_instance_by_node_id(
                workflow_run_id, successor_node_id
            )

            if existing_instance:
                # Another session already created this successor — just create
                # the edge instance linking our completed node to it.
                await self.edge_repo.create_edge_instance(
                    workflow_run_id=workflow_run_id,
                    edge_id=edge.edge_id,
                    edge_uuid=edge.id,
                    from_instance_id=completed_node.id,
                    to_instance_id=existing_instance.id,
                )
                continue

            # Find the node definition
            successor_node = next(
                (node for node in workflow.nodes if node.node_id == successor_node_id),
                None,
            )

            if successor_node:
                # Create successor node instance
                successor_instance = await self.create_node_instance(
                    workflow_run_id,
                    successor_node.node_id,
                    successor_node.id,
                    template_id=successor_node.node_template_id,
                )

                # Create edge instance to track data flow
                await self.edge_repo.create_edge_instance(
                    workflow_run_id=workflow_run_id,
                    edge_id=edge.edge_id,
                    edge_uuid=edge.id,
                    from_instance_id=completed_node.id,
                    to_instance_id=successor_instance.id,
                )

        # Commit edges (and any "edge-only" rows from the existing-successor path).
        # Node instances are already committed by create_node_instance(), but edges
        # created after that call are only flushed — they need an explicit commit.
        await self.session.commit()

    @staticmethod
    async def _start_background_execution_static(workflow_run_id: UUID) -> None:
        """
        Start background execution with a fresh database session.
        This runs in a separate async task to avoid session conflicts.
        """
        try:
            logger.info(
                "starting_background_execution_for_workflowrunid",
                workflow_run_id=workflow_run_id,
            )
            # Import here to avoid circular imports
            from analysi.db.session import AsyncSessionLocal

            # Create new session for background execution
            logger.info("Creating new database session for background execution")
            async with AsyncSessionLocal() as background_session:
                logger.info("Created background session, creating WorkflowExecutor")
                background_executor = WorkflowExecutor(background_session)
                logger.info("Starting monitor_execution")
                await background_executor.monitor_execution(workflow_run_id)
                logger.info("monitor_execution completed, committing session")
                await background_session.commit()
        except Exception as e:
            # Log error but don't raise - background task shouldn't crash main thread
            logger.exception("background_workflow_execution_failed", error=str(e))

    async def _capture_workflow_output(
        self, workflow_run_id: UUID, terminal_node_ids: list[str]
    ) -> None:
        """
        Capture the final output from terminal nodes and store as workflow output.

        Args:
            terminal_node_ids: Pre-computed list of terminal node IDs (nodes with no
                outgoing edges).  Passed as plain strings to avoid accessing ORM
                relationships after expire_all() / asyncio.create_task() usage.
        """
        try:
            logger.debug("capturing_workflow_output", workflow_run_id=workflow_run_id)

            logger.debug(
                "found_terminal_nodes",
                terminal_node_ids_count=len(terminal_node_ids),
                terminal_node_ids=terminal_node_ids,
            )

            if not terminal_node_ids:
                logger.debug("no_terminal_nodes_found")
                return

            # For single terminal node, use its output directly
            if len(terminal_node_ids) == 1:
                terminal_node_id = terminal_node_ids[0]
                logger.debug("single_terminal_node", terminal_node_id=terminal_node_id)

                # Get the node instance by node_id
                node_instance = await self.node_repo.get_node_instance_by_node_id(
                    workflow_run_id, terminal_node_id
                )

                logger.debug("found_node_instance", node_instance=node_instance)

                if (
                    node_instance
                    and node_instance.status == WorkflowConstants.Status.COMPLETED
                ):
                    logger.debug(
                        "found_completed_node_instance",
                        output_type=node_instance.output_type,
                    )

                    # Read the output data from storage (same pattern as workflow router)
                    output_data = None
                    if (
                        node_instance.output_location
                        and node_instance.output_type == "inline"
                    ):
                        output_data = json.loads(node_instance.output_location)

                    logger.debug("parsed_outputdata", output_data=output_data)

                    # Extract the result from the envelope structure for API compatibility
                    # Tests expect direct access to result fields, not wrapped in envelope
                    if isinstance(output_data, dict) and "result" in output_data:
                        workflow_output = output_data["result"]
                    else:
                        workflow_output = output_data

                    logger.debug(
                        "setting_workflow_outputdata_to",
                        workflow_output=workflow_output,
                    )

                    # Store the output using inline storage (same pattern as task execution)
                    await self.run_repo.update_workflow_run_status(
                        workflow_run_id,
                        status=WorkflowConstants.Status.RUNNING,  # Keep current status, will be set to completed later
                        output_type="inline",
                        output_location=json.dumps(workflow_output),
                        tenant_id=self.tenant_id,
                    )
                    await self.session.commit()
                else:
                    logger.debug(
                        "no_completed_instance_found_for_terminal_node",
                        terminal_node_id=terminal_node_id,
                    )
            else:
                # Multiple terminal nodes - combine their outputs
                combined_output = {}
                for terminal_node_id in terminal_node_ids:
                    node_instance = await self.node_repo.get_node_instance_by_node_id(
                        workflow_run_id, terminal_node_id
                    )
                    if (
                        node_instance
                        and node_instance.status == WorkflowConstants.Status.COMPLETED
                    ):
                        # Read the output data from storage
                        output_data = None
                        if (
                            node_instance.output_location
                            and node_instance.output_type == "inline"
                        ):
                            output_data = json.loads(node_instance.output_location)

                        # Extract the result from envelope for each terminal node
                        if isinstance(output_data, dict) and "result" in output_data:
                            combined_output[terminal_node_id] = output_data["result"]
                        else:
                            combined_output[terminal_node_id] = output_data

                logger.debug(
                    "setting_combined_workflow_output", combined_output=combined_output
                )
                await self.run_repo.update_workflow_run_status(
                    workflow_run_id,
                    status=WorkflowConstants.Status.RUNNING,  # Keep current status, will be set to completed later
                    output_type="inline",
                    output_location=json.dumps(combined_output),
                    tenant_id=self.tenant_id,
                )
                await self.session.commit()

        except Exception as e:
            logger.error("error_capturing_workflow_output", error=str(e))
            import traceback

            traceback.print_exc()
            # Don't re-raise - let the workflow complete without output_data
            # This prevents the entire workflow from failing due to output capture issues

    # Workflow execution is handled by ARQ jobs — ARQ naturally dequeues
    # after the API transaction commits.

    @staticmethod
    async def _execute_workflow_synchronously(
        workflow_run_id: UUID, session: AsyncSession | None = None
    ) -> None:
        """
        Execute a workflow synchronously with provided or fresh database session.
        This fixes session isolation issues by using the correct session.

        IMPORTANT: This respects Decision #2 - if workflow is already running/completed,
        skip execution to avoid duplicate processing (tests use manual execution).

        Args:
            workflow_run_id: UUID of the workflow run to execute
            session: Optional session to use (for tests), creates new one if None
        """
        logger.info(
            "starting_synchronous_execution_for_workflowrunid",
            workflow_run_id=workflow_run_id,
        )

        if session:
            # Use provided session (typically for tests)
            logger.debug("using_provided_session_for_sync_execution")
            executor = WorkflowExecutor(session)
            await executor.monitor_execution(workflow_run_id)
            # Don't commit - let the caller handle it
        else:
            # Create fresh session for production
            from analysi.db.session import get_db

            # Use the same session pattern as the rest of the application
            async for fresh_session in get_db():
                try:
                    from sqlalchemy import text

                    # Check if workflow is already running/completed
                    result = await fresh_session.execute(
                        text("SELECT id, status FROM workflow_runs WHERE id = :id"),
                        {"id": str(workflow_run_id)},
                    )
                    our_run = result.fetchone()

                    # IMPORTANT: Check if workflow is already running or completed
                    # This prevents duplicate execution when tests use manual execution (Decision #2)
                    if (
                        our_run
                        and our_run.status
                        in [
                            WorkflowConstants.Status.RUNNING,
                            WorkflowConstants.Status.COMPLETED,
                            WorkflowConstants.Status.FAILED,
                            WorkflowConstants.Status.PAUSED,  # HITL — resume uses explicit resume_paused_workflow()
                        ]
                    ):
                        logger.debug(
                            "workflow_already_executed_skipping",
                            workflow_run_id=workflow_run_id,
                            status=our_run.status,
                        )
                        return

                    # Create a new executor with the fresh session
                    executor = WorkflowExecutor(fresh_session)

                    # Start monitoring with the fresh session
                    await executor.monitor_execution(workflow_run_id)

                    # Session commit is handled by get_db
                    break  # Exit the async generator loop

                except Exception as e:
                    logger.error("error_in_synchronous_execution", error=str(e))
                    # Update workflow status to failed
                    try:
                        run_repo = WorkflowRunRepository(fresh_session)
                        # executor.tenant_id is set by monitor_execution when the run loads;
                        # pass it if available so the UPDATE includes the tenant_id filter.
                        run_tenant_id = getattr(executor, "tenant_id", None)
                        await run_repo.update_workflow_run_status(
                            workflow_run_id,
                            status=WorkflowConstants.Status.FAILED,
                            completed_at=datetime.now(UTC),
                            error_message=str(e),
                            tenant_id=run_tenant_id,
                        )
                        # get_db will handle rollback
                    except Exception as update_error:
                        logger.error(
                            "error_updating_workflow_status", error=str(update_error)
                        )
                    raise


def _validate_template_ast(code: str) -> None:
    """Validate template code AST to block sandbox escape vectors.

    Rejects code that:
    - Accesses dunder attributes (__class__, __bases__, __subclasses__, etc.)
    - Uses import statements
    - Calls exec(), eval(), compile(), or globals()/locals()
    """
    import ast

    _BLOCKED_NAMES = frozenset(
        {
            "exec",
            "eval",
            "compile",
            "__import__",
            "globals",
            "locals",
            "vars",
            "dir",
            "getattr",
            "setattr",
            "delattr",
            "breakpoint",
            "open",
            "input",
        }
    )

    try:
        # Parse as a function body by wrapping
        indented = "\n".join(f"    {line}" for line in code.split("\n"))
        tree = ast.parse(f"def _check():\n{indented}")
    except SyntaxError as e:
        raise ValueError(f"Template syntax error: {e}") from e

    for node in ast.walk(tree):
        # Block import statements
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise ValueError("Template code must not use import statements")

        # Block ALL dunder attribute access except a small allowlist.
        # Allowlist approach prevents bypass via obscure dunders like
        # __getattribute__, __init_subclass__, etc.
        _ALLOWED_DUNDERS = frozenset(
            {
                "__name__",  # type(x).__name__ used in system_merge template
            }
        )
        if (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("__")
            and node.attr.endswith("__")
            and node.attr not in _ALLOWED_DUNDERS
        ):
            raise ValueError(
                f"Template code must not access dunder attributes: {node.attr}"
            )

        # Block calls to dangerous builtins: exec(), eval(), etc.
        if isinstance(node, ast.Name) and node.id in _BLOCKED_NAMES:
            raise ValueError(f"Template code must not use '{node.id}'")


class TransformationNodeExecutor:
    """
    Executes transformation nodes with Python templates.
    Provides secure sandboxed execution environment.
    """

    def __init__(self) -> None:
        self.sandbox = None  # Will use RestrictedPython or similar

    async def execute_template(
        self,
        code: str,
        input_data: Any,
        envelope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute Python template code in sandbox.

        Templates are written as function bodies with 'return' statements.
        Input data is available as 'inp' parameter (simplified - just the result content).
        Full envelope is available as 'workflow_input' parameter.

        Args:
            code: Python code (function body) to execute
            input_data: Input available as 'inp' parameter (simplified)
            envelope: Full envelope available as 'workflow_input' parameter

        Returns:
            Execution result wrapped in envelope
        """
        # Validate template code via AST before execution to block
        # sandbox escape vectors (e.g., __subclasses__() → import os).
        _validate_template_ast(code)

        # Restricted builtins — getattr/setattr/delattr are excluded because
        # they enable sandbox escape via dunder attribute introspection.
        # AST validation blocks dunder access (e.g., __subclasses__) even
        # though type() is allowed for legitimate type comparisons.
        safe_globals = {
            "__builtins__": {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "sum": sum,
                "max": max,
                "min": min,
                "abs": abs,
                "round": round,
                "enumerate": enumerate,
                "isinstance": isinstance,
                "type": type,
                "bool": bool,
                "range": range,
                "sorted": sorted,
                "reversed": reversed,
                "zip": zip,
                "map": map,
                "filter": filter,
                "any": any,
                "all": all,
                # Exceptions for error handling in templates
                "ValueError": ValueError,
                "TypeError": TypeError,
                "KeyError": KeyError,
                "IndexError": IndexError,
            }
        }

        # Wrap template code in a function to allow return statements
        indented_code = "\n".join(f"    {line}" for line in code.split("\n"))
        function_code = f"""
def template_function(inp, workflow_input=None):
{indented_code}
"""

        # Execute the function definition
        local_vars: dict[str, Any] = {}
        exec(function_code, safe_globals, local_vars)  # nosec B102

        # Call the function with input data and optional envelope
        result = local_vars["template_function"](input_data, envelope)

        # Check if result contains an error (similar to task execution fix)
        # This happens when template code catches errors and returns error dicts
        if isinstance(result, dict) and "error" in result:
            error_message = result.get("error", "Unknown transformation error")
            raise ValueError(f"Transformation produced error output: {error_message}")

        # Return result wrapped in envelope
        return self.build_envelope("transformation", result)

    def build_envelope(
        self,
        node_id: str,
        result: Any,
        context: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Build standard envelope structure for node output.

        Returns:
            {
                "node_id": str,
                "context": dict,
                "description": str,
                "result": Any
            }
        """
        return {
            "node_id": node_id,
            "context": context or {},
            "description": description or f"Output from {node_id}",
            "result": result,
        }

    def validate_output_schema(
        self, output: dict[str, Any], schema: dict[str, Any]
    ) -> bool:
        """
        Validate output against JSON schema using the jsonschema library.

        This provides robust validation including:
        - All JSON Schema features (required, additionalProperties, etc.)
        - Proper type checking (including boolean, null, integer vs number)
        - Nested object and array validation
        - Format validation (email, date, URI, etc.) if format checkers enabled
        - Union types and complex schemas

        Args:
            output: The data to validate
            schema: The JSON schema to validate against

        Returns:
            True if output is valid according to schema, False otherwise
        """
        try:
            from jsonschema import ValidationError, validate

            validate(instance=output, schema=schema)
            return True
        except ValidationError:
            # Invalid according to schema
            return False
        except Exception:
            # Any other error (malformed schema, etc.)
            return False


class WorkflowExecutionService:
    """
    High-level service coordinating workflow execution.
    """

    def __init__(self) -> None:
        """Initialize service without session - session passed per method."""
        self.transformation_executor = TransformationNodeExecutor()

    async def start_workflow(
        self,
        session: AsyncSession,
        tenant_id: str,
        workflow_id: UUID,
        input_data: Any,
        execution_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Start workflow execution and return run information.

        Args:
            session: Database session
            tenant_id: Tenant identifier
            workflow_id: Workflow to execute
            input_data: Raw input data (NOT envelope format - that's only for data_samples)
            execution_context: Optional context (e.g., analysis_id for artifact linking)

        Returns:
            {
                "workflow_run_id": UUID,
                "status": "pending",
                "message": "Workflow execution initiated"
            }

        Raises:
            ValueError: If workflow not found or input validation fails
        """
        # First validate that the workflow exists
        workflow_stmt = select(Workflow).where(
            Workflow.id == workflow_id, Workflow.tenant_id == tenant_id
        )
        workflow_result = await session.execute(workflow_stmt)
        workflow = workflow_result.scalar_one_or_none()

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Validate input against workflow io_schema if defined (best-effort, non-blocking)
        if workflow.io_schema and "input" in workflow.io_schema:
            try:
                from jsonschema import ValidationError
                from jsonschema import validate as jsonschema_validate

                jsonschema_validate(
                    instance=input_data, schema=workflow.io_schema["input"]
                )
            except ValidationError as e:
                # Log warning but don't fail - alerts may have null/missing fields
                logger.warning(
                    "workflow_input_validation_mismatch",
                    workflow_id=str(workflow_id),
                    error=e.message,
                    path=".".join(str(p) for p in e.path),
                    message="Input doesn't match io_schema, proceeding anyway",
                )
            except Exception as e:
                # Log warning but don't fail - schema validation is best-effort
                logger.warning(
                    "workflow_input_validation_error",
                    workflow_id=str(workflow_id),
                    error=str(e),
                    message="Failed to validate input against io_schema, proceeding anyway",
                )

        executor = WorkflowExecutor(session)
        workflow_run_id = await executor.execute_workflow(
            tenant_id, workflow_id, input_data, execution_context
        )

        return {
            "workflow_run_id": workflow_run_id,
            "status": WorkflowConstants.Status.PENDING,
            "message": "Workflow execution initiated",
        }

    async def get_workflow_run_status(
        self, session: AsyncSession, tenant_id: str, workflow_run_id: UUID
    ) -> dict[str, Any]:
        """
        Get lightweight workflow run status.
        """
        run_repo = WorkflowRunRepository(session)
        workflow_run = await run_repo.get_workflow_run(tenant_id, workflow_run_id)

        if not workflow_run:
            return {"error": "Workflow run not found"}

        return {
            "workflow_run_id": str(workflow_run.id),
            "status": workflow_run.status,
            "created_at": (
                workflow_run.created_at.isoformat() if workflow_run.created_at else None
            ),
            "updated_at": (
                workflow_run.updated_at.isoformat() if workflow_run.updated_at else None
            ),
            "started_at": (
                workflow_run.started_at.isoformat() if workflow_run.started_at else None
            ),
            "completed_at": (
                workflow_run.completed_at.isoformat()
                if workflow_run.completed_at
                else None
            ),
            "error_message": workflow_run.error_message,
        }

    async def get_workflow_run_details(
        self, session: AsyncSession, tenant_id: str, workflow_run_id: UUID
    ) -> WorkflowRun | None:
        """
        Get full workflow run details with input/output.
        """
        run_repo = WorkflowRunRepository(session)
        return await run_repo.get_workflow_run(tenant_id, workflow_run_id)

    async def get_workflow_run_graph(
        self, session: AsyncSession, tenant_id: str, workflow_run_id: UUID
    ) -> dict[str, Any]:
        """
        Get materialized execution graph for visualization.

        Returns:
            {
                "workflow_run_id": UUID,
                "is_complete": bool,
                "snapshot_at": datetime,
                "nodes": List[node_instances],
                "edges": List[edge_instances]
            }
        """
        node_repo = WorkflowNodeInstanceRepository(session)
        edge_repo = WorkflowEdgeInstanceRepository(session)
        run_repo = WorkflowRunRepository(session)

        # Get workflow run status — tenant-scoped lookup enforces isolation
        workflow_run = await run_repo.get_workflow_run(tenant_id, workflow_run_id)
        if workflow_run is None:
            return None
        workflow_run_status = workflow_run.status

        # Get all node instances (safe: tenant ownership verified above)
        nodes = await node_repo.list_node_instances(workflow_run_id)

        # Get all edge instances
        edge_instances = []
        for node in nodes:
            outgoing = await edge_repo.get_outgoing_edges(workflow_run_id, node.id)
            edge_instances.extend(outgoing)

        # Check completion:
        # 1. Workflow run is in terminal state (failed, completed, cancelled), OR
        # 2. We have nodes AND all instantiated nodes are finished
        workflow_in_terminal_state = workflow_run_status in [
            WorkflowConstants.Status.COMPLETED,
            WorkflowConstants.Status.FAILED,
            WorkflowConstants.Status.CANCELLED,
        ]
        all_nodes_finished = len(nodes) > 0 and all(
            node.status
            in [
                WorkflowConstants.Status.COMPLETED,
                WorkflowConstants.Status.FAILED,
                WorkflowConstants.Status.CANCELLED,
            ]
            for node in nodes
        )
        is_complete = workflow_in_terminal_state or all_nodes_finished

        return {
            "workflow_run_id": str(workflow_run_id),
            "is_complete": is_complete,
            "status": workflow_run_status,
            "snapshot_at": datetime.now(UTC).isoformat(),
            "nodes": [
                {
                    "id": str(node.id),
                    "node_id": node.node_id,
                    "status": node.status,
                    "started_at": (
                        node.started_at.isoformat() if node.started_at else None
                    ),
                    "completed_at": (
                        node.completed_at.isoformat() if node.completed_at else None
                    ),
                    "error_message": node.error_message,
                }
                for node in nodes
            ],
            "edges": [
                {
                    "id": str(edge.id),
                    "workflow_run_id": str(edge.workflow_run_id),
                    "edge_id": edge.edge_id,
                    "edge_uuid": str(edge.edge_uuid),
                    "from_instance_id": str(edge.from_instance_id),
                    "to_instance_id": str(edge.to_instance_id),
                    "delivered_at": (
                        edge.delivered_at.isoformat() if edge.delivered_at else None
                    ),
                    "created_at": edge.created_at.isoformat(),
                }
                for edge in edge_instances
            ],
        }

    async def cancel_workflow_run(
        self, session: AsyncSession, tenant_id: str, workflow_run_id: UUID
    ) -> bool:
        """
        Cancel a running workflow.
        """
        run_repo = WorkflowRunRepository(session)
        node_repo = WorkflowNodeInstanceRepository(session)

        # Get workflow run
        workflow_run = await run_repo.get_workflow_run(tenant_id, workflow_run_id)
        if not workflow_run or workflow_run.status not in [
            WorkflowConstants.Status.PENDING,
            WorkflowConstants.Status.RUNNING,
        ]:
            return False

        # Update workflow status
        await run_repo.update_workflow_run_status(
            workflow_run_id,
            status=WorkflowConstants.Status.CANCELLED,
            completed_at=datetime.now(UTC),
            tenant_id=tenant_id,
        )

        # Cancel running node instances
        running_nodes = await node_repo.list_node_instances(
            workflow_run_id, status=WorkflowConstants.Status.RUNNING
        )
        for node in running_nodes:
            await node_repo.update_node_instance_status(
                node.id,
                status=WorkflowConstants.Status.CANCELLED,
                completed_at=datetime.now(UTC),
            )

        await session.commit()
        return True

    async def list_workflow_runs(
        self,
        session: AsyncSession,
        tenant_id: str,
        workflow_id: UUID,
        limit: int = 20,
    ) -> list[WorkflowRun]:
        """List execution history for a workflow."""
        run_repo = WorkflowRunRepository(session)
        runs, _total = await run_repo.list_workflow_runs(
            tenant_id, workflow_id, limit=limit
        )
        return runs
