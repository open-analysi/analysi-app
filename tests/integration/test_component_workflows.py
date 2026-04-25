"""
Integration tests for Component workflows.
These tests require a PostgreSQL database and test full workflows across multiple models.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from analysi.models import Component, KDGEdge, KnowledgeUnit, KUDocument, Task
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import ComponentKind
from analysi.models.kdg_edge import EdgeType
from analysi.models.knowledge_unit import KUType
from analysi.models.task import TaskFunction, TaskScope


@pytest.mark.asyncio
@pytest.mark.integration
class TestComponentWorkflows:
    """Test complete workflows involving components and related entities."""

    @pytest.mark.asyncio
    async def test_task_creation_workflow(self, integration_test_session):
        """Test complete task creation workflow."""
        tenant_id = f"tenant-{uuid4()}"

        # Create component
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Data Analysis Task",
            description="Analyzes security logs",
            created_by=str(SYSTEM_USER_ID),
            visible=True,
            app="security_app",
            categories=["security", "analysis"],
        )

        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create task linked to component
        llm_config = {
            "default_model": "gpt-4",
            "temperature": 0.1,
            "max_tokens": 2000,
            "system_prompt": "You are a cybersecurity analyst.",
        }

        task = Task(
            component_id=component.id,
            directive="Analyze network logs for suspicious activity",
            script="#!cy 2.1\nanalyze_logs(input_data)",
            function=TaskFunction.REASONING,
            scope=TaskScope.PROCESSING,
            schedule="0 */6 * * *",  # every 6 hours
            llm_config=llm_config,
        )

        integration_test_session.add(task)
        await integration_test_session.commit()

        # Verify complete workflow
        result = await integration_test_session.execute(
            select(Component).where(Component.id == component.id)
        )
        retrieved_component = result.scalar_one()

        # Load task relationship
        await integration_test_session.refresh(retrieved_component, ["task"])

        assert retrieved_component.task is not None
        assert (
            retrieved_component.task.directive
            == "Analyze network logs for suspicious activity"
        )
        assert retrieved_component.task.function == TaskFunction.REASONING
        assert retrieved_component.task.llm_config["default_model"] == "gpt-4"
        assert retrieved_component.categories == ["security", "analysis"]

    @pytest.mark.asyncio
    async def test_knowledge_unit_creation_workflow(self, integration_test_session):
        """Test complete KU creation workflow with document subtype."""
        tenant_id = f"tenant-{uuid4()}"

        # Create component for KU
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Security Playbook",
            description="Incident response procedures",
            created_by=str(SYSTEM_USER_ID),
            system_only=True,
        )

        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create knowledge unit
        ku = KnowledgeUnit(component_id=component.id, ku_type=KUType.DOCUMENT)

        integration_test_session.add(ku)
        await integration_test_session.flush()

        # Create document subtype
        metadata = {
            "source": "internal",
            "classification": "confidential",
            "version": "2.1",
            "approval_status": "approved",
        }

        document = KUDocument(
            component_id=component.id,
            content="# Incident Response Playbook\n\n## Phase 1: Detection...",
            markdown_content="# Incident Response Playbook\n\n## Phase 1: Detection...",
            document_type="markdown",
            content_source="manual",
            doc_metadata=metadata,
            word_count=500,
            character_count=2500,
            language="en",
        )

        integration_test_session.add(document)
        await integration_test_session.commit()

        # Verify complete workflow
        result = await integration_test_session.execute(
            select(Component).where(Component.id == component.id)
        )
        retrieved_component = result.scalar_one()

        # Load KU relationship
        await integration_test_session.refresh(retrieved_component, ["knowledge_unit"])

        assert retrieved_component.knowledge_unit is not None
        assert retrieved_component.knowledge_unit.ku_type == KUType.DOCUMENT

        # Verify document exists
        doc_result = await integration_test_session.execute(
            select(KUDocument).where(KUDocument.component_id == component.id)
        )
        retrieved_doc = doc_result.scalar_one()

        assert retrieved_doc.doc_metadata["classification"] == "confidential"
        assert retrieved_doc.word_count == 500
        assert "Incident Response" in retrieved_doc.content

    @pytest.mark.asyncio
    async def test_kdg_edge_workflow(self, integration_test_session):
        """Test complete KDG edge creation workflow."""
        tenant_id = f"tenant-{uuid4()}"

        # Create source component (Task)
        source_component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Log Analyzer",
            description="Analyzes system logs",
            created_by=str(SYSTEM_USER_ID),
        )

        # Create target component (KU)
        target_component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Log Analysis Rules",
            description="Rules for log analysis",
            created_by=str(SYSTEM_USER_ID),
        )

        integration_test_session.add_all([source_component, target_component])
        await integration_test_session.flush()

        # Create task for source
        task = Task(
            component_id=source_component.id,
            directive="Analyze logs using predefined rules",
            function=TaskFunction.REASONING,
        )

        # Create KU for target
        ku = KnowledgeUnit(component_id=target_component.id, ku_type=KUType.DOCUMENT)

        integration_test_session.add_all([task, ku])
        await integration_test_session.flush()

        # Create KDG edge
        edge_metadata = {
            "dependency_type": "requires",
            "priority": "high",
            "created_by": str(SYSTEM_USER_ID),
        }

        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=source_component.id,
            target_id=target_component.id,
            relationship_type=EdgeType.USES,
            edge_metadata=edge_metadata,
        )

        integration_test_session.add(edge)
        await integration_test_session.commit()

        # Verify complete workflow
        # Check source component has outgoing edge
        await integration_test_session.refresh(source_component, ["outgoing_edges"])
        assert len(source_component.outgoing_edges) == 1
        assert source_component.outgoing_edges[0].target_id == target_component.id
        assert source_component.outgoing_edges[0].relationship_type == EdgeType.USES

        # Check target component has incoming edge
        await integration_test_session.refresh(target_component, ["incoming_edges"])
        assert len(target_component.incoming_edges) == 1
        assert target_component.incoming_edges[0].source_id == source_component.id
        assert target_component.incoming_edges[0].edge_metadata["priority"] == "high"

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, integration_test_session):
        """Test that tenant isolation works across all models."""
        tenant1_id = f"tenant-{uuid4()}"
        tenant2_id = f"tenant-{uuid4()}"

        # Create components for each tenant
        t1_component = Component(
            tenant_id=tenant1_id,
            kind=ComponentKind.TASK,
            name="Tenant 1 Task",
            description="Task for tenant 1",
            created_by=str(SYSTEM_USER_ID),
        )

        t2_component = Component(
            tenant_id=tenant2_id,
            kind=ComponentKind.TASK,
            name="Tenant 2 Task",
            description="Task for tenant 2",
            created_by=str(SYSTEM_USER_ID),
        )

        integration_test_session.add_all([t1_component, t2_component])
        await integration_test_session.flush()

        # Create tasks for each tenant
        t1_task = Task(
            component_id=t1_component.id,
            directive="Tenant 1 analysis",
            function=TaskFunction.REASONING,
        )

        t2_task = Task(
            component_id=t2_component.id,
            directive="Tenant 2 analysis",
            function=TaskFunction.REASONING,
        )

        integration_test_session.add_all([t1_task, t2_task])
        await integration_test_session.commit()

        # Query tenant 1 components only
        t1_result = await integration_test_session.execute(
            select(Component).where(Component.tenant_id == tenant1_id)
        )
        t1_components = t1_result.scalars().all()

        # Query tenant 2 components only
        t2_result = await integration_test_session.execute(
            select(Component).where(Component.tenant_id == tenant2_id)
        )
        t2_components = t2_result.scalars().all()

        # Verify isolation
        assert len(t1_components) == 1
        assert len(t2_components) == 1
        assert t1_components[0].name == "Tenant 1 Task"
        assert t2_components[0].name == "Tenant 2 Task"

        # Verify tasks are also isolated
        for component in t1_components:
            await integration_test_session.refresh(component, ["task"])
            if component.task:
                assert "Tenant 1" in component.task.directive

        for component in t2_components:
            await integration_test_session.refresh(component, ["task"])
            if component.task:
                assert "Tenant 2" in component.task.directive

    @pytest.mark.asyncio
    async def test_complex_dependency_graph(self, integration_test_session):
        """Test creating a complex dependency graph with multiple components."""
        tenant_id = f"tenant-{uuid4()}"

        # Create components: 1 Task -> 2 KUs -> 1 Task (chain)
        components = []
        component_names = [
            ("Data Collector", ComponentKind.TASK),
            ("Raw Data Store", ComponentKind.KU),
            ("Processing Rules", ComponentKind.KU),
            ("Data Processor", ComponentKind.TASK),
        ]

        for name, kind in component_names:
            component = Component(
                tenant_id=tenant_id,
                kind=kind,
                name=name,
                description=f"Component: {name}",
                created_by=str(SYSTEM_USER_ID),
            )
            components.append(component)

        integration_test_session.add_all(components)
        await integration_test_session.flush()

        # Create tasks and KUs
        collector_task = Task(
            component_id=components[0].id,
            directive="Collect raw security data",
            function=TaskFunction.SEARCH,  # COLLECTION doesn't exist, use SEARCH instead
        )

        processor_task = Task(
            component_id=components[3].id,
            directive="Process collected data using rules",
            function=TaskFunction.REASONING,
        )

        raw_data_ku = KnowledgeUnit(component_id=components[1].id, ku_type=KUType.TABLE)

        rules_ku = KnowledgeUnit(component_id=components[2].id, ku_type=KUType.DOCUMENT)

        integration_test_session.add_all(
            [collector_task, processor_task, raw_data_ku, rules_ku]
        )
        await integration_test_session.flush()

        # Create dependency edges: Collector -> Raw Data -> Processor
        #                         Processing Rules -> Processor
        edges = [
            KDGEdge(
                tenant_id=tenant_id,
                source_id=components[0].id,  # Collector
                target_id=components[1].id,  # Raw Data
                relationship_type=EdgeType.GENERATES,
            ),
            KDGEdge(
                tenant_id=tenant_id,
                source_id=components[1].id,  # Raw Data
                target_id=components[3].id,  # Processor
                relationship_type=EdgeType.GENERATES,
            ),
            KDGEdge(
                tenant_id=tenant_id,
                source_id=components[2].id,  # Rules
                target_id=components[3].id,  # Processor
                relationship_type=EdgeType.USES,
            ),
        ]

        integration_test_session.add_all(edges)
        await integration_test_session.commit()

        # Verify the dependency graph
        # Collector should have 1 outgoing edge
        await integration_test_session.refresh(components[0], ["outgoing_edges"])
        assert len(components[0].outgoing_edges) == 1
        assert components[0].outgoing_edges[0].relationship_type == EdgeType.GENERATES

        # Raw Data should have 1 incoming, 1 outgoing
        await integration_test_session.refresh(
            components[1], ["incoming_edges", "outgoing_edges"]
        )
        assert len(components[1].incoming_edges) == 1
        assert len(components[1].outgoing_edges) == 1

        # Processor should have 2 incoming edges
        await integration_test_session.refresh(components[3], ["incoming_edges"])
        assert len(components[3].incoming_edges) == 2

        # Check edge types
        processor_relationship_types = [
            edge.relationship_type for edge in components[3].incoming_edges
        ]
        assert EdgeType.GENERATES in processor_relationship_types
        assert EdgeType.USES in processor_relationship_types
