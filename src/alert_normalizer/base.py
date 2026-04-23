"""Base normalizer class for alert conversion."""

import json
from abc import ABC, abstractmethod
from typing import Any

from analysi.schemas.alert import AlertCreate


class BaseNormalizer(ABC):
    """Abstract base class for all alert normalizers."""

    @abstractmethod
    def to_alertcreate(self, data: dict[str, Any]) -> AlertCreate:
        """Abstract conversion to AlertCreate format.

        Args:
            data: Source alert data

        Returns:
            AlertCreate Pydantic model
        """
        pass

    @abstractmethod
    def from_alertcreate(self, alert_create: dict[str, Any]) -> dict[str, Any]:
        """Abstract conversion from AlertCreate format.

        Args:
            alert_create: AlertCreate dictionary

        Returns:
            Source format dictionary
        """
        pass

    def preserve_raw(self, data: dict[str, Any]) -> str:
        """Convert to JSON string for raw_alert field.

        Args:
            data: Dictionary to preserve

        Returns:
            JSON string
        """
        return json.dumps(data, default=str)

    def normalize(self, data: dict[str, Any]) -> AlertCreate:
        """Compatibility alias for to_alertcreate.

        Args:
            data: Source alert data

        Returns:
            AlertCreate Pydantic model
        """
        return self.to_alertcreate(data)

    def denormalize(self, alert_create: dict[str, Any]) -> dict[str, Any]:
        """Compatibility alias for from_alertcreate.

        Args:
            alert_create: AlertCreate dictionary

        Returns:
            Source format dictionary
        """
        return self.from_alertcreate(alert_create)
