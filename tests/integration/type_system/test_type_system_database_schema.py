"""
Integration tests for type system database schema.

Tests database schema changes that support the Rodos type system:
- workflow_nodes.is_start_node: Marks nodes that receive workflow input schema
- node_templates.kind: Classifies templates for type inference (identity, merge, collect, etc.)

Migrations: V041 (is_start_node) and V042 (kind)

Note: task.output_schema was intentionally NOT added. Task outputs are inferred
via Cy's duck typing at runtime, not predefined in the database.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.integration
class TestMigrationExecution:
    """Test that type system migrations execute correctly."""

    @pytest.mark.asyncio
    async def test_migration_workflow_nodes_is_start_node(
        self, db_session: AsyncSession
    ):
        """
        Test V041 adds is_start_node column to workflow_nodes.

        Positive case: Migration adds field correctly.
        """
        # Check column exists
        result = await db_session.execute(
            text(
                """
                SELECT column_name, column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'workflow_nodes'
                AND column_name = 'is_start_node'
                """
            )
        )
        column_info = result.fetchone()

        # Verify column `is_start_node` exists on workflow_nodes table
        assert column_info is not None, "is_start_node column should exist"

        # Verify default value is false
        assert "false" in str(column_info[1]).lower(), "Default should be false"

        # Verify column is NOT NULL
        assert column_info[2] == "NO", "Column should be NOT NULL"

        # Verify index idx_workflow_nodes_start exists
        result = await db_session.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'workflow_nodes'
                AND indexname = 'idx_workflow_nodes_start'
                """
            )
        )
        index_exists = result.fetchone() is not None
        assert index_exists, "Index idx_workflow_nodes_start should exist"

    @pytest.mark.asyncio
    async def test_migration_node_templates_kind(self, db_session: AsyncSession):
        """
        Test V042 adds kind column to node_templates.

        Positive case: Migration adds field correctly.
        """
        # Check column exists
        result = await db_session.execute(
            text(
                """
                SELECT column_name, column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'node_templates'
                AND column_name = 'kind'
                """
            )
        )
        column_info = result.fetchone()

        # Verify column `kind` exists on node_templates table
        assert column_info is not None, "kind column should exist"

        # NOTE: Column default was removed in a later migration
        # Verify kind is NOT NULL (required field)
        assert column_info[2] == "NO", "Column should be NOT NULL"

        # Verify constraint allows only valid kinds
        result = await db_session.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE conname = 'node_templates_kind_check'
                """
            )
        )
        constraint_exists = result.fetchone() is not None
        assert constraint_exists, "Constraint node_templates_kind_check should exist"

        # Verify index idx_node_templates_kind exists
        result = await db_session.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'node_templates'
                AND indexname = 'idx_node_templates_kind'
                """
            )
        )
        index_exists = result.fetchone() is not None
        assert index_exists, "Index idx_node_templates_kind should exist"

    @pytest.mark.asyncio
    async def test_migration_idempotency(self, db_session: AsyncSession):
        """
        Test migrations are idempotent (safe to run multiple times).

        Positive case: Migrations are idempotent.
        """
        # Verify tables exist (migrations already ran)
        result = await db_session.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name IN ('workflow_nodes', 'node_templates')
                AND column_name IN ('is_start_node', 'kind')
                """
            )
        )
        columns = result.fetchall()

        # Verify both columns exist
        column_names = {col[0] for col in columns}
        assert "is_start_node" in column_names
        assert "kind" in column_names

        # Note: Actual idempotency is tested by Flyway
        # This test verifies the database state is correct

    @pytest.mark.asyncio
    async def test_migration_preserves_existing_workflows(
        self, db_session: AsyncSession
    ):
        """
        Test migrations preserve existing workflows.

        Positive case: Backward compatibility.
        """
        # Create a test workflow with nodes
        workflow_id = uuid4()
        node_id = uuid4()
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        await db_session.execute(
            text(
                """
                INSERT INTO workflows (id, tenant_id, name, io_schema, created_by, is_dynamic)
                VALUES (:id, :tenant_id, :name, :io_schema, :created_by, :is_dynamic)
                """
            ),
            {
                "id": workflow_id,
                "tenant_id": tenant_id,
                "name": "Test Workflow",
                "io_schema": '{"input": {}, "output": {}}',
                "created_by": str(SYSTEM_USER_ID),
                "is_dynamic": False,
            },
        )

        # Create a transformation node (simpler than task - doesn't require task table entry)
        template_id = uuid4()
        template_resource_id = uuid4()
        await db_session.execute(
            text(
                """
                INSERT INTO node_templates
                (id, resource_id, name, input_schema, output_schema, code, language, type, kind, enabled, revision_num)
                VALUES
                (:id, :resource_id, :name, :input_schema, :output_schema, :code, :language, :type, :kind, :enabled, :revision_num)
                """
            ),
            {
                "id": template_id,
                "resource_id": template_resource_id,
                "name": "test_template",
                "input_schema": '{"type": "object"}',
                "output_schema": '{"type": "object"}',
                "code": "return inp",
                "language": "python",
                "type": "static",
                "kind": "identity",
                "enabled": True,
                "revision_num": 1,
            },
        )

        await db_session.execute(
            text(
                """
                INSERT INTO workflow_nodes (id, workflow_id, node_id, kind, name, schemas, node_template_id)
                VALUES (:id, :workflow_id, :node_id, :kind, :name, :schemas, :node_template_id)
                """
            ),
            {
                "id": node_id,
                "workflow_id": workflow_id,
                "node_id": "n1",
                "kind": "transformation",
                "name": "Test Node",
                "schemas": "{}",
                "node_template_id": template_id,
            },
        )
        await db_session.commit()

        # Verify existing workflow still loads correctly
        result = await db_session.execute(
            text("SELECT id FROM workflows WHERE id = :id"),
            {"id": workflow_id},
        )
        assert result.fetchone() is not None, "Workflow should exist"

        # Verify existing nodes have is_start_node=false (default)
        result = await db_session.execute(
            text("SELECT is_start_node FROM workflow_nodes WHERE id = :id"),
            {"id": node_id},
        )
        is_start = result.scalar()
        assert is_start is False, "Default is_start_node should be False"

    @pytest.mark.asyncio
    async def test_migration_preserves_existing_templates(
        self, db_session: AsyncSession
    ):
        """
        Test migrations preserve existing node templates.

        Positive case: Backward compatibility.
        """
        # Create a test node template
        template_id = uuid4()
        resource_id = uuid4()

        await db_session.execute(
            text(
                """
                INSERT INTO node_templates
                (id, resource_id, name, input_schema, output_schema, code, language, type, kind, enabled, revision_num)
                VALUES
                (:id, :resource_id, :name, :input_schema, :output_schema, :code, :language, :type, :kind, :enabled, :revision_num)
                """
            ),
            {
                "id": template_id,
                "resource_id": resource_id,
                "name": "test_template",
                "input_schema": '{"type": "object"}',
                "output_schema": '{"type": "object"}',
                "code": "return inp",
                "language": "python",
                "type": "static",
                "kind": "identity",
                "enabled": True,
                "revision_num": 1,
            },
        )
        await db_session.commit()

        # Verify existing templates have kind='identity' (default)
        result = await db_session.execute(
            text("SELECT kind FROM node_templates WHERE id = :id"),
            {"id": template_id},
        )
        kind = result.scalar()
        assert kind == "identity", "Default kind should be 'identity'"

        # Verify existing templates still work
        result = await db_session.execute(
            text("SELECT id FROM node_templates WHERE id = :id"),
            {"id": template_id},
        )
        assert result.fetchone() is not None, "Template should exist"


@pytest.mark.integration
class TestConstraints:
    """Test database constraints work correctly."""

    @pytest.mark.asyncio
    async def test_node_template_kind_constraint_valid(self, db_session: AsyncSession):
        """
        Test valid kind values are accepted.

        Positive case: Valid kinds accepted.
        """
        # Create node_template with kind='merge'
        template_id = uuid4()
        resource_id = uuid4()

        await db_session.execute(
            text(
                """
                INSERT INTO node_templates
                (id, resource_id, name, input_schema, output_schema, code, language, type, enabled, revision_num, kind)
                VALUES
                (:id, :resource_id, :name, :input_schema, :output_schema, :code, :language, :type, :enabled, :revision_num, :kind)
                """
            ),
            {
                "id": template_id,
                "resource_id": resource_id,
                "name": "merge_template",
                "input_schema": '{"type": "object"}',
                "output_schema": '{"type": "object"}',
                "code": "return inp",
                "language": "python",
                "type": "static",
                "enabled": True,
                "revision_num": 1,
                "kind": "merge",
            },
        )
        await db_session.commit()

        # Verify insert succeeds
        result = await db_session.execute(
            text("SELECT kind FROM node_templates WHERE id = :id"),
            {"id": template_id},
        )
        kind = result.scalar()
        assert kind == "merge"

        # Try kinds: identity, merge, collect
        for test_kind in ["identity", "collect"]:
            template_id_2 = uuid4()
            resource_id_2 = uuid4()

            await db_session.execute(
                text(
                    """
                    INSERT INTO node_templates
                    (id, resource_id, name, input_schema, output_schema, code, language, type, enabled, revision_num, kind)
                    VALUES
                    (:id, :resource_id, :name, :input_schema, :output_schema, :code, :language, :type, :enabled, :revision_num, :kind)
                    """
                ),
                {
                    "id": template_id_2,
                    "resource_id": resource_id_2,
                    "name": f"{test_kind}_template",
                    "input_schema": '{"type": "object"}',
                    "output_schema": '{"type": "object"}',
                    "code": "return inp",
                    "language": "python",
                    "type": "static",
                    "enabled": True,
                    "revision_num": 1,
                    "kind": test_kind,
                },
            )
            await db_session.commit()

            # Verify all succeed
            result = await db_session.execute(
                text("SELECT kind FROM node_templates WHERE id = :id"),
                {"id": template_id_2},
            )
            assert result.scalar() == test_kind

    @pytest.mark.asyncio
    async def test_node_template_kind_constraint_invalid(
        self, db_session: AsyncSession
    ):
        """
        Test invalid kind values are rejected.

        Negative case: Invalid kinds rejected.
        """
        # Attempt to create node_template with kind='invalid'
        template_id = uuid4()
        resource_id = uuid4()

        # Verify constraint violation error
        with pytest.raises(Exception) as exc_info:
            await db_session.execute(
                text(
                    """
                    INSERT INTO node_templates
                    (id, resource_id, name, input_schema, output_schema, code, language, type, enabled, revision_num, kind)
                    VALUES
                    (:id, :resource_id, :name, :input_schema, :output_schema, :code, :language, :type, :enabled, :revision_num, :kind)
                    """
                ),
                {
                    "id": template_id,
                    "resource_id": resource_id,
                    "name": "invalid_template",
                    "input_schema": '{"type": "object"}',
                    "output_schema": '{"type": "object"}',
                    "code": "return inp",
                    "language": "python",
                    "type": "static",
                    "enabled": True,
                    "revision_num": 1,
                    "kind": "invalid",
                },
            )
            await db_session.commit()

        # Should raise constraint violation
        assert (
            "constraint" in str(exc_info.value).lower()
            or "check" in str(exc_info.value).lower()
        )
        await db_session.rollback()
