"""Base OCSF normalizer.

OCSF normalizers produce OCSF Detection Finding v1.8.0 dicts as canonical
output.  Concrete implementations call source-specific extraction functions
and map their output directly to OCSF structure — direct OCSF output.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseOCSFNormalizer(ABC):
    """Abstract base class for OCSF-producing normalizers.

    Subclasses must implement ``to_ocsf`` which returns an OCSF Detection
    Finding dict.
    """

    @abstractmethod
    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert source-format alert to OCSF Detection Finding dict.

        Args:
            data: Raw alert data from the source system.

        Returns:
            OCSF Detection Finding v1.8.0 dict.
        """
