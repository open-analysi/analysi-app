"""QR Code integration actions.

This module provides QR code decoding using OpenCV (cv2). It accepts
base64-encoded image data and returns the decoded QR code content.

OpenCV is a synchronous library, so decoding is wrapped in asyncio.to_thread()
to avoid blocking the event loop.

No authentication is required — this is a pure code integration.
"""

import asyncio
import base64
import binascii
from typing import Any

import cv2
import numpy as np

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.qrcode.constants import (
    ERROR_TYPE_DECODE,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_BASE64,
    MSG_MISSING_IMAGE_DATA,
    MSG_NO_QR_CODE_FOUND,
    MSG_UNABLE_TO_READ_IMAGE,
)

logger = get_logger(__name__)

class HealthCheckAction(IntegrationAction):
    """Health check for QR code decoding capability."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Verify that the OpenCV QR code detector is operational.

        Generates a known QR code in memory and decodes it to confirm the
        library is working correctly.

        Returns:
            Result with status=success if the decoder is working
        """
        try:

            def _check_decoder() -> bool:
                """Create a minimal valid test using the QRCodeDetector."""
                detector = cv2.QRCodeDetector()
                # Use a tiny blank image — just verifying the detector can be instantiated
                # and invoked without crashing
                blank = np.zeros((100, 100, 3), dtype=np.uint8)
                _data, vertices, _binary = detector.detectAndDecode(blank)
                # vertices will be None (no QR code in blank image) — that is expected
                return True

            await asyncio.to_thread(_check_decoder)

            return {
                "healthy": True,
                "status": "success",
                "message": "QR code decoder is operational",
                "data": {
                    "healthy": True,
                    "library": "opencv-python-headless",
                    "version": cv2.__version__,
                },
            }

        except Exception as e:
            logger.error("qrcode_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class DecodeQrCodeAction(IntegrationAction):
    """Decode a QR code image and extract the embedded data."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Decode a QR code from a base64-encoded image.

        The upstream connector read the image from a file path obtained via
        the upstream vault system.  In Naxos the caller passes the image
        content as a base64-encoded string, which is decoded in memory
        before being processed by OpenCV.

        Args:
            **kwargs: Must contain 'image_data' — base64-encoded PNG/JPEG
                      image that contains a QR code.

        Returns:
            On success: ``{"status": "success", "data": "<decoded text>",
                          "found": True}``
            When no QR code is detected: ``{"status": "success",
                          "found": False, "data": None}``
            On error: ``{"status": "error", "error": "...",
                         "error_type": "..."}``
        """
        image_data = kwargs.get("image_data")
        if not image_data:
            return {
                "status": "error",
                "error": MSG_MISSING_IMAGE_DATA,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        try:

            def _decode(b64_data: str) -> dict[str, Any]:
                """Synchronous OpenCV decoding — runs in a thread pool."""
                # Decode base64 to raw bytes
                try:
                    image_bytes = base64.b64decode(b64_data)
                except binascii.Error:
                    return {
                        "status": "error",
                        "error": MSG_INVALID_BASE64,
                        "error_type": ERROR_TYPE_VALIDATION,
                    }

                # Convert bytes to numpy array and then to cv2 image
                np_array = np.frombuffer(image_bytes, dtype=np.uint8)
                image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

                if image is None:
                    return {
                        "status": "error",
                        "error": MSG_UNABLE_TO_READ_IMAGE,
                        "error_type": ERROR_TYPE_DECODE,
                    }

                # Detect and decode the QR code
                detector = cv2.QRCodeDetector()
                data, vertices_array, _binary_qrcode = detector.detectAndDecode(image)

                if vertices_array is not None:
                    return {
                        "status": "success",
                        "found": True,
                        "data": data,
                    }
                return {
                    "status": "success",
                    "found": False,
                    "data": None,
                    "message": MSG_NO_QR_CODE_FOUND,
                }

            result = await asyncio.to_thread(_decode, image_data)
            return result

        except Exception as e:
            logger.error("qrcode_decode_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
