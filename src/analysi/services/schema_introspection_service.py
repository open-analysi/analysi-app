"""Service for introspecting Pydantic model schemas."""

from typing import Any, ClassVar

import pydantic

from analysi.schemas.alert import AlertAnalysisResponse, AlertBase, AlertList
from analysi.schemas.artifact import ArtifactCreate, ArtifactResponse
from analysi.schemas.integration import IntegrationCreate, IntegrationResponse
from analysi.schemas.knowledge_unit import KUBase
from analysi.schemas.task import TaskBase
from analysi.schemas.task_run import TaskRunResponse
from analysi.schemas.workflow import WorkflowResponse
from analysi.schemas.workflow_execution import WorkflowRunResponse


class SchemaIntrospectionService:
    """
    Service for retrieving JSON schemas of Pydantic models.

    Provides easy access to model schemas for development and documentation.
    Supports nested model definitions and customizable output.
    """

    # Model registry - maps model names to Pydantic classes
    MODEL_REGISTRY: ClassVar[dict[str, type]] = {}

    @classmethod
    def initialize_registry(cls) -> None:
        """
        Initialize the model registry with platform models.

        Populates MODEL_REGISTRY with available Pydantic models.
        Called on first use or can be explicitly called.
        """
        cls.MODEL_REGISTRY = {
            # Alert models
            "Alert": AlertBase,
            "AlertAnalysis": AlertAnalysisResponse,
            "AlertList": AlertList,
            # Artifact models
            "Artifact": ArtifactResponse,
            "ArtifactCreate": ArtifactCreate,
            # Task models
            "Task": TaskBase,
            "TaskRun": TaskRunResponse,
            # Knowledge Unit models
            "KnowledgeUnit": KUBase,
            # Workflow models
            "Workflow": WorkflowResponse,
            "WorkflowRun": WorkflowRunResponse,
            # Integration models
            "Integration": IntegrationResponse,
            "IntegrationCreate": IntegrationCreate,
        }

    @classmethod
    def get_model_schema(
        cls, model_name: str, include_definitions: bool = True
    ) -> dict[str, Any]:
        """
        Get JSON schema for a Pydantic model.

        Args:
            model_name: Name of the model (e.g., "Alert", "Task")
            include_definitions: If True, include nested model definitions

        Returns:
            {
                "model_name": str,
                "schema": dict,  # JSON Schema
                "pydantic_version": str,
                "definitions": dict | None  # Nested definitions if include_definitions=True
            }

        Raises:
            ValueError: If model_name not found in registry
        """
        # Initialize registry if empty
        if not cls.MODEL_REGISTRY:
            cls.initialize_registry()

        # Get model class
        if model_name not in cls.MODEL_REGISTRY:
            available = list(cls.MODEL_REGISTRY.keys())
            raise ValueError(
                f"Model '{model_name}' not found. Available models: {', '.join(available)}"
            )

        model_class = cls.MODEL_REGISTRY[model_name]

        # Generate JSON schema
        if include_definitions:
            schema = model_class.model_json_schema()
            definitions = cls._extract_definitions(schema)
        else:
            # Generate minimal schema without nested definitions
            schema = model_class.model_json_schema(mode="validation")
            # Remove $defs if present
            schema_copy = schema.copy()
            schema_copy.pop("$defs", None)
            schema = schema_copy
            definitions = None

        return {
            "model_name": model_name,
            "schema": schema,
            "pydantic_version": pydantic.VERSION,
            "definitions": definitions,
        }

    @classmethod
    def list_available_models(cls) -> list[str]:
        """
        List all available platform models.

        Returns:
            List of model names that can be used with get_model_schema()
        """
        # Initialize registry if empty
        if not cls.MODEL_REGISTRY:
            cls.initialize_registry()

        return sorted(cls.MODEL_REGISTRY.keys())

    @classmethod
    def _extract_definitions(cls, schema: dict[str, Any]) -> dict[str, Any] | None:
        """
        Extract $defs from schema if present.

        Args:
            schema: JSON Schema dict

        Returns:
            Definitions dict or None if not present
        """
        return schema.get("$defs")
