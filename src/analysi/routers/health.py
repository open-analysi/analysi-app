"""Health and readiness probe endpoints."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from analysi.api import ApiResponse, api_response
from analysi.auth.dependencies import require_platform_admin
from analysi.config.logging import get_logger
from analysi.db.session import get_db

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


class ProbeStatus(BaseModel):
    status: str


class DatabaseHealth(BaseModel):
    status: str
    database: str
    error: str | None = None


@router.get("/healthz", response_model=ApiResponse[ProbeStatus])
async def healthz(request: Request) -> ApiResponse[ProbeStatus]:
    """K8s liveness probe — always returns 200 if the process is alive."""
    return api_response(ProbeStatus(status="ok"), request=request)


@router.get("/readyz", response_model=ApiResponse[ProbeStatus])
async def readyz(
    request: Request, db: AsyncSession = Depends(get_db)
) -> ApiResponse[ProbeStatus] | JSONResponse:
    """K8s readiness probe — returns 200 when DB is reachable."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return api_response(ProbeStatus(status="ok"), request=request)
    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable"},
        )


# Separate router for DB health — requires platform admin
admin_health_router = APIRouter(
    tags=["admin"],
    dependencies=[Depends(require_platform_admin)],
)


@admin_health_router.get("/health/db", response_model=ApiResponse[DatabaseHealth])
async def database_health(
    request: Request, db: AsyncSession = Depends(get_db)
) -> ApiResponse[DatabaseHealth] | JSONResponse:
    """Database health check — requires platform admin."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return api_response(
            DatabaseHealth(status="healthy", database="connected"),
            request=request,
        )
    except Exception as e:
        logger.error("health_check_db_failure", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "data": {
                    "status": "unhealthy",
                    "database": "disconnected",
                    "error": "Database connection failed",
                },
            },
        )
