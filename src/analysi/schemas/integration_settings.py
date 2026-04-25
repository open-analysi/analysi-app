"""
Settings validation for integrations.

NOTE: All integrations now use the Naxos framework with manifest-based validation.
This module is kept for backward compatibility but returns None for all integrations.
"""

from pydantic import BaseModel


def get_settings_model(integration_type: str):
    """Get the appropriate settings model for an integration type.

    Returns None - all integrations now use Naxos framework manifest-based validation.
    """
    return


def validate_integration_settings(
    integration_type: str, settings: dict
) -> BaseModel | None:
    """Validate and parse settings for a specific integration type.

    Returns None - all integrations now use Naxos framework manifest-based validation.
    """
    return None
