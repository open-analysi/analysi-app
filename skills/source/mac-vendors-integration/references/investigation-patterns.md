# MAC Vendors — Investigation Patterns

## Contents

- [MAC Address Randomization](#mac-address-randomization) — Why `vendor_found: false` usually means randomization, not a rogue device
- [Pattern 1: Device Classification](#pattern-1-device-classification-by-vendor) — Vendor → device category via LLM
- [Pattern 2: Rogue Device Detection](#pattern-2-rogue-device-detection-mac--splunk-corroboration) — MAC vendor + Splunk DHCP/asset corroboration
- [Pattern 3: Multi-MAC Enrichment](#pattern-3-multi-mac-enrichment-for-network-alerts) — Enrich all MACs in a network alert
- [Pattern 4: VM Detection](#pattern-4-vm-detection-for-lateral-movement-triage) — Keyword-based VM identification
- [Common Vendor Strings](#common-vendor-strings-reference) — Known OUI → vendor mappings
- [Corroboration with Other Integrations](#corroboration-with-other-integrations) — Pairing MAC lookup with Splunk, WHOIS, Tor, DNS
- [Rate Limit Management](#rate-limit-management) — OUI dedup pattern for batch operations

## Base Pattern Note

All patterns below build on the canonical single-lookup pattern from `actions-reference.md` § Single MAC Lookup (Canonical Pattern). That pattern defines the standard guard → try/catch → extract structure. Each pattern here is a self-contained Cy script but adds unique logic on top (LLM classification, Splunk corroboration, etc.).

---

## When MAC Vendor Lookup Matters

MAC vendor identification is useful during:

1. **Rogue device detection** — An unknown vendor on a corporate network segment may indicate an unauthorized device (but check for MAC randomization first — see below).
2. **Lateral movement investigation** — Identifying whether a source MAC belongs to a VM (VMware, Hyper-V), a workstation (Dell, Lenovo), or IoT (Raspberry Pi, Espressif) helps determine attack surface.
3. **Network anomaly triage** — A MAC from an unexpected vendor category (e.g., IoT device on a server VLAN) can corroborate or refute an alert.
4. **Asset inventory enrichment** — Adding vendor context to network-layer alerts helps analysts understand what kind of device generated the traffic.

---

## MAC Address Randomization

**This is the most common reason you will see `vendor_found: false` in modern networks.**

Since 2020, most consumer operating systems randomize MAC addresses by default:
- **iOS 14+** (2020): Private Wi-Fi addresses enabled per-network
- **Android 10+** (2019): Randomized MACs per-SSID by default
- **Windows 10/11** (2015/2021): Random hardware addresses, opt-in then default

Randomized MACs use the **locally administered** bit (the second hex character is 2, 6, A, or E — e.g., `x2:xx:xx:...`, `xA:xx:xx:...`). The MAC Vendors API correctly returns `vendor_found: false` for these because they are not registered OUIs.

**Triage implication**: A `vendor_found: false` result on a Wi-Fi segment with BYOD users is *expected behavior*, not an indicator of compromise. Before escalating:

1. Check if the second hex digit of the MAC is 2, 6, A, or E — if so, it's almost certainly a randomized address from a consumer device.
2. Cross-reference with DHCP logs or 802.1X authentication records to identify the actual device.
3. Only escalate unresolved MACs on **wired segments** or **server VLANs** where randomization is not expected.

```cy
# Quick check: is this MAC locally administered (likely randomized)?
mac_addr = input.network_info.src_mac ?? ""
is_randomized = False
if (len(mac_addr) >= 2) {
    # Extract second hex character (works for colon, dash, and raw formats)
    second_char = lowercase(mac_addr)
    # For colon/dash format, second char is at index 1
    # For raw hex, second char is also at index 1
    # Check if second nibble has the locally-administered bit set
    la_chars = ["2", "3", "6", "7", "a", "b", "e", "f"]
    check_char = ""
    if (len(mac_addr) > 1) {
        check_char = regex_extract(r"^.(.)", second_char) ?? ""
    }
    for (c in la_chars) {
        if (check_char == c) {
            is_randomized = True
        }
    }
}
```

---

## Pattern 1: Device Classification by Vendor

Map the raw vendor string to a device category for triage decisions. This pattern extends the base lookup with LLM reasoning to classify vendors that don't match simple keyword rules.

```cy
mac_addr = input.network_info.src_mac ?? ""
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ?? "unknown alert"

if (mac_addr == "") {
    return enrich_alert(input, {
        "status": "skipped",
        "reason": "no MAC address in alert",
        "ai_analysis": "No source MAC available — cannot perform device classification."
    })
}

# Resolve vendor (base pattern — see actions-reference.md § Single MAC Lookup)
try {
    result = app::mac_vendors::lookup_mac(mac=mac_addr)
} catch (e) {
    return enrich_alert(input, {
        "status": "error",
        "error": "${e}",
        "ai_analysis": "MAC vendor lookup failed: ${e}. Cannot classify device."
    })
}

vendor = result.vendor ?? "unknown"
found = result.vendor_found ?? False

# LLM-based classification with alert context
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

MAC address ${mac_addr} resolved to vendor: ${vendor}
Vendor found: ${found}

Classify this device into one category:
- "corporate_endpoint" (Dell, HP, Lenovo, Apple laptops/desktops)
- "virtual_machine" (VMware, Microsoft Hyper-V, QEMU, Xen)
- "network_infrastructure" (Cisco, Juniper, Aruba, Fortinet)
- "iot_ot" (Raspberry Pi, Espressif, Honeywell, Siemens)
- "mobile" (Samsung, Apple mobile, OnePlus, Xiaomi)
- "randomized_mac" (vendor not found AND second hex digit is 2/6/A/E — likely iOS/Android/Windows randomized address)
- "unknown" (vendor not found, not randomized pattern)

Then assess: Is this device type expected given the alert context?

Return JSON (no markdown): {"category": "...", "expected": true/false, "reasoning": "one sentence"}"""
)

enrichment = {
    "mac": mac_addr,
    "vendor": vendor,
    "vendor_found": found,
    "device_classification": analysis,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

### Decision Tree After Classification

```
vendor_found == false AND second hex digit is 2/6/A/E
  → Likely randomized MAC (iOS/Android/Windows)
  → Expected on Wi-Fi/BYOD segments — do not escalate
  → Cross-reference with 802.1X or DHCP if device identity needed

vendor_found == false AND NOT randomized pattern
  → Genuinely unregistered OUI — possibly spoofed
  → Escalate if on wired/server segments

category == "virtual_machine"
  → Expected on server VLANs; suspicious on user endpoints
  → Cross-reference with EDR to confirm VM presence on host

category == "iot_ot"
  → Unexpected on corporate VLANs — potential rogue device
  → Check if device is in asset inventory via Splunk

category == "unknown"
  → Vendor string unrecognizable — escalate for manual review
```

---

## Pattern 2: Rogue Device Detection (MAC + Splunk Corroboration)

Combine MAC vendor lookup with Splunk DHCP/ARP logs to determine if a device is authorized. This pattern extends the base lookup with a Splunk search and LLM synthesis.

```cy
mac_addr = input.network_info.src_mac ?? ""
src_ip = input.network_info.src_ip ?? input.primary_ioc_value ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ?? "unknown alert"

if (mac_addr == "") {
    return enrich_alert(input, {
        "status": "skipped",
        "ai_analysis": "No MAC address — cannot perform rogue device check."
    })
}

# Vendor lookup (base pattern — see actions-reference.md § Single MAC Lookup)
vendor_info = {}
try {
    vr = app::mac_vendors::lookup_mac(mac=mac_addr)
    vendor_info = {
        "vendor": vr.vendor ?? "unknown",
        "vendor_found": vr.vendor_found ?? False
    }
} catch (e) {
    vendor_info = {"vendor": "lookup_failed", "vendor_found": False, "error": "${e}"}
}

# Search Splunk for DHCP lease or asset inventory entry
splunk_context = {}
try {
    spl_query = """search index=dhcp OR index=assets mac="${mac_addr}" OR mac_address="${mac_addr}"
| head 10
| table _time, mac, mac_address, ip, hostname, asset_group, owner"""
    splunk_result = app::splunk::search(query=spl_query)
    splunk_context = {"events": splunk_result, "found": True}
} catch (e) {
    splunk_context = {"events": [], "found": False, "error": "${e}"}
}

# LLM synthesis
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Device investigation for MAC ${mac_addr} (IP: ${src_ip}):

Vendor lookup: ${to_json(vendor_info)}
Splunk asset/DHCP records: ${to_json(splunk_context)}

Determine:
1. Is this a known/authorized device?
2. Is the vendor expected for this network context?
3. Could this be a randomized MAC from a mobile device (check if second hex digit is 2/6/A/E)?
4. Should this be escalated as a potential rogue device?

Return JSON (no markdown): {"authorized": true/false, "risk": "high/medium/low", "reasoning": "one sentence"}"""
)

enrichment = {
    "mac": mac_addr,
    "vendor": vendor_info.vendor ?? "unknown",
    "vendor_found": vendor_info.vendor_found ?? False,
    "splunk_asset_found": splunk_context.found ?? False,
    "rogue_assessment": analysis,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 3: Multi-MAC Enrichment for Network Alerts

Some network alerts (e.g., ARP spoofing, VLAN hopping) contain multiple MAC addresses. Enrich all of them in a single pass. This pattern extends the base lookup with multi-address collection and LLM landscape summary.

```cy
# Gather all MACs from different alert fields
src_mac = input.network_info.src_mac ?? ""
dst_mac = input.network_info.dst_mac ?? ""
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ?? "unknown alert"

mac_list = []
if (src_mac != "") {
    mac_list = mac_list + [{"label": "source", "mac": src_mac}]
}
if (dst_mac != "") {
    mac_list = mac_list + [{"label": "destination", "mac": dst_mac}]
}

if (len(mac_list) == 0) {
    return enrich_alert(input, {
        "status": "skipped",
        "ai_analysis": "No MAC addresses found in alert for vendor enrichment."
    })
}

# Lookup all MACs (for-in auto-parallelizes)
lookups = []
for (entry in mac_list) {
    try {
        result = app::mac_vendors::lookup_mac(mac=entry.mac)
        lookups = lookups + [{
            "label": entry.label,
            "mac": entry.mac,
            "vendor": result.vendor ?? "unknown",
            "vendor_found": result.vendor_found ?? False
        }]
    } catch (e) {
        lookups = lookups + [{
            "label": entry.label,
            "mac": entry.mac,
            "vendor": "lookup_failed",
            "vendor_found": False,
            "error": "${e}"
        }]
    }
}

# LLM summary
lookup_summary = to_json(lookups)
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

MAC vendor lookups for this alert:
${lookup_summary}

Summarize the device landscape: what types of devices are involved?
Flag anything unusual (e.g., VM talking to IoT, unknown vendor on corporate VLAN).
Note if any unresolved MACs appear to be randomized (second hex digit 2/6/A/E).

Return JSON (no markdown): {"summary": "one paragraph", "anomalies": ["list of concerns or empty"]}"""
)

enrichment = {
    "mac_lookups": lookups,
    "device_landscape": analysis,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 4: VM Detection for Lateral Movement Triage

During lateral movement alerts, knowing whether the source is a VM helps assess the attack surface. Virtual machines with VMware or Hyper-V OUIs on unexpected segments are a strong signal. This pattern extends the base lookup with keyword-based VM classification — no LLM needed.

```cy
mac_addr = input.network_info.src_mac ?? ""
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ?? "unknown alert"

if (mac_addr == "") {
    return enrich_alert(input, {
        "status": "skipped",
        "ai_analysis": "No source MAC — cannot determine if source is a virtual machine."
    })
}

# Resolve vendor (base pattern — see actions-reference.md § Single MAC Lookup)
try {
    result = app::mac_vendors::lookup_mac(mac=mac_addr)
} catch (e) {
    return enrich_alert(input, {
        "status": "error",
        "ai_analysis": "MAC vendor lookup failed: ${e}"
    })
}

vendor = result.vendor ?? "unknown"
vendor_lower = lowercase(vendor)

# Quick keyword check for common VM vendors
is_vm = False
vm_vendors = ["vmware", "microsoft", "xen", "qemu", "parallels", "virtualbox", "hyper-v"]
for (vm_keyword in vm_vendors) {
    if (regex_match(vm_keyword, vendor_lower)) {
        is_vm = True
    }
}

enrichment = {
    "mac": mac_addr,
    "vendor": vendor,
    "is_virtual_machine": is_vm,
    "ai_analysis": if (is_vm) {
        "Source MAC ${mac_addr} belongs to ${vendor} — virtual machine detected. Assess whether VMs are expected on this network segment."
    } else {
        "Source MAC ${mac_addr} belongs to ${vendor} — not a recognized VM vendor."
    }
}

return enrich_alert(input, enrichment)
```

---

## Common Vendor Strings Reference

These are exact strings returned by the MAC Vendors API, useful for keyword matching:

<!-- EVIDENCE: MCP live test — all values confirmed via run_integration_tool -->

| OUI Prefix | Vendor String | Category |
|---|---|---|
| `00:0C:29`, `00:50:56` | `"VMware, Inc."` | Virtual Machine |
| `d0:a6:37` | `"Apple, Inc."` | Corporate Endpoint / Mobile |
| `00:00:00` | `"XEROX CORPORATION"` | Historical (all-zeros OUI) |

Additional well-known OUI mappings (not live-tested but widely documented):

| Vendor Pattern | Category | Investigation Significance |
|---|---|---|
| VMware, Microsoft Corp | Virtual Machine | Check if VMs are expected on segment |
| Cisco Systems, Juniper Networks, Aruba | Network Infrastructure | Typically benign unless spoofed |
| Dell, HP, Lenovo | Corporate Endpoints | Standard workstations |
| Espressif, Raspberry Pi | IoT / Embedded | Unexpected on corporate VLANs |
| Intel Corporate | Can be endpoint or server NIC | Needs additional context |

---

## Corroboration with Other Integrations

MAC vendor lookup provides device-level context. Combine with other integrations for full situational awareness:

| Integration | Corroboration Value |
|---|---|
| **Splunk** | Search DHCP logs for MAC-to-IP binding, asset inventory for authorization status |
| **WHOIS RDAP** | If the IP associated with the MAC belongs to an unexpected ASN, combined with an unexpected vendor, strengthens rogue device hypothesis |
| **Tor** | If the IP is a Tor exit node AND the MAC is a VM vendor, strongly suggests an anonymization setup |
| **Global DNS** | Reverse-resolve the IP to see if the hostname matches the expected device type from MAC vendor |

---

## Rate Limit Management

For workflows processing many MACs (e.g., network scan enrichment):

1. **Check volume before batch**: If the alert contains >100 MACs, consider sampling or deduplicating by OUI prefix (first 6 hex chars) since all MACs from the same OUI return the same vendor.
2. **Deduplicate by OUI**: Extract the first 3 octets, deduplicate, then look up only unique prefixes. Map results back to full MACs.
3. **Health check first**: Call `health_check()` before batch operations to confirm API availability.
4. **Graceful degradation**: If lookups start failing mid-batch (possible rate limit), log the error and continue with partial results rather than failing the entire task.

### OUI Dedup Pattern

```cy
# Deduplicate MACs by OUI prefix before batch lookup
# All MACs sharing the same first 3 octets return the same vendor
mac_list = input.network_info.mac_addresses ?? []

# Extract OUI prefix (first 8 chars of colon-separated, e.g., "d0:a6:37")
oui_map = {}
for (mac_addr in mac_list) {
    normalized = lowercase(replace(mac_addr, "-", ":"))
    prefix = regex_extract(r"^([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})", normalized) ?? ""
    if (prefix != "") {
        # Store one representative MAC per OUI prefix
        oui_map[prefix] = mac_addr
    }
}

# Lookup only unique OUI prefixes
oui_results = {}
for (prefix in oui_map) {
    representative_mac = oui_map[prefix]
    try {
        result = app::mac_vendors::lookup_mac(mac=representative_mac)
        oui_results[prefix] = result.vendor ?? "unknown"
    } catch (e) {
        log("OUI lookup failed for ${prefix}: ${e}")
        oui_results[prefix] = "lookup_failed"
    }
}

# Map results back to all original MACs
enriched_macs = []
for (mac_addr in mac_list) {
    normalized = lowercase(replace(mac_addr, "-", ":"))
    prefix = regex_extract(r"^([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})", normalized) ?? ""
    vendor = oui_results[prefix] ?? "unknown"
    enriched_macs = enriched_macs + [{"mac": mac_addr, "vendor": vendor}]
}

enrichment = {
    "unique_ouis": len(oui_results),
    "total_macs": len(mac_list),
    "lookups_saved": len(mac_list) - len(oui_results),
    "results": enriched_macs,
    "ai_analysis": "Resolved ${len(oui_results)} unique OUI prefixes for ${len(mac_list)} MAC addresses (saved ${len(mac_list) - len(oui_results)} API calls)."
}

return enrich_alert(input, enrichment)
```
