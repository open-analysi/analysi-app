"""Unit tests for QR Code integration actions.

All tests use mocked cv2 calls to avoid real image processing.
Tests should run in <0.1s per test.
"""

import base64
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from analysi.integrations.framework.integrations.qrcode.actions import (
    DecodeQrCodeAction,
    HealthCheckAction,
)
from analysi.integrations.framework.integrations.qrcode.constants import (
    ERROR_TYPE_DECODE,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_BASE64,
    MSG_MISSING_IMAGE_DATA,
    MSG_NO_QR_CODE_FOUND,
    MSG_UNABLE_TO_READ_IMAGE,
)


@pytest.fixture
def make_action():
    """Factory fixture returning action instances with empty settings/credentials."""
    return lambda action_class: action_class(
        integration_id="qrcode",
        action_id="test_action",
        settings={},
        credentials={},
    )


# Minimal valid PNG bytes (1x1 white pixel) encoded as base64 — used for mocked tests.
_VALID_PNG_B64 = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
).decode()


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(make_action):
    """Health check returns success when OpenCV detector can be instantiated."""
    action = make_action(HealthCheckAction)

    mock_detector = MagicMock()
    mock_detector.detectAndDecode.return_value = ("", None, None)

    with patch(
        "analysi.integrations.framework.integrations.qrcode.actions.cv2.QRCodeDetector",
        return_value=mock_detector,
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert result["data"]["healthy"] is True
    assert "opencv" in result["data"]["library"].lower()
    assert "version" in result["data"]


@pytest.mark.asyncio
async def test_health_check_failure(make_action):
    """Health check returns error when OpenCV raises an exception."""
    action = make_action(HealthCheckAction)

    with patch(
        "analysi.integrations.framework.integrations.qrcode.actions.cv2.QRCodeDetector",
        side_effect=RuntimeError("cv2 not available"),
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert result["data"]["healthy"] is False
    assert "cv2 not available" in result["error"]


# ============================================================================
# DecodeQrCodeAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_decode_qr_code_success(make_action):
    """Decode action returns extracted data when QR code is found."""
    action = make_action(DecodeQrCodeAction)

    mock_detector = MagicMock()
    # vertices_array is not None when a QR code is detected
    mock_vertices = np.array(
        [[[10, 10], [20, 10], [20, 20], [10, 20]]], dtype=np.float32
    )
    mock_detector.detectAndDecode.return_value = (
        "https://example.com",
        mock_vertices,
        None,
    )

    mock_image = np.zeros((100, 100, 3), dtype=np.uint8)

    with (
        patch(
            "analysi.integrations.framework.integrations.qrcode.actions.cv2.imdecode",
            return_value=mock_image,
        ),
        patch(
            "analysi.integrations.framework.integrations.qrcode.actions.cv2.QRCodeDetector",
            return_value=mock_detector,
        ),
    ):
        result = await action.execute(image_data=_VALID_PNG_B64)

    assert result["status"] == "success"
    assert result["found"] is True
    assert result["data"] == "https://example.com"


@pytest.mark.asyncio
async def test_decode_qr_code_no_qr_found(make_action):
    """Decode action returns success with found=False when no QR code is detected."""
    action = make_action(DecodeQrCodeAction)

    mock_detector = MagicMock()
    # vertices_array is None when no QR code is present
    mock_detector.detectAndDecode.return_value = ("", None, None)

    mock_image = np.zeros((100, 100, 3), dtype=np.uint8)

    with (
        patch(
            "analysi.integrations.framework.integrations.qrcode.actions.cv2.imdecode",
            return_value=mock_image,
        ),
        patch(
            "analysi.integrations.framework.integrations.qrcode.actions.cv2.QRCodeDetector",
            return_value=mock_detector,
        ),
    ):
        result = await action.execute(image_data=_VALID_PNG_B64)

    assert result["status"] == "success"
    assert result["found"] is False
    assert result["data"] is None
    assert MSG_NO_QR_CODE_FOUND in result["message"]


@pytest.mark.asyncio
async def test_decode_qr_code_missing_image_data(make_action):
    """Decode action returns ValidationError when image_data is not provided."""
    action = make_action(DecodeQrCodeAction)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert MSG_MISSING_IMAGE_DATA in result["error"]


@pytest.mark.asyncio
async def test_decode_qr_code_invalid_base64(make_action):
    """Decode action returns ValidationError for input that fails base64 decoding.

    Python's base64.b64decode raises binascii.Error for truly invalid characters
    such as a lone '%' or other non-alphabet bytes when validate=True is used.
    We patch base64.b64decode directly to simulate this failure.
    """
    import binascii

    action = make_action(DecodeQrCodeAction)

    with patch(
        "analysi.integrations.framework.integrations.qrcode.actions.base64.b64decode",
        side_effect=binascii.Error("Invalid base64-encoded string"),
    ):
        result = await action.execute(image_data="not-real-base64")

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert MSG_INVALID_BASE64 in result["error"]


@pytest.mark.asyncio
async def test_decode_qr_code_unreadable_image(make_action):
    """Decode action returns DecodeError when cv2 cannot decode the image bytes."""
    action = make_action(DecodeQrCodeAction)

    # Valid base64 but not a valid image format
    not_an_image = base64.b64encode(b"not an image").decode()

    with patch(
        "analysi.integrations.framework.integrations.qrcode.actions.cv2.imdecode",
        return_value=None,  # cv2.imdecode returns None for unreadable data
    ):
        result = await action.execute(image_data=not_an_image)

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_DECODE
    assert MSG_UNABLE_TO_READ_IMAGE in result["error"]


@pytest.mark.asyncio
async def test_decode_qr_code_opencv_exception(make_action):
    """Decode action returns error when cv2 raises an unexpected exception."""
    action = make_action(DecodeQrCodeAction)

    mock_image = np.zeros((100, 100, 3), dtype=np.uint8)

    with (
        patch(
            "analysi.integrations.framework.integrations.qrcode.actions.cv2.imdecode",
            return_value=mock_image,
        ),
        patch(
            "analysi.integrations.framework.integrations.qrcode.actions.cv2.QRCodeDetector",
            side_effect=Exception("cv2 internal error"),
        ),
    ):
        result = await action.execute(image_data=_VALID_PNG_B64)

    assert result["status"] == "error"
    assert "cv2 internal error" in result["error"]
