"""
Integration tests for database operations and transactions.
These tests require a PostgreSQL database and test complex database operations.
"""

from uuid import uuid4

import pytest
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from analysi.models import (
    Component,
    KDGEdge,
    KnowledgeUnit,
    KUDocument,
    Task,
)
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import ComponentKind, ComponentStatus
from analysi.models.kdg_edge import EdgeType
from analysi.models.knowledge_unit import KUType
from analysi.models.task import TaskFunction, TaskScope


@pytest.mark.asyncio
@pytest.mark.integration
class TestDatabaseOperations:
    """Test complex database operations, transactions, and constraints."""

    @pytest.mark.asyncio
    async def test_cascade_delete_component_with_task(self, integration_test_session):
        """Test that deleting a component cascades to delete related task."""
        tenant_id = f"tenant-{uuid4()}"

        # Create component with task
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Deletable Task Component",
            description="Will be deleted",
            created_by=str(SYSTEM_USER_ID),
        )

        integration_test_session.add(component)
        await integration_test_session.flush()

        task = Task(
            component_id=component.id,
            directive="This task will be deleted",
            function=TaskFunction.REASONING,
        )

        integration_test_session.add(task)
        await integration_test_session.commit()

        # Verify task exists
        task_count = await integration_test_session.scalar(
            select(func.count(Task.id)).where(Task.component_id == component.id)
        )
        assert task_count == 1

        # Delete component
        await integration_test_session.delete(component)
        await integration_test_session.commit()

        # Verify task was cascade deleted
        remaining_task_count = await integration_test_session.scalar(
            select(func.count(Task.id)).where(Task.component_id == component.id)
        )
        assert remaining_task_count == 0

    @pytest.mark.asyncio
    async def test_cascade_delete_component_with_ku_and_subtypes(
        self, integration_test_session
    ):
        """Test cascade delete works with KU and its subtypes."""
        tenant_id = f"tenant-{uuid4()}"

        # Create component with KU and document
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Deletable KU Component",
            description="Will be deleted with KU",
            created_by=str(SYSTEM_USER_ID),
        )

        integration_test_session.add(component)
        await integration_test_session.flush()

        ku = KnowledgeUnit(component_id=component.id, ku_type=KUType.DOCUMENT)

        integration_test_session.add(ku)
        await integration_test_session.flush()

        document = KUDocument(
            component_id=component.id,
            content="Document to be deleted",
            document_type="text",
        )

        integration_test_session.add(document)
        await integration_test_session.commit()

        # Verify all exist
        ku_count = await integration_test_session.scalar(
            select(func.count(KnowledgeUnit.id)).where(
                KnowledgeUnit.component_id == component.id
            )
        )
        doc_count = await integration_test_session.scalar(
            select(func.count(KUDocument.id)).where(
                KUDocument.component_id == component.id
            )
        )
        assert ku_count == 1
        assert doc_count == 1

        # Delete component
        await integration_test_session.delete(component)
        await integration_test_session.commit()

        # Verify all were cascade deleted
        remaining_ku_count = await integration_test_session.scalar(
            select(func.count(KnowledgeUnit.id)).where(
                KnowledgeUnit.component_id == component.id
            )
        )
        remaining_doc_count = await integration_test_session.scalar(
            select(func.count(KUDocument.id)).where(
                KUDocument.component_id == component.id
            )
        )
        assert remaining_ku_count == 0
        assert remaining_doc_count == 0

    @pytest.mark.asyncio
    async def test_kdg_edge_cascade_delete(self, integration_test_session):
        """Test that deleting components cascades to delete KDG edges."""
        tenant_id = f"tenant-{uuid4()}"

        # Create two components with an edge between them
        source_component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Source Component",
            description="Source for edge",
            created_by=str(SYSTEM_USER_ID),
        )

        target_component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Target Component",
            description="Target for edge",
            created_by=str(SYSTEM_USER_ID),
        )

        integration_test_session.add_all([source_component, target_component])
        await integration_test_session.flush()

        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=source_component.id,
            target_id=target_component.id,
            relationship_type=EdgeType.USES,
        )

        integration_test_session.add(edge)
        await integration_test_session.commit()

        # Verify edge exists
        edge_count = await integration_test_session.scalar(
            select(func.count(KDGEdge.id)).where(
                KDGEdge.source_id == source_component.id
            )
        )
        assert edge_count == 1

        # Delete source component
        await integration_test_session.delete(source_component)
        await integration_test_session.commit()

        # Verify edge was cascade deleted
        remaining_edge_count = await integration_test_session.scalar(
            select(func.count(KDGEdge.id)).where(
                KDGEdge.source_id == source_component.id
            )
        )
        assert remaining_edge_count == 0

    @pytest.mark.asyncio
    async def test_constraint_violations(self, integration_test_session):
        """Test that database constraints are properly enforced."""
        tenant_id = f"tenant-{uuid4()}"

        # Test unique constraint on component_id in Task
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Test Component",
            description="For constraint testing",
            created_by=str(SYSTEM_USER_ID),
        )

        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create first task
        task1 = Task(
            component_id=component.id,
            directive="First task",
            function=TaskFunction.REASONING,
        )

        integration_test_session.add(task1)
        await integration_test_session.flush()

        # Try to create second task with same component_id (should fail)
        task2 = Task(
            component_id=component.id,
            directive="Second task",
            function=TaskFunction.REASONING,
        )

        integration_test_session.add(task2)

        with pytest.raises(IntegrityError):
            await integration_test_session.commit()

        await integration_test_session.rollback()

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, integration_test_session):
        """Test that failed transactions properly rollback."""
        tenant_id = f"tenant-{uuid4()}"

        # Create a component successfully
        component1 = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Component 1",
            description="First component",
            created_by=str(SYSTEM_USER_ID),
        )

        integration_test_session.add(component1)
        await integration_test_session.commit()

        initial_count = await integration_test_session.scalar(
            select(func.count(Component.id)).where(Component.tenant_id == tenant_id)
        )
        assert initial_count == 1

        # Start a transaction that will fail
        try:
            # Add a valid component
            component2 = Component(
                tenant_id=tenant_id,
                kind=ComponentKind.KU,
                name="Component 2",
                description="Second component",
                created_by=str(SYSTEM_USER_ID),
            )
            integration_test_session.add(component2)
            await integration_test_session.flush()

            # Add an invalid task (violating unique constraint)
            task1 = Task(
                component_id=component1.id,
                directive="First task",
                function=TaskFunction.REASONING,
            )
            integration_test_session.add(task1)
            await integration_test_session.flush()

            # This should fail due to unique constraint
            task2 = Task(
                component_id=component1.id,  # Same component_id
                directive="Second task",
                function=TaskFunction.REASONING,
            )
            integration_test_session.add(task2)
            await integration_test_session.commit()

        except IntegrityError:
            await integration_test_session.rollback()

        # Verify that component2 was rolled back
        final_count = await integration_test_session.scalar(
            select(func.count(Component.id)).where(Component.tenant_id == tenant_id)
        )
        assert final_count == 1  # Only component1 should remain

    @pytest.mark.asyncio
    async def test_complex_query_with_joins(self, integration_test_session):
        """Test complex queries involving joins across multiple tables."""
        tenant_id = f"tenant-{uuid4()}"

        # Create components with tasks and KUs
        task_component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Analysis Task",
            description="Analyzes data",
            created_by=str(SYSTEM_USER_ID),
            categories=["analysis", "security"],
        )

        ku_component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name="Security Rules",
            description="Rules for analysis",
            created_by=str(SYSTEM_USER_ID),
            categories=["rules", "security"],
        )

        integration_test_session.add_all([task_component, ku_component])
        await integration_test_session.flush()

        task = Task(
            component_id=task_component.id,
            directive="Analyze using security rules",
            function=TaskFunction.REASONING,
            scope=TaskScope.PROCESSING,
        )

        ku = KnowledgeUnit(component_id=ku_component.id, ku_type=KUType.DOCUMENT)

        document = KUDocument(
            component_id=ku_component.id,
            content="Security analysis rules content",
            document_type="rules",
            word_count=100,
        )

        integration_test_session.add_all([task, ku, document])
        await integration_test_session.flush()

        # Create edge
        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=task_component.id,
            target_id=ku_component.id,
            relationship_type=EdgeType.USES,
        )

        integration_test_session.add(edge)
        await integration_test_session.commit()

        # Complex query: Find all tasks that use documents with word count > 50
        query = (
            select(Task, Component, KUDocument)
            .join(Component, Task.component_id == Component.id)
            .join(KDGEdge, KDGEdge.source_id == Component.id)
            .join(KUDocument, KUDocument.component_id == KDGEdge.target_id)
            .where(
                and_(
                    Component.tenant_id == tenant_id,
                    KUDocument.word_count > 50,
                    KDGEdge.relationship_type == EdgeType.USES,
                )
            )
        )

        result = await integration_test_session.execute(query)
        rows = result.all()

        assert len(rows) == 1
        task_result, component_result, document_result = rows[0]
        assert task_result.directive == "Analyze using security rules"
        assert component_result.name == "Analysis Task"
        assert document_result.word_count == 100

    @pytest.mark.asyncio
    async def test_bulk_operations(self, integration_test_session):
        """Test bulk insert and update operations."""
        tenant_id = f"tenant-{uuid4()}"

        # Bulk create components
        components = []
        for i in range(10):
            component = Component(
                tenant_id=tenant_id,
                kind=ComponentKind.TASK if i % 2 == 0 else ComponentKind.KU,
                name=f"Bulk Component {i}",
                description=f"Component created in bulk {i}",
                created_by=str(SYSTEM_USER_ID),
                categories=["bulk", f"batch_{i // 5}"],
            )
            components.append(component)

        integration_test_session.add_all(components)
        await integration_test_session.flush()

        # Create tasks for task components
        tasks = []
        for component in components:
            if component.kind == ComponentKind.TASK:
                task = Task(
                    component_id=component.id,
                    directive=f"Bulk task for {component.name}",
                    function=TaskFunction.REASONING,
                )
                tasks.append(task)

        integration_test_session.add_all(tasks)
        await integration_test_session.commit()

        # Verify bulk operations
        component_count = await integration_test_session.scalar(
            select(func.count(Component.id)).where(Component.tenant_id == tenant_id)
        )
        task_count = await integration_test_session.scalar(
            select(func.count(Task.id))
            .join(Component, Task.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
        )

        assert component_count == 10
        assert task_count == 5  # Only task components got tasks

        # Test bulk update
        from sqlalchemy import update

        await integration_test_session.execute(
            update(Component)
            .where(
                and_(
                    Component.tenant_id == tenant_id,
                    Component.categories.op("@>")(["bulk"]),
                )
            )
            .values(status=ComponentStatus.DISABLED)
        )
        await integration_test_session.commit()

        # Verify bulk update
        disabled_count = await integration_test_session.scalar(
            select(func.count(Component.id)).where(
                and_(
                    Component.tenant_id == tenant_id,
                    Component.status == ComponentStatus.DISABLED,
                )
            )
        )
        assert disabled_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_access_simulation(self, integration_test_session):
        """Test database behavior under concurrent-like access patterns."""
        tenant_id = f"tenant-{uuid4()}"

        # Simulate concurrent component creation
        base_component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name="Concurrent Test Component",
            description="Testing concurrent access",
            created_by=str(SYSTEM_USER_ID),
        )

        integration_test_session.add(base_component)
        await integration_test_session.flush()

        # Create multiple KDG edges from different "sessions"
        target_components = []
        for i in range(5):
            target = Component(
                tenant_id=tenant_id,
                kind=ComponentKind.KU,
                name=f"Target Component {i}",
                description=f"Target {i}",
                created_by=str(SYSTEM_USER_ID),
            )
            target_components.append(target)

        integration_test_session.add_all(target_components)
        await integration_test_session.flush()

        # Create edges to all targets
        edges = []
        for i, target in enumerate(target_components):
            edge = KDGEdge(
                tenant_id=tenant_id,
                source_id=base_component.id,
                target_id=target.id,
                relationship_type=EdgeType.USES,
                edge_metadata={"batch": i // 2, "priority": "normal"},
            )
            edges.append(edge)

        integration_test_session.add_all(edges)
        await integration_test_session.commit()

        # Verify all edges were created correctly
        edge_count = await integration_test_session.scalar(
            select(func.count(KDGEdge.id)).where(KDGEdge.source_id == base_component.id)
        )
        assert edge_count == 5

        # Test querying with aggregations - count edges per source
        edge_count_per_source = await integration_test_session.scalar(
            select(func.count(KDGEdge.id)).where(KDGEdge.source_id == base_component.id)
        )
        assert edge_count_per_source == 5  # Should have 5 outgoing edges
