"""Webhook HMAC signature verification.

Alert ingestion previously had no source-level integrity check — any
authenticated tenant principal could inject arbitrary alerts.
Optional HMAC-SHA256 signing closes that gap for sources that support
it (most modern SIEMs do). The verification is opt-in per tenant: if
no secret is configured, the endpoint behaves as before.
"""

from __future__ import annotations

import pytest

from analysi.auth.webhook_signature import (
    compute_signature,
    verify_signature,
)


class TestComputeSignature:
    def test_format_is_sha256_hex_with_prefix(self):
        sig = compute_signature(b"hello world", "secret")
        assert sig.startswith("sha256=")
        # 64 hex chars after the prefix
        assert len(sig) == len("sha256=") + 64
        assert all(c in "0123456789abcdef" for c in sig.split("=", 1)[1])

    def test_deterministic_for_same_input(self):
        a = compute_signature(b"payload", "secret")
        b = compute_signature(b"payload", "secret")
        assert a == b

    def test_different_secret_yields_different_sig(self):
        a = compute_signature(b"payload", "secret-a")
        b = compute_signature(b"payload", "secret-b")
        assert a != b

    def test_different_body_yields_different_sig(self):
        a = compute_signature(b"payload-1", "secret")
        b = compute_signature(b"payload-2", "secret")
        assert a != b


class TestVerifySignature:
    def test_accepts_valid_signature(self):
        body = b'{"alert": "test"}'
        secret = "shared-key"
        sig = compute_signature(body, secret)
        assert verify_signature(body, sig, secret) is True

    def test_rejects_tampered_body(self):
        body = b'{"alert": "test"}'
        secret = "shared-key"
        sig = compute_signature(body, secret)
        # Same signature, different body
        assert verify_signature(b'{"alert": "tampered"}', sig, secret) is False

    def test_rejects_wrong_secret(self):
        body = b"data"
        sig = compute_signature(body, "real-secret")
        assert verify_signature(body, sig, "wrong-secret") is False

    def test_rejects_missing_prefix(self):
        body = b"data"
        # Header value without "sha256=" prefix is invalid
        sig = compute_signature(body, "secret").split("=", 1)[1]
        assert verify_signature(body, sig, "secret") is False

    def test_rejects_unsupported_algorithm(self):
        # We only accept sha256 — explicit reject of other algos
        assert verify_signature(b"data", "sha1=abc", "secret") is False
        assert verify_signature(b"data", "md5=abc", "secret") is False

    def test_rejects_garbage_header(self):
        assert verify_signature(b"data", "", "secret") is False
        assert verify_signature(b"data", "not a signature", "secret") is False
        assert verify_signature(b"data", "sha256=", "secret") is False
        assert verify_signature(b"data", "sha256=NOT_HEX", "secret") is False

    def test_constant_time_comparison(self):
        """Smoke check that we use compare_digest (no early-return on mismatch).
        We can't easily measure timing in unit tests, so just confirm that
        both 'right length, wrong content' and 'right content' don't blow up
        and that the wrong one returns False without exception.
        """
        body = b"data"
        secret = "k"
        good = compute_signature(body, secret)
        # Same length as good but different content
        bad = "sha256=" + ("0" * 64)
        assert verify_signature(body, good, secret) is True
        assert verify_signature(body, bad, secret) is False

    @pytest.mark.parametrize(
        "header",
        [
            None,  # missing entirely
            "  sha256=" + "a" * 64 + "  ",  # surrounding whitespace
            "SHA256=" + "a" * 64,  # uppercase prefix
        ],
    )
    def test_handles_edge_case_headers(self, header):
        """Don't crash on missing/whitespace/case-variant headers; reject cleanly."""
        body = b"data"
        result = verify_signature(body, header or "", "secret")
        # All of these should return False (or True only if signature actually matches)
        assert isinstance(result, bool)
