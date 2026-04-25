---
name: qrcode-integration
description: Decode QR codes from images during quishing and phishing investigations using the Analysi QR Code integration. Use when triaging phishing alerts with QR codes, extracting URLs from embedded images, or building quishing investigation workflows.
version: 0.1.0
---

# QR Code Integration for Quishing Investigations

Decode QR codes from base64-encoded images to extract embedded URLs, text, and other payloads during phishing/quishing alert triage. The integration uses OpenCV locally — no external API calls, no rate limits, no authentication.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any QR code action | Parameters, return schemas, Cy examples, error handling, known limitations, data_samples template |
| `references/investigation-patterns.md` | Building quishing triage workflows | Decision trees, multi-integration chaining (DNS, unshorten, WHOIS, Tor), Cy task templates |

## Quick Decision Path

1. **Got a base64 image from an alert?** → Call `decode_qr_code` (see actions-reference.md § Basic Decode)
2. **Decoded a URL?** → Chain with `unshortenme`, `global_dns`, `whois_rdap`, `tor` (see investigation-patterns.md)
3. **Decoded non-URL text?** → Pass to LLM for contextual analysis
4. **Null result?** → No QR detected, or image quality too low for OpenCV — log and continue triage without blocking

## Guardrails

- `decode_qr_code` returns `null` (not an error) when no QR code is detected — always null-check before processing
- Input must be base64-encoded PNG or JPEG — the caller must extract and encode images from email attachments or inline HTML before calling
- Invalid base64 or empty input raises a `ValidationError` exception (caught by `try/catch`)
- QR code generation, batch decoding, and direct URL/file-path input are not supported
