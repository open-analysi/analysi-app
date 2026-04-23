# WHOIS RDAP Investigation Patterns

Practical triage patterns that use WHOIS RDAP for IP attribution during SOC investigations. All examples include error handling and are ready to use in Cy tasks.

All patterns use the **Standard IP Extraction and Call Pattern** defined in `actions-reference.md` § Standard IP Extraction. For edge-case behavior (private IPs returning `null`, invalid input errors), see `actions-reference.md` § Edge Cases.

## Table of Contents

- [Decision Tree: IP Attribution Triage](#decision-tree-ip-attribution-triage)
- [Pattern 1: WHOIS + Tor Exit Node Correlation](#pattern-1-whois--tor-exit-node-correlation)
- [Pattern 2: WHOIS + DNS Reverse Lookup Correlation](#pattern-2-whois--dns-reverse-lookup-correlation)
- [Pattern 3: Multi-IP Batch Enrichment](#pattern-3-multi-ip-batch-enrichment)
- [Pattern 4: WHOIS with LLM-Powered Attribution Analysis](#pattern-4-whois-with-llm-powered-attribution-analysis)
- [Pattern 5: ASN Clustering for Brute Force Detection](#pattern-5-asn-clustering-for-brute-force-detection)
- [Field Interpretation Guide](#field-interpretation-guide)

---

## Decision Tree: IP Attribution Triage

When an alert contains a source or destination IP, use this decision flow:

```
1. Is the IP private/reserved?
   YES → Skip WHOIS, investigate as internal lateral movement
   NO  → Continue to step 2

2. Call app::whois_rdap::whois_ip(ip=ip)
   NULL result? → Likely reserved/special-use IP, log and skip
   ERROR?       → Log error, continue investigation without WHOIS data

3. Check asn_description — does it match a known hosting/cloud/Tor provider?
   "TORSERVERS"  → High suspicion, correlate with Tor exit node check
   "AMAZON", "GOOGLE", "MICROSOFT" → Likely cloud infra, check if expected
   "OVH", "HETZNER", "DIGITALOCEAN" → Hosting provider, moderate concern
   ISP name (e.g., "COMCAST", "DTAG") → Residential, could be compromised host

4. Check network.remarks for explicit signals (see § network.remarks Signals below)

5. Check asn_country_code — does the country align with expected traffic?
   Unexpected country for this user/service → Elevated risk
   Expected country → Lower risk signal

6. Check asn_date — was the ASN recently allocated?
   Very recent (< 6 months) → Could indicate freshly provisioned attack infra
   Established (> 1 year) → Normal, lower risk signal
```

## Pattern 1: WHOIS + Tor Exit Node Correlation

Combine WHOIS RDAP with the Tor integration for definitive Tor attribution. WHOIS alone shows hosting context; the Tor check confirms active exit node status.

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

if (ip == "0.0.0.0") {
    return enrich_alert(input, {"ip_attribution": "no_ip_available"})
}

# Parallel lookups: WHOIS and Tor
whois_data = null
tor_data = null
whois_error = ""
tor_error = ""

try {
    whois_data = app::whois_rdap::whois_ip(ip=ip)
} catch (e) {
    whois_error = "${e}"
    log("WHOIS failed for ${ip}: ${e}")
}

try {
    tor_data = app::tor::check_ip(ip=ip)
} catch (e) {
    tor_error = "${e}"
    log("Tor check failed for ${ip}: ${e}")
}

# Determine Tor status from both sources
is_tor_whois = False
if (whois_data != null) {
    network_name = whois_data.network.name ?? ""
    if (network_name == "TOR-EXIT") {
        is_tor_whois = True
    }
}

is_tor_confirmed = tor_data.is_tor_exit ?? False

# Build enrichment
enrichment = {
    "ip": ip,
    "is_tor_exit": is_tor_confirmed,
    "tor_signal_in_whois": is_tor_whois,
    "asn": if (whois_data != null) { whois_data.asn ?? "unknown" } else { "lookup_failed" },
    "asn_description": if (whois_data != null) { whois_data.asn_description ?? "unknown" } else { "lookup_failed" },
    "asn_country": if (whois_data != null) { whois_data.asn_country_code ?? "unknown" } else { "unknown" },
    "whois_error": whois_error,
    "tor_error": tor_error
}

return enrich_alert(input, enrichment)
```

## Pattern 2: WHOIS + DNS Reverse Lookup Correlation

Combine WHOIS ownership data with DNS reverse lookup to get both the registered owner and the hostname/PTR record. Useful for determining if an IP belongs to a legitimate service.

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"

if (ip == "0.0.0.0") {
    return enrich_alert(input, {"ip_context": "no_ip_available"})
}

# WHOIS lookup
whois_data = null
try {
    whois_data = app::whois_rdap::whois_ip(ip=ip)
} catch (e) {
    log("WHOIS failed: ${e}")
}

# DNS reverse lookup
dns_data = null
try {
    dns_data = app::global_dns::reverse_lookup(ip=ip)
} catch (e) {
    log("DNS reverse lookup failed: ${e}")
}

# Combine findings
enrichment = {
    "ip": ip,
    "asn_org": if (whois_data != null) { whois_data.asn_description ?? "unknown" } else { "whois_failed" },
    "asn": if (whois_data != null) { whois_data.asn ?? "unknown" } else { "unknown" },
    "netblock": if (whois_data != null) { whois_data.network.cidr ?? "unknown" } else { "unknown" },
    "country": if (whois_data != null) { whois_data.asn_country_code ?? "unknown" } else { "unknown" },
    "reverse_dns": if (dns_data != null) { dns_data.hostname ?? "no_ptr" } else { "dns_failed" }
}

return enrich_alert(input, enrichment)
```

## Pattern 3: Multi-IP Batch Enrichment

When an alert contains multiple IPs (e.g., brute force sources), loop through them individually. Keep batches reasonable to avoid upstream RDAP throttling.

**Note on parallelism:** Cy's for-in loops can auto-parallelize when loop iterations are independent (no cross-iteration dependencies). In this pattern, each WHOIS lookup is independent, so the runtime may execute them concurrently. However, because RDAP is a free public service with upstream rate limits, high concurrency on large IP lists could trigger throttling. For lists exceeding ~20 IPs, consider whether the upstream RIR can handle the burst.

```cy
# Extract IPs from alert IOCs
iocs = input.iocs ?? []
target_ips = []
for (ioc in iocs) {
    if (ioc.type == "ipv4" or ioc.type == "ipv6") {
        target_ips = target_ips + [ioc.value ?? ""]
    }
}

# Also include network_info IPs if not already present
src_ip = input.network_info.src_ip ?? ""
dst_ip = input.network_info.dst_ip ?? ""
if (src_ip != "") {
    target_ips = target_ips + [src_ip]
}
if (dst_ip != "") {
    target_ips = target_ips + [dst_ip]
}

# Lookup each IP
results = []
for (ip in target_ips) {
    if (ip == "" or ip == "0.0.0.0") {
        results = results + [{"ip": ip, "status": "skipped"}]
    } else {
        try {
            rdap = app::whois_rdap::whois_ip(ip=ip)
            if (rdap == null) {
                results = results + [{"ip": ip, "status": "private_or_reserved"}]
            } else {
                results = results + [{
                    "ip": ip,
                    "status": "resolved",
                    "asn": rdap.asn ?? "unknown",
                    "org": rdap.asn_description ?? "unknown",
                    "cidr": rdap.asn_cidr ?? "unknown",
                    "country": rdap.asn_country_code ?? "unknown",
                    "network_name": rdap.network.name ?? "unknown"
                }]
            }
        } catch (e) {
            results = results + [{"ip": ip, "status": "error", "error": "${e}"}]
        }
    }
}

enrichment = {
    "ip_count": len(target_ips),
    "whois_results": results
}

return enrich_alert(input, enrichment)
```

## Pattern 4: WHOIS with LLM-Powered Attribution Analysis

Use LLM reasoning to interpret WHOIS data in the context of a specific alert. The LLM can assess whether the IP's ownership and hosting context are consistent with the alert type.

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

if (ip == "0.0.0.0") {
    return enrich_alert(input, {"whois_analysis": "no_ip_available"})
}

try {
    rdap = app::whois_rdap::whois_ip(ip=ip)
} catch (e) {
    return enrich_alert(input, {"whois_analysis": "lookup_failed", "error": "${e}"})
}

if (rdap == null) {
    return enrich_alert(input, {"whois_analysis": "private_or_reserved_ip", "ip": ip})
}

# Extract network remarks for context
network_remarks = ""
remarks_list = rdap.network.remarks ?? []
for (r in remarks_list) {
    network_remarks = network_remarks + (r.description ?? "") + " "
}

# Project key fields for LLM (keep token count low)
whois_summary = {
    "ip": ip,
    "asn": rdap.asn ?? "unknown",
    "org": rdap.asn_description ?? "unknown",
    "country": rdap.asn_country_code ?? "unknown",
    "netblock": rdap.network.cidr ?? "unknown",
    "network_name": rdap.network.name ?? "unknown",
    "network_type": rdap.network.type ?? "unknown",
    "asn_date": rdap.asn_date ?? "unknown",
    "remarks": network_remarks
}

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

WHOIS/RDAP data for ${ip}:
- Organization: ${whois_summary.org}
- ASN: ${whois_summary.asn} (allocated ${whois_summary.asn_date})
- Country: ${whois_summary.country}
- Netblock: ${whois_summary.netblock} (${whois_summary.network_name})
- Type: ${whois_summary.network_type}
- Remarks: ${whois_summary.remarks}

Based on this IP ownership data and the alert context:
1. Is this IP's ownership consistent with legitimate traffic for this alert type?
2. Are there any red flags (Tor, bulletproof hosting, unexpected country, very recent ASN allocation)?

Return JSON (no markdown): {"verdict": "suspicious|benign|inconclusive", "reason": "one sentence"}"""
)

enrichment = {
    "ip": ip,
    "asn": whois_summary.asn,
    "org": whois_summary.org,
    "country": whois_summary.country,
    "netblock": whois_summary.netblock,
    "network_name": whois_summary.network_name,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

## Pattern 5: ASN Clustering for Brute Force Detection

When investigating brute force or credential stuffing, cluster source IPs by ASN to identify if attacks come from a single network (botnet on one hosting provider) or are distributed. This pattern chains after Pattern 3's batch enrichment.

```cy
# Assumes multi-IP batch results from Pattern 3
whois_results = input.enrichments.whois_batch_lookup.whois_results ?? []

# Group by ASN
asn_groups = {}
for (result in whois_results) {
    if (result.status == "resolved") {
        asn_key = result.asn ?? "unknown"
        existing = asn_groups[asn_key] ?? []
        existing = existing + [result.ip]
        asn_groups[asn_key] = existing
    }
}

# Identify dominant ASNs (>= 3 IPs from same ASN)
concentrated_asns = []
for (asn_key in asn_groups) {
    ips_in_asn = asn_groups[asn_key] ?? []
    if (len(ips_in_asn) >= 3) {
        concentrated_asns = concentrated_asns + [{
            "asn": asn_key,
            "ip_count": len(ips_in_asn),
            "ips": ips_in_asn
        }]
    }
}

enrichment = {
    "total_asns": len(asn_groups),
    "concentrated_asns": concentrated_asns,
    "is_distributed": len(concentrated_asns) == 0
}

return enrich_alert(input, enrichment)
```

---

## Field Interpretation Guide

### `asn_description` — What the Org Name Tells You

| Pattern in `asn_description` | Interpretation | Risk Signal |
|---|---|---|
| `"GOOGLE"`, `"MICROSOFT"`, `"AMAZON"` | Major cloud/tech provider | Low — unless unexpected for this traffic type |
| `"OVH"`, `"HETZNER"`, `"DIGITALOCEAN"`, `"LINODE"` | Hosting/VPS provider | Medium — commonly used for scanning, C2 |
| `"TORSERVERS"`, `"CALYX"` | Known Tor/privacy infrastructure | High — anonymization network |
| ISP names (`"COMCAST"`, `"DTAG"`, `"BT"`) | Residential ISP | Context-dependent — could be compromised host |
| `"CLOUDFLARENET"` | CDN/proxy provider | Low — but true origin IP is hidden |

### `asn_date` — Infrastructure Age

The `asn_date` field shows when the ASN allocation was registered. SOC interpretation:

| Age | Interpretation |
|---|---|
| < 3 months old | Fresh infrastructure — elevated suspicion for attack staging |
| 3–12 months | Relatively new — worth noting but not conclusive |
| > 1 year | Established — lower risk signal for the allocation itself |

Compare against the alert timestamp: an ASN allocated days before a brute force campaign is a stronger signal than one allocated years ago. This heuristic is most useful when combined with other indicators (hosting provider type, country mismatch).

### `network.type` — Allocation Context

| Value | Meaning |
|---|---|
| `"DIRECT ALLOCATION"` | IP block directly assigned by RIR to the org |
| `"ASSIGNED PA"` | Provider-aggregatable — sub-allocated from a larger block |
| `"REALLOCATED"` | Re-allocated from one org to another |

### `asn_registry` — Which RIR Responded

| Registry | Region |
|---|---|
| `arin` | North America |
| `ripencc` | Europe, Middle East, Central Asia |
| `apnic` | Asia-Pacific |
| `afrinic` | Africa |
| `lacnic` | Latin America, Caribbean |

### `network.remarks` Signals

The `network.remarks` field contains free-text from the registrant. For the raw field schema, see `actions-reference.md` § `network` Object. SOC-relevant patterns to look for:

- **Tor exit notices:** `"This network is used for Tor Exits"` — definitive Tor signal, confirmed in live testing against known Tor exit IP `185.220.101.45`
- **Abuse reporting URLs:** Indicates the network has known abuse history
- **VPN/proxy mentions:** Some hosting providers note their blocks are for VPN services
- **Research network:** Academic or research networks sometimes note their purpose

Always extract and pass this field to the LLM during triage — it provides context that structured fields miss.
