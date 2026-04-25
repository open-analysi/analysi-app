#!/usr/bin/env python3
"""
Manual test to demonstrate ad hoc table search using KU functions.

Run this to test table reading through a task.
"""

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.repositories.task import TaskRepository
from analysi.services.task_execution import DefaultTaskExecutor


async def run_adhoc_table_search():
    """Demonstrate ad hoc search by reading a table through a task."""

    # Database connection
    DATABASE_URL = (
        "postgresql+asyncpg://analysi_user:yourpassword@localhost:5434/analysi"
    )
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        tenant_id = "demo-tenant"

        # Step 1: Create a table with searchable data
        print("Creating sample table with data...")
        ku_repo = KnowledgeUnitRepository(session)

        table_data = [
            {
                "id": 1,
                "entity": "192.168.1.100",
                "type": "ip",
                "severity": "high",
                "description": "Suspicious outbound traffic",
            },
            {
                "id": 2,
                "entity": "malware.exe",
                "type": "file",
                "severity": "critical",
                "description": "Known malware detected",
            },
            {
                "id": 3,
                "entity": "192.168.1.101",
                "type": "ip",
                "severity": "medium",
                "description": "Port scanning activity",
            },
            {
                "id": 4,
                "entity": "user@example.com",
                "type": "email",
                "severity": "low",
                "description": "Phishing attempt",
            },
            {
                "id": 5,
                "entity": "192.168.1.100",
                "type": "ip",
                "severity": "medium",
                "description": "Multiple login failures",
            },
        ]

        await ku_repo.create_table_ku(
            tenant_id,
            {
                "name": "Security Events",
                "description": "Table of security events for analysis",
                "content": {"rows": table_data},
                "row_count": len(table_data),
                "column_count": 5,
            },
        )
        await session.commit()
        print(f"✅ Created table 'Security Events' with {len(table_data)} rows")

        # Step 2: Create an ad hoc search task
        print("\nCreating ad hoc search task...")
        task_repo = TaskRepository(session)

        # This Cy script performs an ad hoc search
        cy_script = """
# Ad hoc search: Read security events and filter
events = table_read("Security Events")

# Search for specific criteria
search_ip = "192.168.1.100"
high_severity_events = []
ip_events = []

i = 0
while (i < len(events)) {
    event = events[i]

    # Find high/critical severity events
    if (event["severity"] == "high" || event["severity"] == "critical") {
        high_severity_events = high_severity_events + [event]
    }

    # Find events for specific IP
    if (event["entity"] == search_ip) {
        ip_events = ip_events + [event]
    }

    i = i + 1
}

# Return search results
return {
    "total_events": len(events),
    "high_severity_count": len(high_severity_events),
    "high_severity_events": high_severity_events,
    "events_for_ip": ip_events,
    "ip_searched": search_ip
}
"""

        task = await task_repo.create(
            {
                "tenant_id": tenant_id,
                "name": "Ad Hoc Security Search",
                "description": "Search security events table for high severity and specific IP",
                "cy_code": cy_script,
            }
        )
        await session.commit()
        print(f"✅ Created ad hoc search task: {task.component.name}")

        # Step 3: Execute the search task
        print("\nExecuting ad hoc search...")
        executor = DefaultTaskExecutor()

        execution_context = {
            "tenant_id": tenant_id,
            "task_id": str(task.component_id),
            "task_run_id": str(uuid4()),
            "session": session,  # Important: Pass the session for KU access
        }

        result = await executor.execute(
            cy_script=task.cy_code,
            input_data={},
            execution_context=execution_context,
        )

        # Step 4: Display results
        if result["status"] == "completed":
            output = result["output"]
            if isinstance(output, str):
                import ast

                output = ast.literal_eval(output)

            print("\n" + "=" * 50)
            print("AD HOC SEARCH RESULTS:")
            print("=" * 50)
            print(f"Total events in table: {output['total_events']}")
            print(f"High/Critical severity events: {output['high_severity_count']}")
            print("\nHigh severity events found:")
            for event in output["high_severity_events"]:
                print(
                    f"  - [{event['severity'].upper()}] {event['entity']}: {event['description']}"
                )

            print(f"\nEvents for IP {output['ip_searched']}:")
            for event in output["events_for_ip"]:
                print(f"  - [{event['severity']}] {event['description']}")
            print("=" * 50)

            # Step 5: Demonstrate updating the table with search results
            print("\nCreating results summary table...")
            summary_data = [
                {
                    "search_type": "high_severity",
                    "count": output["high_severity_count"],
                },
                {
                    "search_type": f"ip_{output['ip_searched']}",
                    "count": len(output["events_for_ip"]),
                },
            ]

            await ku_repo.create_table_ku(
                tenant_id,
                {
                    "name": "Search Results Summary",
                    "description": "Summary of ad hoc search results",
                    "content": {"rows": summary_data},
                    "row_count": len(summary_data),
                    "column_count": 2,
                },
            )
            await session.commit()
            print("✅ Created summary table with search results")

        else:
            print(f"❌ Search failed: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    print("Ad Hoc Table Search Demo")
    print("-" * 30)
    asyncio.run(run_adhoc_table_search())
    print("\n✅ Ad hoc search demonstration complete!")
