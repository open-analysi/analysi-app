---
name: splunk-skill
description: Use this skill when working with Splunk queries, Search Processing Language (SPL), building Splunk searches, creating dashboards, or analyzing log data. This skill provides comprehensive reference material for SPL commands, eval functions, stats functions, regex patterns, and query optimization techniques.
version: 1.0.0
---

# Splunk Skill

## Quick Reference Selection

| Task Type | Start With |
|-----------|------------|
| Writing/debugging SPL queries | `common-pitfalls.md` then `splunk-cheat-sheet.md` |
| Slow query optimization | `search-acceleration-guide.md` or `tstats-tutorial.md` |
| Security investigation workflow | `common-workflows.md` |
| CIM compliance / data model work | `cim_documentation/overview.md` |
| Splunk infrastructure monitoring | `performance-monitoring-queries.md` |
| Security apps (InfoSec, SSE) | `splunk-security-tools.md` |
| Metrics / observability (rare) | `splunk-metrics-for-observability.md` |

## Reference Material

### references/splunk-cheat-sheet.md

Complete Splunk SPL reference including core concepts, commands, functions, regex patterns, and time formatting.

**Load when**: Writing SPL queries, looking up command syntax, building field extractions, or formatting time values.

### references/common-pitfalls.md

20 common mistakes when writing Splunk queries, with incorrect and correct examples for each.

**Load when**: Debugging slow queries, reviewing SPL for best practices, or learning Splunk anti-patterns to avoid.

### references/common-workflows.md

Step-by-step procedures for common Splunk tasks including dashboard building, performance troubleshooting, security investigations, and alert creation.

**Load when**: Following a structured approach to a Splunk task, onboarding new data, or creating alerts.

### references/performance-monitoring-queries.md

Production-ready SPL queries for monitoring Splunk infrastructure: data ingestion, resource utilization, system health, queue monitoring, and search performance.

**Load when**: Building infrastructure dashboards, troubleshooting Splunk performance, analyzing resource utilization, or detecting queue blocking issues.

### references/splunk-security-tools.md

Guide to Splunk security applications (InfoSec App, Security Essentials), Windows TA configuration, CIM compliance, and saved search configuration.

**Load when**: Implementing security apps, configuring Windows data collection, normalizing data to CIM, or setting up scheduled searches and alerts.

### references/cim_documentation/

CIM field mappings organized by category:

| File | Data Models |
|------|-------------|
| `overview.md` | Common cross-model fields, naming conventions, best practices |
| `security-fields.md` | Alerts, Authentication, DLP, Endpoint, IDS, Malware, Vulnerabilities |
| `network-fields.md` | Certificates, DNS, Network Sessions, Network Traffic, Web |
| `it-operations-fields.md` | Change, Data Access, Databases, Inventory, Performance, Updates |
| `other-fields.md` | Email, Interprocess Messaging, JVM, Splunk Audit, Tickets |

**Load when**: Mapping custom data to CIM fields, correlating across data models, or designing field extractions. Start with `overview.md`, then load category-specific file as needed.

### references/tstats-tutorial.md

Comprehensive guide to the `tstats` command for high-performance queries on accelerated data.

**Load when**: Building fast dashboard queries, querying large time ranges, working with data model acceleration, or optimizing slow stats searches.

### references/search-acceleration-guide.md

Guide to all Splunk acceleration techniques with real-world performance examples showing 10-10,000x speed improvements.

**Load when**: Choosing between acceleration techniques, understanding TSIDX architecture, transitioning to accelerated queries, or managing high-cardinality fields.

### references/splunk-metrics-for-observability.md

Metrics commands (`mstats`, `mcatalog`, `mpreview`) for time-series numeric data. **Most security workflows use events, not metrics.**

**Load when**: Explicitly working with metric indexes for infrastructure monitoring, APM, or cloud metrics. Not needed for security log analysis.

### references/general-splunk-concepts.md

Basic Splunk concepts: events, fields, indexes, architecture components, reports, dashboards, alerts.

**Load when**: Using smaller models (e.g., Haiku) that need foundational Splunk context. Not needed for capable models.
