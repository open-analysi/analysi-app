#!/usr/bin/env python
"""
Script to inspect workflow execution details including input/output for each node.
Shows the data flow through a workflow execution for debugging.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import desc, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload  # noqa: E402

from analysi.config.settings import settings  # noqa: E402
from analysi.models.workflow import Workflow  # noqa: E402
from analysi.models.workflow_execution import (  # noqa: E402
    WorkflowNodeInstance,
    WorkflowRun,
)
from analysi.services.storage import StorageManager  # noqa: E402

# Adjust DATABASE_URL for local execution (replace Docker hostname with localhost)
database_url = settings.DATABASE_URL
if "postgres" in database_url and not os.getenv("RUNNING_IN_DOCKER"):
    # Replace Docker internal hostname with localhost and port 5434
    database_url = database_url.replace("postgres:5432", "localhost:5434")
    print("📌 Using local database connection via port 5434")

# Create async engine with settings from .env
engine = create_async_engine(
    database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_latest_workflow_run(
    session: AsyncSession, limit: int = 1
) -> list[WorkflowRun]:
    """Get the most recent workflow runs."""
    stmt = select(WorkflowRun).order_by(desc(WorkflowRun.created_at)).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_workflow_details(session: AsyncSession, workflow_id: UUID) -> Workflow:
    """Get workflow details with nodes."""
    stmt = (
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .options(selectinload(Workflow.nodes))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_node_instances(
    session: AsyncSession, workflow_run_id: UUID
) -> list[WorkflowNodeInstance]:
    """Get all node instances for a workflow run."""
    stmt = (
        select(WorkflowNodeInstance)
        .where(WorkflowNodeInstance.workflow_run_id == workflow_run_id)
        .order_by(WorkflowNodeInstance.created_at)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def retrieve_data(
    storage_manager: StorageManager, storage_type: str, location: str
) -> any:
    """Retrieve data from storage."""
    if not storage_type or not location:
        return None

    try:
        content = await storage_manager.retrieve(
            storage_type=storage_type,
            location=location,
            content_type="application/json",
        )

        # Try to parse as JSON if it's a string
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content
        return content
    except Exception as e:
        return f"Error retrieving data: {e!s}"


def format_json(data: any, indent: int = 2) -> str:
    """Format JSON data for display."""
    if data is None:
        return "None"
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, indent=indent, default=str)
    except (TypeError, ValueError):
        return str(data)


async def inspect_workflow_execution(workflow_run_id: UUID = None):
    """Inspect a workflow execution showing input/output for each node."""
    async with AsyncSessionLocal() as session:
        storage_manager = StorageManager()

        # Get the workflow run
        if workflow_run_id:
            stmt = select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
            result = await session.execute(stmt)
            workflow_run = result.scalar_one_or_none()
            if not workflow_run:
                print(f"❌ Workflow run {workflow_run_id} not found")
                return
        else:
            # Get the latest workflow run
            runs = await get_latest_workflow_run(session, limit=1)
            if not runs:
                print("❌ No workflow runs found")
                return
            workflow_run = runs[0]

        print("=" * 80)
        print("🔍 WORKFLOW EXECUTION INSPECTION")
        print("=" * 80)
        print(f"Run ID:      {workflow_run.id}")
        print(f"Status:      {workflow_run.status}")
        print(f"Created:     {workflow_run.created_at}")
        print(f"Started:     {workflow_run.started_at}")
        print(f"Ended:       {workflow_run.completed_at}")

        # Get workflow details
        workflow = await get_workflow_details(session, workflow_run.workflow_id)
        if workflow:
            print(f"Workflow:    {workflow.name}")
            print(f"Description: {workflow.description}")

        print("\n" + "=" * 80)
        print("WORKFLOW INPUT")
        print("=" * 80)

        # Retrieve workflow input
        workflow_input = await retrieve_data(
            storage_manager, workflow_run.input_type, workflow_run.input_location
        )
        print(format_json(workflow_input))

        # Get all node instances
        node_instances = await get_node_instances(session, workflow_run.id)

        print("\n" + "=" * 80)
        print(f"NODE EXECUTIONS ({len(node_instances)} nodes)")
        print("=" * 80)

        # Create a map of node_id to node details
        node_map = {}
        if workflow:
            for node in workflow.nodes:
                node_map[node.node_id] = node

        for i, node_instance in enumerate(node_instances, 1):
            print(f"\n{'─' * 40}")
            print(f"Node {i}: {node_instance.node_id}")
            print(f"{'─' * 40}")

            # Get node details
            node_details = node_map.get(node_instance.node_id)
            if node_details:
                print(f"Name:        {node_details.name}")
                print(f"Type:        {node_details.kind}")
                if node_details.task_id:
                    print(f"Task ID:     {node_details.task_id}")

            print(f"Status:      {node_instance.status}")
            print(f"Started:     {node_instance.started_at}")
            print(f"Ended:       {node_instance.completed_at}")

            if node_instance.task_run_id:
                print(f"Task Run:    {node_instance.task_run_id}")

            if node_instance.error_message:
                print(f"❌ Error:    {node_instance.error_message}")

            # Retrieve and display input
            print("\n📥 INPUT:")
            if node_instance.input_type and node_instance.input_location:
                input_data = await retrieve_data(
                    storage_manager,
                    node_instance.input_type,
                    node_instance.input_location,
                )
                print(format_json(input_data))
            else:
                print("  (No input stored)")

            # Retrieve and display output
            print("\n📤 OUTPUT:")
            if node_instance.output_type and node_instance.output_location:
                output_data = await retrieve_data(
                    storage_manager,
                    node_instance.output_type,
                    node_instance.output_location,
                )
                print(format_json(output_data))
            else:
                print("  (No output stored)")

        print("\n" + "=" * 80)
        print("WORKFLOW OUTPUT")
        print("=" * 80)

        # Retrieve workflow output
        if workflow_run.output_type and workflow_run.output_location:
            workflow_output = await retrieve_data(
                storage_manager, workflow_run.output_type, workflow_run.output_location
            )
            print(format_json(workflow_output))
        else:
            print("(No output stored)")

        print("\n" + "=" * 80)
        print("✅ Inspection complete")
        print("=" * 80)


async def list_recent_workflows(limit: int = 10):
    """List recent workflow executions."""
    async with AsyncSessionLocal() as session:
        runs = await get_latest_workflow_run(session, limit=limit)

        print("=" * 80)
        print(f"📋 RECENT WORKFLOW EXECUTIONS (Last {limit})")
        print("=" * 80)

        for run in runs:
            # Get workflow name
            workflow = await get_workflow_details(session, run.workflow_id)
            workflow_name = workflow.name if workflow else "Unknown"

            print(f"\nRun ID:   {run.id}")
            print(f"Workflow: {workflow_name}")
            print(f"Status:   {run.status}")
            print(f"Created:  {run.created_at}")
            print("-" * 40)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Inspect workflow execution details")
    parser.add_argument(
        "--run-id",
        type=str,
        help="Specific workflow run ID to inspect (defaults to latest)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List recent workflow executions"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent workflows to list (default: 10)",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show database configuration being used",
    )

    args = parser.parse_args()

    if args.show_config:
        print("=" * 80)
        print("📋 DATABASE CONFIGURATION")
        print("=" * 80)
        print(f"Original URL: {settings.DATABASE_URL}")
        print(f"Active URL:   {database_url}")
        print(f"Environment:  {settings.ENVIRONMENT}")
        print("=" * 80)
        return

    if args.list:
        await list_recent_workflows(args.limit)
    else:
        run_id = UUID(args.run_id) if args.run_id else None
        await inspect_workflow_execution(run_id)


if __name__ == "__main__":
    asyncio.run(main())
