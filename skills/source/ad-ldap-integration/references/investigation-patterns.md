# LDAP Investigation Patterns

<!-- LOW_CONFIDENCE: Timestamp values such as `lastLogon`, `lastLogonTimestamp`, `lockoutTime`, and `pwdLastSet` are AD FILETIME-style large integers by schema, but live JSON serialization may vary by directory and library behavior. Inspect one real response before writing strict timestamp transforms in a production task. -->

Load `references/actions-reference.md` first for exact parameters, action quirks, and filter-value safety rules. Use this file when you need to decide what to ask LDAP next and how to interpret the returned identity context during triage.

## Table of Contents

- [Decision Matrix](#decision-matrix)
- [Pattern 1: User Baseline / Identity Enrichment](#pattern-1-user-baseline--identity-enrichment)
- [Pattern 2: Auth Anomaly / Brute Force Triage](#pattern-2-auth-anomaly--brute-force-triage)
- [Pattern 3: Group Membership and Privilege Context](#pattern-3-group-membership-and-privilege-context)
- [Pattern 4: Service Account and Kerberoast Context](#pattern-4-service-account-and-kerberoast-context)
- [Pattern 5: Lateral Movement Correlation](#pattern-5-lateral-movement-correlation)
- [Pattern 6: Multi-Source Corroboration](#pattern-6-multi-source-corroboration)
- [Corroboration Rules](#corroboration-rules)
- [Batch and Failure Guardrails](#batch-and-failure-guardrails)

All templates assume the lookup value already passed `actions-reference.md § Filter-Value Safety`. If you only have raw alert text, normalize it into a dedicated lookup key first.

---

## Decision Matrix

| Investigation question | First LDAP move | Pull these fields | Interpret with care | Corroborate with |
|---|---|---|---|---|
| Is this a real domain identity? | Exact `run_query` on `sAMAccountName`, UPN, or `mail` | `distinguishedName`, `displayName`, `mail`, `sAMAccountName`, `userPrincipalName`, `userAccountControl` | No match often means local, cloud-only, malformed, or stale identity — not necessarily malicious | SIEM identity normalization, IdP logs, endpoint username |
| Is this password spray, brute force, or lockout noise? | Exact `run_query` on the user | `badPwdCount`, `lastLogon`, `lastLogonTimestamp`, `lockoutTime`, `pwdLastSet`, `userAccountControl` | `badPwdCount` and `lastLogon` are DC-local; `lastLogonTimestamp` is delayed for coarse recency only | Sign-in failures, source IP spread, EDR logons |
| Is the user privileged? | Nested-membership `run_query` against the high-value group DN | `memberOf`, `primaryGroupID`, `distinguishedName`, `userAccountControl` | `memberOf` misses primary-group-only membership | Group-change logs, admin logons, privileged host access |
| Is this a service account or Kerberoast target? | `run_query` for SPN-bearing user objects | `servicePrincipalName`, `pwdLastSet`, `memberOf`, `userAccountControl` | Old passwords and privileged groups matter more than SPN presence alone | TGS request telemetry, host or service ownership, EDR activity |

---

## Pattern 1: User Baseline / Identity Enrichment

**When**: Any alert with a username, email, or user DN that needs identity context before disposition.

**Goal**: Determine who the user is, what groups they belong to, and whether the account profile matches the alert behavior.

**What to learn first**:
- Did LDAP resolve exactly one object?
- Is the returned object a user-shaped AD identity or something else?
- Does the account look enabled, normal, and consistent with the alert's claimed actor?

### Cy Task Template

```cy
principal = input.normalized_principal ??
            input.user_upn ??
            input.user_email ??
            input.samaccountname ??
            null

if (principal == null) {
    # Try extracting from alert fields
    principal = alert.get("user_info", {}).get("username", "")
    if (principal == "") {
        principal = alert.get("source", {}).get("user", "")
    }
    if (principal == "") {
        log("No normalized AD principal available for baseline lookup")
        return input
    }
}

identity_context = {
    "lookup_key": str(principal),
    "directory_match": false,
    "total_objects": 0,
    "entries": [],
    "error": null
}

try {
    baseline = app::ad_ldap::run_query(
        filter="""(&(objectCategory=person)(objectClass=user)(|(sAMAccountName=${principal})(userPrincipalName=${principal})(mail=${principal})))""",
        attributes="distinguishedName;displayName;mail;sAMAccountName;userPrincipalName;memberOf;userAccountControl;whenCreated;title",
        search_base="DC=corp,DC=example,DC=com"
    )

    identity_context["directory_match"] = (baseline.total_objects ?? 0) > 0
    identity_context["total_objects"] = baseline.total_objects ?? 0
    identity_context["entries"] = baseline.data.entries ?? []

    if (identity_context["directory_match"]) {
        entry = baseline.data.entries[0]
        groups = entry.attributes.memberof ?? []

        # Flag privileged group membership
        privileged_groups = []
        for g in groups {
            g_lower = g.lower()
            if "domain admins" in g_lower or "enterprise admins" in g_lower or "schema admins" in g_lower or "account operators" in g_lower {
                privileged_groups = privileged_groups + [g]
            }
        }

        identity_context["is_privileged"] = len(privileged_groups) > 0
        identity_context["privileged_groups"] = privileged_groups
    }
} catch (e) {
    log("AD baseline lookup failed: ${e}")
    identity_context["error"] = str(e)
}

return enrich_alert(input, identity_context, "ad_ldap_identity")
```

### Fast Triage Readout

- `0` matches after an exact `sAMAccountName`/UPN/`mail` OR-filter usually means local account, cloud-only identity, stale alias, or parser issue.
- `>1` matches usually means shared mailbox or address ambiguity, or a too-loose filter. Disambiguate with DN or UPN before making a disposition decision.
- A disabled account in LDAP does not, by itself, explain a successful-auth alert. Cached tokens, stale sessions, and service usage can still exist outside LDAP's static state.

### Decision Points After Enrichment

- User not in directory → likely external actor or deleted account → escalate if alert is auth-related
- User is in a privileged group → raise severity — privileged account compromise has higher blast radius
- User title/department doesn't match the activity (e.g., HR user triggering SQL injection) → possible compromised account
- If the alert is about repeated failures → load Pattern 2 (auth-state) next
- If the alert is about admin behavior or lateral movement → load Pattern 3 (privilege context) next
- If the identity resolves to an SPN-bearing user → load Pattern 4 (service-account) next

---

## Pattern 2: Auth Anomaly / Brute Force Triage

**When**: Alert indicates brute force, password spray, impossible travel, lockout, or unusual auth pattern.

**Goal**: Correlate LDAP identity and auth-state context with SIEM auth event logs to determine if the attack succeeded and assess impact.

### Field Semantics

<!-- EVIDENCE: public API docs — Microsoft AD schema documentation -->

| Field | What it helps answer | What can mislead you |
|---|---|---|
| `badPwdCount` | Has this domain controller seen recent bad-password attempts? | Not replicated; maintained separately on each DC. Behind a VIP, repeated reads may vary. |
| `lastLogon` | What is the freshest logon value from the specific DC that answered? | Not replicated. For domain-wide "true last logon," every DC must be queried. |
| `lastLogonTimestamp` | Has the account been used recently (coarse recency)? | Replicated, but updates only when value is older than `current_time - msDS-LogonTimeSyncInterval`. Can lag 9–14 days. Do not use for exact chronology. |
| `lockoutTime` | Did AD record a lockout? | `0` means not currently locked. Nonzero still needs SIEM corroboration. |
| `pwdLastSet` | Did the password just change (remediation or admin action)? | FILETIME-style large integer by schema. Convert before human review. |
| `userAccountControl` | Is the account disabled or otherwise flagged? | Use bit tests, not string comparisons. `ACCOUNTDISABLE` is `0x0002`. |

### Decision Tree

```
Alert: auth anomaly for username X
  │
  ├─ Step 1: LDAP lookup → Does user X exist in AD?
  │   ├─ NO → External/deleted account. Check SIEM for failed auth count.
  │   │        If > 50 failures → automated attack on invalid account → low priority
  │   │        If < 10 failures → targeted guessing → monitor
  │   └─ YES → Continue to Step 2
  │
  ├─ Step 2: Check group membership → Is user privileged?
  │   ├─ YES → Escalate immediately regardless of success/failure
  │   └─ NO → Continue to Step 3
  │
  └─ Step 3: SIEM auth log correlation → Did any attempt succeed?
      ├─ YES (successful login after failures) → Likely TP — compromised account
      └─ NO (all failures) → Attack blocked → low priority if short burst, monitor if ongoing
```

### Interpretation Shortcuts

- Rising `badPwdCount` with many source IPs in SIEM supports spray or brute force more than user error, but the count is controller-local.
- `lockoutTime != 0` plus many failures and no recent success usually supports active password attack.
- Recent `pwdLastSet` after alert onset often means remediation has already begun; downgrade urgency only if sign-in data also calms down.
- A more recent `lastLogon` than `lastLogonTimestamp` is expected and not suspicious. The first is controller-local; the second is replicated but delayed.

### Cy Task Template: LDAP Auth-State Enrichment

```cy
principal = input.normalized_principal ??
            input.user_upn ??
            input.user_email ??
            input.samaccountname ??
            null

if (principal == null) {
    log("No normalized AD principal available for auth-state lookup")
    return input
}

auth_context = {
    "lookup_key": str(principal),
    "directory_match": false,
    "total_objects": 0,
    "entries": [],
    "error": null
}

try {
    auth_state = app::ad_ldap::run_query(
        filter="""(&(objectCategory=person)(objectClass=user)(|(sAMAccountName=${principal})(userPrincipalName=${principal})(mail=${principal})))""",
        attributes="sAMAccountName;userPrincipalName;badPwdCount;lastLogon;lastLogonTimestamp;lockoutTime;pwdLastSet;userAccountControl;memberOf",
        search_base="DC=corp,DC=example,DC=com"
    )

    auth_context["directory_match"] = (auth_state.total_objects ?? 0) > 0
    auth_context["total_objects"] = auth_state.total_objects ?? 0
    auth_context["entries"] = auth_state.data.entries ?? []
} catch (e) {
    log("AD auth-state lookup failed: ${e}")
    auth_context["error"] = str(e)
}

return enrich_alert(input, auth_context, "ad_ldap_auth_state")
```

### Cy Task Template: LDAP + SIEM Auth Correlation

```cy
try {
    username = alert.get("user_info", {}).get("username", "")
    source_ip = alert.get("source", {}).get("ip", "")

    # Step 1: LDAP identity + auth-state lookup
    user_exists = false
    is_privileged = false

    try {
        ldap_result = app::ad_ldap::run_query(
            filter="(&(objectCategory=person)(objectClass=user)(sAMAccountName=" + username + "))",
            attributes="cn;mail;memberOf;userAccountControl;badPwdCount;lockoutTime",
            search_base="DC=corp,DC=example,DC=com"
        )

        if ldap_result.total_objects > 0 {
            user_exists = true
            groups = ldap_result.data.entries[0].attributes.memberof ?? []
            for g in groups {
                if "admin" in g.lower() {
                    is_privileged = true
                }
            }
        }
    } catch (e) {
        log("LDAP lookup failed: ${e}")
    }

    # Step 2: SIEM auth event search (last 24h)
    splunk_query = "search index=* sourcetype=*auth* OR sourcetype=*security* \"" + username + "\" | stats count by action, src_ip, result | head 50"

    splunk_result = app::splunk::search(
        query=splunk_query,
        earliest_time="-24h",
        latest_time="now"
    )

    # Step 3: Synthesize findings
    assessment = llm_run(
        "Analyze brute force alert for user '" + username + "'.\n" +
        "User exists in AD: " + str(user_exists) + "\n" +
        "Privileged account: " + str(is_privileged) + "\n" +
        "LDAP auth-state: " + str(ldap_result) + "\n" +
        "SIEM auth events: " + str(splunk_result) + "\n" +
        "Determine: 1) Was the attack successful? 2) TP or FP? 3) Recommended action."
    )

    emit("brute_force_analysis", {
        "username": username,
        "user_exists": user_exists,
        "is_privileged": is_privileged,
        "assessment": assessment
    })

} catch (e) {
    emit("brute_force_analysis", {"status": "action_failed", "error": str(e)})
}
```

### Disposition Hints

- Escalate faster when LDAP says the account exists, is enabled, and SIEM shows geographically or topologically inconsistent failures or successes.
- De-escalate cautiously when the account is disabled, no recent SIEM success exists, and activity looks like stale credential noise or an old service dependency.
- Do not close as false positive from LDAP alone. LDAP gives identity state, not proof that the authentication event did or did not occur.

---

## Pattern 3: Group Membership and Privilege Context

**When**: Alert involves a known or suspected privileged account, admin logon, lateral movement, suspicious group change, or you need to enumerate privileged users for scope assessment.

**Goal**: Determine effective privilege through nested group membership and cross-reference with alert activity.

### What Matters Before a Privilege Decision

<!-- EVIDENCE: public API docs — Microsoft AD schema: memberOf, primaryGroupToken -->

- `memberOf` is useful, but it omits the user's primary group.
- For inherited privilege, use the LDAP matching rule in chain (`1.2.840.113556.1.4.1941`) instead of checking only direct `memberOf`.
- If nested lookup is empty, resolve the group's `primaryGroupToken` and compare it with the user's `primaryGroupID` before ruling membership out.

### Transitive Group Membership (AD Only)

OID `1.2.840.113556.1.4.1941` (`LDAP_MATCHING_RULE_IN_CHAIN`) tells AD to walk the group membership chain recursively. If User A is in Group B, and Group B is in Domain Admins, this filter matches User A — a plain `memberOf` filter would not. This OID is AD-specific and will error on OpenLDAP.

**When to use transitive vs. direct:**
- **Direct** (`memberOf=...`): Fast, works on both AD and OpenLDAP, sufficient when groups are flat.
- **Transitive** (`memberOf:1.2.840.113556.1.4.1941:=...`): Needed when investigating privilege escalation through nested groups, or when you need a complete picture of effective admin access.

### Cy Task Template: Nested Privilege Check with primaryGroupID Fallback

```cy
principal = input.normalized_principal ??
            input.user_upn ??
            input.samaccountname ??
            null

high_value_group_dn = input.high_value_group_dn ??
                      "CN=Domain Admins,CN=Users,DC=corp,DC=example,DC=com"

if (principal == null) {
    log("No normalized AD principal available for privilege lookup")
    return input
}

privilege_context = {
    "lookup_key": str(principal),
    "group_dn": str(high_value_group_dn),
    "nested_match_count": 0,
    "nested_entries": [],
    "primary_group_match_count": 0,
    "primary_group_entries": [],
    "error": null
}

try {
    # Step 1: Check transitive membership
    nested = app::ad_ldap::run_query(
        filter="""(&(objectCategory=person)(objectClass=user)(|(sAMAccountName=${principal})(userPrincipalName=${principal})(mail=${principal}))(memberOf:1.2.840.113556.1.4.1941:=${high_value_group_dn}))""",
        attributes="distinguishedName;sAMAccountName;userPrincipalName;memberOf;primaryGroupID;userAccountControl",
        search_base="DC=corp,DC=example,DC=com"
    )

    privilege_context["nested_match_count"] = nested.total_objects ?? 0
    privilege_context["nested_entries"] = nested.data.entries ?? []

    # Step 2: If nested lookup found nothing, check primaryGroupID
    if ((nested.total_objects ?? 0) == 0) {
        group_token = app::ad_ldap::run_query(
            filter="""(&(objectClass=group)(distinguishedName=${high_value_group_dn}))""",
            attributes="cn;primaryGroupToken",
            search_base="DC=corp,DC=example,DC=com"
        )

        if ((group_token.total_objects ?? 0) > 0) {
            rid = group_token.data.entries[0].attributes.primarygrouptoken ?? null

            if (rid != null) {
                primary_group = app::ad_ldap::run_query(
                    filter="""(&(objectCategory=person)(objectClass=user)(|(sAMAccountName=${principal})(userPrincipalName=${principal})(mail=${principal}))(primaryGroupID=${rid}))""",
                    attributes="distinguishedName;sAMAccountName;userPrincipalName;primaryGroupID;userAccountControl",
                    search_base="DC=corp,DC=example,DC=com"
                )

                privilege_context["primary_group_match_count"] = primary_group.total_objects ?? 0
                privilege_context["primary_group_entries"] = primary_group.data.entries ?? []
            }
        }
    }
} catch (e) {
    log("AD privilege lookup failed: ${e}")
    privilege_context["error"] = str(e)
}

return enrich_alert(input, privilege_context, "ad_ldap_privilege_context")
```

### Enumerating Privileged Group Members

To enumerate all direct members of a privileged group (adapt the DN to your environment):

```cy
try {
    result = app::ad_ldap::run_query(
        filter="(&(objectCategory=person)(objectClass=user)(memberOf=CN=Domain Admins,CN=Users,DC=corp,DC=com))",
        attributes="cn;mail;samaccountname"
    )

    admin_accounts = []
    for entry in result.data.entries {
        admin_accounts = admin_accounts + [{"dn": entry.dn, "cn": entry.attributes.cn, "mail": entry.attributes.mail}]
    }
    emit("privileged_accounts", {"group": "Domain Admins", "count": result.total_objects, "members": admin_accounts})
} catch (e) {
    emit("privileged_accounts", {"status": "error", "error": str(e)})
}
```

Common privileged groups: `Domain Admins`, `Enterprise Admins`, `Schema Admins`, `Account Operators`. If the exact DN is unknown, use a substring match: `(&(objectClass=group)(cn=*Admin*))`.

### Interpretation Shortcuts

- Nested membership hit on a high-value group should materially increase severity for auth, lateral movement, and admin-action alerts.
- Empty nested membership plus positive `primaryGroupID` match is rare but important — do not miss it.
- If LDAP says privileged but EDR shows only low-value workstation activity, prioritize credential-theft or token-reuse questions over "admin intentionally did this."

---

## Pattern 4: Service Account and Kerberoast Context

**When**: Alert references a service logon, unusual Kerberos ticketing, lateral movement through services, or an account that might own SPNs.

**Goal**: Determine if the identity has SPNs, whether it is enabled and active, and whether it has privileged group membership or a very old password.

### Cy Task Template

```cy
principal = input.normalized_principal ??
            input.user_upn ??
            input.user_email ??
            input.samaccountname ??
            null

if (principal == null) {
    log("No normalized AD principal available for service-account lookup")
    return input
}

service_context = {
    "lookup_key": str(principal),
    "directory_match": false,
    "total_objects": 0,
    "entries": [],
    "error": null
}

try {
    service_state = app::ad_ldap::run_query(
        filter="""(&(objectCategory=person)(objectClass=user)(servicePrincipalName=*)(|(sAMAccountName=${principal})(userPrincipalName=${principal})(mail=${principal})))""",
        attributes="sAMAccountName;userPrincipalName;servicePrincipalName;pwdLastSet;memberOf;userAccountControl",
        search_base="DC=corp,DC=example,DC=com"
    )

    service_context["directory_match"] = (service_state.total_objects ?? 0) > 0
    service_context["total_objects"] = service_state.total_objects ?? 0
    service_context["entries"] = service_state.data.entries ?? []
} catch (e) {
    log("AD service-account lookup failed: ${e}")
    service_context["error"] = str(e)
}

return enrich_alert(input, service_context, "ad_ldap_service_context")
```

### Enumerating Service Accounts

```cy
try {
    # Option A: Search by naming convention
    result = app::ad_ldap::run_query(
        filter="(|(uid=svc_*)(uid=sa_*)(cn=svc_*)(cn=sa_*))",
        attributes="cn;uid;mail;objectclass;memberof"
    )

    # Option B: Search by OU (if service accounts are in a dedicated OU)
    # result = app::ad_ldap::run_query(
    #     filter="(objectClass=person)",
    #     attributes="cn;uid;mail;memberof",
    #     search_base="ou=ServiceAccounts,dc=corp,dc=com"
    # )

    svc_accounts = []
    for entry in result.data.entries {
        svc_accounts = svc_accounts + [{"dn": entry.dn, "cn": entry.attributes.cn, "uid": entry.attributes.uid, "groups": entry.attributes.memberof}]
    }
    emit("service_accounts", {"count": result.total_objects, "accounts": svc_accounts})
} catch (e) {
    emit("service_accounts", {"status": "error", "error": str(e)})
}
```

### Interpretation Shortcuts

- SPN presence alone does not make the alert malicious; combine it with ticketing volume, privileged group exposure, and password age.
- Old `pwdLastSet` plus SPNs plus privileged memberships is a stronger escalation signal than any one alone.
- No LDAP match for a supposed service account often points to local service principals, non-AD identities, or telemetry normalization problems.

---

## Pattern 5: Lateral Movement Correlation

**When**: Alert suggests lateral movement (e.g., anomalous logons across hosts) and you need to verify whether the user account has legitimate access to the target systems.

**Goal**: Check group memberships to determine if the access pattern is authorized.

### Cy Task Template

```cy
try {
    username = alert.get("user_info", {}).get("username", "")
    target_host = alert.get("destination", {}).get("hostname", "")

    ldap_result = {"data": {"entries": []}, "total_objects": 0}
    try {
        ldap_result = app::ad_ldap::run_query(
            filter="(&(objectCategory=person)(objectClass=user)(sAMAccountName=" + username + "))",
            attributes="cn;memberOf;objectClass;title;userAccountControl",
            search_base="DC=corp,DC=example,DC=com"
        )
    } catch (e) {
        log("LDAP lookup failed for lateral movement check: ${e}")
    }

    if ldap_result.total_objects > 0 {
        user = ldap_result.data.entries[0]
        groups = user.attributes.memberof ?? []

        # Use LLM to assess whether group membership justifies access
        assessment = llm_run(
            "User '" + username + "' (title: " + str(user.attributes.title ?? []) + ") " +
            "was detected accessing host '" + target_host + "'.\n" +
            "Group memberships: " + str(groups) + "\n" +
            "Based on the group names, is this user likely authorized to access this host? " +
            "Consider: server admin groups, remote desktop users, IT support groups. " +
            "Respond with authorized/unauthorized/inconclusive and reasoning."
        )

        emit("lateral_movement_analysis", {
            "username": username,
            "target_host": target_host,
            "groups": groups,
            "group_count": len(groups),
            "assessment": assessment
        })
    } else {
        emit("lateral_movement_analysis", {
            "username": username,
            "status": "no_ldap_data",
            "note": "Could not retrieve identity context — proceed with SIEM-only analysis"
        })
    }
} catch (e) {
    emit("lateral_movement_analysis", {"status": "action_failed", "error": str(e)})
}
```

---

## Pattern 6: Multi-Source Corroboration

**When**: Alert has both a username and a source IP. LDAP provides identity context, SIEM provides event history, and threat intel (e.g., AbuseIPDB) provides external reputation on the source IP.

### LDAP + SIEM + Threat Intel Pattern

```cy
try {
    username = alert.get("user_info", {}).get("username", "")
    source_ip = alert.get("source", {}).get("ip", "")

    # 1. LDAP: Identity context
    identity = {"status": "skipped"}
    if username != "" {
        try {
            ldap_result = app::ad_ldap::run_query(
                filter="(&(objectCategory=person)(objectClass=user)(sAMAccountName=" + username + "))",
                attributes="cn;mail;memberOf;title;userAccountControl",
                search_base="DC=corp,DC=example,DC=com"
            )
            identity = {
                "status": "found" if ldap_result.total_objects > 0 else "no_match",
                "entries": ldap_result.data.entries,
                "total": ldap_result.total_objects
            }
        } catch (e) {
            identity = {"status": "error", "error": str(e)}
        }
    }

    # 2. Threat intel on source IP
    threat_intel = {"status": "skipped"}
    if source_ip != "" {
        try {
            abuse_result = app::abuseipdb::check_ip(ip=source_ip)
            threat_intel = abuse_result
        } catch (e) {
            threat_intel = {"status": "error", "error": str(e)}
        }
    }

    # 3. LLM synthesis
    disposition = llm_run(
        "Correlate these findings for alert triage:\n" +
        "Alert: " + str(alert.get("title", "")) + "\n" +
        "Username: " + username + "\n" +
        "Source IP: " + source_ip + "\n" +
        "Identity context: " + str(identity) + "\n" +
        "Threat intel: " + str(threat_intel) + "\n" +
        "Determine: TP/FP, confidence, recommended action."
    )

    emit("multi_source_enrichment", {
        "identity": identity,
        "threat_intel": threat_intel,
        "disposition": disposition
    })

} catch (e) {
    emit("multi_source_enrichment", {"status": "action_failed", "error": str(e)})
}
```

### Workflow Composition

For production workflows, run LDAP, SIEM, and threat intel enrichments as **parallel tasks** and merge results:

```
Workflow: identity_alert_triage
  ┌─ identity (start)
  ├─ [ldap_user_enrichment, splunk_triggering_events, abuseipdb_ip_check]  ← parallel
  ├─ merge
  └─ llm_disposition_assessment
```

Each parallel task should emit its results independently and handle its own errors — a timeout in one enrichment source must not block the others. The merge node collects whatever succeeded, and the disposition LLM works with partial data if needed.

---

## Corroboration Rules

These rules prevent bad conclusions from LDAP data alone:

- **LDAP is identity context, not event truth.** Confirm auth activity, source IPs, and host impact in SIEM or EDR before disposition.
- **Trust SIEM for time, LDAP for state.** Use sign-in logs for exact chronology; use LDAP to decide whether the account is enabled, privileged, stale, or service-like.
- **Use EDR to ground privilege alerts.** A privileged user touching a non-sensitive endpoint matters differently from the same identity touching a Tier 0 host.
- **Stop pivoting when identity class is wrong.** If the alert clearly involves local accounts, cloud-only users, or application principals, move to the right identity source instead of forcing AD to fit.
- **Do not close as FP from LDAP alone.** A disabled account in LDAP does not explain away a successful-auth alert — cached tokens, stale sessions, and service usage persist outside AD state.

---

## Batch and Failure Guardrails

<!-- EVIDENCE: source code — actions.py lines 213, 493; manifest.json line 61 -->

- This integration has no paging, retry, or enforced timeout in the action code. Keep live triage queries narrow and targeted.
- Prefer one precise `run_query` per investigated identity over broad enumeration. If an upstream alert names many users, prune the suspect set first with SIEM or EDR evidence.
- Use `search_base` aggressively to keep subtree searches cheap.
- On LDAP failure, return the alert with an LDAP-error enrichment instead of failing the whole workflow. Missing identity context should degrade analysis quality, not crash the case.
- Pull the smallest field set that answers the question, then expand into auth-state or group context only if the first pass supports the hypothesis.
