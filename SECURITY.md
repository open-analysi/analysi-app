# Security Policy

## Reporting a Vulnerability

If you believe you've found a security vulnerability in Analysi, please **do
not file a public GitHub issue**. Public disclosure before a fix is available
puts users at risk.

Instead, report it privately via one of these channels:

- **GitHub private vulnerability reports** — preferred. Open the
  [Security tab](https://github.com/open-analysi/analysi-app/security) on the
  repository and click *"Report a vulnerability"*. This creates a private
  advisory visible only to you and the maintainers.
- **Email** — send details to **openanalysi.security@gmail.com**. Include
  "SECURITY" in the subject line.

When reporting, please include:

- A clear description of the vulnerability and its impact.
- Steps to reproduce (a minimal proof-of-concept is ideal).
- The affected version(s) and any relevant configuration.
- Your suggested mitigation, if you have one.

We'll acknowledge your report within **5 business days**, validate the issue,
and keep you updated on remediation progress. Once a fix is released, we'll
credit you in the release notes (unless you prefer to remain anonymous).

## Supported Versions

Analysi is in active development and currently has no LTS branches. Security
fixes are applied to `main`. Production deployers should track `main` and
upgrade promptly when a fix lands.

## Scope

In scope:

- Bugs in this repository's code that can be exploited to cause unauthorized
  access, data exposure, privilege escalation, or denial of service.
- Misconfigurations in the default Docker, Helm, or Kubernetes manifests
  shipped here.
- Insecure dependencies (please open a regular issue for low-severity
  upstream advisories; reserve private reports for actively exploitable
  cases).

Out of scope:

- Vulnerabilities in third-party services (Splunk, OpenSearch, Vault, etc.)
  — please report those upstream.
- Issues that require an authenticated administrator to misuse documented
  capabilities (e.g., an admin running an arbitrary Cy script).
- Self-XSS, missing best-practice headers without demonstrated impact, or
  rate-limit findings on local-development endpoints.

## Safe Harbor

We will not pursue legal action against researchers who:

- Make a good-faith effort to follow this policy.
- Avoid privacy violations, service disruption, and data destruction.
- Give us reasonable time to remediate before public disclosure (we
  recommend 90 days from initial report).

Thank you for helping keep Analysi and its users safe.
