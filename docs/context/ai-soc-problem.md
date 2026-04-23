# The AI SOC Problem — and How Analysi Addresses It

## The Problem

Security Operations Centers face a structural mismatch: alert volume grows faster than analyst capacity. The consequences are well-documented:

- **Alert fatigue**: Analysts face thousands of alerts daily. Up to 80% of effort goes to proving a threat *doesn't* exist. Critical signals get buried.
- **Data quality gap**: Adding AI to poorly normalized, un-enriched data produces noise, not insight. Most organizations struggle with data onboarding, schematization, and enrichment before they can even consider automation.
- **Talent shortage**: Not enough analysts, and Tier 1 triage has a steep learning curve. High turnover means institutional knowledge walks out the door.
- **Brittle automation**: Traditional SOAR playbooks are rigid — deterministic sequences that break when alert formats change. Building and maintaining them requires specialized engineering effort.

## How Analysi Addresses This

Analysi is a security automation platform that uses AI agents to investigate alerts the way a human analyst would — but at machine scale. Here's what's built and working:

### Alert Processing Pipeline
Alerts are ingested from SIEMs (Splunk, Elasticsearch) and normalized to **OCSF Detection Finding v1.8.0** — a vendor-neutral schema. This solves the data quality problem at the front door: every alert arrives in a consistent format with typed observables, MITRE ATT&CK mappings, and structured metadata.

### AI-Powered Workflow Generation (Project Kea)
When an alert arrives, the **Automated Workflow Builder** examines the alert type and automatically composes a custom analysis workflow. It matches the alert against runbooks, generates investigation hypotheses, and chains together the right enrichment and analysis tasks — no static playbooks required.

The workflow builder uses a LangGraph pipeline with progressive context retrieval from a database-backed skills system (SkillsIR). Each stage follows a SubStep pattern: Retrieve relevant knowledge → Execute with LLM reasoning → Validate output → Loop if needed.

### Composable Task and Workflow System
Workflows are directed acyclic graphs (DAGs) of **Tasks** — reusable analysis components written in the **Cy language** (a domain-specific scripting language). Tasks can:

- Query external tools via the **Naxos integration framework** (Splunk searches, VirusTotal lookups, LDAP queries, EDR endpoint data)
- Use LLM reasoning for analysis, correlation, and disposition decisions
- Run in parallel for independent enrichment paths, then merge results

This is the composability that SOAR promised but rarely delivered — workflows are generated per-alert, not hand-coded per-alert-type.

### Progressive Contextualization Pattern
Every workflow follows a consistent investigation pattern:

1. **Summarize** — Generate a human-readable context of the alert
2. **Retrieve evidence** — Pull triggering and supporting events from the SIEM
3. **Enrich** — Parallel queries to threat intel, identity providers, endpoint telemetry
4. **Correlate** — Merge enrichment data and assess risk across dimensions
5. **Dispose** — Final determination (true positive, false positive, benign) with confidence score and recommended actions

Each task adds context without replacing previous work — the alert grows richer through each stage, preserving the full investigation trail.

### Human-in-the-Loop (Project Kalymnos)
When automated analysis reaches a decision point that requires human judgment, the system pauses. Analysts receive Slack notifications with investigation context and respond directly — the workflow resumes from where it left off using memoized replay (no re-execution of completed steps).

### Control Event Bus (Project Tilos)
A transactional outbox pattern enables reactive automation: when an alert reaches a disposition, configured rules can fire follow-up actions — JIRA ticket creation, Slack notifications, webhook pushes — all without modifying the core analysis workflow.

### Multi-Tenant, Production-Ready
- **Keycloak-based auth** with OIDC, API keys, and RBAC (Project Mikonos)
- **Per-tenant credential isolation** via Vault Transit encryption
- **Content Packs** for portable, installable bundles of tasks, skills, and workflows (Project Delos)
- **Structured logging** with structlog, correlation IDs, and OpenTelemetry foundations (Project Syros)
- **Helm charts** for Kubernetes deployment, CI/CD via GitHub Actions (Project Lefkada)

## What This Means

The SOC industry consensus is that AI should augment analysts, not replace them. Analysi operationalizes this by:

- **Investigating 100% of alerts** — not just the ones analysts have time for
- **Generating investigation workflows on the fly** — no playbook maintenance burden
- **Preserving human oversight** — analysts review dispositions and intervene when needed
- **Building on clean data** — OCSF normalization ensures AI operates on structured, vendor-neutral inputs

The result is a system where Tier 1 triage is automated with full transparency, and human analysts focus on the investigations that actually need their judgment.
