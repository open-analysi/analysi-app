"""API key validation and dev bootstrapping.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)

Validation: look up API keys by SHA-256 hash, resolve roles from membership.
Bootstrapping: idempotent provisioning of dev API keys on startup.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.models import CurrentUser
from analysi.config.logging import get_logger
from analysi.models.auth import ApiKey, Membership, User

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------


async def validate_api_key(
    key: str,
    db: AsyncSession,
) -> CurrentUser | None:
    """Look up an API key by its SHA-256 hash.

    Returns a CurrentUser if the key is valid and not expired, or None if the
    key is unknown or expired.  Also stamps last_used_at on success.
    """
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await db.execute(stmt)
    api_key_row: ApiKey | None = result.scalar_one_or_none()

    if api_key_row is None:
        return None

    # Check expiry
    now = datetime.now(UTC)
    if api_key_row.expires_at is not None:
        expires = api_key_row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < now:
            logger.debug("api_key_expired", key_prefix=api_key_row.key_prefix)
            return None

    # Stamp last_used_at (best-effort — don't fail auth on update error)
    try:
        from analysi.repositories.api_key_repository import ApiKeyRepository

        repo = ApiKeyRepository(db)
        await repo.update_last_used(api_key_row.id, now)
    except Exception:
        logger.warning("api_key_last_used_update_failed", key_id=str(api_key_row.id))

    tenant_id = api_key_row.tenant_id

    if api_key_row.user_id is not None:
        # User-owned key: resolve identity and tenant role
        user_result = await db.execute(
            select(User).where(User.id == api_key_row.user_id)
        )
        db_user: User | None = user_result.scalar_one_or_none()

        if db_user is None:
            # Linked user was deleted — key is no longer valid
            return None

        membership_result = await db.execute(
            select(Membership).where(
                Membership.user_id == db_user.id,
                Membership.tenant_id == tenant_id,
            )
        )
        membership: Membership | None = membership_result.scalar_one_or_none()
        roles = [membership.role] if membership else []
        if membership and membership.role == "owner":
            roles.append("platform_admin")

        return CurrentUser(
            user_id=str(db_user.keycloak_id),
            email=db_user.email,
            tenant_id=tenant_id,
            roles=roles,
            actor_type="api_key",
            db_user_id=db_user.id,
        )
    # System key (user_id is NULL) — explicit permissions via "system" role.
    # Does NOT include platform_admin — workers use _SYSTEM_PERMS RBAC,
    # not blanket bypass. Add permissions to _SYSTEM_PERMS if workers
    # need new operations.
    return CurrentUser(
        user_id=f"system:{api_key_row.key_prefix}",
        email="system@analysi.internal",
        tenant_id=tenant_id,
        roles=["system"],
        actor_type="system",
    )


# ---------------------------------------------------------------------------
# Dev bootstrapping — idempotent API key provisioning
# ---------------------------------------------------------------------------


VALID_DEV_ROLES = frozenset({"viewer", "analyst", "admin", "owner"})


@dataclass(frozen=True)
class DevApiKeySpec:
    """Specification for a dev API key to provision on startup.

    Attributes:
        raw_key: Plaintext key value (from env var).
        role: Membership role — must be one of VALID_DEV_ROLES.
        email: Email for the associated user.
        key_name: Display name for the API key row.
        user_id: Explicit user ID. Uses SYSTEM_USER_ID for owner,
                 deterministic uuid5 for others.
    """

    raw_key: str
    role: str
    email: str
    key_name: str
    user_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.role not in VALID_DEV_ROLES:
            raise ValueError(
                f"Invalid role '{self.role}'. Must be one of: "
                f"{', '.join(sorted(VALID_DEV_ROLES))}"
            )


async def provision_dev_api_keys(
    specs: list[DevApiKeySpec],
    tenant_id: str,
    db: AsyncSession,
) -> None:
    """Provision multiple dev API keys in a single session.

    Each key is idempotent: skipped if its hash already exists.
    Creates user + membership as needed.
    """
    for spec in specs:
        await _provision_one(spec, tenant_id, db)


async def _provision_one(
    spec: DevApiKeySpec,
    tenant_id: str,
    db: AsyncSession,
) -> None:
    """Provision a single API key with its user and membership."""
    key_hash = hashlib.sha256(spec.raw_key.encode()).hexdigest()

    # Idempotent: skip if key already provisioned
    existing = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    if existing.scalar_one_or_none() is not None:
        logger.debug("dev_api_key_already_exists", role=spec.role)
        return

    # Resolve user ID
    user_id = spec.user_id or uuid.uuid5(uuid.NAMESPACE_URL, spec.email)

    # Ensure user exists
    user_result = await db.execute(select(User).where(User.id == user_id))
    if user_result.scalar_one_or_none() is None:
        db.add(
            User(
                id=user_id,
                keycloak_id=str(user_id),
                email=spec.email,
            )
        )
        logger.info("dev_user_created", email=spec.email, role=spec.role)

    # Ensure membership
    membership_result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
        )
    )
    if membership_result.scalar_one_or_none() is None:
        db.add(
            Membership(
                user_id=user_id,
                tenant_id=tenant_id,
                role=spec.role,
            )
        )
        logger.info("dev_membership_created", role=spec.role, tenant_id=tenant_id)

    # Create API key
    key_prefix = spec.raw_key[:8] if len(spec.raw_key) >= 8 else spec.raw_key
    db.add(
        ApiKey(
            tenant_id=tenant_id,
            user_id=user_id,
            name=spec.key_name,
            key_hash=key_hash,
            key_prefix=key_prefix,
        )
    )
    logger.info("dev_api_key_provisioned", role=spec.role, tenant_id=tenant_id)


async def provision_system_api_key(
    raw_key: str,
    tenant_id: str,
    db: AsyncSession,
) -> None:
    """Ensure a system API key (user_id=NULL) exists.

    System keys are NOT tied to any user and get the "system" role
    with explicit permissions via _SYSTEM_PERMS. Used by workers.
    Runs in all environments (not dev-only).
    """
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    existing = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    if existing.scalar_one_or_none() is not None:
        logger.debug("system_api_key_already_exists")
        return

    key_prefix = raw_key[:8] if len(raw_key) >= 8 else raw_key
    api_key = ApiKey(
        tenant_id=tenant_id,
        user_id=None,
        name="System API Key",
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    db.add(api_key)
    logger.info("system_api_key_provisioned", tenant_id=tenant_id)
