"""
Data factory for creating test data.
Provides utilities for generating realistic test data for models.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from analysi.models import (
    Component,
    KDGEdge,
    KnowledgeUnit,
    KUDocument,
    KUIndex,
    KUTable,
    KUTool,
    Task,
)
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import ComponentKind, ComponentStatus
from analysi.models.kdg_edge import EdgeType
from analysi.models.knowledge_unit import KUType
from analysi.models.task import TaskFunction, TaskScope


class DataFactory:
    """Factory for creating test data with realistic values."""

    @staticmethod
    def create_component(
        tenant_id: str,
        kind: ComponentKind = ComponentKind.TASK,
        name: str | None = None,
        description: str | None = None,
        created_by: UUID = SYSTEM_USER_ID,
        status: ComponentStatus = ComponentStatus.ENABLED,
        visible: bool = False,
        system_only: bool = False,
        app: str = "default",
        categories: list[str] | None = None,
        version: str = "1.0.0",
        **kwargs,
    ) -> Component:
        """Create a component with realistic defaults."""
        if name is None:
            name = f"Test {kind.title()} Component"

        if description is None:
            description = f"A test {kind} component for integration testing"

        if categories is None:
            categories = ["test", kind]

        return Component(
            tenant_id=tenant_id,
            kind=kind,
            name=name,
            description=description,
            created_by=created_by,
            status=status,
            visible=visible,
            system_only=system_only,
            app=app,
            categories=categories,
            version=version,
            **kwargs,
        )

    @staticmethod
    def create_task(
        component_id: UUID,
        directive: str | None = None,
        script: str | None = None,
        function: TaskFunction = TaskFunction.REASONING,
        scope: TaskScope = TaskScope.INPUT,
        schedule: str | None = None,
        llm_config: dict[str, Any] | None = None,
        **kwargs,
    ) -> Task:
        """Create a task with realistic defaults."""
        if directive is None:
            directive = f"Execute {function} on the provided data"

        if script is None:
            script = f"#!cy 2.1\n# {function} script\nprocess_data(input_data)"

        if llm_config is None:
            llm_config = {
                "default_model": "gpt-4",
                "temperature": 0.2,
                "max_tokens": 1000,
            }

        return Task(
            component_id=component_id,
            directive=directive,
            script=script,
            function=function,
            scope=scope,
            schedule=schedule,
            llm_config=llm_config,
            **kwargs,
        )

    @staticmethod
    def create_knowledge_unit(
        component_id: UUID, ku_type: KUType = KUType.DOCUMENT, **kwargs
    ) -> KnowledgeUnit:
        """Create a knowledge unit."""
        return KnowledgeUnit(component_id=component_id, ku_type=ku_type, **kwargs)

    @staticmethod
    def create_ku_document(
        component_id: UUID,
        content: str | None = None,
        document_type: str = "markdown",
        content_source: str = "manual",
        doc_metadata: dict[str, Any] | None = None,
        word_count: int | None = None,
        character_count: int | None = None,
        **kwargs,
    ) -> KUDocument:
        """Create a KU document with realistic content."""
        if content is None:
            content = """# Security Analysis Guide

## Overview
This document provides guidelines for conducting security analysis of network traffic.

## Methodology
1. Collect network logs
2. Identify suspicious patterns
3. Correlate with threat intelligence
4. Generate alerts for high-risk activities

## Key Indicators
- Unusual port scanning
- Data exfiltration attempts
- Command and control communications
"""

        if doc_metadata is None:
            doc_metadata = {
                "source": "internal",
                "classification": "internal",
                "version": "1.0",
                "tags": ["security", "analysis", "guide"],
            }

        if word_count is None:
            word_count = len(content.split())

        if character_count is None:
            character_count = len(content)

        return KUDocument(
            component_id=component_id,
            content=content,
            markdown_content=content,
            document_type=document_type,
            content_source=content_source,
            doc_metadata=doc_metadata,
            word_count=word_count,
            character_count=character_count,
            **kwargs,
        )

    @staticmethod
    def create_ku_table(
        component_id: UUID,
        schema: dict[str, Any] | None = None,
        content: list[dict[str, Any]] | None = None,
        row_count: int | None = None,
        column_count: int | None = None,
        **kwargs,
    ) -> KUTable:
        """Create a KU table with sample data."""
        if schema is None:
            schema = {
                "type": "object",
                "properties": {
                    "ip_address": {"type": "string"},
                    "risk_score": {"type": "number", "minimum": 0, "maximum": 100},
                    "last_seen": {"type": "string", "format": "date-time"},
                    "threat_type": {"type": "string"},
                    "country": {"type": "string"},
                },
                "required": ["ip_address", "risk_score"],
            }

        if content is None:
            content = [
                {
                    "ip_address": "192.168.1.100",
                    "risk_score": 85,
                    "last_seen": "2024-01-15T10:30:00Z",
                    "threat_type": "malware",
                    "country": "US",
                },
                {
                    "ip_address": "10.0.0.50",
                    "risk_score": 92,
                    "last_seen": "2024-01-15T11:15:00Z",
                    "threat_type": "botnet",
                    "country": "RU",
                },
                {
                    "ip_address": "172.16.0.25",
                    "risk_score": 67,
                    "last_seen": "2024-01-15T09:45:00Z",
                    "threat_type": "scanning",
                    "country": "CN",
                },
            ]

        if row_count is None:
            row_count = len(content)

        if column_count is None:
            column_count = len(schema.get("properties", {}))

        return KUTable(
            component_id=component_id,
            schema=schema,
            content=content,
            row_count=row_count,
            column_count=column_count,
            **kwargs,
        )

    @staticmethod
    def create_ku_tool(
        component_id: UUID,
        tool_type: str = "mcp",
        mcp_endpoint: str | None = None,
        mcp_server_config: dict[str, Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        auth_type: str = "api_key",
        **kwargs,
    ) -> KUTool:
        """Create a KU tool with realistic configuration."""
        if mcp_endpoint is None and tool_type == "mcp":
            mcp_endpoint = "http://localhost:3000/mcp/security-scanner"

        if mcp_server_config is None and tool_type == "mcp":
            mcp_server_config = {
                "server_name": "security-scanner-mcp",
                "version": "1.2.0",
                "capabilities": ["scan", "analyze", "report"],
                "timeout": 30000,
                "max_concurrent": 5,
            }

        if input_schema is None:
            input_schema = {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target to scan"},
                    "scan_type": {
                        "type": "string",
                        "enum": ["quick", "deep", "custom"],
                    },
                    "options": {
                        "type": "object",
                        "description": "Additional scan options",
                    },
                },
                "required": ["target"],
            }

        if output_schema is None:
            output_schema = {
                "type": "object",
                "properties": {
                    "scan_id": {"type": "string"},
                    "status": {"type": "string"},
                    "results": {"type": "array"},
                    "summary": {"type": "object"},
                },
            }

        return KUTool(
            component_id=component_id,
            tool_type=tool_type,
            mcp_endpoint=mcp_endpoint,
            mcp_server_config=mcp_server_config,
            input_schema=input_schema,
            output_schema=output_schema,
            auth_type=auth_type,
            **kwargs,
        )

    @staticmethod
    def create_ku_index(
        component_id: UUID,
        index_type: str = "vector",
        vector_database: str = "pinecone",
        embedding_model: str = "text-embedding-ada-002",
        chunking_config: dict[str, Any] | None = None,
        build_status: str = "completed",
        index_stats: dict[str, Any] | None = None,
        **kwargs,
    ) -> KUIndex:
        """Create a KU index with realistic configuration."""
        if chunking_config is None:
            chunking_config = {
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "separators": ["\\n\\n", "\\n", ". ", " "],
                "keep_separator": True,
            }

        if index_stats is None:
            index_stats = {
                "total_chunks": 250,
                "total_tokens": 75000,
                "embedding_dimensions": 1536,
                "build_time_seconds": 45,
                "index_size_mb": 12.5,
            }

        return KUIndex(
            component_id=component_id,
            index_type=index_type,
            vector_database=vector_database,
            embedding_model=embedding_model,
            chunking_config=chunking_config,
            build_status=build_status,
            index_stats=index_stats,
            **kwargs,
        )

    @staticmethod
    def create_kdg_edge(
        source_id: UUID,
        target_id: UUID,
        tenant_id: str,
        relationship_type: EdgeType = EdgeType.USES,
        edge_metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> KDGEdge:
        """Create a KDG edge with realistic metadata."""
        if edge_metadata is None:
            edge_metadata = {
                "created_by": str(SYSTEM_USER_ID),
                "last_verified": datetime.now(tz=UTC).isoformat(),
                "notes": f"Auto-generated {relationship_type} relationship",
            }

        return KDGEdge(
            source_id=source_id,
            target_id=target_id,
            tenant_id=tenant_id,
            relationship_type=relationship_type,
            edge_metadata=edge_metadata,
            **kwargs,
        )


class ScenarioFactory:
    """Factory for creating complete test scenarios."""

    @staticmethod
    async def create_security_analysis_workflow(
        session, tenant_id: str
    ) -> dict[str, Any]:
        """Create a complete security analysis workflow scenario."""

        # 1. Create data collector task
        collector_component = DataFactory.create_component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Network Data Collector",
            description="Collects network traffic data for analysis",
            categories=["security", "data-collection"],
        )
        session.add(collector_component)
        await session.flush()

        collector_task = DataFactory.create_task(
            component_id=collector_component.id,
            directive="Collect and normalize network traffic data from multiple sources",
            function=TaskFunction.SEARCH,
            scope=TaskScope.INPUT,
            schedule="*/5 * * * *",  # Every 5 minutes
        )
        session.add(collector_task)

        # 2. Create threat intelligence KU
        threat_intel_component = DataFactory.create_component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Threat Intelligence Database",
            description="Known threat indicators and patterns",
            categories=["security", "threat-intel"],
        )
        session.add(threat_intel_component)
        await session.flush()

        threat_intel_ku = DataFactory.create_knowledge_unit(
            component_id=threat_intel_component.id, ku_type=KUType.TABLE
        )
        session.add(threat_intel_ku)

        threat_intel_table = DataFactory.create_ku_table(
            component_id=threat_intel_component.id
        )
        session.add(threat_intel_table)

        # 3. Create analysis task
        analyzer_component = DataFactory.create_component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Security Event Analyzer",
            description="Analyzes network data against threat intelligence",
            categories=["security", "analysis"],
        )
        session.add(analyzer_component)
        await session.flush()

        analyzer_task = DataFactory.create_task(
            component_id=analyzer_component.id,
            directive="Analyze network events and correlate with threat intelligence",
            function=TaskFunction.REASONING,
            scope=TaskScope.PROCESSING,
            llm_config={
                "default_model": "gpt-4",
                "temperature": 0.1,
                "system_prompt": "You are a cybersecurity analyst. Analyze the provided network data for security threats.",
            },
        )
        session.add(analyzer_task)

        # 4. Create reporting tool KU
        reporting_component = DataFactory.create_component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Security Reporting Tool",
            description="Generates security reports and alerts",
            categories=["security", "reporting"],
        )
        session.add(reporting_component)
        await session.flush()

        reporting_ku = DataFactory.create_knowledge_unit(
            component_id=reporting_component.id, ku_type=KUType.TOOL
        )
        session.add(reporting_ku)

        reporting_tool = DataFactory.create_ku_tool(
            component_id=reporting_component.id,
            tool_type="mcp",
            mcp_endpoint="http://localhost:3000/mcp/security-reporter",
        )
        session.add(reporting_tool)

        await session.flush()

        # 5. Create KDG edges to connect the workflow
        edges = [
            # Collector feeds analyzer
            DataFactory.create_kdg_edge(
                source_id=collector_component.id,
                target_id=analyzer_component.id,
                relationship_type=EdgeType.GENERATES,
                tenant_id=tenant_id,
            ),
            # Analyzer uses threat intel
            DataFactory.create_kdg_edge(
                source_id=analyzer_component.id,
                target_id=threat_intel_component.id,
                relationship_type=EdgeType.USES,
                tenant_id=tenant_id,
            ),
            # Analyzer produces reports via tool
            DataFactory.create_kdg_edge(
                source_id=analyzer_component.id,
                target_id=reporting_component.id,
                relationship_type=EdgeType.GENERATES,
                tenant_id=tenant_id,
            ),
        ]

        session.add_all(edges)
        await session.commit()

        return {
            "collector": {"component": collector_component, "task": collector_task},
            "threat_intel": {
                "component": threat_intel_component,
                "ku": threat_intel_ku,
                "table": threat_intel_table,
            },
            "analyzer": {"component": analyzer_component, "task": analyzer_task},
            "reporting": {
                "component": reporting_component,
                "ku": reporting_ku,
                "tool": reporting_tool,
            },
            "edges": edges,
        }
