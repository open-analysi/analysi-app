"""Helm chart security regression tests.

The chart must not ship insecure defaults. In particular, dependency
credentials (PostgreSQL, Valkey, MinIO, Vault) and platform secrets
(system API key) must NOT have plaintext defaults like "changeme" —
operators must supply their own per environment. This test renders
the chart with the bundled values.yaml and asserts that the rendering
fails fast when passwords are missing, and succeeds when they are
supplied via an overlay.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHART_DIR = REPO_ROOT / "deployments" / "helm" / "analysi"

# Minimal overlay that supplies just the passwords (no other overrides).
# Keeps tests independent of the contents of values/local.yaml etc.
_PASSWORD_OVERRIDES = """
global:
  database:
    password: test-db-pw
  valkey:
    password: test-valkey-pw
  minio:
    accessKey: test-minio-ak
    secretKey: test-minio-sk
  vault:
    token: test-vault-tk
  auth:
    systemApiKey: test-system-key
postgresql:
  auth:
    password: test-db-pw
valkey:
  auth:
    password: test-valkey-pw
minio:
  auth:
    rootUser: test-minio-ak
    rootPassword: test-minio-sk
vault:
  devRootToken: test-vault-tk
"""


def _have_helm() -> bool:
    return shutil.which("helm") is not None


pytestmark = pytest.mark.skipif(not _have_helm(), reason="helm not installed")


def _helm_template(extra_values: str | None = None) -> subprocess.CompletedProcess:
    """Run `helm template` against the chart, optionally with an overlay."""
    cmd = ["helm", "template", "test-release", str(CHART_DIR)]
    if extra_values is not None:
        # Write overlay to a temp file and pass via -f
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as overlay:
            overlay.write(extra_values)
            overlay_path = overlay.name
        cmd += ["-f", overlay_path]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class TestNoInsecurePasswordDefaults:
    """The bundled defaults must not contain insecure 'changeme' values."""

    def test_rendering_fails_without_passwords(self):
        """Without explicit passwords, helm template must fail."""
        result = _helm_template(extra_values=None)
        assert result.returncode != 0, (
            "helm template succeeded with default values.yaml — "
            "this means insecure defaults are still in place"
        )
        # The error should mention what's required (helpful for operators)
        combined = result.stdout + result.stderr
        assert any(
            keyword in combined.lower()
            for keyword in ("password", "required", "secret")
        ), f"helm template failed but error message is unhelpful: {combined!r}"

    def test_rendering_succeeds_with_explicit_passwords(self):
        """When all required passwords are supplied, helm template succeeds."""
        result = _helm_template(extra_values=_PASSWORD_OVERRIDES)
        assert result.returncode == 0, (
            f"helm template failed with explicit passwords supplied. "
            f"stderr={result.stderr!r}"
        )
        # Sanity: the overlay password values should appear in the rendered
        # Secret resource (proves the overlay was actually applied).
        assert "test-db-pw" in result.stdout
        assert "test-valkey-pw" in result.stdout

    def test_no_changeme_in_default_values_file(self):
        """The shipped values.yaml must not contain 'changeme' literals."""
        values_file = CHART_DIR / "values.yaml"
        content = values_file.read_text()
        # Allow it inside comments, but not as a value.
        for lineno, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "changeme" not in line.lower(), (
                f"values.yaml:{lineno} still contains 'changeme': {line!r}. "
                "Replace with empty default and require explicit value."
            )


class TestUiSecurityHardening:
    """The UI pod must run with zero privileges. It is the only component
    that speaks HTTP to an external browser, so if anything is going to be
    hardened to the maximum, this is it.

    Invariants enforced:
      * Image runs as non-root (UID 101 — the nginx user)
      * Zero added capabilities (drop ALL)
      * Container port is non-privileged (>=1024) — no CAP_NET_BIND_SERVICE
      * Read-only root filesystem
      * No privilege escalation
      * seccomp RuntimeDefault

    Regression backstop for PR #42: the initial "drop ALL caps" change
    silently broke the UI because nginx:alpine's entrypoint needs
    CAP_CHOWN and CAP_NET_BIND_SERVICE at boot. The proper fix is to use
    nginxinc/nginx-unprivileged which doesn't need either — these tests
    lock that posture down.
    """

    def _ui_deployment(self) -> dict:
        """Return the rendered UI Deployment spec (pod template level)."""
        import yaml

        result = _helm_template(
            extra_values=_PASSWORD_OVERRIDES + "\nui:\n  enabled: true\n"
        )
        assert result.returncode == 0, result.stderr

        for doc in yaml.safe_load_all(result.stdout):
            if not doc:
                continue
            if doc.get("kind") != "Deployment":
                continue
            labels = doc.get("metadata", {}).get("labels", {})
            if labels.get("app.kubernetes.io/component") != "ui":
                continue
            return doc["spec"]["template"]["spec"]
        raise AssertionError("UI Deployment not found in rendered chart")

    def _ui_container(self) -> dict:
        return self._ui_deployment()["containers"][0]

    def _ui_container_security(self) -> dict:
        return self._ui_container().get("securityContext", {})

    def _ui_pod_security(self) -> dict:
        return self._ui_deployment().get("securityContext", {})

    def test_ui_runs_as_non_root(self):
        """Pod-level: runAsNonRoot and a non-zero UID enforced."""
        pod_ctx = self._ui_pod_security()
        assert pod_ctx.get("runAsNonRoot") is True, (
            f"UI pod must set runAsNonRoot=true: {pod_ctx!r}"
        )
        uid = pod_ctx.get("runAsUser")
        assert isinstance(uid, int), (
            f"UI pod must set runAsUser to an int (got {uid!r})"
        )
        assert uid > 0, f"UI pod must run as non-zero UID (got runAsUser={uid})"

    def test_ui_drops_all_capabilities_without_adding_any(self):
        """The unprivileged image does not need CAP_CHOWN or CAP_NET_BIND_SERVICE.
        Any 'add' list is a regression — likely someone switched back to the
        root nginx image and patched the crash-loop with capabilities instead
        of fixing the image."""
        caps = self._ui_container_security().get("capabilities", {})
        assert caps.get("drop") == ["ALL"], f"UI must drop ALL capabilities: {caps!r}"
        added = caps.get("add") or []
        assert added == [], (
            f"UI must not add any capabilities — the unprivileged nginx "
            f"image does not need them. Added: {added!r}. If you just added "
            f"a cap to fix a crash-loop, you probably switched images away "
            f"from nginxinc/nginx-unprivileged; fix the image instead."
        )

    def test_ui_binds_non_privileged_port(self):
        """Container port must be non-privileged (>=1024) so no CAP_NET_BIND_SERVICE
        is ever needed. Port 80 is the historical footgun."""
        ports = self._ui_container().get("ports", [])
        assert ports, "UI container must declare at least one port"
        container_port = ports[0].get("containerPort")
        assert container_port is not None, "UI container must declare containerPort"
        assert container_port >= 1024, (
            f"UI container must bind a non-privileged port (>=1024), got "
            f"{container_port}. Privileged ports force the pod to grant "
            f"CAP_NET_BIND_SERVICE, which contradicts our zero-caps posture."
        )

    def test_ui_has_read_only_root_filesystem(self):
        """readOnlyRootFilesystem prevents a compromised nginx from writing
        a webshell or modifying binaries on disk."""
        assert self._ui_container_security().get("readOnlyRootFilesystem") is True

    def test_ui_no_privilege_escalation(self):
        assert self._ui_container_security().get("allowPrivilegeEscalation") is False

    def test_ui_seccomp_default_profile(self):
        """RuntimeDefault seccomp blocks most dangerous syscalls out of the box."""
        seccomp = self._ui_pod_security().get("seccompProfile", {})
        assert seccomp.get("type") == "RuntimeDefault", (
            f"UI pod must set seccompProfile.type=RuntimeDefault: {seccomp!r}"
        )

    def test_ui_has_writable_volumes_for_nginx_runtime(self):
        """Read-only root fs means nginx needs emptyDir mounts for its
        generated config (/etc/nginx/conf.d after envsubst) and its runtime
        temp dir (/tmp where the unprivileged image writes pid/client_temp/etc)."""
        container = self._ui_container()
        pod = self._ui_deployment()

        mount_paths = {m["mountPath"] for m in container.get("volumeMounts", [])}
        assert "/etc/nginx/conf.d" in mount_paths, (
            f"UI needs /etc/nginx/conf.d as emptyDir — the entrypoint runs "
            f"envsubst and writes the generated config there. Mounts: {mount_paths!r}"
        )
        assert "/tmp" in mount_paths, (
            f"UI needs /tmp as emptyDir — nginx-unprivileged writes "
            f"pid/temp files there. Mounts: {mount_paths!r}"
        )

        # Each mount must be backed by an emptyDir (not a hostPath, configMap,
        # or secret — those would import outside state into the pod).
        volumes_by_name = {v["name"]: v for v in pod.get("volumes", [])}
        for mount in container.get("volumeMounts", []):
            if mount["mountPath"] not in ("/etc/nginx/conf.d", "/tmp"):
                continue
            vol = volumes_by_name.get(mount["name"])
            assert vol is not None, (
                f"Volume '{mount['name']}' referenced but not declared"
            )
            assert "emptyDir" in vol, (
                f"UI runtime volume '{mount['name']}' must be emptyDir, got {vol!r}"
            )

    def test_ui_service_targets_container_port(self):
        """The Service's targetPort must match whatever port nginx listens on.
        Catches the 'changed the container port but forgot the Service' bug."""
        import yaml

        result = _helm_template(
            extra_values=_PASSWORD_OVERRIDES + "\nui:\n  enabled: true\n"
        )
        container_port = self._ui_container()["ports"][0]["containerPort"]
        for doc in yaml.safe_load_all(result.stdout):
            if not doc or doc.get("kind") != "Service":
                continue
            labels = doc.get("metadata", {}).get("labels", {})
            if labels.get("app.kubernetes.io/component") != "ui":
                continue
            target = doc["spec"]["ports"][0]["targetPort"]
            assert target == container_port, (
                f"UI Service targetPort ({target}) must equal container "
                f"port ({container_port})"
            )
            return
        raise AssertionError("UI Service not found")


class TestWebhookSecretsEnvWiring:
    """Regression: the Helm chart must inject ANALYSI_ALERT_WEBHOOK_SECRETS
    into the API pod when configured. Without this, signature verification
    code looks at the env, finds nothing, and silently falls back to
    no-verification — defeating the whole feature in chart-managed
    deployments. Codex review on PR #42 commit ca51f3add.
    """

    def _api_env(self, extra_values: str) -> list[dict]:
        """Render the chart and return the API container's env list."""
        import yaml

        result = _helm_template(extra_values=_PASSWORD_OVERRIDES + extra_values)
        assert result.returncode == 0, result.stderr
        for doc in yaml.safe_load_all(result.stdout):
            if not doc:
                continue
            if doc.get("kind") != "Deployment":
                continue
            labels = doc.get("metadata", {}).get("labels", {})
            if labels.get("app.kubernetes.io/component") != "api":
                continue
            return doc["spec"]["template"]["spec"]["containers"][0].get("env", [])
        raise AssertionError("API Deployment not found in rendered chart")

    def test_env_omitted_when_unset(self):
        """Default: no secret reference, env var must not be present.
        (App still works; signature verification just stays opt-out.)"""
        env = self._api_env("")
        names = {e["name"] for e in env}
        assert "ANALYSI_ALERT_WEBHOOK_SECRETS" not in names

    def test_env_injected_from_external_secret_ref(self):
        """When operator points at a pre-existing Kubernetes Secret, the env
        var must be sourced from there via secretKeyRef."""
        overlay = (
            "  alertWebhookSecretsRef:\n"
            "    name: my-webhook-secrets\n"
            "    key: secrets-json\n"
        )
        merged = _PASSWORD_OVERRIDES.replace("global:\n", "global:\n" + overlay, 1)
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(merged)
            f_path = f.name

        result = subprocess.run(
            ["helm", "template", "test-release", str(CHART_DIR), "-f", f_path],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

        import yaml

        for doc in yaml.safe_load_all(result.stdout):
            if not doc or doc.get("kind") != "Deployment":
                continue
            labels = doc.get("metadata", {}).get("labels", {})
            if labels.get("app.kubernetes.io/component") != "api":
                continue
            env = doc["spec"]["template"]["spec"]["containers"][0].get("env", [])
            matches = [e for e in env if e["name"] == "ANALYSI_ALERT_WEBHOOK_SECRETS"]
            assert len(matches) == 1
            ref = matches[0].get("valueFrom", {}).get("secretKeyRef", {})
            assert ref.get("name") == "my-webhook-secrets"
            assert ref.get("key") == "secrets-json"
            return
        raise AssertionError("API Deployment not found in rendered chart")


class TestCredentialSingleSourceOfTruth:
    """Regression: every app ↔ dep credential pair must come from the same
    source. Previously `secrets.yaml` required both `global.X.password` and
    `X.auth.password` but did not enforce they match, so an operator could
    set only the global side (passing `required`) and deploy a broken
    cluster where the dep pod authenticates with a different password.

    Codex review on PR #42 commit 8c64b12c3.
    """

    def _render_secret(self, overlay: str) -> dict[str, str]:
        """Render the chart and return the `stringData` dict from the
        analysi-secrets Secret."""
        import yaml

        result = _helm_template(extra_values=overlay)
        assert result.returncode == 0, result.stderr
        for doc in yaml.safe_load_all(result.stdout):
            if not doc:
                continue
            if doc.get("kind") != "Secret":
                continue
            name = doc.get("metadata", {}).get("name", "")
            if "analysi-secrets" in name or name.endswith("-secrets"):
                return doc.get("stringData", {})
        raise AssertionError("analysi-secrets Secret not found")

    def test_postgres_password_single_source(self):
        """When only global.database.password is set, postgresql-password
        secret key MUST carry the same value so the dep pod and app agree."""
        overlay = _PASSWORD_OVERRIDES.replace(
            "postgresql:\n  auth:\n    password: test-db-pw\n",
            "",  # remove the dep-side password entirely
        )
        secret = self._render_secret(overlay)
        assert secret["database-password"] == "test-db-pw"
        assert secret["postgresql-password"] == secret["database-password"], (
            "postgres pod and app must receive the same password from a "
            "single configured source"
        )

    def test_valkey_password_single_source(self):
        """When only global.valkey.password is set, the Valkey pod's
        --requirepass must receive the same value."""
        import yaml

        overlay = _PASSWORD_OVERRIDES.replace(
            "valkey:\n  auth:\n    password: test-valkey-pw\n",
            "",
        )
        result = _helm_template(extra_values=overlay)
        assert result.returncode == 0, result.stderr
        # Find the valkey Deployment and check the command arg
        for doc in yaml.safe_load_all(result.stdout):
            if not doc or doc.get("kind") != "Deployment":
                continue
            labels = doc.get("metadata", {}).get("labels", {})
            if labels.get("app.kubernetes.io/component") != "valkey":
                continue
            containers = doc["spec"]["template"]["spec"]["containers"]
            cmd = containers[0].get("command", [])
            # Expect command like: ["valkey-server", "--requirepass", "<pw>"]
            assert cmd[0] == "valkey-server"
            assert cmd[1] == "--requirepass"
            password = cmd[2]
            assert password == "test-valkey-pw", (
                f"Valkey server configured with password '{password}', but "
                f"app pods will use 'test-valkey-pw'. Single-source-of-truth "
                f"violated — operators can set only global.valkey.password "
                f"and still get a broken cluster."
            )
            return
        raise AssertionError("valkey Deployment not found")

    def test_minio_credentials_single_source(self):
        """MinIO root user/password must match the global access/secret keys."""
        overlay = _PASSWORD_OVERRIDES.replace(
            "minio:\n  auth:\n    rootUser: test-minio-ak\n    rootPassword: test-minio-sk\n",
            "",
        )
        secret = self._render_secret(overlay)
        assert secret["minio-access-key"] == "test-minio-ak"
        assert secret["minio-secret-key"] == "test-minio-sk"
        assert secret["minio-root-user"] == secret["minio-access-key"]
        assert secret["minio-root-password"] == secret["minio-secret-key"]

    def test_vault_token_single_source(self):
        """Vault dev root token must match the global.vault.token."""
        overlay = _PASSWORD_OVERRIDES.replace(
            "vault:\n  devRootToken: test-vault-tk\n",
            "",
        )
        secret = self._render_secret(overlay)
        assert secret["vault-token"] == "test-vault-tk"
        assert secret["vault-dev-token"] == secret["vault-token"]
