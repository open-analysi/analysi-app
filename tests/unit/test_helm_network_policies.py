"""NetworkPolicy regression tests for the Helm chart.

The chart must define NetworkPolicies that limit pod-to-pod traffic to
the explicit set of edges the app actually uses. Without policies, any
pod compromise (RCE, leaked credential) gives the attacker free reach
across the whole namespace — including direct DB access.

Required edges (from the Tilos / Sifnos architecture):
  api               → postgresql, valkey, minio, vault
  alerts-worker     → postgresql, valkey, minio, vault
  integrations-worker → postgresql, valkey, minio, vault
  notifications-worker → postgresql, valkey
  flyway (job)      → postgresql

Default-deny ingress on all dependency pods (postgres, valkey, minio, vault)
limits the blast radius of any compromised app pod.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHART_DIR = REPO_ROOT / "deployments" / "helm" / "analysi"

# Use the local-mode overlay (provides all required passwords)
LOCAL_VALUES = CHART_DIR / "values" / "local.yaml"


def _have_helm() -> bool:
    return shutil.which("helm") is not None


pytestmark = pytest.mark.skipif(not _have_helm(), reason="helm not installed")


def _render_manifests() -> list[dict]:
    """Render the chart and return all NetworkPolicy resources."""
    result = subprocess.run(
        [
            "helm",
            "template",
            "test-release",
            str(CHART_DIR),
            "-f",
            str(LOCAL_VALUES),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    docs = list(yaml.safe_load_all(result.stdout))
    return [d for d in docs if d and d.get("kind") == "NetworkPolicy"]


class TestNetworkPolicies:
    """The chart must ship NetworkPolicies covering every dep pod."""

    def test_at_least_one_network_policy_exists(self):
        policies = _render_manifests()
        assert policies, (
            "No NetworkPolicy resources rendered — without them, any pod "
            "compromise gives free access to all other pods in the namespace."
        )

    def test_postgresql_has_restrictive_ingress(self):
        """PostgreSQL must only accept traffic from app pods, not the world."""
        policies = _render_manifests()
        pg_policies = [
            p
            for p in policies
            if p.get("spec", {})
            .get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "postgresql"
        ]
        assert pg_policies, "No NetworkPolicy targeting postgresql pod"

        pol = pg_policies[0]
        ingress_rules = pol["spec"].get("ingress", [])
        assert ingress_rules, (
            "Postgres NetworkPolicy has no ingress rules — denies everything"
        )

        # Each ingress rule must restrict by `from:` (no anywhere-allowed rules).
        for rule in ingress_rules:
            assert "from" in rule, (
                f"Postgres ingress rule has no 'from' clause (allows all sources): {rule}"
            )

    def test_valkey_has_restrictive_ingress(self):
        """Valkey must only accept traffic from app pods that need cache."""
        policies = _render_manifests()
        vk_policies = [
            p
            for p in policies
            if p.get("spec", {})
            .get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "valkey"
        ]
        assert vk_policies, "No NetworkPolicy targeting valkey pod"

        for rule in vk_policies[0]["spec"].get("ingress", []):
            assert "from" in rule, "Valkey ingress rule allows all sources"

    def test_vault_has_restrictive_ingress(self):
        """Vault holds tenant secrets — must only accept traffic from app pods."""
        policies = _render_manifests()
        vault_policies = [
            p
            for p in policies
            if p.get("spec", {})
            .get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "vault"
        ]
        assert vault_policies, "No NetworkPolicy targeting vault pod"

        for rule in vault_policies[0]["spec"].get("ingress", []):
            assert "from" in rule, "Vault ingress rule allows all sources"

    def test_minio_has_restrictive_ingress(self):
        """MinIO holds artifacts (often sensitive) — must restrict ingress."""
        policies = _render_manifests()
        minio_policies = [
            p
            for p in policies
            if p.get("spec", {})
            .get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "minio"
        ]
        assert minio_policies, "No NetworkPolicy targeting minio pod"

        for rule in minio_policies[0]["spec"].get("ingress", []):
            assert "from" in rule, "Minio ingress rule allows all sources"
