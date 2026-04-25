"""
Workflow Composer Service - Main orchestrator for type-safe workflow composition.

Coordinates parsing, resolution, validation, and workflow creation.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.settings import settings
from analysi.schemas.audit_context import AuditContext

from .builder import ComposerWorkflowBuilder
from .models import (
    CompositionError,
    CompositionPlan,
    CompositionResult,
    CompositionWarning,
    ParsedComposition,
    Question,
    ResolvedTask,
    ResolvedTemplate,
)
from .parser import CompositionParser
from .questions import QuestionGenerator
from .resolvers import TEMPLATE_SHORTCUTS, TaskResolver, TemplateResolver
from .validators import SchemaValidator, StructuralValidator


class WorkflowComposerService:
    """
    Orchestrate intelligent workflow composition.

    Workflow:
    1. Parse composition array → graph structure
    2. Resolve cy_names → tasks, shortcuts → templates
    3. Validate structure (DAG, reachability)
    4. Validate schemas (type compatibility)
    5. Generate questions if needed
    6. Build workflow if approved
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize WorkflowComposerService.

        Args:
            session: Database session
        """
        self.session = session
        self.parser = CompositionParser()
        self.task_resolver = TaskResolver(session)
        self.template_resolver = TemplateResolver(session)
        self.structural_validator = StructuralValidator()
        self.schema_validator = SchemaValidator(session)
        self.question_generator = QuestionGenerator()
        self.builder = ComposerWorkflowBuilder(session)

    async def compose_workflow(
        self,
        composition: list[Any],
        workflow_name: str,
        workflow_description: str,
        tenant_id: str,
        created_by: str,
        execute: bool = False,
        audit_context: AuditContext | None = None,
        data_samples: list[dict[str, Any]] | None = None,
    ) -> CompositionResult:
        """
        Compose workflow from array format.

        Args:
            composition: Array of cy_names, shortcuts, or nested arrays
            workflow_name: Name for created workflow
            workflow_description: Description for created workflow
            tenant_id: Tenant ID
            created_by: Creator username
            execute: If True, create workflow; if False, return plan only
            audit_context: Optional audit context for logging
            data_samples: Optional data samples for workflow testing.
                         Pass the triggering alert as a sample for proper testing.

        Returns:
            CompositionResult with status, errors, warnings, questions, or workflow_id
        """
        all_errors: list[CompositionError] = []
        all_warnings: list[CompositionWarning] = []
        all_questions: list[Question] = []
        workflow_id: UUID | None = None
        plan: CompositionPlan | None = None

        # Step 1: Parse composition
        parsed_composition, parse_errors = await self._parse_composition(composition)
        all_errors.extend(parse_errors)

        if parsed_composition is None or parse_errors:
            # Parsing failed
            return CompositionResult(
                status="error",
                workflow_id=None,
                errors=all_errors,
                warnings=all_warnings,
                questions=all_questions,
                plan=None,
            )

        # Step 2: Resolve nodes
        resolved_nodes, resolve_errors, resolve_questions = await self._resolve_nodes(
            parsed_composition, tenant_id
        )
        all_errors.extend(resolve_errors)
        all_questions.extend(resolve_questions)

        if resolve_errors:
            # Resolution failed
            return CompositionResult(
                status="error",
                workflow_id=None,
                errors=all_errors,
                warnings=all_warnings,
                questions=all_questions,
                plan=None,
            )

        # Step 3: Validate composition
        (
            validation_errors,
            validation_warnings,
            validation_questions,
            input_schema,
            output_schema,
        ) = await self._validate_composition(
            parsed_composition, resolved_nodes, tenant_id
        )
        all_errors.extend(validation_errors)
        all_warnings.extend(validation_warnings)
        all_questions.extend(validation_questions)

        # Create plan
        node_details = [
            {
                "node_id": node.node_id,
                "reference": node.reference,
                "layer": node.layer,
                "parallel_group": node.parallel_group,
            }
            for node in parsed_composition.nodes
        ]

        plan = CompositionPlan(
            nodes=len(parsed_composition.nodes),
            edges=len(parsed_composition.edges),
            inferred_input_schema=input_schema,
            inferred_output_schema=output_schema,
            node_details=node_details,
        )

        # Determine status
        if all_errors:
            status = "error"
        elif all_questions:
            status = "needs_decision"
        else:
            status = "success"

        # Step 4: Build workflow if execute=True and no blockers
        if execute and status == "success":
            try:
                workflow_id = await self._build_workflow(
                    parsed_composition=parsed_composition,
                    resolved_nodes=resolved_nodes,
                    workflow_name=workflow_name,
                    workflow_description=workflow_description,
                    tenant_id=tenant_id,
                    created_by=created_by,
                    input_schema=input_schema,
                    output_schema=output_schema,
                    audit_context=audit_context,
                    data_samples=data_samples,
                )
            except Exception as e:
                all_errors.append(
                    CompositionError(
                        error_type="build_error",
                        message=f"Failed to build workflow: {e!s}",
                        context={},
                    )
                )
                status = "error"

        return CompositionResult(
            status=status,
            workflow_id=workflow_id,
            errors=all_errors,
            warnings=all_warnings,
            questions=all_questions,
            plan=plan,
        )

    async def compose_workflow_plan(
        self,
        composition: list[Any],
        tenant_id: str,
    ) -> CompositionResult:
        """
        Generate plan without creating workflow.

        Args:
            composition: Array of cy_names, shortcuts, or nested arrays
            tenant_id: Tenant ID

        Returns:
            CompositionResult with plan showing what would be created
        """
        # Call compose_workflow with execute=False and dummy names
        return await self.compose_workflow(
            composition=composition,
            workflow_name="[Plan Only]",
            workflow_description="[Plan Only]",
            tenant_id=tenant_id,
            created_by="[Plan Only]",
            execute=False,
        )

    async def _parse_composition(
        self, composition: list[Any]
    ) -> tuple[ParsedComposition | None, list[CompositionError]]:
        """
        Parse composition array into graph structure.

        Args:
            composition: Array of cy_names, shortcuts, or nested arrays

        Returns:
            Tuple of (ParsedComposition, errors)
        """
        errors: list[CompositionError] = []

        try:
            parsed = self.parser.parse(composition)
            return parsed, errors
        except ValueError as e:
            errors.append(
                CompositionError(
                    error_type="parse_error",
                    message=f"Failed to parse composition: {e!s}",
                    context={"composition": composition},
                )
            )
            return None, errors
        except Exception as e:
            errors.append(
                CompositionError(
                    error_type="parse_error",
                    message=f"Unexpected error during parsing: {e!s}",
                    context={"composition": composition},
                )
            )
            return None, errors

    async def _resolve_nodes(
        self, parsed_composition: ParsedComposition, tenant_id: str
    ) -> tuple[
        dict[str, ResolvedTask | ResolvedTemplate],
        list[CompositionError],
        list[Question],
    ]:
        """
        Resolve cy_names and shortcuts to tasks/templates.

        Args:
            parsed_composition: ParsedComposition from parser
            tenant_id: Tenant ID

        Returns:
            Tuple of (resolved_nodes, errors, questions)
        """
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate] = {}
        errors: list[CompositionError] = []
        questions: list[Question] = []

        for node in parsed_composition.nodes:
            try:
                # Check if reference is a template shortcut
                if node.reference in TEMPLATE_SHORTCUTS:
                    resolved = await self.template_resolver.resolve(node.reference)
                    resolved_nodes[node.node_id] = resolved
                else:
                    # Try to resolve as task cy_name
                    resolved = await self.task_resolver.resolve(
                        node.reference, tenant_id
                    )
                    resolved_nodes[node.node_id] = resolved

            except ValueError as e:
                # Resolution failed - could be task not found, disabled, or ambiguous
                if "ambiguous" in str(e).lower() or "multiple" in str(e).lower():
                    # Ambiguous resolution - generate question
                    # For now, just add as error since we don't have candidate info
                    errors.append(
                        CompositionError(
                            error_type="ambiguous_resolution",
                            message=str(e),
                            context={
                                "node_id": node.node_id,
                                "reference": node.reference,
                            },
                        )
                    )
                else:
                    # Task not found or disabled
                    errors.append(
                        CompositionError(
                            error_type="resolution_error",
                            message=f"Failed to resolve '{node.reference}': {e!s}",
                            context={
                                "node_id": node.node_id,
                                "reference": node.reference,
                            },
                        )
                    )
            except Exception as e:
                errors.append(
                    CompositionError(
                        error_type="resolution_error",
                        message=f"Unexpected error resolving '{node.reference}': {e!s}",
                        context={"node_id": node.node_id, "reference": node.reference},
                    )
                )

        return resolved_nodes, errors, questions

    async def _validate_composition(
        self,
        parsed_composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
        tenant_id: str,
    ) -> tuple[
        list[CompositionError],
        list[CompositionWarning],
        list[Question],
        dict[str, Any],
        dict[str, Any],
    ]:
        """
        Validate structure and schemas.

        Args:
            parsed_composition: ParsedComposition from parser
            resolved_nodes: Resolved tasks/templates
            tenant_id: Tenant ID

        Returns:
            Tuple of (errors, warnings, questions, input_schema, output_schema)
        """
        all_errors: list[CompositionError] = []
        all_warnings: list[CompositionWarning] = []
        all_questions: list[Question] = []

        # Structural validation
        structural_errors = self.structural_validator.validate(
            parsed_composition, resolved_nodes
        )
        all_errors.extend(structural_errors)

        # Check for missing aggregation in structural errors → generate questions
        for error in structural_errors:
            if error.error_type == "missing_aggregation":
                question = (
                    self.question_generator.generate_missing_aggregation_question(
                        parallel_node_ids=error.context.get("parallel_nodes", []),
                        layer=error.context.get("layer", 0),
                        resolved_nodes=resolved_nodes,
                    )
                )
                all_questions.append(question)

        # Schema validation (controlled by feature flag)
        if settings.ENABLE_WORKFLOW_TYPE_VALIDATION:
            (
                schema_errors,
                schema_warnings,
                input_schema,
                output_schema,
            ) = await self.schema_validator.validate(
                parsed_composition, resolved_nodes, tenant_id
            )
            all_errors.extend(schema_errors)
            all_warnings.extend(schema_warnings)
        else:
            # Skip schema validation - infer schemas without type checking
            input_schema, output_schema = self.schema_validator._infer_workflow_schemas(
                parsed_composition, resolved_nodes
            )
            all_warnings.append(
                CompositionWarning(
                    warning_type="validation_disabled",
                    message="Schema validation is disabled (ENABLE_WORKFLOW_TYPE_VALIDATION=False)",
                    context={"feature_flag": "ENABLE_WORKFLOW_TYPE_VALIDATION"},
                )
            )

        return all_errors, all_warnings, all_questions, input_schema, output_schema

    async def _build_workflow(
        self,
        parsed_composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
        workflow_name: str,
        workflow_description: str,
        tenant_id: str,
        created_by: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        audit_context: AuditContext | None = None,
        data_samples: list[dict[str, Any]] | None = None,
    ) -> UUID:
        """
        Create workflow in database.

        Args:
            parsed_composition: ParsedComposition from parser
            resolved_nodes: Resolved tasks/templates
            workflow_name: Workflow name
            workflow_description: Workflow description
            tenant_id: Tenant ID
            created_by: Creator username
            input_schema: Inferred workflow input schema
            output_schema: Inferred workflow output schema
            audit_context: Optional audit context for logging
            data_samples: Optional data samples for workflow testing

        Returns:
            Created workflow UUID
        """
        workflow_id = await self.builder.build_workflow(
            composition=parsed_composition,
            resolved_nodes=resolved_nodes,
            workflow_name=workflow_name,
            workflow_description=workflow_description,
            tenant_id=tenant_id,
            created_by=created_by,
            input_schema=input_schema,
            output_schema=output_schema,
            audit_context=audit_context,
            data_samples=data_samples,
        )
        return workflow_id
