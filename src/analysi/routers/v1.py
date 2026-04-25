from fastapi import APIRouter, Depends

from analysi.auth.dependencies import check_tenant_access
from analysi.routers import (
    activity_audit,
    alerts,
    api_keys,
    artifacts,
    bulk_operations,
    chat,
    content_reviews,
    control_event_channels,
    control_event_rules,
    control_events,
    credentials,
    integration_execution,
    integration_managed,
    integrations,
    kdg,
    kea_coordination,
    knowledge_units,
    members,
    packs,
    schedules,
    skills,
    task_assist,
    task_execution,
    task_feedback,
    task_generations,
    task_generations_internal,
    tasks,
    users,
    workflow_execution,
    workflows,
)

router = APIRouter(dependencies=[Depends(check_tenant_access)])

# Include routers
router.include_router(tasks.router)
router.include_router(task_assist.router)
router.include_router(knowledge_units.router)
router.include_router(skills.router)
router.include_router(content_reviews.router)
router.include_router(kdg.router)
router.include_router(task_execution.router)
router.include_router(workflows.router)
router.include_router(workflow_execution.router)
router.include_router(artifacts.router)
router.include_router(alerts.router)
router.include_router(integrations.router)
router.include_router(integration_managed.router)
router.include_router(integration_execution.router)
router.include_router(credentials.router)
router.include_router(kea_coordination.router)
router.include_router(task_generations_internal.router)
router.include_router(task_feedback.router)
router.include_router(task_generations.router)
router.include_router(activity_audit.router)
router.include_router(control_event_channels.router)
router.include_router(control_event_rules.router)
router.include_router(control_events.router)
router.include_router(members.router)
router.include_router(api_keys.router)
router.include_router(users.router)
router.include_router(chat.router)
router.include_router(bulk_operations.router)
router.include_router(packs.router)
router.include_router(schedules.router)
