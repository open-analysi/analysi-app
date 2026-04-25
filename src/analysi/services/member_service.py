"""Member management service — JIT provisioning, invitations, and RBAC.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.models import CurrentUser
from analysi.auth.rate_limit import invite_rate_limiter
from analysi.config.logging import get_logger
from analysi.models.auth import User
from analysi.repositories.api_key_repository import ApiKeyRepository
from analysi.repositories.invitation_repository import InvitationRepository
from analysi.repositories.membership_repository import MembershipRepository
from analysi.repositories.user_repository import UserRepository
from analysi.schemas.auth import InvitationResponse, MemberResponse

logger = get_logger(__name__)

# Valid tenant-scoped roles that can be invited/assigned.
_VALID_ROLES = {"viewer", "analyst", "admin", "owner"}
# Role hierarchy for invite validation (higher index = more privilege).
_ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2, "owner": 3}

# Default invitation expiry.
_INVITE_EXPIRY_DAYS = 7


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _normalize_email(email: str) -> str:
    """Canonical form for email comparison: strip whitespace, casefold."""
    return email.strip().casefold()


def _role_rank(role: str) -> int:
    return _ROLE_RANK.get(role, -1)


def _build_member_response(membership) -> MemberResponse:
    """Build MemberResponse from a Membership with eagerly loaded User."""
    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        tenant_id=membership.tenant_id,
        role=membership.role,
        email=membership.user.email if membership.user else "",
        created_at=membership.created_at,
    )


class MemberService:
    """Business logic for member and invitation management."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._memberships = MembershipRepository(session)
        self._invitations = InvitationRepository(session)
        self._api_keys = ApiKeyRepository(session)

    # ------------------------------------------------------------------
    # JIT provisioning
    # ------------------------------------------------------------------

    async def provision_user_jit(
        self,
        current_user: CurrentUser,
    ) -> User | None:
        """Auto-create User + Membership on first valid JWT login.

        Only processes real tenant users (not platform_admin, not API key actors).
        Returns the User record, or None if provisioning was skipped.
        """
        if current_user.is_platform_admin:
            return None
        if current_user.actor_type != "user":
            return None
        if not current_user.tenant_id:
            return None
        if not current_user.user_id:
            logger.warning("jit_skip_empty_user_id", email=current_user.email)
            return None

        # Upsert User
        db_user = await self._users.get_by_keycloak_id(current_user.user_id)
        if db_user is None:
            # Backfill: user may exist with empty keycloak_id (pre-sub-mapper)
            # or from a prior seeding. Match by email and update keycloak_id.
            db_user = await self._users.get_by_email(current_user.email)
            if db_user is not None:
                db_user.keycloak_id = current_user.user_id
                await self._session.flush()
                logger.info(
                    "jit_keycloak_id_backfilled",
                    user_id=str(db_user.id),
                    email=current_user.email,
                )
            else:
                # ``create`` is idempotent: concurrent first-login races resolve
                # at the DB layer via ON CONFLICT DO NOTHING and return the
                # winning row. No try/except needed here.
                db_user = await self._users.create(
                    keycloak_id=current_user.user_id,
                    email=current_user.email,
                )
                logger.info(
                    "jit_user_created",
                    user_id=str(db_user.id),
                    email=current_user.email,
                )

        await self._users.update_last_seen(db_user.id, datetime.now(UTC))

        # Upsert Membership
        existing = await self._memberships.get_by_user_and_tenant(
            db_user.id, current_user.tenant_id
        )
        if existing is None:
            members = await self._memberships.list_by_tenant(current_user.tenant_id)
            if len(members) == 0:
                role = "owner"  # First user in tenant gets owner
            else:
                # Use JWT role if it's a valid tenant role, otherwise default to viewer
                jwt_roles = set(current_user.roles) & _VALID_ROLES
                role = (
                    max(jwt_roles, key=lambda r: _ROLE_RANK[r])
                    if jwt_roles
                    else "viewer"
                )
            await self._memberships.create(
                user_id=db_user.id,
                tenant_id=current_user.tenant_id,
                role=role,
            )
            logger.info(
                "jit_membership_created",
                user_id=str(db_user.id),
                tenant_id=current_user.tenant_id,
                role=role,
            )

        return db_user

    # ------------------------------------------------------------------
    # Member listing
    # ------------------------------------------------------------------

    async def list_members(self, tenant_id: str) -> list[MemberResponse]:
        """Return all members of a tenant."""
        memberships = await self._memberships.list_by_tenant_with_user(tenant_id)
        return [_build_member_response(m) for m in memberships]

    # ------------------------------------------------------------------
    # Invitation flow
    # ------------------------------------------------------------------

    async def invite_member(
        self,
        tenant_id: str,
        email: str,
        role: str,
        inviter_user_id: UUID,
    ) -> tuple[InvitationResponse, str]:
        """Create a single-use invitation.

        Returns (InvitationResponse, plaintext_token).
        The plaintext token must be sent via email; only its hash is stored.
        """
        if role not in _VALID_ROLES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid role '{role}'. Must be one of: {', '.join(sorted(_VALID_ROLES))}",
            )

        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires_at = datetime.now(UTC) + timedelta(days=_INVITE_EXPIRY_DAYS)

        invitation = await self._invitations.create(
            tenant_id=tenant_id,
            email=_normalize_email(email),
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
            invited_by=inviter_user_id,
        )

        return InvitationResponse.model_validate(invitation), token

    async def accept_invite(
        self,
        tenant_id: str,
        token: str,
        current_user: CurrentUser,
    ) -> MemberResponse:
        """Accept an invitation token and create a tenant membership.

        Validates:
        - Token exists and belongs to tenant
        - Not expired
        - Not already accepted (single-use)
        - Rate limit (5 attempts/hour per token hash)
        - invited_by user still has role >= invited role (anti-privilege-escalation)
        """
        token_hash = _hash_token(token)

        # Rate limit check (per token hash)
        if not invite_rate_limiter.check_and_record(token_hash):
            raise HTTPException(
                status_code=429,
                detail="Too many attempts for this invitation token. Try again later.",
            )

        invitation = await self._invitations.get_by_token_hash(token_hash)
        if invitation is None or invitation.tenant_id != tenant_id:
            raise HTTPException(status_code=400, detail="Invalid invitation token.")

        # Bind redemption to invited email — prevent token theft
        if _normalize_email(current_user.email) != _normalize_email(invitation.email):
            raise HTTPException(
                status_code=403,
                detail="This invitation was sent to a different email address.",
            )

        now = datetime.now(UTC)
        if invitation.expires_at.replace(tzinfo=UTC) < now:
            raise HTTPException(status_code=400, detail="Invitation has expired.")

        if invitation.accepted_at is not None:
            raise HTTPException(
                status_code=400, detail="Invitation has already been used."
            )

        # Re-validate inviter's role to prevent privilege escalation
        if invitation.invited_by is not None:
            inviter_membership = await self._memberships.get_by_user_and_tenant(
                invitation.invited_by, tenant_id
            )
            if inviter_membership is None or _role_rank(
                inviter_membership.role
            ) < _role_rank(invitation.role):
                raise HTTPException(
                    status_code=403,
                    detail="The inviting user no longer has sufficient privileges.",
                )

        # Upsert User
        db_user = await self._users.get_by_keycloak_id(current_user.user_id)
        if db_user is None:
            db_user = await self._users.create(
                keycloak_id=current_user.user_id,
                email=current_user.email,
            )

        # Create Membership (fail if already a member)
        existing = await self._memberships.get_by_user_and_tenant(db_user.id, tenant_id)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="User is already a member of this tenant.",
            )

        membership = await self._memberships.create(
            user_id=db_user.id,
            tenant_id=tenant_id,
            role=invitation.role,
            invited_by=invitation.invited_by,
        )

        # Mark invitation used
        await self._invitations.mark_accepted(invitation.id, now)

        return MemberResponse(
            id=membership.id,
            user_id=membership.user_id,
            tenant_id=membership.tenant_id,
            role=membership.role,
            email=db_user.email,
            created_at=membership.created_at,
        )

    # ------------------------------------------------------------------
    # Role changes
    # ------------------------------------------------------------------

    async def change_role(
        self,
        tenant_id: str,
        user_id: UUID,
        new_role: str,
    ) -> MemberResponse:
        """Change a member's role.

        Guard: after the change, the tenant must still have at least one owner.
        """
        if new_role not in _VALID_ROLES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid role '{new_role}'. Must be one of: {', '.join(sorted(_VALID_ROLES))}",
            )

        membership = await self._memberships.get_by_user_and_tenant(user_id, tenant_id)
        if membership is None:
            raise HTTPException(status_code=404, detail="Member not found.")

        # Prevent ownerless tenant
        if membership.role == "owner" and new_role != "owner":
            owner_count = await self._memberships.count_owners(tenant_id)
            if owner_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot change role: tenant must have at least one owner.",
                )

        updated = await self._memberships.update_role(membership.id, new_role)
        if updated is None:
            raise HTTPException(status_code=500, detail="Role update failed.")

        # Reload with user to build response
        reloaded = await self._memberships.get_by_id_with_user(membership.id)
        if reloaded is None:
            raise HTTPException(status_code=500, detail="Could not reload membership.")

        return _build_member_response(reloaded)

    # ------------------------------------------------------------------
    # Member removal
    # ------------------------------------------------------------------

    async def remove_member(
        self,
        tenant_id: str,
        user_id: UUID,
    ) -> None:
        """Remove a member and cascade-delete their API keys for this tenant."""
        membership = await self._memberships.get_by_user_and_tenant(user_id, tenant_id)
        if membership is None:
            raise HTTPException(status_code=404, detail="Member not found.")

        # Guard: can't remove the last owner
        if membership.role == "owner":
            owner_count = await self._memberships.count_owners(tenant_id)
            if owner_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot remove the last owner of a tenant.",
                )

        # Cascade: delete all API keys for this user+tenant
        deleted_keys = await self._api_keys.delete_by_user_and_tenant(
            user_id, tenant_id
        )
        if deleted_keys > 0:
            logger.info(
                "api_keys_cascade_deleted",
                user_id=str(user_id),
                tenant_id=tenant_id,
                count=deleted_keys,
            )

        await self._memberships.delete(membership.id)
