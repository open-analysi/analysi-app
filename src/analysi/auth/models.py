"""Auth domain models — CurrentUser dataclass."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class CurrentUser:
    """Resolved identity for every authenticated request.

    Populated from a validated JWT or API key lookup.
    Available via ``get_current_user`` FastAPI dependency.
    """

    user_id: str
    email: str
    tenant_id: str | None  # None for platform_admin
    roles: list[str] = field(default_factory=list)
    actor_type: str = "user"  # "user" | "api_key" | "system"
    db_user_id: UUID | None = None  # FK-ready UUID from users table

    @property
    def is_platform_admin(self) -> bool:
        """True when the user carries the platform_admin realm role."""
        return "platform_admin" in self.roles
