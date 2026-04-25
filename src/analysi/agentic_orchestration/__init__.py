"""
Agentic Orchestration module for Project Kea.

This module provides the core infrastructure for AI-powered workflow generation,
using the Claude Agent SDK to orchestrate multi-stage generation processes.

Public API:
    - WorkflowGenerationStage: Enum of generation stages
    - WorkflowGenerationStatus: Enum of generation statuses
    - ToolCallTrace: Record of a single tool invocation
    - StageExecutionMetrics: Metrics from a stage execution
    - ProgressCallback: Protocol for progress reporting
    - AgentOrchestrationExecutor: SDK wrapper for executing stages
    - AgentWorkspace: Workspace for agent file capture
    - get_mcp_servers: Build tenant-aware MCP server configuration
    - run_full_orchestration: Complete alert → Workflow pipeline
"""

from .config import create_eval_executor, create_executor, get_mcp_servers
from .observability import (
    ProgressCallback,
    StageExecutionMetrics,
    ToolCallTrace,
    WorkflowGenerationStage,
    WorkflowGenerationStatus,
)
from .orchestrator import run_full_orchestration
from .sdk_wrapper import AgentOrchestrationExecutor
from .task_generation_client import (
    TaskBuildingProgressCallback,
    TaskBuildingRunApiClient,
    TaskGenerationApiClient,
    TaskGenerationProgressCallback,
)
from .workspace import AgentWorkspace

__all__ = [
    "AgentOrchestrationExecutor",
    "AgentWorkspace",
    "ProgressCallback",
    "StageExecutionMetrics",
    "TaskBuildingProgressCallback",  # backward-compat alias
    "TaskBuildingRunApiClient",  # backward-compat alias
    "TaskGenerationApiClient",
    "TaskGenerationProgressCallback",
    "ToolCallTrace",
    "WorkflowGenerationStage",
    "WorkflowGenerationStatus",
    "create_eval_executor",
    "create_executor",
    "get_mcp_servers",
    "run_full_orchestration",
]
