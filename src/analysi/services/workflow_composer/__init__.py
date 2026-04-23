"""
Workflow Composer - Type-safe workflow assembly from simple array format.

Main entry point: WorkflowComposerService
"""

from .builder import ComposerWorkflowBuilder
from .models import (
    CompositionError,
    CompositionPlan,
    CompositionResult,
    CompositionWarning,
    ParsedComposition,
    ParsedEdge,
    ParsedNode,
    Question,
    ResolvedTask,
    ResolvedTemplate,
)
from .parser import CompositionParser
from .questions import QuestionGenerator
from .resolvers import TEMPLATE_SHORTCUTS, TaskResolver, TemplateResolver
from .service import WorkflowComposerService
from .validators import SchemaValidator, StructuralValidator

__all__ = [
    # Constants
    "TEMPLATE_SHORTCUTS",
    "ComposerWorkflowBuilder",
    "CompositionError",
    # Core components
    "CompositionParser",
    "CompositionPlan",
    "CompositionResult",
    "CompositionWarning",
    # Models
    "ParsedComposition",
    "ParsedEdge",
    "ParsedNode",
    "Question",
    "QuestionGenerator",
    "ResolvedTask",
    "ResolvedTemplate",
    "SchemaValidator",
    "StructuralValidator",
    "TaskResolver",
    "TemplateResolver",
    # Main service
    "WorkflowComposerService",
]
