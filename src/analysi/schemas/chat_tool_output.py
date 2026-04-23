"""Chat tool output schemas.

Slim Pydantic models for formatting chat tool output. Each schema:
- Reuses real model enums (AlertSeverity, AlertStatus) to prevent drift
- Has a from_*() constructor that validates fields at construction time
- Has to_chat_line() for list formatting and to_chat_detail() for single-entity views
- Has format_list() for assembling list-style tool output

These replace the manual dict/string building in chat_tools.py. The security
wrappers (cap_tool_result, sanitize_tool_result) are applied AFTER formatting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from analysi.schemas.alert import AlertSeverity, AlertStatus


class AlertChatSummary(BaseModel):
    """Slim alert for list output."""

    alert_id: UUID
    title: str
    severity: AlertSeverity
    analysis_status: AlertStatus
    source_vendor: str | None = None
    source_product: str | None = None
    short_summary: str | None = None

    @classmethod
    def from_alert_response(cls, alert: Any) -> AlertChatSummary:
        """Build from AlertResponse (or any object with the same fields)."""
        return cls(
            alert_id=alert.alert_id,
            title=alert.title,
            severity=alert.severity,
            analysis_status=alert.analysis_status,
            source_vendor=getattr(alert, "source_vendor", None),
            source_product=getattr(alert, "source_product", None),
            short_summary=getattr(alert, "short_summary", None),
        )

    def to_chat_line(self) -> str:
        """Single-line summary for list output."""
        summary = (
            f" — {self.short_summary[:100]}..."
            if self.short_summary and len(self.short_summary) > 100
            else (f" — {self.short_summary}" if self.short_summary else "")
        )
        return (
            f"- **{self.title}** "
            f"(ID: {self.alert_id}, {self.severity}/{self.analysis_status})"
            f"{summary}"
        )

    @staticmethod
    def format_list(items: list[AlertChatSummary], total: int) -> str:
        """Format a list of alert summaries with header and severity breakdown."""
        if not items:
            return "No alerts found."
        lines = [f"Found {total} alerts (showing {len(items)}):\n"]
        lines.extend(item.to_chat_line() for item in items)

        # Pre-computed breakdown
        from collections import Counter

        sev_counts = Counter(item.severity.value for item in items)
        status_counts = Counter(item.analysis_status.value for item in items)
        lines.append(
            "\n**Severity breakdown**: "
            + ", ".join(f"{s}: {c}" for s, c in sev_counts.most_common())
        )
        lines.append(
            "**Status breakdown**: "
            + ", ".join(f"{s}: {c}" for s, c in status_counts.most_common())
        )
        return "\n".join(lines)


class AlertChatDetail(AlertChatSummary):
    """Full alert detail for get_alert output."""

    triggering_event_time: datetime | None = None
    description: str | None = None
    entities: Any | None = None  # OCSF: actor + device
    observables: Any | None = None  # OCSF: observables array
    disposition_category: str | None = None
    disposition_display_name: str | None = None
    disposition_confidence: int | None = None
    current_analysis: dict[str, Any] | None = None

    @classmethod
    def from_alert_response_detail(cls, alert: Any) -> AlertChatDetail:
        """Build from AlertResponse with full detail (model_dump result)."""
        data = alert.model_dump(mode="json") if hasattr(alert, "model_dump") else alert

        # Extract analysis sub-summary if present
        analysis_data = None
        raw_analysis = data.get("current_analysis")
        if raw_analysis:
            analysis_data = {
                "status": raw_analysis.get("status"),
                "short_summary": raw_analysis.get("short_summary"),
            }

        return cls(
            alert_id=data["alert_id"],
            title=data["title"],
            severity=data["severity"],
            analysis_status=data["analysis_status"],
            source_vendor=data.get("source_vendor"),
            source_product=data.get("source_product"),
            triggering_event_time=data.get("triggering_event_time"),
            description=data.get("description"),
            entities=data.get("entities"),
            observables=data.get("observables"),
            # Disposition lives at alert level, not inside current_analysis
            disposition_category=data.get("current_disposition_category"),
            disposition_display_name=data.get("current_disposition_display_name"),
            disposition_confidence=data.get("current_disposition_confidence"),
            current_analysis=analysis_data,
        )

    def to_chat_detail(self) -> str:
        """Full detail for single-entity view."""
        import json

        summary = {
            "alert_id": str(self.alert_id),
            "title": self.title,
            "severity": self.severity.value,
            "analysis_status": self.analysis_status.value,
            "source_vendor": self.source_vendor,
            "source_product": self.source_product,
            "triggering_event_time": str(self.triggering_event_time)
            if self.triggering_event_time
            else None,
            "description": self.description,
            "disposition_category": self.disposition_category,
            "disposition_display_name": self.disposition_display_name,
            "disposition_confidence": self.disposition_confidence,
            "entities": self.entities,
            "observables": self.observables,
        }
        if self.current_analysis:
            summary["current_analysis"] = self.current_analysis

        return f"# Alert: {self.title}\n\n{json.dumps(summary, indent=2, default=str)}"


class TaskChatSummary(BaseModel):
    """Slim task for list output."""

    id: UUID
    name: str
    cy_name: str
    function: str | None = None
    status: str = "enabled"
    categories: list[str] = []
    description: str | None = None

    @classmethod
    def from_task(cls, task: Any) -> TaskChatSummary:
        """Build from Task ORM model (which has task.component relationship)."""
        comp = task.component
        return cls(
            id=comp.id,
            name=comp.name or "Unnamed",
            cy_name=comp.cy_name or "",
            function=task.function,
            status=comp.status or "unknown",
            categories=comp.categories or [],
            description=comp.description,
        )

    def to_chat_line(self) -> str:
        """Single-line summary for list output."""
        cats = f" [{', '.join(self.categories[:5])}]" if self.categories else ""
        fn = f" ({self.function})" if self.function else ""
        desc = f" — {self.description[:80]}" if self.description else ""
        status_tag = "" if self.status == "enabled" else f" **{self.status}**"
        return (
            f"- **{self.name}** (`{self.cy_name}`, ID: {self.id})"
            f"{fn}{cats}{status_tag}{desc}"
        )

    def to_chat_detail(self) -> str:
        """Full detail for single-entity view."""
        import json

        summary = {
            "id": str(self.id),
            "name": self.name,
            "cy_name": self.cy_name,
            "description": self.description,
            "status": self.status,
            "function": self.function,
            "categories": self.categories,
        }
        return f"# Task: {self.name}\n\n{json.dumps(summary, indent=2, default=str)}"

    @staticmethod
    def format_list(items: list[TaskChatSummary], total: int) -> str:
        """Format a list of task summaries with header and function breakdown."""
        if not items:
            return "No tasks found."
        lines = [f"Found {total} tasks (showing {len(items)}):\n"]
        lines.extend(item.to_chat_line() for item in items)

        # Pre-computed function breakdown (LLMs can't count reliably from long lists)
        from collections import Counter

        fn_counts = Counter(item.function or "unknown" for item in items)
        cat_counts = Counter(cat for item in items for cat in (item.categories or []))
        status_counts = Counter(item.status for item in items)
        lines.append(
            "\n**Function breakdown**: "
            + ", ".join(f"{fn}: {c}" for fn, c in fn_counts.most_common())
        )
        if cat_counts:
            top_cats = cat_counts.most_common(10)
            lines.append(
                "**Top categories**: " + ", ".join(f"{cat}: {c}" for cat, c in top_cats)
            )
        lines.append(
            "**Status breakdown**: "
            + ", ".join(f"{s}: {c}" for s, c in status_counts.most_common())
        )
        return "\n".join(lines)


class WorkflowChatSummary(BaseModel):
    """Slim workflow for list output."""

    id: UUID
    name: str
    description: str | None = None
    node_count: int = 0

    @classmethod
    def from_workflow(cls, wf: Any) -> WorkflowChatSummary:
        """Build from Workflow ORM model or dict (get_workflow returns dict)."""
        if isinstance(wf, dict):
            nodes = wf.get("nodes", [])
            return cls(
                id=wf.get("id", wf.get("workflow_id")),
                name=wf.get("name", "Unnamed"),
                description=wf.get("description"),
                node_count=len(nodes) if isinstance(nodes, list) else 0,
            )
        # ORM model — nodes are eagerly loaded by the repository
        node_count = len(wf.nodes) if hasattr(wf, "nodes") and wf.nodes else 0
        return cls(
            id=wf.id,
            name=wf.name or "Unnamed",
            description=getattr(wf, "description", None),
            node_count=node_count,
        )

    def to_chat_line(self) -> str:
        nodes = f" ({self.node_count} nodes)" if self.node_count else ""
        desc = f" — {self.description[:100]}" if self.description else ""
        return f"- **{self.name}** (ID: {self.id}){nodes}{desc}"

    @staticmethod
    def format_list(items: list[WorkflowChatSummary], total: int) -> str:
        if not items:
            return "No workflows found."
        # Sort by node_count descending for "complexity" readability
        sorted_items = sorted(items, key=lambda w: w.node_count, reverse=True)
        lines = [
            f"Found {total} workflows (showing {len(items)}), sorted by complexity:\n"
        ]
        lines.extend(item.to_chat_line() for item in sorted_items)
        return "\n".join(lines)


class IntegrationChatSummary(BaseModel):
    """Slim integration for list output."""

    integration_id: str
    name: str
    integration_type: str
    enabled: bool
    health_status: str = "unknown"
    health_message: str | None = None

    @classmethod
    def from_integration(cls, integ: Any) -> IntegrationChatSummary:
        """Build from IntegrationResponse (with health sub-object)."""
        health_status = "unknown"
        health_message = None
        if hasattr(integ, "health") and integ.health:
            health_status = integ.health.status or "unknown"
            msg = getattr(integ.health, "message", None)
            if msg:
                health_message = msg[:200]  # Truncate to prevent bloat
        return cls(
            integration_id=integ.integration_id,
            name=integ.name or integ.integration_type,
            integration_type=integ.integration_type,
            enabled=integ.enabled,
            health_status=health_status,
            health_message=health_message,
        )

    def to_chat_line(self) -> str:
        enabled = "enabled" if self.enabled else "disabled"
        reason = f" — {self.health_message}" if self.health_message else ""
        return (
            f"- **{self.name}** ({self.integration_type}, "
            f"{enabled}, health: {self.health_status}){reason}"
        )

    def to_chat_detail(self) -> str:
        import json

        summary = {
            "integration_id": self.integration_id,
            "integration_type": self.integration_type,
            "name": self.name,
            "enabled": self.enabled,
            "health_status": self.health_status,
            "health_message": self.health_message,
        }
        return f"# Integration: {self.name}\n\n{json.dumps(summary, indent=2, default=str)}"

    @staticmethod
    def format_list(items: list[IntegrationChatSummary]) -> str:
        if not items:
            return "No integrations configured."

        from collections import Counter

        health_counts = Counter(item.health_status for item in items)
        lines = [f"Found {len(items)} integrations:\n"]
        lines.extend(item.to_chat_line() for item in items)
        lines.append(
            "\n**Health breakdown**: "
            + ", ".join(f"{s}: {c}" for s, c in health_counts.most_common())
        )
        return "\n".join(lines)


class WorkflowRunChatSummary(BaseModel):
    """Slim workflow run for list and detail views."""

    id: UUID
    workflow_id: UUID
    workflow_name: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    @classmethod
    def from_workflow_run(cls, run: Any) -> WorkflowRunChatSummary:
        return cls(
            id=run.id,
            workflow_id=run.workflow_id,
            workflow_name=getattr(run, "workflow_name", None),
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
        )

    def to_chat_line(self) -> str:
        name = self.workflow_name or "Unnamed"
        ts = (
            self.started_at.strftime("%Y-%m-%d %H:%M")
            if self.started_at
            else "not started"
        )
        err = f" — {self.error_message[:80]}" if self.error_message else ""
        return f"- **{name}** (ID: {self.id}, {self.status}, {ts}){err}"

    def to_chat_detail(self) -> str:
        import json

        summary = {
            "workflow_run_id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "workflow_name": self.workflow_name,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "error_message": self.error_message,
        }
        return f"# Workflow Run\n\n{json.dumps(summary, indent=2, default=str)}"

    @staticmethod
    def format_list(items: list[WorkflowRunChatSummary], total: int) -> str:
        if not items:
            return "No workflow runs found."
        from collections import Counter

        status_counts = Counter(item.status for item in items)
        lines = [f"Found {total} workflow runs (showing {len(items)}):\n"]
        lines.extend(item.to_chat_line() for item in items)
        lines.append(
            "\n**Status breakdown**: "
            + ", ".join(f"{s}: {c}" for s, c in status_counts.most_common())
        )
        return "\n".join(lines)


class TaskRunChatSummary(BaseModel):
    """Slim task run for list and detail views."""

    id: UUID
    task_id: UUID | None = None
    task_name: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    output_data: Any | None = None

    @classmethod
    def from_task_run(cls, run: Any) -> TaskRunChatSummary:
        return cls(
            id=run.id,
            task_id=run.task_id,
            task_name=getattr(run, "task_name", None),
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=getattr(run, "error_message", None),
            output_data=getattr(run, "output_data", None),
        )

    def to_chat_line(self) -> str:
        name = self.task_name or "Unnamed"
        ts = (
            self.started_at.strftime("%Y-%m-%d %H:%M")
            if self.started_at
            else "not started"
        )
        err = f" — {self.error_message[:80]}" if self.error_message else ""
        return f"- **{name}** (ID: {self.id}, {self.status}, {ts}){err}"

    def to_chat_detail(self) -> str:
        import json

        summary: dict[str, Any] = {
            "task_run_id": str(self.id),
            "task_id": str(self.task_id) if self.task_id else None,
            "task_name": self.task_name,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "error_message": self.error_message,
        }
        if self.output_data:
            summary["output"] = self.output_data
        return f"# Task Run\n\n{json.dumps(summary, indent=2, default=str)}"

    @staticmethod
    def format_list(items: list[TaskRunChatSummary], total: int) -> str:
        if not items:
            return "No task runs found."
        from collections import Counter

        status_counts = Counter(item.status for item in items)
        lines = [f"Found {total} task runs (showing {len(items)}):\n"]
        lines.extend(item.to_chat_line() for item in items)
        lines.append(
            "\n**Status breakdown**: "
            + ", ".join(f"{s}: {c}" for s, c in status_counts.most_common())
        )
        return "\n".join(lines)
