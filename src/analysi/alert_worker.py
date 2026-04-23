#!/usr/bin/env python
"""Alert Analysis Worker Service Entry Point"""

import asyncio

from arq import create_pool
from arq.worker import Worker

from analysi.alert_analysis.worker import WorkerSettings, process_alert_analysis
from analysi.config.logging import configure_logging, get_logger

# Unified logging (Project Syros AD-5)
configure_logging()
logger = get_logger(__name__)


async def main():
    """Main entry point for alert analysis worker"""
    logger.info("alert_worker_starting")

    try:
        # Create Redis/Valkey connection pool
        redis = await create_pool(WorkerSettings.redis_settings)
        logger.info(
            "valkey_pool_created", redis_settings=str(WorkerSettings.redis_settings)
        )

        # Create worker with registered functions
        worker = Worker(
            redis_pool=redis,
            functions=[
                process_alert_analysis,  # Main job function
            ],
            max_jobs=WorkerSettings.max_jobs,
            job_timeout=WorkerSettings.job_timeout,
            poll_delay=WorkerSettings.poll_delay,
        )

        # Run worker
        logger.info("alert_worker_started")
        await worker.main()

    except Exception as e:
        logger.error("alert_worker_start_failed", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())
