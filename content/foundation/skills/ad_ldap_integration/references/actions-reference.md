# `ad_ldap` Actions Reference

## Table of Contents

- [Operating Model](#operating-model)
- [Configuration Facts](#configuration-facts)
- [health_check](#health_check)
- [get_attributes — Principal Attribute Lookup](#get_attributes)
- [run_query — Raw LDAP Filter Query](#run_query)
- [Filter-Value Safety](#filter-value-safety)
- [Filter Cookbook](#filter-cookbook)
- [LDAP Filter Syntax Quick Reference](#ldap-filter-syntax-quick-reference)
- [Known Limitations](#known-limitations)

---

## Operating Model

<!-- EVIDENCE: source code — task_execution.py lines 840, 849, 1011, 649 -->
<!-- EVIDENCE: source code — integration_tools.py line 266 -->
<!-- EVIDENCE: MCP live query — list_integration_tools(ad_ldap) -->

- Call the integration with `app::ad_ldap::health_check()`, `app::ad_ldap::get_attributes(...)`, or `app::ad_ldap::run_query(...)`.
- The integration type, not the configured instance ID, appears in Cy. The platform resolves the enabled `ad_ldap` instance behind `app::ad_ldap::*`.
- Always wrap LDAP calls in `try/catch`. The Cy runtime converts integration errors into exceptions rather than returning `{"status": "error"}` payloads.
- On success in the Cy runtime, `status` and `timestamp` are stripped from the response. For `get_attributes` and `run_query`, you receive a dict with `data` and `total_objects`.

**Note on raw vs. Cy response shapes**: When calling integration tools directly via MCP (outside the Cy runtime), responses include `status`, `error`, and `error_type` fields. The Cy examples in this document assume the Cy runtime context where errors are exceptions and success responses omit `status`. If you observe `status` in your response, check both patterns.

---

## Configuration Facts

<!-- EVIDENCE: source code — manifest.json params_schema -->
<!-- EVIDENCE: source code — constants.py line 11 -->
<!-- EVIDENCE: source code — actions.py line 81 -->

- Required credentials are `server`, `username`, and `password`.
- Default settings are LDAPS-oriented: `force_ssl=true`, `ssl_port=636`, `validate_ssl_cert=false`.
- The `server` field may be a hostname, IP, or VIP. Treat controller-local attributes (`lastLogon`, `badPwdCount`) as the view from whichever domain controller answered that bind.
- A `timeout` setting exists in the manifest, but the action code does not pass it to `ldap3`. Do not assume broad searches will be cut off automatically.

---

## health_check

<!-- EVIDENCE: source code — manifest.json params_schema -->
<!-- EVIDENCE: source code — actions.py line 240 -->

**Purpose**: Distinguish "LDAP path is broken" from "this user or group does not exist." Run this first if lookups suddenly fail or every result looks implausible.

### Parameters

None. `health_check` takes no action parameters.

### Cy Example

```cy
health = null

try {
    health = app::ad_ldap::health_check()
} catch (e) {
    log("AD LDAP health check failed: ${e}")
    health = {"message": "LDAP unavailable", "data": {"connected": false}}
}
```

### Result Shape

```json
{
  "message": "Test Connectivity Passed",
  "data": {
    "connected": true,
    "server": "dc01.corp.example.com"
  }
}
```

### Limitations

<!-- EVIDENCE: source code — actions.py line 304 -->

- Validates bind and connectivity only. It does not prove your bind account can read every OU or attribute your investigation needs.
- The declared `timeout` setting is not applied here either; a slow or hanging LDAP path may stall the workflow.

---

## get_attributes

<!-- EVIDENCE: MCP live query — list_integration_tools(ad_ldap) -->
<!-- EVIDENCE: source code — actions.py GetAttributesAction.execute() lines 388-398 -->

**Purpose**: Fast convenience lookup when the alert gives you an email address or common name and you want a small attribute set without hand-writing an LDAP filter. Use for quick first-pass enrichment — switch to `run_query` for any disposition-affecting decision.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `principals` | string | Yes | Semicolon-separated values — usernames, common names, or email addresses (e.g., `"jsmith;jane.doe@corp.com;John Smith"`) |
| `attributes` | string | Yes | Semicolon-separated attribute names to retrieve (e.g., `"cn;mail;uid;memberOf;objectClass"`) |

### What the Code Actually Does

<!-- EVIDENCE: source code — actions.py lines 388, 395 -->

For each supplied principal, the action generates three sub-filters and combines them with OR:

```
(|(uid=jsmith)(cn=jsmith)(mail=jsmith))
```

The action searches `uid`, `cn`, and `mail` — **not** `sAMAccountName`, `userPrincipalName`, or `distinguishedName`, despite what the manifest description says. On a typical AD deployment where `uid` is unpopulated, passing a `sAMAccountName` value (e.g., `jsmith`) will only match if AD happens to have a matching `cn` or `mail`. If `get_attributes` returns empty for a user you know exists, fall back to `run_query` with an explicit `(sAMAccountName=jsmith)` filter.

### Cy Example

```cy
quick_lookup = {"data": {"entries": []}, "total_objects": 0}

try {
    quick_lookup = app::ad_ldap::get_attributes(
        principals="jsmith;jane.doe@corp.com",
        attributes="cn;mail;uid;memberOf;objectClass;title;telephoneNumber"
    )

    if quick_lookup.total_objects > 0 {
        for entry in quick_lookup.data.entries {
            emit("identity_context", {
                "dn": entry.dn,
                "cn": entry.attributes.cn,
                "mail": entry.attributes.mail,
                "groups": entry.attributes.memberOf
            })
        }
    } else {
        emit("identity_context", {"status": "no_match", "principals_queried": "jsmith;jane.doe@corp.com"})
    }
} catch (e) {
    log("LDAP quick lookup failed: ${e}")
    emit("identity_context", {"status": "action_failed", "error": str(e)})
}
```

### Extracting Principal from Alert

In most SOC workflows, the principal comes from the alert itself. Common field locations:

```cy
username = alert.get("user_info", {}).get("username", "")
if username == "" {
    username = alert.get("source", {}).get("user", "")
}
if username == "" {
    username = alert.get("raw_event", {}).get("src_user", "")
}
```

### Result Shape

<!-- EVIDENCE: MCP live test — run_integration_tool(get_attributes, ...) -->

```json
{
  "data": {
    "entries": [
      {
        "dn": "CN=John Smith,OU=Users,DC=corp,DC=com",
        "attributes": {
          "cn": ["John Smith"],
          "mail": ["jsmith@corp.com"],
          "uid": ["jsmith"],
          "objectClass": ["top", "person", "inetOrgPerson"],
          "memberOf": ["cn=SecurityTeam,ou=Groups,dc=corp,dc=com"]
        }
      }
    ]
  },
  "total_objects": 1
}
```

Key details:
- Results are nested at `result.data.entries`, not `result.entries`.
- `entries` is always an array (empty `[]` when no matches — not an error).
- `dn` is returned automatically — do not request it as an attribute (causes `"invalid attribute type dn"` error).
- Attribute values are typically arrays, even for single-valued attributes like `cn`.
- `total_objects` is the count of non-referral entries.
- Attribute key casing is preserved as returned by the server (not lowercased).
- There is no `search_base` parameter — every lookup searches the default naming context subtree.

---

## run_query

<!-- EVIDENCE: MCP live query — list_integration_tools(ad_ldap) -->
<!-- EVIDENCE: source code — actions.py RunQueryAction.execute() lines 440-557 -->

**Purpose**: Primary investigation action for exact AD lookups, group pivots, auth-state enrichment, service-account context, and any search that `get_attributes` cannot express.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `filter` | string | Yes | LDAP filter in standard syntax (e.g., `"(sAMAccountName=jsmith)"`) |
| `attributes` | string | Yes | Semicolon-separated attribute names (e.g., `"cn;mail;memberOf"`) |
| `search_base` | string | No | Distinguished name for search root (e.g., `"DC=corp,DC=example,DC=com"`). Defaults to `defaultNamingContext` from the server; falls back to `dc=example,dc=com` for OpenLDAP — set it explicitly when in doubt. |

### Execution Behavior

<!-- EVIDENCE: source code — actions.py lines 198, 213, 530 -->

- Search scope is always subtree; there is no way to request `BASE` or `ONELEVEL`.
- If you omit `search_base`, the code uses `defaultNamingContext` from server info. If that is missing, it falls back to `dc=example,dc=com` — an OpenLDAP placeholder and a bad default for real AD. Set `search_base` explicitly for production queries.
- **Attribute keys are lowercased** in the response. If you request `memberOf`, access it as `entry.attributes.memberof`. This differs from `get_attributes`, which preserves original casing.
- The action validates only presence of `filter` and `attributes`. It does not validate filter safety, retry on transient errors, or paginate results.

### Cy Examples

**Exact user lookup by sAMAccountName (AD-specific):**

```cy
directory = {"data": {"entries": []}, "total_objects": 0}

try {
    directory = app::ad_ldap::run_query(
        filter="(&(objectCategory=person)(objectClass=user)(sAMAccountName=alice))",
        attributes="distinguishedName;displayName;mail;sAMAccountName;userPrincipalName;memberOf;userAccountControl",
        search_base="DC=corp,DC=example,DC=com"
    )

    if directory.total_objects > 0 {
        entry = directory.data.entries[0]
        emit("ad_user", {
            "dn": entry.dn,
            "cn": entry.attributes.displayname,
            "samaccountname": entry.attributes.samaccountname,
            "groups": entry.attributes.memberof
        })
    } else {
        emit("ad_user", {"status": "no_match"})
    }
} catch (e) {
    log("LDAP query failed: ${e}")
    emit("ad_user", {"status": "action_failed", "error": str(e)})
}
```

**Search by email domain (e.g., investigating vendor accounts):**

```cy
try {
    result = app::ad_ldap::run_query(
        filter="(&(objectClass=person)(mail=*@external-vendor.com))",
        attributes="cn;uid;mail;memberof;objectclass"
    )

    emit("vendor_accounts", {
        "count": result.total_objects,
        "accounts": result.data.entries
    })
} catch (e) {
    log("LDAP vendor search failed: ${e}")
    emit("vendor_accounts", {"status": "error", "error": str(e)})
}
```

**Wildcard name search:**

```cy
try {
    result = app::ad_ldap::run_query(
        filter="(&(objectClass=person)(cn=John*))",
        attributes="cn;uid;mail;memberof"
    )

    emit("user_search", {"count": result.total_objects, "matches": result.data.entries})
} catch (e) {
    emit("user_search", {"status": "action_failed", "error": str(e)})
}
```

For privileged group enumeration, service account audits, auth-state lookups, and `search_base`-scoped queries, see `investigation-patterns.md`.

### Result Shape

<!-- EVIDENCE: MCP live test — run_integration_tool(run_query, ...) -->
<!-- EVIDENCE: source code — actions.py lines 531-536, explicit lowercase conversion -->

```json
{
  "data": {
    "entries": [
      {
        "dn": "CN=Alice Doe,OU=Users,DC=corp,DC=example,DC=com",
        "attributes": {
          "distinguishedname": "CN=Alice Doe,OU=Users,DC=corp,DC=example,DC=com",
          "displayname": "Alice Doe",
          "mail": "alice@example.com",
          "samaccountname": "alice",
          "userprincipalname": "alice@example.com",
          "memberof": [
            "CN=Tier1 Analysts,OU=Groups,DC=corp,DC=example,DC=com"
          ],
          "useraccountcontrol": 512
        }
      }
    ]
  },
  "total_objects": 1
}
```

Key details:
- All attribute keys are **lowercased** (unlike `get_attributes`).
- `entries` is always an array (empty `[]` when no matches).
- `dn` is automatic — do not request it as an attribute.
- `total_objects` is the count of non-referral entries.

---

## Filter-Value Safety

<!-- EVIDENCE: source code — actions.py lines 395, 515 -->
<!-- EVIDENCE: public API docs — RFC 4515 -->

Neither action escapes user-supplied values for you:
- `get_attributes` concatenates each principal directly into `uid`, `cn`, and `mail` filter clauses.
- `run_query` forwards your raw `filter` string straight into `connection.search(search_filter=...)`.

RFC 4515 requires escaping assertion values that contain LDAP filter metacharacters:

| Character | Escape sequence |
|---|---|
| `\` | `\5c` |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| NUL | `\00` |

**Escaping in Cy** (backslash first, then the rest):

```cy
safe_user = username.replace("\\", "\\5c").replace("*", "\\2a").replace("(", "\\28").replace(")", "\\29")
filter_str = "(sAMAccountName=" + safe_user + ")"
```

**When to escape**: Only interpolate values that are already normalized as a username, UPN, email, or a DN returned by a prior LDAP response. If the alert field is free-form, multi-value text, or may contain filter metacharacters, normalize it upstream or skip LDAP enrichment. Prefer DNs returned by a prior LDAP response over DNs copied from raw SIEM text — DN strings have their own escaping rules that this integration does not handle.

If the principal comes directly from an alert field and you have no reason to expect special characters, the risk is low — but escaping is a good default habit, especially for display names or email addresses that may contain parentheses.

---

## Filter Cookbook

<!-- EVIDENCE: public API docs — https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax -->
<!-- EVIDENCE: public API docs — https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/1e889adc-b503-4423-8985-c28d5c7d4887 -->

All substituted values must already pass filter-value safety (above).

| Investigation goal | LDAP filter |
|---|---|
| Exact user by `sAMAccountName` | `(&(objectCategory=person)(objectClass=user)(sAMAccountName=alice))` |
| Exact user by UPN | `(&(objectCategory=person)(objectClass=user)(userPrincipalName=alice@example.com))` |
| Exact object by DN | `(distinguishedName=CN=Alice Doe,OU=Users,DC=corp,DC=example,DC=com)` |
| Direct members of a group | `(&(objectCategory=person)(objectClass=user)(memberOf=CN=Domain Admins,CN=Users,DC=corp,DC=example,DC=com))` |
| Nested members of a group (AD only) | `(&(objectCategory=person)(objectClass=user)(memberOf:1.2.840.113556.1.4.1941:=CN=Domain Admins,CN=Users,DC=corp,DC=example,DC=com))` |
| Disabled user | `(&(objectCategory=person)(objectClass=user)(sAMAccountName=alice)(userAccountControl:1.2.840.113556.1.4.803:=2))` |
| SPN-bearing user (service / Kerberoast) | `(&(objectCategory=person)(objectClass=user)(servicePrincipalName=*))` |
| Users in email domain | `(&(objectClass=person)(mail=*@corp.com))` |
| Service accounts by naming convention | `(|(uid=svc_*)(uid=sa_*)(cn=svc_*)(cn=sa_*))` |
| Groups matching a name pattern | `(&(objectClass=group)(cn=*Admin*))` |

---

## LDAP Filter Syntax Quick Reference

| Pattern | Meaning | Example |
|---|---|---|
| `(attr=value)` | Exact match | `(uid=jsmith)` |
| `(attr=val*)` | Prefix match | `(cn=John*)` |
| `(attr=*val*)` | Substring match | `(mail=*@corp.com)` |
| `(attr=*)` | Attribute exists | `(mail=*)` |
| `(&(a)(b))` | AND | `(&(objectClass=person)(mail=*@corp.com))` |
| `(|(a)(b))` | OR | `(|(uid=jsmith)(uid=jdoe))` |
| `(!(a))` | NOT | `(!(objectClass=computer))` |

---

## Known Limitations

- **Read-only**: No password reset, account lock/unlock, group membership modification, or OU management.
- **No `sAMAccountName` search in `get_attributes`**: The action searches `uid`, `cn`, and `mail` only. On AD where `uid` is unpopulated, `get_attributes` may miss valid accounts. Use `run_query` with `(sAMAccountName=...)` as a fallback.
- **AD-specific attributes may fail on OpenLDAP**: Attributes like `userAccountControl`, `lastLogon`, `whenCreated`, `pwdLastSet`, `department` return `"invalid attribute type"` on OpenLDAP backends. Use `objectClass` to identify the directory type and adjust your attribute list.
- **No pagination**: Large result sets are returned in full. The action does not paginate or retry on transient errors. Use narrow filters and explicit `search_base` to avoid timeouts.
- **`dn` cannot be requested as an attribute**: It is automatically included in every entry. Requesting it explicitly causes an `"invalid attribute type dn"` error.
- **Direct group membership only via `memberOf`**: For nested/transitive memberships on AD, use `LDAP_MATCHING_RULE_IN_CHAIN` (OID `1.2.840.113556.1.4.1941`) via `run_query`. This OID is AD-specific and errors on OpenLDAP. Also, `memberOf` omits the user's primary group — check `primaryGroupID` if the privilege decision depends on it.
- **Controller-local attributes**: `lastLogon` and `badPwdCount` are not replicated. Values reflect only the DC that answered the bind. `lastLogonTimestamp` is replicated but intentionally delayed (up to 9–14 days under default settings).
- **Timeout not enforced**: The manifest `timeout` setting is not passed to `ldap3` in the action code. Broad searches may stall without automatic cutoff.
- **Search scope is always subtree**: There is no way to request `BASE` or `ONELEVEL` scope. Use `search_base` as your primary performance and noise-control lever.
