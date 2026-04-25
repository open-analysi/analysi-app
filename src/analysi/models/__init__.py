"""
SQLAlchemy models for Analysi component architecture.
"""

from .activity_audit import ActivityAuditTrail
from .auth import ApiKey, Invitation, Membership, User
from .checkpoint import Checkpoint
from .component import Component
from .control_event import ControlEvent, ControlEventDispatch, ControlEventRule
from .conversation import ChatMessage, Conversation
from .credential import Credential, IntegrationCredential
from .hitl_question import HITLQuestion
from .index_entry import IndexEntry
from .job_run import JobRun
from .kdg_edge import KDGEdge
from .kea_coordination import AlertRoutingRule, AnalysisGroup, WorkflowGeneration
from .knowledge_extraction import KnowledgeExtraction
from .knowledge_module import KnowledgeModule
from .knowledge_unit import KnowledgeUnit, KUDocument, KUIndex, KUTable, KUTool
from .schedule import Schedule
from .task import Task
from .task_generation import TaskGeneration
from .task_run import TaskRun
from .tenant import Tenant
from .workflow import Workflow, WorkflowEdge, WorkflowNode
from .workflow_execution import WorkflowEdgeInstance, WorkflowNodeInstance, WorkflowRun

# Backward-compatible alias
TaskBuildingRun = TaskGeneration

__all__ = [
    "ActivityAuditTrail",
    "AlertRoutingRule",
    "AnalysisGroup",
    "ApiKey",
    "ChatMessage",
    "Checkpoint",
    "Component",
    "ControlEvent",
    "ControlEventDispatch",
    "ControlEventRule",
    "Conversation",
    "Credential",
    "HITLQuestion",
    "IndexEntry",
    "IntegrationCredential",
    "Invitation",
    "JobRun",
    "KDGEdge",
    "KUDocument",
    "KUIndex",
    "KUTable",
    "KUTool",
    "KnowledgeExtraction",
    "KnowledgeModule",
    "KnowledgeUnit",
    "Membership",
    "Schedule",
    "Task",
    "TaskBuildingRun",  # backward-compat alias
    "TaskGeneration",
    "TaskRun",
    "Tenant",
    "User",
    "Workflow",
    "WorkflowEdge",
    "WorkflowEdgeInstance",
    "WorkflowGeneration",
    "WorkflowNode",
    "WorkflowNodeInstance",
    "WorkflowRun",
]
