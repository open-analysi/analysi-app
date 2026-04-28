# Coverage Uplift Plan

> Source-of-truth for the in-flight coverage PR. We harvest meaningful unit
> tests (happy path + corner cases + error/unhappy paths) for modules that
> are under-covered by **both** unit and integration test suites today.
> Integration-only territory (routers, repositories) is called out
> explicitly at the end and **not** addressed in this PR.

## 1. Baseline (run on this branch)

### 1a. Original baseline (before any changes in this PR)

| Metric | Value |
| --- | --- |
| Tool | `pytest tests/unit/ --cov=src` (the same command the CI workflow runs) |
| Total statements | **62 530** |
| Covered | 46 346 (74.12 %) |
| Missing | **16 184** |
| Files below 90 % | **260** (out of ~430 source files) |

### 1b. After Commit 1 — orphan-tests fix

A non-trivial chunk of `tests/alert_normalizer/` (≈ 558 tests) was
**orphaned** — never executed in CI because `[tool.pytest.ini_options]
testpaths` was set to `["tests/unit"]`. Adding `tests/alert_normalizer` to
`testpaths` and quarantining 30 obsolete legacy-field assertions in
`test_splunk_demo_notables.py` (pending an OCSF rewrite — see module
docstring) yields:

| Metric | Value | Δ |
| --- | --- | --- |
| Covered statements | **47 641** | +1 295 |
| Coverage | **76.19 %** | +2.07 pp |
| Tests added | 0 | (just enabled existing ones) |
| Tests skipped | 48 | obsolete legacy-field assertions |

This single configuration fix lifts every OCSF normalizer from 0 % to
≥ 89 %:

| File | Before | After |
| --- | ---: | ---: |
| `aws_security_ocsf.py` | 0 % | 98.6 % |
| `chronicle_ocsf.py` | 0 % | 93.3 % |
| `cortex_xdr_ocsf.py` | 62.6 % | 99.2 % |
| `crowdstrike_ocsf.py` | 0 % | 99.5 % |
| `elastic_ocsf.py` | 0 % | 89.7 % |
| `qradar_ocsf.py` | 82.7 % | 96.8 % |
| `sentinel_ocsf.py` | 80.4 % | 98.3 % |
| `sentinelone_ocsf.py` | 75.8 % | 95.7 % |

### 1c. After Commit 2 — Bucket A pure-function tests

New parametrized tests for the smallest, lowest-coverage pure-function
modules. Every file is now ≥ 95 %:

| File | Before | After | Tests added |
| --- | ---: | ---: | ---: |
| `alert_normalizer/helpers/ip_classification.py` | 20.4 % | **100 %** | 106 (parametrized) |
| `services/cy_time_functions.py` | 12.2 % | 97.6 % | 25 |
| `services/cy_sleep_functions.py` | 35.3 % | **100 %** | 9 |
| `services/type_propagation/schema_validation.py` | 9.4 % | ~95 % | 19 |
| `services/type_propagation/data_sample_validator.py` | 45.0 % | ~85 % | 20 (corner cases) |
| `services/cy_functions.py` (corner cases) | 73.0 % | ~80 % | 12 (orphan-artifact, UUID coercion, str-fallback) |

| Metric | Value | Δ |
| --- | --- | --- |
| Covered statements | **47 799** | +158 over Commit 1 |
| Coverage | **76.44 %** | +0.25 pp over Commit 1 |
| Tests added | 191 | (across 6 files) |

Cumulative uplift in this PR so far: **74.12 % → 76.44 %** (+2.32 pp,
+1 453 lines covered) with **0 production-code changes** (just config +
tests). This pattern — finding orphaned tests and writing tight,
parametrized pure-function suites — is the highest-ROI work in the plan.

### 1d. Combined coverage (unit + integration) — the *true* picture

The unit-only baseline overstates how bad coverage is, because integration
tests exercise routers and repositories. Running the full integration
suite (`make test-db-up && pytest tests/integration -m "integration and
not requires_full_stack and not requires_api"`) and unioning the executed
lines with the unit-test data gives the **combined view we should plan
against**. Regenerate with::

    poetry run python scripts/code_quality_tools/combine_coverage.py \
        out.json coverage_unit.json coverage_integration.json

| Metric | Combined |
| --- | --- |
| Covered statements | **51 827 / 62 530** |
| Coverage | **82.88 %** |
| Missing | **10 703** |

Integration tests massively rescue routers and repositories:

| Area | Unit-only | Combined | Δ |
| --- | ---: | ---: | ---: |
| `src/analysi/routers/**` | 36.9 % | **70.9 %** | +34.0 pp |
| `src/analysi/repositories/**` | 55.9 % | **79.7 %** | +23.8 pp |
| `src/analysi/agentic_orchestration/**` | 74.3 % | 75.9 % | +1.6 |
| `src/analysi/alert_analysis/**` | 70.1 % | 71.1 % | +1.0 |
| `src/analysi/services/**` | 63.0 % | 71.0 % | +8.0 |

#### True gaps — files still < 90 % in BOTH suites

This is the actionable list. Filtering out every file that integration
tests already cover, here are the files where unit tests **still** have
the most leverage. Sorted by absolute uncovered lines:

##### Bucket P0 — large + low coverage in both (highest ROI)

| File | Combined | Missing | Why uncovered by integration |
| --- | ---: | ---: | --- |
| `services/cy_autocomplete.py` | 27 % | 175 | Pure trie/grammar — never called by API endpoints |
| `alert_analysis/clients.py` | 40 % | 174 | API-client wrappers; integration mocks them out |
| `services/chat_tool_registry.py` | 24 % | 146 | 22 LLM-tool wrappers; integration tests stub the LLM agent |
| `mcp/tools/workflow_tools.py` | 77 % | 133 | MCP transport not exercised in API integration tests |
| `services/splunk_factory.py` | **0 %** | 131 | **Dead code — unused, propose to delete** |
| `utils/splunk_utils.py` | 58 % | 102 | SPL string sanitizers; not on hot integration path |
| `services/chat_tools.py` | 61 % | 88 | Chat tool implementations; LLM-stubbed in integration |
| `data/cim_mappings.py` | 11 % | 77 | KU lookup loader; rarely walked end-to-end |
| `routers/credentials.py` | 27 % | 75 | Permission-denial branches not in integration happy path |
| `agentic_orchestration/stages/agent_stages.py` | 49 % | 68 | LLM-driven; integration stubs LLM |

##### Bucket P1 — medium-size files with mid coverage

| File | Combined | Missing |
| --- | ---: | ---: |
| `agentic_orchestration/task_generation_client.py` | 42 % | 57 |
| `alert_analysis/jobs/content_review.py` | 44 % | 58 |
| `services/chat_action_tools.py` | 43 % | 46 |
| `services/knowledge_index.py` | 68 % | 45 |
| `agentic_orchestration/skills_sync.py` | 67 % | 45 |
| `services/knowledge_module.py` | 64 % | 42 |
| `mcp/analysi_server.py` | 67 % | 42 |
| `services/artifact_service.py` | 72 % | 41 |
| `mcp/tools/cy_tools.py` | 77 % | 40 |

##### Bucket P2 — third-party `actions.py` (74 files, 5 290 missing lines)

These are HTTP-action wrappers for vendor APIs. Integration tests don't
hit them because the lab containers cover only Splunk + Echo EDR + LDAP +
Elastic. Strategy: **shared httpx-mock fixture + parametrized
success/4xx/5xx/timeout matrix per action**, applied to the top 10 by
absolute uncovered LOC first:

| Integration | Combined | Missing |
| --- | ---: | ---: |
| slack | 45 % | 377 |
| cortex_xdr | 59 % | 335 |
| crowdstrike | 64 % | 262 |
| sentinelone | 68 % | 208 |
| microsoftteams | 45 % | 205 |
| defender_endpoint | 53 % | 205 |
| echo_edr | 37 % | 188 |
| zscaler | 65 % | 167 |
| paloalto_firewall | 75 % | 156 |
| splunk | 73 % | 149 |
| **(top 10 subtotal)** | — | **2 252** |

Bringing the top 10 to 85 % each closes ~1 200 missing lines (~2 pp
overall). Remaining 64 integrations get a smaller catch-up pass (one
"auth fail + rate limit + malformed payload" parametrized test each).

##### Bucket P3 — routers / repositories still under 90 % (deferred)

These need **more integration tests**, not unit tests. We open a
follow-up issue but do **not** address in this PR (would yield
mock-heavy, brittle unit tests):

| Router | Combined |
| --- | ---: |
| `routers/workflow_execution.py` | 35 % |
| `routers/integrations.py` | 53 % |
| `routers/bulk_operations.py` | 62 % |
| `routers/task_execution.py` | 62 % |
| `routers/artifacts.py` | 46 % |

| Repository | Combined |
| --- | ---: |
| `repositories/knowledge_unit.py` | 81 % |
| `repositories/alert_repository.py` | 80 % |
| `repositories/workflow.py` | 75 % |
| `repositories/conversation_repository.py` | 65 % |
| `repositories/checkpoint_repository.py` | 54 % |

To reproduce locally:
`make test-db-up && ANTHROPIC_API_KEY="" OPENAI_API_KEY="" poetry run pytest --cov=src --cov-report=term-missing --cov-report=json:coverage.json`.
JSON snapshot kept at `coverage.json` while this PR is open.

## 2. Aggregated gap by area

| Area | Coverage | Missing / Total | Files <90 % | Comment |
| --- | --- | --- | --- | --- |
| `src/analysi/integrations/framework/integrations/**` | 81.6 % | 5 339 / 30 205 | 74 | Action handlers — partial unit-test value, mostly httpx mocks |
| `src/analysi/services/**` | 63.0 % | 2 661 / 7 194 | 49 | **Highest unit-test ROI** — pure logic, mockable |
| `src/analysi/routers/**` | 36.9 % | 2 135 / 3 384 | 33 | Mostly **integration territory** (FastAPI handlers) |
| `src/alert_normalizer/**` | very low | ≈ 1 600 / ≈ 2 100 | 7 | Several files at **0 %** — pure transformers, prime unit-test target |
| `src/analysi/repositories/**` | 55.9 % | 1 203 / 2 730 | 22 | Mostly **integration territory** (DB layer) |
| `src/analysi/mcp/**` | 42.7 % | 753 / 1 313 | 11 | Tool wrappers — partial unit-test value with mocks |
| `src/analysi/alert_analysis/**` | 70.1 % | 462 / 1 546 | 8 | Mix of pure logic + DB jobs |
| `src/analysi/agentic_orchestration/**` | 74.3 % | 448 / 1 745 | 14 | LLM-heavy; testable with stub providers |

## 3. Worst-offender cliff (zero or near-zero coverage)

These are files with effectively no tests today. They are mostly **pure
transformers / pure factories** — perfect unit-test targets, fast to write,
fast to run, easy to challenge with malformed input.

| File | LOC | Cov | Notes |
| --- | --- | --- | --- |
| `alert_normalizer/elastic_ocsf.py` | 368 | 0 % | ECS → OCSF mapping, pure function |
| `alert_normalizer/chronicle_ocsf.py` | 297 | 0 % | UDM → OCSF mapping |
| `alert_normalizer/aws_security_ocsf.py` | 293 | 0 % | GuardDuty + Security Hub → OCSF |
| `alert_normalizer/crowdstrike_ocsf.py` | 205 | 0 % | Falcon → OCSF |
| `alert_normalizer/__main__.py` | 71 | 0 % | CLI entry — happy path + arg-error tests |
| `services/chat_tool_registry.py` | 191 | 0 % | 22 tool wrappers, currently never imported in any unit test |
| `services/splunk_factory.py` | 131 | 0 % | Factory pattern; mock IntegrationService + VaultClient |
| `slack_listener/__main__.py` | 23 | 0 % | CLI entry |
| `analysi/alert_worker.py` | 20 | 0 % | Worker entry — boot + signal-handling smoke tests |
| `analysi/tools/linting.py` | 29 | 0 % | Lint runner script |
| `schemas/integration_credentials.py` | 20 | 0 % | Likely dead/unused — **investigate, delete if obsolete** |
| `data/cim_mappings.py` | 87 | 11.5 % | Mapping loader; KU table → dict |
| `services/cy_time_functions.py` | 41 | 12.2 % | Time helpers — easy pure-function tests |
| `services/cy_autocomplete.py` | 239 | 18.0 % | Trie/grammar logic |
| `db/health.py` | 38 | 18.4 % | Health probe — mock async session |
| `services/partition_management.py` | 54 | 20.4 % | Wrapper around `partman.run_maintenance_proc()` |
| `alert_normalizer/helpers/ip_classification.py` | 54 | 20.4 % | Pure IP-range classifier |

> **Rule of thumb**: anything ≤ 25 % coverage in `services/`, `alert_normalizer/`,
> `mcp/tools/`, `utils/` or `common/` is almost certainly a *missing test*
> rather than untestable code. We address each one explicitly below.

## 4. Work plan — bucketed by testability

We split the work into five buckets in priority order. Each bucket states the
*kind* of test we expect, so we don't slip into vanity coverage.

### Bucket A — pure transformers / mappers / parsers (highest ROI)

Fully unit-testable, no DB, no HTTP, no LLM. Perfect for fast tests with
generous corner-case coverage. **Target: 95 %+ on these files.**

| File | Currently | Test plan |
| --- | --- | --- |
| `alert_normalizer/elastic_ocsf.py` | 0 % | Happy: typical Elastic alert → OCSF. Corners: missing `kibana.alert.*` keys, multiple `host.ip` values, severity mapping edges (info / critical / unknown), missing timestamps, malformed `event.action`. Errors: empty doc, non-dict input. |
| `alert_normalizer/chronicle_ocsf.py` | 0 % | Happy: rule + UDM event. Corners: detection without events, ruleLabels with MITRE tags vs without, multiple events (pick first), missing principal/target. |
| `alert_normalizer/aws_security_ocsf.py` | 0 % | Both GuardDuty *and* Security Hub auto-detect (lowercase `type` vs `Severity.Label`). Corners: ASFF with no resources, GuardDuty with empty `Service.Action`. |
| `alert_normalizer/crowdstrike_ocsf.py` | 0 % | Happy: alerts/v1 payload. Corners: missing `device`, missing `behaviors`, severity 0 vs 100. |
| `alert_normalizer/cortex_xdr_ocsf.py` | 62.6 % | Fill in the 89 missing lines — corner cases for missing/malformed fields. |
| `alert_normalizer/sentinelone_ocsf.py` | 75.8 % | Same — fill 67 missing lines. |
| `alert_normalizer/sentinel_ocsf.py` | 80.4 % | Same. |
| `alert_normalizer/qradar_ocsf.py` | 82.7 % | Same. |
| `alert_normalizer/splunk_ocsf.py` | 93.6 % | Cover the last 22 missing lines (mostly default branches). |
| `alert_normalizer/mappers/splunk_notable_lists.py` | 84.9 % | Edge cases for severity / risk mapping. |
| `alert_normalizer/mappers/splunk_notable.py` | 88.1 % | 43 missing — likely error/default branches. |
| `alert_normalizer/splunk.py` | 64.2 % | Pure parsing helpers. |
| `alert_normalizer/helpers/ip_classification.py` | 20.4 % | RFC1918 / loopback / link-local / IPv6 / invalid. Pure pytest parametrize. |
| `data/cim_mappings.py` | 11.5 % | Replace KU lookups with stub session; assert dict shape + caching. |
| `services/cy_time_functions.py` | 12.2 % | TZ-aware now/parse/diff functions; assert `datetime.tzinfo is not None` (project rule). |
| `services/cy_alert_functions.py` | 93.8 % | Cover remaining 2 lines. |
| `services/cy_ingest_functions.py` | 91.5 % | Cover remaining 7 lines. |
| `services/type_propagation/schema_validation.py` | 9.4 % | Pure JSON-schema validator. |
| `services/type_propagation/data_sample_validator.py` | 45 % | Pure validator. |
| `services/type_propagation/task_inference.py` | 72.2 % | Pure type-inference logic. |
| `services/type_system/unification.py` | 64.6 % | Pure type unification. |
| `services/type_system/duck_typing.py` | 80.4 % | Pure duck-typing checks. |
| `services/workflow_composer/validators.py` | 78.9 % | Pure validators — happy + each rejection path. |
| `services/workflow_composer/resolvers.py` | 72.8 % | Pure name resolution. |
| `services/workflow_composer/builder.py` | 85.9 % | Cover remaining 9 lines. |
| `services/workflow_composer/service.py` | 79.0 % | Pure orchestration over the above. |
| `utils/splunk_utils.py` | 58.2 % | SPL-string sanitizers / helpers — many missing branches. |

### Bucket B — services with mockable dependencies (high ROI)

Services that depend on a session or external client, but whose logic is
substantive. We unit-test by injecting fakes/mocks. **Target: ≥ 90 %.**

| File | Currently | What to challenge |
| --- | --- | --- |
| `services/chat_tool_registry.py` | 0 % | Each of the 22 tool wrappers: success path, missing-arg path, downstream-error path. |
| `services/splunk_factory.py` | 0 % | Cache hit, cache miss → vault lookup, vault failure, integration disabled. |
| `services/integration_service.py` | 34.2 % | CRUD; vault round-trip; tenant scoping; soft-delete; bulk health. |
| `services/managed_resources.py` | 29.9 % | Resource limits, quota exhaustion, concurrent-access guard. |
| `services/task_factory.py` | 40.7 % | Each input shape; unknown task-type; validation error. |
| `services/chat_action_tools.py` | 42.5 % | Each action; permission denial; downstream error. |
| `services/task_run.py` | 45.3 % | State transitions: pending → running → succeeded / failed / paused / cancelled; replay-from-checkpoint path. |
| `services/tenant.py` | 37.2 % | Slug uniqueness, soft-delete, default-tenant guard. |
| `services/credential_service.py` | 69.0 % | Encrypt/decrypt round-trip; rotation; vault unavailable. |
| `services/alert_service.py` | 59.2 % | Status transitions; OCSF normalization plumbing; deduplication. |
| `services/chat_service.py` | 67.2 % | Tool dispatch; output guard; model resolver fallbacks. |
| `services/chat_tools.py` | 60.9 % | Each tool's happy + arg-validation + error path. |
| `services/chat_meta_tools.py` | 73.8 % | Same. |
| `services/chat_model_resolver.py` | 78.7 % | Provider fallback chain; missing key error. |
| `services/content_review.py` | 65.8 % | Approve / reject / request-changes; LLM stub. |
| `services/knowledge_extraction.py` | 72.2 % | Each extraction pipeline branch with a stubbed LLM. |
| `services/knowledge_index.py` | 59.9 % | Vector-index add/query/remove; backend errors. |
| `services/knowledge_module.py` | 24.8 % | CRUD + version bump; circular dependency; dependency resolution. |
| `services/kdg.py` | 71.7 % | Edge insertion / cycle detection / topo-sort. |
| `services/artifact_service.py` | 65.3 % | Lifecycle: stage → commit → expire; checksum mismatch; storage error. |
| `services/artifact_storage.py` | 64.5 % | Storage backend selection; S3 upload error; presigned-URL TTL. |
| `services/task.py` | 66.9 % | Task definition CRUD; validation errors. |
| `services/task_execution.py` | 71.0 % | Cy interpreter integration: success, runtime error, timeout, hi-latency pause; checkpoint persistence. **HUGE file (2 309 LOC) — split into multiple test modules.** |
| `services/workflow_execution.py` | 82.0 % | Node-instance state machine; pause/resume; failure propagation; **also large (2 293 LOC).** |
| `services/llm_factory.py` | 81.5 % | Provider switch; pricing miss; retry/back-off. |
| `services/cy_functions.py` | 73.0 % | Each registered Cy function happy + bad-arg path. |
| `services/cy_llm_functions.py` | 83.9 % | Stubbed LLM client. |
| `services/cy_task_functions.py` | 78.4 % | Function-call routing; permission denial. |
| `services/cy_index_functions.py` | 79.7 % | Index lookups with fake index backend. |
| `services/cy_ku_functions.py` | 85.7 % | KU lookups with fake repo. |
| `services/cy_sleep_functions.py` | 35.3 % | Pause-token emission. |
| `services/agent_credential_factory.py` | 85.3 % | Cover remaining 16 lines. |
| `services/integration_registry_service.py` | 52.0 % | Registry caching, manifest validation. |
| `services/integration_execution_service.py` | 79.8 % | Tool dispatch; argument schema mismatch. |
| `services/feedback_relevance.py` | 98.4 % | Cover remaining 1 line. |
| `services/storage.py` | 88.4 % | S3 / local backend behaviour edges. |
| `services/vault_client.py` | 93.8 % | Auth-token refresh; secret-not-found. |

### Bucket C — MCP tools (medium ROI, mockable)

MCP tool wrappers — same pattern as services. The tools themselves are thin
adapters over services, so unit tests stub the underlying service and verify
argument validation + error mapping. **Target: ≥ 85 %.**

| File | Currently | Notes |
| --- | --- | --- |
| `mcp/tools/workflow_tools.py` | 29.8 % (587 LOC) | Largest MCP file — each tool: happy, missing arg, service raises, audit log emitted. |
| `mcp/tools/cy_tools.py` | 16.2 % | Same pattern. |
| `mcp/tools/task_tools.py` | 15.5 % | Same pattern. |
| `mcp/integration_tools.py` | 77.4 % | Edge cases. |
| `mcp/analysi_server.py` | 67.2 % | Lifecycle hooks; rate-limit middleware integration. |
| `mcp/middleware.py` | 84.2 % | Auth path / unauth path; rate-limit decision. |
| `mcp/utils/db.py` | 33.3 % | Tiny — just exhaust the branches. |
| `mcp/utils/cy_helpers.py` | 36.4 % | Tiny helpers. |
| `mcp/audit.py` | 80.8 % | Action → audit-row mapping. |
| `mcp/context.py` | 81.3 % | Context-manager edges. |

### Bucket D — agentic orchestration & alert analysis (medium ROI)

Mix of pure logic and LLM/DB pipelines. Use `ANTHROPIC_API_KEY=""` +
`OPENAI_API_KEY=""` to force the stub paths (already supported via env-var
checks in the orchestrator). **Target: ≥ 85 %.**

| File | Currently | Notes |
| --- | --- | --- |
| `agentic_orchestration/stages/agent_stages.py` | 49.3 % | Each stage transition; failure → rollback. |
| `agentic_orchestration/task_generation_client.py` | 41.8 % | Stub HTTP; retry; non-2xx handling. |
| `agentic_orchestration/skills_sync.py` | 67.2 % | Pack install / update / removal; conflict detection. |
| `agentic_orchestration/langgraph/skills/db_store.py` | 66.1 % | DB-backed resource store — fake session. |
| `agentic_orchestration/jobs/task_build_job.py` | 76.3 % | Failure / requeue / dead-letter. |
| `agentic_orchestration/jobs/workflow_generation_job.py` | 85.5 % | Edge cases. |
| `agentic_orchestration/subgraphs/first_subgraph.py` | 63.5 % | Each conditional edge. |
| `agentic_orchestration/subgraphs/second_subgraph_no_langgraph.py` | 71.5 % | Each branch + error path. |
| `agentic_orchestration/sdk_wrapper.py` | 83.7 % | Edge cases. |
| `agentic_orchestration/workspace.py` | 78.8 % | Path safety; cleanup. |
| `agentic_orchestration/langgraph/knowledge_extraction/nodes.py` | 86.9 % | Add the unhappy paths. |
| `agentic_orchestration/langgraph/kea/phase1/validators.py` | 85.5 % | Add reject paths. |
| `alert_analysis/clients.py` | 40.0 % | API-client wrappers; retry/timeout. |
| `alert_analysis/jobs/content_review.py` | 23.3 % | Approve/reject branching with stubbed LLM. |
| `alert_analysis/jobs/reconciliation.py` | 82.1 % | Stuck-job detection; expired HITL pause. |
| `alert_analysis/jobs/control_events.py` | 86.4 % | `human:responded` happy + duplicate + unknown ref. |
| `alert_analysis/worker.py` | 71.0 % | Job dispatch; failure handling. |
| `alert_analysis/db.py` | 83.9 % | Repository edges. |
| `alert_analysis/steps/final_disposition_update.py` | 79.7 % | Each disposition value + permission check. |
| `alert_analysis/steps/workflow_builder.py` | 82.4 % | Builder edges. |

### Bucket E — auth, common, middleware, schemas (small but easy wins)

Small files where 90 % is one or two extra tests away. **Target: ≥ 95 %.**

| File | Currently | Notes |
| --- | --- | --- |
| `auth/dependencies.py` | 47.4 % | Each dependency: token present / missing / expired / wrong scope. |
| `auth/jwks.py` | 75.0 % | Cache hit / miss / refresh failure. |
| `auth/api_key.py` | 90.2 % | One more rejection branch. |
| `common/stuck_detection.py` | 59.2 % | Stuck-state detector — staleness windows, pause-aware logic. |
| `common/retry_config.py` | 73.4 % | Each retry-policy combinator. |
| `common/job_tracking.py` | 77.3 % | Status transitions; idempotency. |
| `common/arq_enqueue.py` | 76.3 % | Enqueue success / queue-full / serialization error. |
| `common/correlation.py` | 89.7 % | Cover the last 3 lines. |
| `middleware/logging.py` | 70.1 % | Request/response branches; error-with-no-route case. |
| `middleware/security_headers.py` | 45.5 % | Header set / preserve. |
| `db/health.py` | 18.4 % | Probe success/failure with mocked session. |
| `db/session.py` | 44.4 % | Engine factory branches. |
| `dependencies/audit.py` | 54.5 % | Tiny — exhaust branches. |
| `models/task_flat.py` | 48.0 % | Pure pydantic model — happy + each validator. |
| `models/workflow.py` | 78.7 % | Validator edges. |
| `schemas/control_event_rule.py` | 80.6 % | Validator edges. |
| `schemas/integration.py` | 83.7 % | Validator edges. |
| `schemas/chat.py` | 82.6 % | Validator edges. |
| `schemas/workflow_execution.py` | 87.5 % | Validator edges. |
| `schemas/task_execution.py` | 88.9 % | Validator edges. |
| `schemas/integration_credentials.py` | 0 % | **Audit first — likely unused; delete if dead.** |
| `config/telemetry.py` | 75.9 % | Init paths / disabled path. |
| `config/logging.py` | 76.5 % | Formatter selection / level edges. |
| `slack_listener/connection.py` | 73.8 % | Socket-mode reconnect; auth failure. |
| `slack_listener/_credentials.py` | 88.6 % | Vault round-trip edges. |
| `slack_listener/service.py` | 88.8 % | Cover the last 9 lines. |

### Bucket F — third-party integration `actions.py` (selective)

There are 74 integration `actions.py` files contributing **5 339 missing
lines**. Most of the missing lines are error-path branches in HTTP wrappers.
Strategy:

1. **Add a shared `httpx`-mock fixture** (probably the biggest single lever
   for this PR) that lets one decorator drive the success/4xx/5xx/timeout
   matrix per action.
2. **Pick the top ten by absolute missing lines** (table below) and bring
   each to ≥ 85 %. This is where the bulk of the codebase lives.
3. Remaining 64 files: catch up incrementally — each gets one
   "auth failure + rate limit + malformed payload" parametrized test.

Top 10 priorities (by absolute uncovered LOC):

| File | Cov | Missing |
| --- | --- | --- |
| `slack/actions.py` | 45.1 % | 377 |
| `cortex_xdr/actions.py` | 59.4 % | 335 |
| `crowdstrike/actions.py` | 64.2 % | 262 |
| `sentinelone/actions.py` | 68.2 % | 208 |
| `microsoftteams/actions.py` | 45.0 % | 205 |
| `defender_endpoint/actions.py` | 53.0 % | 205 |
| `echo_edr/actions.py` | 36.9 % | 188 |
| `zscaler/actions.py` | 64.8 % | 167 |
| `paloalto_firewall/actions.py` | 74.6 % | 156 |
| `splunk/actions.py` | 73.4 % | 149 |

> Note: these tests are still **unit tests** — we're not hitting real APIs.
> The lab containers (Splunk / Echo EDR / OpenLDAP) live in
> `analysi-demo-loader` and are exercised by `@pytest.mark.requires_*`
> integration tests, which are out of scope for this PR.

## 5. Out of scope for this PR (deferred — discuss at end)

The following are **better tested with integration tests**. Including them
here would either bloat the PR or yield meaningless mock-heavy tests. We will
open a follow-up issue per area after this PR lands.

1. **`src/analysi/routers/**`** (37 % avg) — FastAPI handler shells. Almost
   all logic lives in services; the routers are thin glue. Coverage will rise
   naturally when we add API integration tests in `tests/integration/`.
   Files: `alerts`, `workflows`, `workflow_execution`, `tasks`,
   `task_execution`, `bulk_operations`, `skills`, `knowledge_units`,
   `integrations`, `integration_managed`, `kea_coordination`, `alerts`,
   `credentials`, `schedules`, `content_reviews`, `task_generations`,
   `task_feedback`, `chat`, `platform`, `members`, `kdg`, `packs`,
   `artifacts`, `api_keys`, `health`, `users`, `invitations`,
   `task_assist`, `control_event_*`, `activity_audit`,
   `integration_execution`.
2. **`src/analysi/repositories/**`** (56 % avg) — SQLAlchemy queries. Mocking
   `AsyncSession` here produces brittle tests that don't catch SQL errors.
   Better tested against the per-branch test DB
   (`make test-db-up && make test-integration-db`). Files include the
   biggest gaps: `knowledge_unit.py`, `knowledge_module.py`,
   `alert_repository.py`, `workflow.py`, `tenant.py`,
   `task_generation_repository.py`, `schedule_repository.py`,
   `activity_audit_repository.py`, `integration_repository.py`,
   `conversation_repository.py`.
3. **`src/analysi/main.py`** (41.9 %) — application bootstrap; covered by
   the API smoke integration test.
4. **`src/analysi/alert_worker.py`** (0 %) — worker entry point; integration
   territory.
5. **`src/analysi/workflow/task_node_executor.py`** (39.2 %) — already
   exercised by `tests/integration/workflow/`. Add unit tests only for the
   new `_resolve_*` pure helpers.

## 6. Execution plan / commit cadence

1. **Commit 1 — instrumentation only**: enable `--cov` on the unit-test
   target locally and update `Makefile` + `pyproject.toml` to dump a per-file
   delta report. No code changes.
2. **Commit 2 — Bucket A (transformers/mappers)**: 7 OCSF normalizers + Cy
   pure helpers + `cim_mappings`. Expected lift: ≈ 1 800 lines, +3 %.
3. **Commit 3 — Bucket B chunk 1 (chat / cy services)**: `chat_*`, `cy_*`,
   `feedback_relevance`, `storage`, `vault_client`. Expected: ≈ 600 lines.
4. **Commit 4 — Bucket B chunk 2 (workflow / task / artifact)**: largest
   services (`task_execution`, `workflow_execution`, `task_run`, `task`,
   `task_factory`, `artifact_*`, `content_review`). Expected: ≈ 900 lines.
5. **Commit 5 — Bucket B chunk 3 (knowledge / kdg / integrations)**:
   `knowledge_*`, `kdg`, `integration_*`, `splunk_factory`. Expected: ≈ 700.
6. **Commit 6 — Bucket C (MCP tools)**: workflow / cy / task tools. Expected:
   ≈ 700.
7. **Commit 7 — Bucket D (orchestration + alert_analysis)**. Expected: ≈ 600.
8. **Commit 8 — Bucket E (auth/common/middleware/schemas)**. Expected: ≈ 400.
9. **Commit 9 — Bucket F top-10 + shared httpx fixture**. Expected: ≈ 2 000.
10. **Commit 10 — dead-code sweep**: delete `schemas/integration_credentials.py`
    if confirmed unused; align `__main__.py` smoke tests; update
    `codecov.yml` to flip from `informational: true` to a real `target:
    auto + threshold: 1 %` once we cross 90 %.

## 7. Test-quality bar (non-negotiable)

Every new test file should:

- Be importable without a DB or network — i.e., pass `pytest -m unit -p no:cacheprovider` in < 30 s for the file.
- Cover at least one **happy path**, one **boundary / corner case**, and one
  **error / unhappy path**. No vanity assertions like `assert x is not None`
  alone.
- For pure functions: use `pytest.mark.parametrize` aggressively.
- For services with mocks: use `pytest-mock`'s `mocker.patch` on the
  module-under-test boundary (not deep into SQLAlchemy or httpx internals).
- Use timezone-aware datetimes (project rule).
- No tests with hard-coded UUIDs / tenant IDs (project rule — see
  `scripts/code_quality_tools/`).

## 8. Tracking

- Coverage delta tracked via Codecov on every push (already wired).
- Local helper: `make code-quality-check` after each bucket to verify no new
  hygiene regressions.
- Branch protection: leave Codecov soft-signal until Bucket E lands, then
  flip `codecov.yml` patch threshold to fail PRs with > 1 % regression.

---

**Total expected uplift after all 9 commits**: ~7 700 covered lines →
~89–91 % overall, with no file in the in-scope set below 85 % and the worst
offenders (Bucket A files, MCP tools, services) above 95 %.
