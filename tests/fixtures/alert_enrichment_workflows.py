"""
Realistic alert enrichment workflow configurations for testing.

These workflows represent common patterns where:
1. Alert comes in with IoCs (IPs, domains, hashes, etc.)
2. Multiple parallel enrichment steps query external threat intel sources
3. Merge nodes combine enriched data back into the alert
4. Additional reasoning/decision steps process the enriched alert
5. Final actions (block, investigate, close) based on risk assessment
"""

from typing import Any


def get_basic_threat_intel_workflow() -> dict[str, Any]:
    """
    Basic single-stage threat intel enrichment workflow.

    Flow:
    Alert → Extract IoCs → Lookup Threat Intel → Enrich Alert → Assess Risk

    This represents the simplest enrichment pattern:
    - Extract IPs/domains from alert
    - Query single threat intel source (e.g., VirusTotal)
    - Add reputation scores to alert
    - Decide if high risk (block) or low risk (investigate)
    """
    return {
        "name": "Basic Threat Intel Enrichment",
        "description": "Single-stage enrichment with VirusTotal lookup",
        "io_schema": {
            "input": {
                "type": "object",
                "properties": {
                    "alert": {
                        "type": "object",
                        "properties": {
                            "alert_id": {"type": "string"},
                            "title": {"type": "string"},
                            "severity": {"type": "string"},
                            "iocs": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                        "type": {"type": "string"},
                                    },
                                },
                            },
                        },
                    }
                },
            },
            "output": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "enriched_alert": {"type": "object"},
                },
            },
        },
        "data_samples": [
            {
                "alert": {
                    "alert_id": "alert-001",
                    "title": "Suspicious Network Activity",
                    "severity": "high",
                    "iocs": [
                        {"value": "192.168.1.100", "type": "ipv4"},
                        {"value": "malicious.com", "type": "domain"},
                    ],
                }
            }
        ],
        "nodes": [
            {
                "node_id": "extract-iocs",
                "kind": "transformation",
                "name": "Extract IoCs from Alert",
                "is_start_node": True,
                "description": "Extract IPs and domains from alert.iocs array",
                "template_name": "extract_iocs",
                "schemas": {
                    "input": {
                        "type": "object",
                        "properties": {"alert": {"type": "object"}},
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "alert": {"type": "object"},
                            "ioc_list": {"type": "array"},
                        },
                    },
                },
            },
            {
                "node_id": "lookup-virustotal",
                "kind": "task",
                "name": "VirusTotal Lookup",
                "description": "Query VirusTotal for IoC reputation",
                "integration": "virustotal",
                "action": "lookup_indicator",
                "schemas": {
                    "input": {
                        "type": "object",
                        "properties": {
                            "alert": {"type": "object"},
                            "ioc_list": {"type": "array"},
                        },
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "alert": {"type": "object"},
                            "threat_intel": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "ioc": {"type": "string"},
                                        "score": {"type": "number"},
                                        "source": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            {
                "node_id": "enrich-alert",
                "kind": "transformation",
                "name": "Enrich Alert with Threat Intel",
                "description": "Add threat_intel array to alert",
                "template_name": "merge_threat_intel",
                "schemas": {
                    "input": {
                        "type": "object",
                        "properties": {
                            "alert": {"type": "object"},
                            "threat_intel": {"type": "array"},
                        },
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "enriched_alert": {
                                "type": "object",
                                "properties": {"threat_intel": {"type": "array"}},
                            }
                        },
                    },
                },
            },
            {
                "node_id": "assess-risk",
                "kind": "transformation",
                "name": "Assess Risk Level",
                "description": "Calculate risk score from threat intel",
                "template_name": "calculate_risk_score",
                "schemas": {
                    "input": {
                        "type": "object",
                        "properties": {"enriched_alert": {"type": "object"}},
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "enriched_alert": {"type": "object"},
                        },
                    },
                },
            },
        ],
        "edges": [
            {
                "edge_id": "e1",
                "from_node_id": "extract-iocs",
                "to_node_id": "lookup-virustotal",
            },
            {
                "edge_id": "e2",
                "from_node_id": "lookup-virustotal",
                "to_node_id": "enrich-alert",
            },
            {
                "edge_id": "e3",
                "from_node_id": "enrich-alert",
                "to_node_id": "assess-risk",
            },
        ],
    }


def get_parallel_enrichment_workflow() -> dict[str, Any]:
    """
    Multi-source parallel threat intel enrichment with merge.

    Flow:
                        ┌→ VirusTotal Lookup ─┐
    Alert → Extract IoCs ┼→ AbuseIPDB Lookup  ├→ Merge Intel → Enrich Alert → Assess Risk
                        └→ AlienVault Lookup ─┘

    This represents parallel enrichment from multiple sources:
    - Extract IoCs from alert
    - Query 3 threat intel sources in parallel (VirusTotal, AbuseIPDB, AlienVault)
    - Merge node combines all 3 threat intel responses
    - Add merged threat intel to alert
    - Assess risk based on combined intelligence
    """
    return {
        "name": "Parallel Multi-Source Threat Intel",
        "description": "Parallel enrichment from VirusTotal, AbuseIPDB, and AlienVault OTX",
        "io_schema": {
            "input": {
                "type": "object",
                "properties": {
                    "alert": {
                        "type": "object",
                        "properties": {
                            "alert_id": {"type": "string"},
                            "iocs": {"type": "array"},
                        },
                    }
                },
            },
            "output": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "enriched_alert": {"type": "object"},
                },
            },
        },
        "data_samples": [
            {
                "alert": {
                    "alert_id": "alert-002",
                    "iocs": [{"value": "malicious.com", "type": "domain"}],
                }
            }
        ],
        "nodes": [
            {
                "node_id": "extract-iocs",
                "is_start_node": True,
                "kind": "transformation",
                "name": "Extract IoCs",
                "template_name": "extract_iocs",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "alert": {"type": "object"},
                            "ioc_list": {"type": "array"},
                        },
                    },
                },
            },
            {
                "node_id": "lookup-virustotal",
                "kind": "task",
                "name": "VirusTotal Lookup",
                "integration": "virustotal",
                "action": "lookup_indicator",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"vt_intel": {"type": "array"}},
                    },
                },
            },
            {
                "node_id": "lookup-abuseipdb",
                "kind": "task",
                "name": "AbuseIPDB Lookup",
                "integration": "abuseipdb",
                "action": "check_ip",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"abuseipdb_intel": {"type": "array"}},
                    },
                },
            },
            {
                "node_id": "lookup-alienvault",
                "kind": "task",
                "name": "AlienVault OTX Lookup",
                "integration": "alienvaultotx",
                "action": "query_indicator",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"otx_intel": {"type": "array"}},
                    },
                },
            },
            {
                "node_id": "merge-threat-intel",
                "kind": "transformation",
                "name": "Merge All Threat Intel",
                "template_name": "merge",
                "description": "Merge node combines vt_intel, abuseipdb_intel, otx_intel",
                "schemas": {
                    "input": {"type": "array"},  # List of objects from 3 predecessors
                    "output": {
                        "type": "object",
                        "properties": {
                            "combined_intel": {
                                "type": "object",
                                "properties": {
                                    "vt_intel": {"type": "array"},
                                    "abuseipdb_intel": {"type": "array"},
                                    "otx_intel": {"type": "array"},
                                },
                            }
                        },
                    },
                },
            },
            {
                "node_id": "enrich-alert",
                "kind": "transformation",
                "name": "Enrich Alert",
                "template_name": "add_threat_intel_to_alert",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"enriched_alert": {"type": "object"}},
                    },
                },
            },
            {
                "node_id": "assess-risk",
                "kind": "transformation",
                "name": "Assess Risk",
                "template_name": "calculate_risk_score",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "enriched_alert": {"type": "object"},
                        },
                    },
                },
            },
        ],
        "edges": [
            # Extract IoCs → 3 parallel lookups
            {
                "edge_id": "e1",
                "from_node_id": "extract-iocs",
                "to_node_id": "lookup-virustotal",
            },
            {
                "edge_id": "e2",
                "from_node_id": "extract-iocs",
                "to_node_id": "lookup-abuseipdb",
            },
            {
                "edge_id": "e3",
                "from_node_id": "extract-iocs",
                "to_node_id": "lookup-alienvault",
            },
            # 3 lookups → Merge node
            {
                "edge_id": "e4",
                "from_node_id": "lookup-virustotal",
                "to_node_id": "merge-threat-intel",
            },
            {
                "edge_id": "e5",
                "from_node_id": "lookup-abuseipdb",
                "to_node_id": "merge-threat-intel",
            },
            {
                "edge_id": "e6",
                "from_node_id": "lookup-alienvault",
                "to_node_id": "merge-threat-intel",
            },
            # Merge → Enrich → Assess
            {
                "edge_id": "e7",
                "from_node_id": "merge-threat-intel",
                "to_node_id": "enrich-alert",
            },
            {
                "edge_id": "e8",
                "from_node_id": "enrich-alert",
                "to_node_id": "assess-risk",
            },
        ],
    }


def get_multi_stage_enrichment_workflow() -> dict[str, Any]:
    """
    Multi-stage enrichment: Network context, then threat intel, then user context.

    Flow:
    Alert → Extract Network Context → GeoIP Lookup → Add Geo to Alert
          ↓
          Extract IoCs → VirusTotal + AbuseIPDB → Merge Intel → Add Intel to Alert
          ↓
          Extract User → AD Lookup → Add User Context to Alert
          ↓
          Assess Combined Risk → Decide Action

    This represents staged enrichment where each stage builds on previous:
    1. Stage 1 (Network): Add geographic context for IPs
    2. Stage 2 (Threat Intel): Add reputation for IoCs
    3. Stage 3 (Identity): Add user/entity risk profile
    4. Stage 4 (Decision): Assess combined risk and decide action
    """
    return {
        "name": "Multi-Stage Alert Enrichment Pipeline",
        "description": "Three-stage enrichment: Network → Threat Intel → Identity → Decision",
        "io_schema": {
            "input": {"type": "object", "properties": {"alert": {"type": "object"}}},
            "output": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "enriched_alert": {"type": "object"},
                    "risk_score": {"type": "number"},
                },
            },
        },
        "data_samples": [
            {"alert": {"alert_id": "alert-003", "network_info": {"src_ip": "10.0.0.1"}}}
        ],
        "nodes": [
            # Stage 1: Network Context
            {
                "node_id": "extract-network",
                "is_start_node": True,
                "kind": "transformation",
                "name": "Extract Network Info",
                "template_name": "extract_network_artifacts",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "alert": {"type": "object"},
                            "src_ip": {"type": "string"},
                            "dst_ip": {"type": "string"},
                        },
                    },
                },
            },
            {
                "node_id": "geoip-lookup",
                "kind": "task",
                "name": "GeoIP Lookup",
                "integration": "maxmind",
                "action": "lookup_ip",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "geo_data": {
                                "type": "object",
                                "properties": {
                                    "src_country": {"type": "string"},
                                    "dst_country": {"type": "string"},
                                },
                            }
                        },
                    },
                },
            },
            {
                "node_id": "add-geo-to-alert",
                "kind": "transformation",
                "name": "Add Geographic Context",
                "template_name": "merge_geo_context",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"alert_with_geo": {"type": "object"}},
                    },
                },
            },
            # Stage 2: Threat Intel (Parallel)
            {
                "node_id": "extract-iocs",
                "kind": "transformation",
                "name": "Extract IoCs",
                "template_name": "extract_iocs",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "alert_with_geo": {"type": "object"},
                            "ioc_list": {"type": "array"},
                        },
                    },
                },
            },
            {
                "node_id": "lookup-virustotal-stage2",
                "kind": "task",
                "name": "VirusTotal Lookup",
                "integration": "virustotal",
                "action": "lookup_indicator",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"vt_intel": {"type": "array"}},
                    },
                },
            },
            {
                "node_id": "lookup-abuseipdb-stage2",
                "kind": "task",
                "name": "AbuseIPDB Lookup",
                "integration": "abuseipdb",
                "action": "check_ip",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"abuseipdb_intel": {"type": "array"}},
                    },
                },
            },
            {
                "node_id": "merge-threat-intel-stage2",
                "kind": "transformation",
                "name": "Merge Threat Intel",
                "template_name": "merge",
                "schemas": {
                    "input": {"type": "array"},
                    "output": {
                        "type": "object",
                        "properties": {"combined_threat_intel": {"type": "object"}},
                    },
                },
            },
            {
                "node_id": "add-intel-to-alert",
                "kind": "transformation",
                "name": "Add Threat Intel to Alert",
                "template_name": "merge_threat_intel_to_alert",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"alert_with_intel": {"type": "object"}},
                    },
                },
            },
            # Stage 3: Identity/User Context
            {
                "node_id": "extract-user",
                "kind": "transformation",
                "name": "Extract User Identity",
                "template_name": "extract_primary_risk_entity",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "alert_with_intel": {"type": "object"},
                            "username": {"type": "string"},
                        },
                    },
                },
            },
            {
                "node_id": "ad-lookup",
                "kind": "task",
                "name": "Active Directory Lookup",
                "integration": "ad_ldap",
                "action": "query_user",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "user_context": {
                                "type": "object",
                                "properties": {
                                    "department": {"type": "string"},
                                    "title": {"type": "string"},
                                    "risk_level": {"type": "string"},
                                },
                            }
                        },
                    },
                },
            },
            {
                "node_id": "add-user-context",
                "kind": "transformation",
                "name": "Add User Context to Alert",
                "template_name": "merge_user_context",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"fully_enriched_alert": {"type": "object"}},
                    },
                },
            },
            # Stage 4: Decision
            {
                "node_id": "assess-combined-risk",
                "kind": "transformation",
                "name": "Assess Combined Risk",
                "template_name": "calculate_combined_risk_score",
                "description": "Considers geo, threat intel, and user context",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "risk_score": {"type": "number"},
                            "risk_factors": {"type": "array"},
                        },
                    },
                },
            },
            {
                "node_id": "decide-action",
                "kind": "transformation",
                "name": "Decide Action",
                "template_name": "risk_based_action_decision",
                "description": "High risk → block, Medium → investigate, Low → close",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "enriched_alert": {"type": "object"},
                            "risk_score": {"type": "number"},
                        },
                    },
                },
            },
        ],
        "edges": [
            # Stage 1: Network
            {
                "edge_id": "e1",
                "from_node_id": "extract-network",
                "to_node_id": "geoip-lookup",
            },
            {
                "edge_id": "e2",
                "from_node_id": "geoip-lookup",
                "to_node_id": "add-geo-to-alert",
            },
            # Stage 2: Threat Intel
            {
                "edge_id": "e3",
                "from_node_id": "add-geo-to-alert",
                "to_node_id": "extract-iocs",
            },
            {
                "edge_id": "e4",
                "from_node_id": "extract-iocs",
                "to_node_id": "lookup-virustotal-stage2",
            },
            {
                "edge_id": "e5",
                "from_node_id": "extract-iocs",
                "to_node_id": "lookup-abuseipdb-stage2",
            },
            {
                "edge_id": "e6",
                "from_node_id": "lookup-virustotal-stage2",
                "to_node_id": "merge-threat-intel-stage2",
            },
            {
                "edge_id": "e7",
                "from_node_id": "lookup-abuseipdb-stage2",
                "to_node_id": "merge-threat-intel-stage2",
            },
            {
                "edge_id": "e8",
                "from_node_id": "merge-threat-intel-stage2",
                "to_node_id": "add-intel-to-alert",
            },
            # Stage 3: Identity
            {
                "edge_id": "e9",
                "from_node_id": "add-intel-to-alert",
                "to_node_id": "extract-user",
            },
            {
                "edge_id": "e10",
                "from_node_id": "extract-user",
                "to_node_id": "ad-lookup",
            },
            {
                "edge_id": "e11",
                "from_node_id": "ad-lookup",
                "to_node_id": "add-user-context",
            },
            # Stage 4: Decision
            {
                "edge_id": "e12",
                "from_node_id": "add-user-context",
                "to_node_id": "assess-combined-risk",
            },
            {
                "edge_id": "e13",
                "from_node_id": "assess-combined-risk",
                "to_node_id": "decide-action",
            },
        ],
    }


def get_edr_investigation_workflow() -> dict[str, Any]:
    """
    EDR-focused workflow with parallel device and process enrichment.

    Flow:
    Alert → Extract Device & Process Info
          ↓
          ┌→ EDR Device Lookup (isolation status, vulnerabilities) ─┐
          ├→ Process Tree Lookup (parent processes, children)        ├→ Merge Context
          └→ Hash Reputation (file hashes via VirusTotal)            ─┘
          ↓
          Add EDR Context to Alert → Assess Endpoint Risk → Decide Action

    This represents EDR-specific enrichment:
    - Query endpoint security platform for device state
    - Get process execution tree
    - Check file hash reputation
    - Merge all EDR context
    - Decide if containment is needed
    """
    return {
        "name": "EDR Investigation & Response Workflow",
        "description": "Parallel EDR enrichment: device status, process tree, hash reputation",
        "io_schema": {
            "input": {
                "type": "object",
                "properties": {
                    "alert": {
                        "type": "object",
                        "properties": {
                            "source_category": {"type": "string"},  # "EDR"
                            "primary_risk_entity_value": {"type": "string"},  # hostname
                            "process_info": {
                                "type": "object",
                                "properties": {
                                    "process_name": {"type": "string"},
                                    "file_hash": {"type": "string"},
                                },
                            },
                        },
                    }
                },
            },
            "output": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "enriched_alert": {"type": "object"},
                    "containment_required": {"type": "boolean"},
                },
            },
        },
        "data_samples": [
            {
                "alert": {
                    "source_category": "EDR",
                    "primary_risk_entity_value": "LAPTOP-001",
                    "process_info": {
                        "process_name": "suspicious.exe",
                        "file_hash": "abcd1234",
                    },
                }
            }
        ],
        "nodes": [
            {
                "node_id": "extract-edr-artifacts",
                "is_start_node": True,
                "kind": "transformation",
                "name": "Extract EDR Artifacts",
                "template_name": "extract_device_and_process_info",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "alert": {"type": "object"},
                            "hostname": {"type": "string"},
                            "process_name": {"type": "string"},
                            "file_hash": {"type": "string"},
                        },
                    },
                },
            },
            # Parallel EDR enrichment
            {
                "node_id": "edr-device-lookup",
                "kind": "task",
                "name": "Query EDR Platform - Device",
                "integration": "crowdstrike",  # or sentinelone, defender_endpoint
                "action": "get_device_details",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "device_context": {
                                "type": "object",
                                "properties": {
                                    "isolated": {"type": "boolean"},
                                    "last_seen": {"type": "string"},
                                    "vulnerabilities": {"type": "array"},
                                    "os_version": {"type": "string"},
                                },
                            }
                        },
                    },
                },
            },
            {
                "node_id": "process-tree-lookup",
                "kind": "task",
                "name": "Get Process Tree",
                "integration": "crowdstrike",
                "action": "get_process_tree",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "process_tree": {
                                "type": "object",
                                "properties": {
                                    "parent_process": {"type": "string"},
                                    "child_processes": {"type": "array"},
                                    "execution_chain": {"type": "array"},
                                },
                            }
                        },
                    },
                },
            },
            {
                "node_id": "hash-reputation-lookup",
                "kind": "task",
                "name": "File Hash Reputation",
                "integration": "virustotal",
                "action": "lookup_file_hash",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "hash_reputation": {
                                "type": "object",
                                "properties": {
                                    "malicious_score": {"type": "number"},
                                    "detections": {"type": "number"},
                                    "first_seen": {"type": "string"},
                                },
                            }
                        },
                    },
                },
            },
            {
                "node_id": "merge-edr-context",
                "kind": "transformation",
                "name": "Merge All EDR Context",
                "template_name": "merge",
                "schemas": {
                    "input": {"type": "array"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "edr_context": {
                                "type": "object",
                                "properties": {
                                    "device_context": {"type": "object"},
                                    "process_tree": {"type": "object"},
                                    "hash_reputation": {"type": "object"},
                                },
                            }
                        },
                    },
                },
            },
            {
                "node_id": "add-edr-to-alert",
                "kind": "transformation",
                "name": "Add EDR Context to Alert",
                "template_name": "merge_edr_context_to_alert",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {"enriched_alert": {"type": "object"}},
                    },
                },
            },
            {
                "node_id": "assess-endpoint-risk",
                "kind": "transformation",
                "name": "Assess Endpoint Risk",
                "template_name": "calculate_endpoint_risk",
                "description": "Considers process behavior, hash reputation, device vulnerabilities",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "endpoint_risk_score": {"type": "number"},
                            "indicators_of_compromise": {"type": "array"},
                        },
                    },
                },
            },
            {
                "node_id": "decide-containment",
                "kind": "transformation",
                "name": "Decide Containment Action",
                "template_name": "edr_action_decision",
                "description": "High risk → isolate device, Medium → kill process, Low → monitor",
                "schemas": {
                    "input": {"type": "object"},
                    "output": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "enriched_alert": {"type": "object"},
                            "containment_required": {"type": "boolean"},
                        },
                    },
                },
            },
        ],
        "edges": [
            # Extract → 3 parallel lookups
            {
                "edge_id": "e1",
                "from_node_id": "extract-edr-artifacts",
                "to_node_id": "edr-device-lookup",
            },
            {
                "edge_id": "e2",
                "from_node_id": "extract-edr-artifacts",
                "to_node_id": "process-tree-lookup",
            },
            {
                "edge_id": "e3",
                "from_node_id": "extract-edr-artifacts",
                "to_node_id": "hash-reputation-lookup",
            },
            # 3 lookups → Merge
            {
                "edge_id": "e4",
                "from_node_id": "edr-device-lookup",
                "to_node_id": "merge-edr-context",
            },
            {
                "edge_id": "e5",
                "from_node_id": "process-tree-lookup",
                "to_node_id": "merge-edr-context",
            },
            {
                "edge_id": "e6",
                "from_node_id": "hash-reputation-lookup",
                "to_node_id": "merge-edr-context",
            },
            # Merge → Enrich → Assess → Decide
            {
                "edge_id": "e7",
                "from_node_id": "merge-edr-context",
                "to_node_id": "add-edr-to-alert",
            },
            {
                "edge_id": "e8",
                "from_node_id": "add-edr-to-alert",
                "to_node_id": "assess-endpoint-risk",
            },
            {
                "edge_id": "e9",
                "from_node_id": "assess-endpoint-risk",
                "to_node_id": "decide-containment",
            },
        ],
    }


# Workflow registry for easy access in tests
ALERT_ENRICHMENT_WORKFLOWS = {
    "basic_threat_intel": get_basic_threat_intel_workflow,
    "parallel_enrichment": get_parallel_enrichment_workflow,
    "multi_stage_enrichment": get_multi_stage_enrichment_workflow,
    "edr_investigation": get_edr_investigation_workflow,
}


def get_workflow_by_name(name: str) -> dict[str, Any]:
    """Get workflow configuration by name."""
    if name not in ALERT_ENRICHMENT_WORKFLOWS:
        raise ValueError(
            f"Unknown workflow: {name}. Available: {list(ALERT_ENRICHMENT_WORKFLOWS.keys())}"
        )
    return ALERT_ENRICHMENT_WORKFLOWS[name]()
