---
name: ad-ldap-integration
description: >-
  Active Directory LDAP user attribute lookups and identity context queries during SOC alert triage. Use when investigating user accounts, group memberships, authentication anomalies, lockouts, privileged access, or correlating alerts with AD data via Analysi.
version: 0.1.0
---

# AD LDAP Investigation Guide

The `ad_ldap` integration provides identity context during alert triage by querying Active Directory via LDAP. Three actions are available: a connectivity health check, a principal-based attribute lookup, and a raw LDAP filter query.

## Reference Loading

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any `app::ad_ldap::*` action or validating response shape | Parameters, Cy return behavior, response schemas, filter cookbook, filter-value safety, error handling, known limitations |
| `references/investigation-patterns.md` | Building identity investigation workflows or interpreting AD results | Decision matrix, field semantics, triage templates, corroboration rules, escalation/de-escalation signals |

## Quick Decision Path

- **Connection issues?** Run `health_check` to distinguish "LDAP path broken" from "user/group does not exist."
- **Know the username/email?** Use `get_attributes` for a quick first pass with semicolon-separated principals.
- **Need exact AD lookup or filtered search?** Use `run_query` — prefer this for any disposition-affecting decision (`sAMAccountName`, group enumeration, auth-state attributes, disabled accounts).
- **Investigating auth anomalies?** Combine LDAP identity context with SIEM auth logs — see `investigation-patterns.md § Auth Anomaly Triage`.
- **Need transitive (nested) group membership?** Use `LDAP_MATCHING_RULE_IN_CHAIN` via `run_query` — see `investigation-patterns.md § Group Membership and Privilege Context`.

## Compact Patterns

- **User baseline**: resolve one exact AD identity via `run_query`, confirm object shape, then decide whether the alert needs auth-state, group, or service-account follow-up.
- **Auth anomaly**: collect `badPwdCount`, `lastLogon`, `lastLogonTimestamp`, `lockoutTime`, `pwdLastSet`, and `userAccountControl`; treat `lastLogonTimestamp` as coarse recency, not exact timing.
- **Privilege context**: check nested membership for the high-value group first, then `primaryGroupID` only if the privilege decision still matters.

## Guardrails

- This integration is read-only — no password resets, account enable/disable, or group modifications.
- `get_attributes` is not a reliable exact-match lookup for `sAMAccountName`, DN, or UPN — switch to `run_query` before making a disposition call.
- `lastLogon` and `badPwdCount` are controller-local; `lastLogonTimestamp` is replicated but intentionally delayed. Use SIEM/EDR for exact chronology.
- `memberOf` alone is not a complete entitlement decision — it omits primary group and nested memberships.
- If the alert identity is free-form or contains filter metacharacters, do not interpolate directly — follow `actions-reference.md § Filter-Value Safety` or skip LDAP enrichment.
- LDAP is identity state, not event truth — always corroborate with SIEM/EDR for event confirmation.
