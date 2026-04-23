"""Duo Security integration for Naxos framework.

Provides MFA and authentication-related actions using Duo's Auth API.
"""

from analysi.integrations.framework.integrations.duo.actions import (
    AuthorizeAction,
    HealthCheckAction,
)

__all__ = [
    "AuthorizeAction",
    "HealthCheckAction",
]
