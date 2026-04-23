from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore extra environment variables
    )

    ENVIRONMENT: str = Field(default="development")
    PORT: int = Field(default=8000)
    LOG_LEVEL: str = Field(default="INFO")

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://dev:devpassword@localhost:5432/analysi_db"
    )

    DATABASE_POOL_SIZE: int = Field(default=10)
    DATABASE_MAX_OVERFLOW: int = Field(default=20)
    DATABASE_ECHO: bool = Field(default=False)
    DATABASE_SSL: bool = Field(default=False)  # True for RDS; False for in-cluster PG

    # Use NoDecode annotation to prevent automatic JSON parsing
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )

    # MinIO / Object Storage Configuration
    MINIO_ENDPOINT: str = Field(default="localhost:9000")
    MINIO_ACCESS_KEY: str = Field(default="")
    MINIO_SECRET_KEY: str = Field(default="")
    ARTIFACTS_BUCKET: str = Field(default="analysi-storage")

    # Auth — Keycloak / OIDC (Project Mikonos)
    # Set ANALYSI_AUTH_JWKS_URI to enable JWT validation.
    # When unset, auth is skipped (dev mode without Keycloak).
    ANALYSI_AUTH_JWKS_URI: str | None = Field(default=None)
    ANALYSI_AUTH_ISSUER: str = Field(default="http://localhost:8080/realms/analysi")
    ANALYSI_AUTH_AUDIENCE: str = Field(default="analysi-app")
    ANALYSI_AUTH_MODE: str = Field(default="dev")  # "dev" | "production"

    # System API key for worker-to-API authentication (Project Mikonos)
    # Workers (alert-worker, integrations-worker) use this key to call the REST API.
    # Set to a strong random value in production; leave unset in dev (auth is skipped).
    ANALYSI_SYSTEM_API_KEY: str | None = Field(default=None)

    # Owner API key for tooling that needs full tenant control (e.g., demo-loader clean-all).
    # Linked to the sentinel system user with "owner" role + platform_admin access.
    ANALYSI_OWNER_API_KEY: str | None = Field(default=None)
    # Dev admin API key — "admin" role (no owner bypass). For testing non-owner flows.
    ANALYSI_ADMIN_API_KEY: str | None = Field(default=None)

    # Feature Flags
    ENABLE_WORKFLOW_TYPE_VALIDATION: bool = Field(default=False)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        if isinstance(v, list):
            return v
        return v


settings = Settings()
