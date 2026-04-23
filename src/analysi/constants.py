"""
Global constants for Analysi API.

This file contains constants used across the application,
especially for UI display and API responses.

Status inner classes use StrEnum so values compare equal to plain strings,
making adoption incremental — existing ``status == "completed"`` checks
still work while new code uses ``TaskConstants.Status.COMPLETED``.
"""

from enum import StrEnum


class TaskConstants:
    """Constants related to task operations."""

    # Task modes
    class Mode:
        AD_HOC = "ad_hoc"
        SAVED = "saved"

    # Display names for task types
    AD_HOC_TASK_NAME = "Ad Hoc Task"

    # Task run statuses
    class Status(StrEnum):
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"
        PAUSED = "paused"  # HITL — Project Kalymnos


class IntegrationHealthStatus(StrEnum):
    """Cached health status on Integration, updated by health check hook."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ManagedResourceKey(StrEnum):
    """Keys for system-managed Tasks created by the task factory."""

    ALERT_INGESTION = "alert_ingestion"
    HEALTH_CHECK = "health_check"


class WorkflowConstants:
    """Constants related to workflow operations."""

    # Default workflow name for ad-hoc executions (if applicable)
    AD_HOC_WORKFLOW_NAME = "Ad Hoc Workflow"

    # Workflow / node-instance statuses
    class Status(StrEnum):
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"
        PAUSED = "paused"  # HITL — Project Kalymnos: task awaiting human input


class HITLQuestionConstants:
    """Constants for HITL question tracking (Project Kalymnos)."""

    class Status(StrEnum):
        PENDING = "pending"
        ANSWERED = "answered"
        EXPIRED = "expired"

    # Default question timeout in hours
    DEFAULT_TIMEOUT_HOURS = 4

    # Internal control event channel for human responses
    CHANNEL_HUMAN_RESPONDED = "human:responded"

    # Audit trail action for answered questions
    AUDIT_ACTION_ANSWERED = "hitl.question_answered"


class ControlEventConstants:
    """Constants related to the control event bus (Project Tilos)."""

    class Status(StrEnum):
        PENDING = "pending"
        CLAIMED = "claimed"
        COMPLETED = "completed"
        FAILED = "failed"


class RunStatus(StrEnum):
    """Unified job execution lifecycle status (Project Leros).

    6 values covering the full lifecycle of any tracked job.
    Domain-specific statuses (e.g., 'paused_workflow_building') map to these.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ComponentConstants:
    """Constants related to component operations."""

    # Component statuses
    class Status(StrEnum):
        ENABLED = "enabled"
        DISABLED = "disabled"
        DEPRECATED = "deprecated"

    # Component kinds
    class Kind(StrEnum):
        KU = "ku"
        TASK = "task"
        MODULE = "module"


class APIConstants:
    """Constants related to API operations."""

    # Pagination defaults
    DEFAULT_LIMIT = 50
    MAX_LIMIT = 100

    # Sorting defaults
    DEFAULT_SORT_FIELD = "created_at"
    DEFAULT_SORT_ORDER = "desc"

    class SortOrder:
        ASC = "asc"
        DESC = "desc"


class StorageConstants:
    """Constants related to storage operations."""

    # Storage types
    class Type:
        INLINE = "inline"
        S3 = "s3"

    # Storage thresholds (in bytes)
    INLINE_THRESHOLD = 512 * 1024  # 512KB


class ChatConstants:
    """Constants for product chatbot (Project Rhodes)."""

    # Input validation
    MAX_MESSAGE_LENGTH = 4000
    MAX_CONVERSATIONS_PER_USER = 100

    # Rate limits (enforcement deferred — requires Valkey)
    MAX_MESSAGES_PER_MINUTE = 20
    MAX_CONCURRENT_STREAMS = 2

    # Token budgets (enforcement deferred — requires Valkey)
    USER_HOURLY_TOKEN_BUDGET = 50_000
    TENANT_HOURLY_TOKEN_BUDGET = 500_000
    CONVERSATION_LIFETIME_TOKEN_BUDGET = 200_000

    # Skills (progressive disclosure)
    MAX_PINNED_SKILLS = 3

    # Tool results (tenant knowledge tools)
    MAX_TOOL_RESULT_TOKENS = 4000

    # Security hardening
    MAX_HISTORY_MESSAGES = 20
    MAX_HISTORY_TOKENS = 30_000
    MAX_TOOL_CALLS_PER_TURN = 8

    # Streaming
    STREAM_TIMEOUT_SECONDS = 120

    # Audit trail actions
    AUDIT_CONVERSATION_CREATED = "chat.conversation_created"
    AUDIT_MESSAGE_SENT = "chat.message_sent"

    # Message roles
    class Role:
        USER = "user"
        ASSISTANT = "assistant"
        SYSTEM = "system"
        TOOL = "tool"


class TemplateConstants:
    """
    System-provided NodeTemplate constants.

    These templates are seeded at database initialization and provide
    the foundational transformation patterns for the Rodos workflow system.
    """

    from uuid import UUID

    # System Template UUIDs (deterministic, seeded by migration V030)
    SYSTEM_IDENTITY_TEMPLATE_ID = UUID("00000000-0000-0000-0000-000000000001")
    SYSTEM_MERGE_TEMPLATE_ID = UUID("00000000-0000-0000-0000-000000000002")
    SYSTEM_COLLECT_TEMPLATE_ID = UUID("00000000-0000-0000-0000-000000000003")

    # Template names (for lookup and verification)
    SYSTEM_IDENTITY_TEMPLATE_NAME = "system_identity"
    SYSTEM_MERGE_TEMPLATE_NAME = "system_merge"
    SYSTEM_COLLECT_TEMPLATE_NAME = "system_collect"

    # Template kinds (for validation)
    TEMPLATE_KIND_IDENTITY = "identity"
    TEMPLATE_KIND_MERGE = "merge"
    TEMPLATE_KIND_COLLECT = "collect"


class PackConstants:
    """Constants for Content Pack operations (Project Delos)."""

    # The default app value — components not belonging to any pack
    DEFAULT_APP = "default"
    # Grace period (seconds) before a component is considered user-modified
    MODIFICATION_THRESHOLD_SECONDS = 60


class AlertConstants:
    """Constants related to alert operations."""

    class Status(StrEnum):
        NEW = "new"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"


class TaskFunctionType(StrEnum):
    """Task function type constants."""

    SUMMARIZATION = "summarization"
    DATA_CONVERSION = "data_conversion"
    EXTRACTION = "extraction"
    REASONING = "reasoning"
    PLANNING = "planning"
    VISUALIZATION = "visualization"
    SEARCH = "search"


class TaskScopeType(StrEnum):
    """Task scope constants."""

    INPUT = "input"
    PROCESSING = "processing"
    OUTPUT = "output"


class TaskModeType(StrEnum):
    """Task mode constants."""

    AD_HOC = "ad_hoc"
    SAVED = "saved"


class KUTypeConstants(StrEnum):
    """Knowledge Unit type constants."""

    TABLE = "table"
    DOCUMENT = "document"
    TOOL = "tool"
    INDEX = "index"


class ModuleTypeConstants(StrEnum):
    """Knowledge module type constants."""

    SKILL = "skill"


class EdgeTypeConstants(StrEnum):
    """Knowledge Dependency Graph edge type constants."""

    USES = "uses"
    GENERATES = "generates"
    UPDATES = "updates"
    CALLS = "calls"
    TRANSFORMS_INTO = "transforms_into"
    SUMMARIZES_INTO = "summarizes_into"
    INDEXES_INTO = "indexes_into"
    DERIVED_FROM = "derived_from"
    ENRICHES = "enriches"
    CONTAINS = "contains"
    INCLUDES = "includes"
    DEPENDS_ON = "depends_on"
    REFERENCES = "references"
    STAGED_FOR = "staged_for"
    FEEDBACK_FOR = "feedback_for"


class ContentReviewConstants:
    """Constants related to content review operations."""

    class Status(StrEnum):
        PENDING = "pending"
        APPROVED = "approved"
        FLAGGED = "flagged"
        APPLIED = "applied"
        REJECTED = "rejected"
        FAILED = "failed"
