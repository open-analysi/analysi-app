"""
Integration tests for ``UserRepository`` idempotency.

Regression for the first-login race:
    INSERT INTO users ... /* duplicate key value violates unique constraint
    "users_email_key". Key (email)=(dev@analysi.local) already exists. */

Background: on UI cold-start, several parallel API calls hit
``provision_user_jit`` before any of them commit. Each finds no existing user
and issues an INSERT; the losers raise ``IntegrityError``, which the caller
catches and recovers from — but every loss is logged as an ERROR by Postgres.
The fix is to make ``UserRepository.create`` race-safe via
``ON CONFLICT DO NOTHING`` so concurrent callers no-op instead of erroring.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.user_repository import UserRepository

pytestmark = [pytest.mark.integration]


@pytest.mark.asyncio
async def test_create_is_idempotent_on_email_conflict(
    integration_test_session: AsyncSession,
):
    """Calling ``create`` twice with the same email must not raise.

    Both calls must return the SAME user row. This is the repository-level
    invariant that eliminates the Postgres duplicate-key ERROR log when
    concurrent first-login requests race through ``provision_user_jit``.
    """
    repo = UserRepository(integration_test_session)

    first = await repo.create(
        keycloak_id="race-test-keycloak-id-1",
        email="race-test@example.com",
        display_name="Race Tester",
    )
    # A second create with the same email (and same keycloak_id) must not
    # raise IntegrityError. Same id returned → conflict was handled silently.
    second = await repo.create(
        keycloak_id="race-test-keycloak-id-1",
        email="race-test@example.com",
        display_name="Race Tester",
    )

    assert first.id == second.id
    assert first.email == second.email
    assert first.keycloak_id == second.keycloak_id


@pytest.mark.asyncio
async def test_create_returns_existing_on_email_reuse_with_different_keycloak_id(
    integration_test_session: AsyncSession,
):
    """If a second caller races in with the same email but a different
    keycloak_id, ``create`` must still not raise — the first writer wins and
    the second gets back whatever row the DB holds (real JIT flow can then
    backfill or reconcile).
    """
    repo = UserRepository(integration_test_session)

    first = await repo.create(
        keycloak_id="race-test-keycloak-id-A",
        email="race-test-b@example.com",
    )
    second = await repo.create(
        keycloak_id="race-test-keycloak-id-B",
        email="race-test-b@example.com",
    )

    # Same row — the winner survives, loser gets the existing.
    assert first.id == second.id
    assert first.keycloak_id == "race-test-keycloak-id-A"
