# Analysi

Security automation platform that processes alerts through AI-powered investigation workflows. Ingests alerts from SIEMs, enriches them via threat intelligence, runs automated investigation playbooks, and produces analyst-ready dispositions.

## Where to start

- **New here?** Read the [Concept](concepts/concept.md) page — one paragraph and a diagram explain what Analysi does and why.
- **Want the full story?** Walk the [Alert lifecycle](concepts/alert-lifecycle.md), then the [Component architecture](concepts/component-architecture.md).
- **Looking up a term?** [Terminology reference](reference/terminology.md).
- **Looking for a connector?** [Integrations catalog](reference/integrations.md) — 101 built-in integrations across 27 archetypes.
- **Want to run it?** Build and deploy instructions live in the project [README on GitHub](https://github.com/open-analysi/analysi-app#readme).

## What Analysi solves

Tier-1 SOC analysts spend most of their time investigating the same kinds of alerts over and over. Analysi watches what's investigated for each detection rule, synthesizes a reusable agentic workflow on first encounter, and replays it cheaply on every subsequent alert from the same rule. See [the AI SOC problem](https://github.com/open-analysi/analysi-app/blob/main/docs/context/ai-soc-problem.md) for the longer write-up.
