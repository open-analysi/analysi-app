# Concepts

Different angles on the system. Read top-to-bottom if you're new; jump straight to a page otherwise.

**Big picture**

- **[Concept](concept.md)** — the central insight: knowledge is keyed to detection rules; one workflow per rule.
- **[Alert lifecycle](alert-lifecycle.md)** — the rule-driven path from alert ingestion to reaction action, with both rule engines.
- **[Component architecture](component-architecture.md)** — the runtime processes that implement the lifecycle, and the wires between them.

**Building blocks**

- **[Cy in Analysi](cy-language.md)** — the scripting language, the tools registered into the interpreter, and where it runs.
- **[Tasks](tasks.md)** — the smallest reusable unit of investigation: Cy script + IO schemas + lifecycle.
- **[Workflows](workflows.md)** — DAG of Tasks; envelope mechanics; alert in, enriched alert out.

**Cross-cutting flows**

- **[Workflow generation](workflow-generation.md)** — the cold path that synthesises a workflow the first time a detection rule fires.
- **[Disposition](disposition.md)** — the workflow's verdict; how it fans out to side-effects.
- **[Human-in-the-loop](hitl.md)** — pause a workflow on a Slack question, resume on the analyst's reply.
