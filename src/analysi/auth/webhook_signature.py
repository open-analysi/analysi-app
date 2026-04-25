"""HMAC-SHA256 signature verification for inbound webhooks.

Many SIEM/SOAR vendors sign webhook payloads with a shared secret so the
receiver can verify the source. We accept the convention used by GitHub,
Slack, Stripe, and most others:

    X-Webhook-Signature: sha256=<hex digest of HMAC-SHA256(body, secret)>

The verification is opt-in per tenant — no secret configured means no
verification (preserves backward compatibility with existing deployments).
"""

from __future__ import annotations

import hashlib
import hmac

_PREFIX = "sha256="


def compute_signature(body: bytes, secret: str) -> str:
    """Compute the canonical signature for a webhook body.

    Returns ``sha256=<hex>`` so the value can be compared directly to the
    ``X-Webhook-Signature`` header sent by the source.
    """
    if not isinstance(body, bytes):
        raise TypeError("body must be bytes")
    digest = hmac.new(
        secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{_PREFIX}{digest}"


def verify_signature(body: bytes, header_value: str, secret: str) -> bool:
    """Constant-time check that ``header_value`` matches the expected HMAC.

    Returns False (never raises) for malformed headers, wrong algorithms,
    missing prefix, or content mismatch — callers should treat any False as
    an authentication failure.
    """
    if not header_value:
        return False

    # Strip incidental whitespace from the header (some proxies add it)
    header_value = header_value.strip()

    # Only sha256 is accepted. Reject sha1, md5, etc. explicitly even
    # though they happen to share the prefix-style format.
    if not header_value.startswith(_PREFIX):
        return False

    received_hex = header_value[len(_PREFIX) :]
    if not received_hex:
        return False

    # Hex-decode early so timing of the compare doesn't depend on body
    try:
        received_bytes = bytes.fromhex(received_hex)
    except ValueError:
        return False

    expected_bytes = hmac.new(
        secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).digest()

    return hmac.compare_digest(expected_bytes, received_bytes)
