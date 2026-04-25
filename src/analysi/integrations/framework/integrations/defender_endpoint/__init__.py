"""Microsoft Defender for Endpoint integration.

This integration provides endpoint detection and response capabilities through
Microsoft Defender for Endpoint's API.
"""

from analysi.integrations.framework.integrations.defender_endpoint.actions import (
    GetAlertAction,
    GetDeviceDetailsAction,
    HealthCheckAction,
    IsolateDeviceAction,
    ListAlertsAction,
    ListDevicesAction,
    QuarantineFileAction,
    ReleaseDeviceAction,
    RestrictAppExecutionAction,
    RunAdvancedQueryAction,
    ScanDeviceAction,
    UnrestrictAppExecutionAction,
    UpdateAlertAction,
)

__all__ = [
    "GetAlertAction",
    "GetDeviceDetailsAction",
    "HealthCheckAction",
    "IsolateDeviceAction",
    "ListAlertsAction",
    "ListDevicesAction",
    "QuarantineFileAction",
    "ReleaseDeviceAction",
    "RestrictAppExecutionAction",
    "RunAdvancedQueryAction",
    "ScanDeviceAction",
    "UnrestrictAppExecutionAction",
    "UpdateAlertAction",
]
