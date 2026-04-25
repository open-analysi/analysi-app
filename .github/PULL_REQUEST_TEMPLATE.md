<!--
Thanks for contributing to Analysi! Please fill out the sections below.
For larger changes, consider opening a Discussion or Issue first to align
on direction before investing in the implementation.
-->

## Summary

<!-- What does this PR change, and why? Link to any related issue. -->

Closes #

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (API, schema, config, or behavior)
- [ ] Documentation only
- [ ] Refactor / internal cleanup
- [ ] Build / CI / tooling

## How this was tested

<!--
Describe the tests you added or ran. Reviewers want to know what behavior
is now verified, not just that "tests pass". Include commands where useful.
-->

- [ ] `poetry run lint` passes
- [ ] `poetry run typecheck` passes
- [ ] Unit tests added or updated (`make test-unit`)
- [ ] Integration tests added or updated (`make test-integration-db` / `test-integration-full`)
- [ ] Manually verified in `make k8s-up` or `make up` (describe below)

## Database / migration impact

<!-- Delete this section if not applicable. -->

- [ ] Adds a new Flyway migration
- [ ] Adds a new partitioned table (registered with pg_partman in baseline)
- [ ] No schema changes

## Backward compatibility

<!--
Note any breaking changes to: REST/MCP APIs, Cy script semantics, env var
names, Helm values, packaged content (skills/tasks/workflows), or DB schema.
If breaking, describe the upgrade path.
-->

## Checklist

- [ ] Every commit is signed off (`git commit -s`) per [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] PR title follows the project's commit style (short, imperative)
- [ ] No secrets, credentials, or production data added to the repo
- [ ] Public-facing changes are documented (README / `docs/` / CLI help)
- [ ] If REST or MCP APIs changed, the API server has been restarted locally and verified
- [ ] If a new MCP tool or REST endpoint was added, audit-trail logging was considered
