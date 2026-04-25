// IP Enrichment Example — Extract and categorize IPs from alert data
//
// Demonstrates: list operations, conditional logic, result structuring.

source_ip = inp.get("source_ip") ?? "unknown"
dest_ip = inp.get("dest_ip") ?? "unknown"

// Simple private IP check
is_private_source = source_ip.startswith("10.") or source_ip.startswith("192.168.") or source_ip.startswith("172.")
is_private_dest = dest_ip.startswith("10.") or dest_ip.startswith("192.168.") or dest_ip.startswith("172.")

log(f"Source IP: {source_ip} (private: {is_private_source})")
log(f"Dest IP: {dest_ip} (private: {is_private_dest})")

result = {
    "source_ip": source_ip,
    "dest_ip": dest_ip,
    "source_is_private": is_private_source,
    "dest_is_private": is_private_dest,
    "direction": "internal" if (is_private_source and is_private_dest) else "external"
}
