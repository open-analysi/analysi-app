"""
Integration tests for complete end-to-end scenarios.
These tests require a PostgreSQL database and test complete workflows.
"""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from analysi.models import Component, KDGEdge, KnowledgeUnit, Task
from analysi.models.component import ComponentKind
from analysi.models.kdg_edge import EdgeType
from analysi.models.knowledge_unit import KUType
from analysi.models.task import TaskFunction
from tests.fixtures.data_factory import DataFactory, ScenarioFactory


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompleteScenarios:
    """Test complete end-to-end scenarios using the data factory."""

    @pytest.mark.asyncio
    async def test_security_analysis_workflow_creation(self, integration_test_session):
        """Test creating a complete security analysis workflow."""
        tenant_id = f"tenant-{uuid4()}"

        # Create the complete workflow
        workflow = await ScenarioFactory.create_security_analysis_workflow(
            integration_test_session, tenant_id
        )

        # Verify all components were created
        component_count = await integration_test_session.scalar(
            select(func.count(Component.id)).where(Component.tenant_id == tenant_id)
        )
        assert component_count == 4  # collector, threat_intel, analyzer, reporting

        # Verify all tasks were created
        task_count = await integration_test_session.scalar(
            select(func.count(Task.id))
            .join(Component, Task.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
        )
        assert task_count == 2  # collector and analyzer tasks

        # Verify all KUs were created
        ku_count = await integration_test_session.scalar(
            select(func.count(KnowledgeUnit.id))
            .join(Component, KnowledgeUnit.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
        )
        assert ku_count == 2  # threat_intel and reporting KUs

        # Verify edges were created
        edge_count = await integration_test_session.scalar(
            select(func.count(KDGEdge.id))
            .join(Component, KDGEdge.source_id == Component.id)
            .where(Component.tenant_id == tenant_id)
        )
        assert (
            edge_count == 3
        )  # collector->analyzer, analyzer->threat_intel, analyzer->reporting

        # Verify workflow structure
        collector = workflow["collector"]["component"]
        analyzer = workflow["analyzer"]["component"]

        # Load relationships
        await integration_test_session.refresh(collector, ["outgoing_edges"])
        await integration_test_session.refresh(
            analyzer, ["incoming_edges", "outgoing_edges"]
        )

        assert len(collector.outgoing_edges) == 1
        assert collector.outgoing_edges[0].target_id == analyzer.id
        assert len(analyzer.incoming_edges) == 1
        assert len(analyzer.outgoing_edges) == 2  # to threat_intel and reporting

    @pytest.mark.asyncio
    async def test_workflow_execution_simulation(self, integration_test_session):
        """Test simulating workflow execution by updating component states."""
        tenant_id = f"tenant-{uuid4()}"

        # Create workflow
        workflow = await ScenarioFactory.create_security_analysis_workflow(
            integration_test_session, tenant_id
        )

        collector_component = workflow["collector"]["component"]
        analyzer_component = workflow["analyzer"]["component"]

        # Simulate workflow execution by updating last_used_at
        from datetime import UTC, datetime

        from sqlalchemy import select

        # Store the IDs before modifying
        collector_id = collector_component.id
        analyzer_id = analyzer_component.id

        # Update collector as "executed"
        collector_component.last_used_at = datetime.now(tz=UTC)

        # Update analyzer as "executed" after collector
        analyzer_component.last_used_at = datetime.now(tz=UTC)

        await integration_test_session.commit()

        # Reload the components from database to verify updates
        collector_reloaded = await integration_test_session.scalar(
            select(Component).where(Component.id == collector_id)
        )
        analyzer_reloaded = await integration_test_session.scalar(
            select(Component).where(Component.id == analyzer_id)
        )

        assert collector_reloaded.last_used_at is not None
        assert analyzer_reloaded.last_used_at is not None
        assert analyzer_reloaded.last_used_at >= collector_reloaded.last_used_at

    @pytest.mark.asyncio
    async def test_multi_tenant_workflow_isolation(self, integration_test_session):
        """Test that workflows are properly isolated between tenants."""
        tenant1_id = f"tenant-{uuid4()}"
        tenant2_id = f"tenant-{uuid4()}"

        # Create workflows for both tenants
        await ScenarioFactory.create_security_analysis_workflow(
            integration_test_session, tenant1_id
        )
        await ScenarioFactory.create_security_analysis_workflow(
            integration_test_session, tenant2_id
        )

        # Verify tenant isolation
        t1_components = await integration_test_session.scalar(
            select(func.count(Component.id)).where(Component.tenant_id == tenant1_id)
        )
        t2_components = await integration_test_session.scalar(
            select(func.count(Component.id)).where(Component.tenant_id == tenant2_id)
        )

        assert t1_components == 4
        assert t2_components == 4

        # Verify no cross-tenant edges
        t1_edges = await integration_test_session.execute(
            select(KDGEdge)
            .join(Component, KDGEdge.source_id == Component.id)
            .where(Component.tenant_id == tenant1_id)
        )

        for edge in t1_edges.scalars().all():
            # Verify target also belongs to tenant1
            target_result = await integration_test_session.execute(
                select(Component).where(Component.id == edge.target_id)
            )
            target_component = target_result.scalar_one()
            assert target_component.tenant_id == tenant1_id

    @pytest.mark.asyncio
    async def test_workflow_dependency_chain_validation(self, integration_test_session):
        """Test validating a complex dependency chain."""
        tenant_id = f"tenant-{uuid4()}"

        # Create a more complex workflow: A -> B -> C -> D
        components = []
        tasks = []

        for i in range(4):
            component = DataFactory.create_component(
                tenant_id=tenant_id,
                kind=ComponentKind.TASK,
                name=f"Chain Task {i}",
                description=f"Task {i} in processing chain",
                categories=["chain", f"step_{i}"],
            )
            components.append(component)
            integration_test_session.add(component)

        await integration_test_session.flush()

        # Create tasks for each component
        for i, component in enumerate(components):
            task = DataFactory.create_task(
                component_id=component.id,
                directive=f"Process step {i} of the chain",
                function=TaskFunction.REASONING,
                llm_config={"step": i, "depends_on_previous": i > 0},
            )
            tasks.append(task)
            integration_test_session.add(task)

        await integration_test_session.flush()

        # Create chain edges: 0->1->2->3
        edges = []
        for i in range(3):
            edge = DataFactory.create_kdg_edge(
                source_id=components[i].id,
                target_id=components[i + 1].id,
                relationship_type=EdgeType.GENERATES,
                edge_metadata={"chain_position": i, "next_step": i + 1},
                tenant_id=tenant_id,
            )
            edges.append(edge)
            integration_test_session.add(edge)

        await integration_test_session.commit()

        # Validate the chain structure
        for i, component in enumerate(components):
            await integration_test_session.refresh(
                component, ["outgoing_edges", "incoming_edges"]
            )

            if i == 0:  # First in chain
                assert len(component.incoming_edges) == 0
                assert len(component.outgoing_edges) == 1
            elif i == 3:  # Last in chain
                assert len(component.incoming_edges) == 1
                assert len(component.outgoing_edges) == 0
            else:  # Middle of chain
                assert len(component.incoming_edges) == 1
                assert len(component.outgoing_edges) == 1

        # Verify chain connectivity
        for i in range(3):
            await integration_test_session.refresh(components[i], ["outgoing_edges"])
            outgoing_edge = components[i].outgoing_edges[0]
            assert outgoing_edge.target_id == components[i + 1].id
            assert outgoing_edge.edge_metadata["chain_position"] == i

    @pytest.mark.asyncio
    async def test_workflow_with_multiple_ku_types(self, integration_test_session):
        """Test a workflow that uses multiple KU types."""
        tenant_id = f"tenant-{uuid4()}"

        # Create central processing task
        processor_component = DataFactory.create_component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Multi-Source Data Processor",
            description="Processes data from multiple KU types",
            categories=["processing", "multi-source"],
        )
        integration_test_session.add(processor_component)
        await integration_test_session.flush()

        processor_task = DataFactory.create_task(
            component_id=processor_component.id,
            directive="Process data from documents, tables, and tools",
            function=TaskFunction.REASONING,
        )
        integration_test_session.add(processor_task)

        # Create KUs of different types
        ku_components = []
        kus = []
        ku_subtypes = []

        # Document KU
        doc_component = DataFactory.create_component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Documentation Source",
            categories=["document", "source"],
        )
        integration_test_session.add(doc_component)
        ku_components.append(doc_component)

        # Table KU
        table_component = DataFactory.create_component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Data Table Source",
            categories=["table", "source"],
        )
        integration_test_session.add(table_component)
        ku_components.append(table_component)

        # Tool KU
        tool_component = DataFactory.create_component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="External Tool Source",
            categories=["tool", "source"],
        )
        integration_test_session.add(tool_component)
        ku_components.append(tool_component)

        await integration_test_session.flush()

        # Create KUs and subtypes
        doc_ku = DataFactory.create_knowledge_unit(doc_component.id, KUType.DOCUMENT)
        doc_subtype = DataFactory.create_ku_document(doc_component.id)

        table_ku = DataFactory.create_knowledge_unit(table_component.id, KUType.TABLE)
        table_subtype = DataFactory.create_ku_table(table_component.id)

        tool_ku = DataFactory.create_knowledge_unit(tool_component.id, KUType.TOOL)
        tool_subtype = DataFactory.create_ku_tool(tool_component.id)

        kus.extend([doc_ku, table_ku, tool_ku])
        ku_subtypes.extend([doc_subtype, table_subtype, tool_subtype])

        integration_test_session.add_all(kus + ku_subtypes)
        await integration_test_session.flush()

        # Create edges from processor to all KUs
        edges = []
        for i, ku_component in enumerate(ku_components):
            edge = DataFactory.create_kdg_edge(
                source_id=processor_component.id,
                target_id=ku_component.id,
                relationship_type=EdgeType.USES,
                edge_metadata={"source_type": ["document", "table", "tool"][i]},
                tenant_id=tenant_id,
            )
            edges.append(edge)
            integration_test_session.add(edge)

        await integration_test_session.commit()

        # Verify the multi-KU workflow
        await integration_test_session.refresh(processor_component, ["outgoing_edges"])
        assert len(processor_component.outgoing_edges) == 3

        # Verify each KU type is represented
        used_ku_types = set()
        for edge in processor_component.outgoing_edges:
            target_result = await integration_test_session.execute(
                select(Component).where(Component.id == edge.target_id)
            )
            target_component = target_result.scalar_one()

            await integration_test_session.refresh(target_component, ["knowledge_unit"])
            if target_component.knowledge_unit:
                used_ku_types.add(target_component.knowledge_unit.ku_type)

        assert used_ku_types == {KUType.DOCUMENT, KUType.TABLE, KUType.TOOL}

    @pytest.mark.asyncio
    async def test_workflow_performance_with_large_dataset(
        self, integration_test_session
    ):
        """Test workflow creation and querying performance with larger dataset."""
        tenant_id = f"tenant-{uuid4()}"

        # Create a larger workflow (20 components, 30 edges)
        components = []

        # Create 10 task components
        for i in range(10):
            component = DataFactory.create_component(
                tenant_id=tenant_id,
                kind=ComponentKind.TASK,
                name=f"Large Workflow Task {i}",
                categories=["large", "performance", f"batch_{i // 5}"],
            )
            components.append(component)
            integration_test_session.add(component)

        # Create 10 KU components
        for i in range(10, 20):
            component = DataFactory.create_component(
                tenant_id=tenant_id,
                kind=ComponentKind.KU,
                name=f"Large Workflow KU {i}",
                categories=["large", "performance", f"batch_{i // 5}"],
            )
            components.append(component)
            integration_test_session.add(component)

        await integration_test_session.flush()

        # Create tasks for task components
        for i in range(10):
            task = DataFactory.create_task(
                component_id=components[i].id,
                directive=f"Large workflow task {i}",
                function=TaskFunction.REASONING,
            )
            integration_test_session.add(task)

        # Create KUs for KU components
        for i in range(10, 20):
            ku = DataFactory.create_knowledge_unit(
                component_id=components[i].id,
                ku_type=KUType.DOCUMENT if i % 2 == 0 else KUType.TABLE,
            )
            integration_test_session.add(ku)

        await integration_test_session.flush()

        # Create 30 unique edges (complex interconnections)
        edges = []
        import random

        used_pairs = set()

        i = 0
        while len(edges) < 30 and i < 100:  # Safety limit to avoid infinite loop
            source_idx = random.randint(0, 19)
            target_idx = random.randint(0, 19)

            # Avoid self-loops
            if source_idx == target_idx:
                target_idx = (target_idx + 1) % 20

            # Check for unique constraint: (tenant_id, source, target, relationship_type)
            edge_key = (components[source_idx].id, components[target_idx].id)

            if edge_key not in used_pairs:
                used_pairs.add(edge_key)
                edge = DataFactory.create_kdg_edge(
                    source_id=components[source_idx].id,
                    target_id=components[target_idx].id,
                    relationship_type=EdgeType.USES,
                    edge_metadata={"edge_number": len(edges), "random_weight": True},
                    tenant_id=tenant_id,
                )
                edges.append(edge)
                integration_test_session.add(edge)

            i += 1

        await integration_test_session.commit()

        # Performance test: Complex query
        import time

        start_time = time.time()

        # Find all task components that have outgoing edges to KU components
        # Create an alias for the target component
        from sqlalchemy.orm import aliased

        TargetComponent = aliased(Component)

        query = (
            select(Component, func.count(KDGEdge.id).label("edge_count"))
            .join(KDGEdge, Component.id == KDGEdge.source_id)
            .join(TargetComponent, KDGEdge.target_id == TargetComponent.id)
            .where(
                Component.tenant_id == tenant_id,
                Component.kind == ComponentKind.TASK,
                TargetComponent.kind == ComponentKind.KU,
            )
            .group_by(Component.id)
            .having(func.count(KDGEdge.id) > 0)
        )

        result = await integration_test_session.execute(query)
        task_components_with_edges = result.all()

        query_time = time.time() - start_time

        # Verify results and performance
        assert len(task_components_with_edges) > 0
        assert query_time < 1.0  # Should complete in under 1 second

        # Verify data integrity
        total_components = await integration_test_session.scalar(
            select(func.count(Component.id)).where(Component.tenant_id == tenant_id)
        )
        total_edges = await integration_test_session.scalar(
            select(func.count(KDGEdge.id))
            .join(Component, KDGEdge.source_id == Component.id)
            .where(Component.tenant_id == tenant_id)
        )

        assert total_components == 20
        assert total_edges == len(
            edges
        )  # Should equal the actual number of edges created
