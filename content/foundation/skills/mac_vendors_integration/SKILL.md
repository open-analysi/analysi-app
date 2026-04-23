---
name: mac-vendors-integration
description: MAC address OUI vendor lookup via Analysi mac_vendors integration for device identification during SOC investigations. Use when triaging alerts involving MAC addresses, identifying device manufacturers, detecting rogue/unauthorized hardware, or enriching network-layer IOCs with vendor context.
version: 0.1.0
---

# MAC Vendors Integration

Resolve MAC addresses to device manufacturers via OUI lookup. Use during network-layer investigations to identify device types, detect virtualization (VMware, Hyper-V), spot IoT/OT hardware, or flag unknown vendors.

## Reference Loading

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any mac_vendors action | Parameters, return schemas, Cy examples, edge cases, format normalization |
| `references/investigation-patterns.md` | Building investigation workflows | Device classification, rogue device detection, MAC randomization handling, Cy task templates, multi-source corroboration |

## Decision Path

- **Single MAC lookup** — call `app::mac_vendors::lookup_mac(mac=addr)`, check `vendor_found` boolean
- **Batch MAC enrichment** — iterate MACs in a for-in loop (auto-parallelized); deduplicate by OUI prefix to conserve rate limit
- **Device classification** — map vendor string to device category (corporate, VM, IoT, networking) via LLM or keyword matching
- **Connectivity check** — call `app::mac_vendors::health_check()` before batch operations

## Guardrails

- **No reverse lookup**: Cannot search by vendor name to find MAC ranges — only MAC-to-vendor direction.
- **OUI only**: Returns the manufacturer registered to the OUI prefix — not device model, firmware, or serial number.
- **Rate limit**: Free tier allows 1,000 requests/day. No rate-limit headers are returned — track usage in your workflow. Exceeding the limit causes errors (handle via try/catch).
- **No historical data**: Returns current OUI registration only — cannot determine if a MAC prefix was reassigned.
- **MAC randomization**: `vendor_found: false` is most commonly caused by randomized MACs (iOS 14+, Android 10+, Windows 10+), not rogue devices. See `investigation-patterns.md` § MAC Address Randomization before escalating.
