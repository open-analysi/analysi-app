# Configuring Okta Federation in Keycloak

This guide explains how to add Okta as an Identity Provider in Keycloak so that Okta
users can log in to Analysi. After federation is set up, Analysi continues to validate
Keycloak-issued JWTs — no backend changes are required.

## Prerequisites

- A running Keycloak instance (local dev: `http://localhost:8080`)
- Admin credentials (`KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD`)
- An Okta developer account

## Step 1: Create an Okta OIDC App

1. In your Okta Admin Console, go to **Applications → Create App Integration**.
2. Select **OIDC - OpenID Connect** and **Web Application**.
3. Set the **Sign-in redirect URI** to:
   ```
   http://localhost:8080/realms/analysi/broker/okta/endpoint
   ```
4. Note the **Client ID** and **Client Secret**.

## Step 2: Add Okta as a Keycloak Identity Provider

1. Log in to Keycloak Admin at `http://localhost:8080/admin`.
2. Select the **analysi** realm.
3. Navigate to **Identity Providers → Add provider → OpenID Connect v1.0**.
4. Fill in the form:
   - **Alias**: `okta`
   - **Display Name**: `Okta`
   - **Discovery endpoint**: `https://<your-okta-domain>/.well-known/openid-configuration`
   - **Client ID**: *(from Step 1)*
   - **Client Secret**: *(from Step 1)*
   - **Default Scopes**: `openid profile email`
5. Click **Add**.

## Step 3: Map `tenant_id` from Okta to Keycloak

Analysi reads `tenant_id` from the JWT claim. You must ensure the Okta user's
`tenant_id` is mapped into the Keycloak user profile so the protocol mapper
(configured in `realm-analysi.json`) can include it in the access token.

1. In the **okta** Identity Provider settings, go to **Mappers → Create**.
2. Add an **Attribute Importer**:
   - **Name**: `tenant_id`
   - **Sync Mode Override**: `force`
   - **Mapper Type**: `Attribute Importer`
   - **Claim**: the Okta claim that holds the tenant (e.g., a custom attribute `tenant_id`)
   - **User Attribute Name**: `tenant_id`
3. Ensure each Okta user has the `tenant_id` custom attribute set correctly in Okta.

> **Security Note**: The `tenant_id` protocol mapper in the Analysi realm is configured
> with `User Editable: false`. This prevents users from changing their own `tenant_id`
> via the Keycloak Account Console. The value can only be set via the Admin API or
> through the IdP mapper above.

## Step 4: Map Okta Groups to Keycloak Roles

To assign Analysi roles (`owner`, `analyst`, `viewer`, etc.) to Okta users:

1. In the **okta** Identity Provider, add another Mapper:
   - **Type**: `Role Importer`
   - **Claim**: the Okta claim that contains roles (e.g., `groups`)
   - **Role**: map Okta group names to Keycloak realm roles as needed

## Step 5: Test the Flow

1. Open `http://localhost:5173` (the Analysi UI).
2. Click **Log in** → you should see an **Okta** option on the Keycloak login page.
3. Authenticate with an Okta account.
4. Keycloak issues a JWT with `tenant_id` and `roles` claims.
5. The Analysi backend validates the JWT and routes the user to the correct tenant.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 403 "No tenant assigned" | `tenant_id` claim missing from JWT | Check Okta attribute and Keycloak mapper |
| 403 "tenant mismatch" | User's `tenant_id` doesn't match the URL | Verify Okta user attribute and Keycloak mapper are in sync |
| Login loop | Redirect URIs mismatch | Add the Keycloak broker callback URI to the Okta app |
