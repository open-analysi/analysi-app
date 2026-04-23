# QR Code Actions Reference

## Integration Overview

<!-- EVIDENCE: MCP live query — list_integrations(configured_only=true) -->
<!-- EVIDENCE: MCP live query — list_integration_tools(integration_type="qrcode") -->

| Field | Value |
|---|---|
| Integration ID | `qrcode` |
| Integration Type | `qrcode` |
| Cy namespace | `app::qrcode::` |
| Backend | OpenCV (`opencv-python-headless` v4.13.0) |
| Auth required | No |
| Rate limits | None (local processing) |

---

## Action: `decode_qr_code`

Decodes a QR code from a base64-encoded image and returns the embedded data (URL, text, etc.).

<!-- EVIDENCE: MCP live query — get_tool(["app::qrcode::decode_qr_code"]) -->

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `image_data` | string | Yes | Base64-encoded image (PNG, JPEG) containing the QR code |

### Return Value

**On success (QR found):** Returns a result object containing the decoded string data.

**On success (no QR found):** Returns `null`. This is not an error — the image was valid but OpenCV's `QRCodeDetector` did not find a decodable QR code. Always null-check the result before processing. Possible reasons for `null` on an image that does contain a QR code include insufficient quiet zone (white border), extreme rotation, very high data density, or low resolution — see Known Limitations below.

<!-- EVIDENCE: MCP live test — run_integration_tool("qrcode", "decode_qr_code", {image_data: "<valid 1x1 PNG>"}) -->
<!-- EVIDENCE: MCP response -->
```json
// No QR code in image → null output, status "success"
{
  "status": "success",
  "output": null,
  "error": null
}
```

### Error Responses

Errors raise exceptions in Cy — use `try/catch` to handle them.

<!-- EVIDENCE: MCP live test — run_integration_tool("qrcode", "decode_qr_code", {image_data: ""}) -->
**Empty input:**
```json
{
  "status": "error",
  "error": "Missing required parameter: image_data",
  "error_type": "ValidationError"
}
```

<!-- EVIDENCE: MCP live test — run_integration_tool("qrcode", "decode_qr_code", {image_data: "not-valid-base64!!!"}) -->
**Invalid base64:**
```json
{
  "status": "error",
  "error": "Invalid base64-encoded image data",
  "error_type": "ValidationError"
}
```

### Cy Example — Basic Decode

This is the **canonical decode pattern** — all investigation patterns in `investigation-patterns.md` build on this snippet.

```cy
# Extract base64 image from alert (e.g., email attachment, embedded image)
image_b64 = input.attachments[0].content_base64 ?? ""

if (image_b64 == "") {
    return enrich_alert(input, {
        "status": "skipped",
        "reason": "no image attachment found",
        "ai_analysis": "No QR code image available for analysis."
    })
}

# Decode the QR code
decoded = null
decode_error = ""
try {
    decoded = app::qrcode::decode_qr_code(image_data=image_b64)
} catch (e) {
    decode_error = "${e}"
}

if (decode_error != "") {
    return enrich_alert(input, {
        "status": "error",
        "error": decode_error,
        "ai_analysis": "QR decode failed: ${decode_error}"
    })
}

# Handle null (no QR code detected)
if (decoded == null) {
    return enrich_alert(input, {
        "status": "no_qr_found",
        "ai_analysis": "Image did not contain a detectable QR code."
    })
}

# QR code found — return decoded payload
is_url = regex_match(r"^https?://", decoded ?? "")

return enrich_alert(input, {
    "decoded_data": decoded,
    "is_url": is_url,
    "status": "decoded",
    "ai_analysis": "QR code decoded successfully. Payload: ${decoded}"
})
```

This pattern also works as a **standalone lightweight decode-only task** in workflows where downstream tasks handle URL analysis separately.

### Cy Example — Batch Decode (Multiple Attachments)

This is the **canonical batch pattern** for scanning all attachments. Investigation patterns that add URL expansion build on this loop structure.

```cy
attachments = input.attachments ?? []
results = []

for (att in attachments) {
    image_b64 = att.content_base64 ?? ""
    if (image_b64 != "") {
        decoded = null
        try {
            decoded = app::qrcode::decode_qr_code(image_data=image_b64)
        } catch (e) {
            log("QR decode error for attachment: ${e}")
        }
        if (decoded != null) {
            results = results + [{"filename": att.filename ?? "unknown", "decoded": decoded}]
        }
    }
}

return enrich_alert(input, {
    "qr_codes_found": len(results),
    "decoded_payloads": results,
    "ai_analysis": if (len(results) > 0) {
        "Found ${len(results)} QR code(s) in attachments."
    } else {
        "No QR codes detected in any attachments."
    }
})
```

### Image Source Notes

The `image_data` parameter requires base64-encoded image bytes. Common sources in phishing alerts:

- **File attachments:** `input.attachments[N].content_base64` — most straightforward; the NAS normalization layer typically provides base64 content.
- **Inline HTML images:** QR codes are sometimes embedded in email HTML as `<img>` tags with CID references or `data:` URIs. Extracting these requires an upstream task to parse the HTML body and convert inline images to base64 before passing to the QR decode task. This integration does not perform HTML parsing.
- **Screenshot attachments:** User-submitted screenshots containing QR codes work the same as file attachments — just provide the base64 of the screenshot image.

### Known Limitations

- **OpenCV detection boundaries.** The underlying `QRCodeDetector` can fail on QR codes with insufficient quiet zones (white border), extreme rotation angles, very high data density, or low resolution. A `null` result does not guarantee "no QR present" — it may mean "QR present but undecodable." If you suspect a false negative, note it in the enrichment for manual analyst review.
- **Single image per call.** No batch endpoint exists. Use the Batch Decode pattern above to loop over multiple attachments.

---

## Action: `health_check`

Verifies the OpenCV QR decoder is operational. Use before batch-processing workflows to confirm the decoder is available, or as a diagnostic when `decode_qr_code` returns unexpected errors.

<!-- EVIDENCE: MCP live test — run_integration_tool("qrcode", "health_check", {}) -->
<!-- EVIDENCE: MCP response -->

### Parameters

None.

### Return Value

```json
{
  "healthy": true,
  "library": "opencv-python-headless",
  "version": "4.13.0"
}
```

| Field | Type | Description |
|---|---|---|
| `healthy` | boolean | `true` if decoder is operational |
| `library` | string | Python package name (`opencv-python-headless`) |
| `version` | string | OpenCV version (currently `4.13.0`) |

### Cy Example

```cy
status = null
try {
    status = app::qrcode::health_check()
} catch (e) {
    return enrich_alert(input, {
        "status": "error",
        "ai_analysis": "QR code integration unavailable: ${e}"
    })
}

healthy = status.healthy ?? False
if (not healthy) {
    log("QR code decoder is not healthy — skipping QR analysis")
}
```

---

## Example data_samples

Use this template when creating Cy tasks that call the QR code integration. The `content_base64` field should contain a real base64-encoded PNG/JPEG in production; the placeholder below shows the expected structure.

```json
[
  {
    "rule_name": "Phishing Email with QR Code Attachment",
    "title": "Suspicious email with QR code image detected",
    "primary_ioc_value": "",
    "iocs": [],
    "attachments": [
      {
        "filename": "scan_me.png",
        "content_type": "image/png",
        "content_base64": "<base64-encoded-png-image>"
      }
    ],
    "email_info": {
      "sender": "security@n0tify-update.com",
      "subject": "Urgent: Verify your account"
    },
    "enrichments": {}
  },
  {
    "rule_name": "Phishing Email - No Attachments",
    "title": "Suspected phishing but no image attachment",
    "primary_ioc_value": "",
    "iocs": [],
    "attachments": [],
    "email_info": {
      "sender": "hr@company.com",
      "subject": "Benefits enrollment reminder"
    },
    "enrichments": {}
  }
]
```

The first sample exercises the decode path; the second tests the "no image" early-return branch.

---

## Companion Integrations for Quishing Triage

These integrations are available on the same tenant and chain naturally with QR code decoding. See `investigation-patterns.md` for full workflow templates that use them.

| Integration | Action | Cy Call | Use Case |
|---|---|---|---|
| `unshortenme` | `unshorten_url` | `app::unshortenme::unshorten_url(url=decoded_url)` | Expand shortened URLs extracted from QR codes |
| `global_dns` | `resolve_domain` | `app::global_dns::resolve_domain(domain=extracted_domain)` | Resolve decoded domain to IPs |
| `global_dns` | `get_mx_records` | `app::global_dns::get_mx_records(domain=sender_domain)` | Verify sender domain has legitimate mail infrastructure |
| `global_dns` | `get_txt_records` | `app::global_dns::get_txt_records(domain=sender_domain)` | Check SPF/DKIM/DMARC records |
| `whois_rdap` | `whois_ip` | `app::whois_rdap::whois_ip(ip=resolved_ip)` | Get registration data for resolved IP |
| `tor` | `lookup_ip` | `app::tor::lookup_ip(ip=resolved_ip)` | Check if destination IP is a Tor exit node |
