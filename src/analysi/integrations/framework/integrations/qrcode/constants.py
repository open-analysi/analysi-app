"""
QR Code integration constants.
"""

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_DECODE = "DecodeError"

# Error messages
MSG_MISSING_IMAGE_DATA = "Missing required parameter: image_data"
MSG_INVALID_BASE64 = "Invalid base64-encoded image data"
MSG_NO_QR_CODE_FOUND = "No QR code found in image"
MSG_UNABLE_TO_READ_IMAGE = "Unable to read or decode image data"
