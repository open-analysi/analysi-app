"""
Integration-test fixtures shared by every test under ``tests/integration``.

In-process ARQ worker
---------------------
Integration tests that drive the real FastAPI app via ``ASGITransport(app=app)``
can enqueue ARQ jobs (``execute_task_run``, ``execute_workflow_run``, …). A
consumer must run before tests can observe a terminal job status. In local dev
the compose ``alerts-worker`` container connects to the production Valkey DB
(``ALERT_PROCESSING_DB``), whereas the test process routes its enqueues to
``TEST_ALERT_PROCESSING_DB`` (DB 100) via ``WorkerSettings.get_redis_settings()``
when ``PYTEST_CURRENT_TEST`` is set. Without a consumer on DB 100 those jobs
sit in the queue forever and tests time out waiting for ``'completed'``.

Before Project Leros (commit 4adaf520d, March 2026) task execution was inline
via ``asyncio.create_task``; Leros replaced that with ``enqueue_or_fail`` but
never added a test-side consumer. This fixture closes that gap.

Opt-in to avoid collateral damage
---------------------------------
Running a background ARQ worker during every integration test caused event-loop
lifecycle interference with tests that manage their own ``AsyncClient`` and
don't need the queue drained (they patched ``queue_alert_analysis`` at the
unit-level). Mark tests that depend on the worker with
``@pytest.mark.arq_worker`` (at test, class, or module level) to opt in.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
import pytest_asyncio

logger = logging.getLogger(__name__)


def pytest_configure(config):
    """Register the ``arq_worker`` marker used by ``_in_process_arq_worker``."""
    config.addinivalue_line(
        "markers",
        "arq_worker: start an in-process ARQ worker for this test so enqueued "
        "jobs (task_run, workflow_run, …) actually execute",
    )


@pytest_asyncio.fixture(autouse=True, loop_scope="function")
async def _in_process_arq_worker(request):
    """Run an ARQ worker in-process only for tests marked ``arq_worker``.

    The worker uses the same ``WorkerSettings`` as production but, because
    ``PYTEST_CURRENT_TEST`` is set during pytest, routes to Valkey DB 100.
    """
    if request.node.get_closest_marker("arq_worker") is None:
        yield None
        return

    from arq.worker import Worker

    from analysi.alert_analysis.worker import WorkerSettings

    worker = Worker(
        functions=WorkerSettings.functions,
        cron_jobs=None,  # no crons in tests — they create surprise rows
        redis_settings=WorkerSettings.get_redis_settings(),
        max_jobs=WorkerSettings.max_jobs,
        job_timeout=WorkerSettings.job_timeout,
        max_tries=1,
        poll_delay=0.1,
        handle_signals=False,
        burst=False,
    )

    task = asyncio.create_task(worker.async_run(), name="test-arq-worker")

    try:
        yield worker
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        try:
            await worker.aclose()
        except Exception:  # noqa: BLE001
            pass
