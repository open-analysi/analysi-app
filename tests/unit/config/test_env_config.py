"""Tests to validate .env files are in sync and follow standardized naming conventions.

This test ensures that all .env files (.env, .env.test, .env.example) maintain
consistent variable names and structure, preventing configuration drift.
"""

import re
from pathlib import Path

import pytest


class TestEnvFilesSync:
    """Test that .env files follow standardized naming conventions."""

    @pytest.fixture
    def env_files(self):
        """Load all three .env files."""
        project_root = Path(__file__).parent.parent.parent.parent
        env_path = project_root / ".env"
        if not env_path.exists():
            pytest.skip(".env file not present (CI environment)")
        return {
            ".env": env_path,
            ".env.test": project_root / ".env.test",
            ".env.example": project_root / ".env.example",
        }

    def parse_env_file(self, file_path: Path) -> dict[str, str]:
        """Parse .env file and extract variable names (ignoring comments and values)."""
        variables = {}
        if not file_path.exists():
            return variables

        with open(file_path) as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                # Extract variable name (before =)
                if "=" in line:
                    var_name = line.split("=")[0].strip()
                    variables[var_name] = True
        return variables

    def test_backend_api_standardized_naming(self, env_files):
        """Test that BACKEND_API_* variables follow standardized naming."""
        required_vars = [
            "BACKEND_API_HOST",
            "BACKEND_API_PORT",
            "BACKEND_API_EXTERNAL_PORT",
        ]

        for env_name, env_path in env_files.items():
            variables = self.parse_env_file(env_path)

            # Check all required variables exist
            for var in required_vars:
                assert var in variables, f"{env_name} missing {var}"

            # Check old deprecated variables are NOT present
            deprecated_vars = ["API_BASE_URL", "BACKEND_API_URL", "BACKEND_BASE_URL"]
            for var in deprecated_vars:
                assert var not in variables, (
                    f"{env_name} still contains deprecated variable {var}. "
                    f"Use BACKEND_API_HOST/PORT instead."
                )

    def test_echo_server_standardized_naming(self, env_files):
        """Test that ECHO_SERVER_* variables follow standardized naming."""
        required_vars = [
            "ECHO_SERVER_HOST",
            "ECHO_SERVER_PORT",
            "ECHO_SERVER_EXTERNAL_PORT",
        ]

        for env_name, env_path in env_files.items():
            # .env.example may not have all Echo server vars
            if env_name == ".env.example":
                continue

            variables = self.parse_env_file(env_path)

            # Check all required variables exist
            for var in required_vars:
                assert var in variables, f"{env_name} missing {var}"

            # Check old deprecated variable is NOT present
            assert "ECHO_SERVER_URL" not in variables, (
                f"{env_name} still contains deprecated variable ECHO_SERVER_URL. "
                f"Use ECHO_SERVER_HOST/PORT instead."
            )

    def test_vault_standardized_naming(self, env_files):
        """Test that VAULT_* variables follow standardized naming."""
        required_vars = [
            "VAULT_HOST",
            "VAULT_PORT",
            "VAULT_EXTERNAL_PORT",
        ]

        for env_name, env_path in env_files.items():
            variables = self.parse_env_file(env_path)

            # Check all required variables exist
            for var in required_vars:
                assert var in variables, f"{env_name} missing {var}"

            # VAULT_ADDR is now derived from VAULT_HOST/PORT in code, but may still
            # exist for backward compatibility
            # We just ensure the new pattern exists

    def test_no_mcp_servers_variable(self, env_files):
        """Test that deprecated MCP_SERVERS variable is removed."""
        for env_name, env_path in env_files.items():
            variables = self.parse_env_file(env_path)
            assert "MCP_SERVERS" not in variables, (
                f"{env_name} still contains deprecated MCP_SERVERS variable. "
                f"MCP service has been deprecated."
            )

    def test_service_naming_pattern(self, env_files):
        """Test that all internal services follow <SERVICE>_HOST/<SERVICE>_PORT pattern."""
        # Services that should follow the standard pattern
        services = [
            "POSTGRES",
            "REDIS",
            "SPLUNK",
            "VAULT",
            "BACKEND_API",
            "ECHO_SERVER",
        ]

        for env_name, env_path in env_files.items():
            variables = self.parse_env_file(env_path)

            for service in services:
                # Skip services not in test env
                if env_name == ".env.test" and service in ["ECHO_SERVER"]:
                    # Test env may use different config
                    continue

                # Check that if service is referenced, it uses HOST/PORT pattern
                host_var = f"{service}_HOST"

                # If we find any variable starting with this service name,
                # ensure HOST/PORT exist
                service_vars = [v for v in variables if v.startswith(service)]
                if service_vars:
                    # Allow some exceptions (like POSTGRES_HOST_AUTH_METHOD)
                    if service == "POSTGRES" or service == "REDIS":
                        # These have valid exceptions
                        continue

                    # For standardized services, check HOST/PORT exist
                    if service in ["BACKEND_API", "ECHO_SERVER", "VAULT"]:
                        assert host_var in variables or env_name == ".env.example", (
                            f"{env_name} should have {host_var} for standardized service"
                        )

    def test_worker_services_have_system_api_key(self):
        """All worker services that call the API must have ANALYSI_SYSTEM_API_KEY.

        Regression test: the alert-analysis-worker was missing this env var,
        causing all internal API calls to fail with 403 (Project Mikonos).
        """
        import yaml

        project_root = Path(__file__).parent.parent.parent.parent
        compose_dir = project_root / "deployments" / "compose"

        # Workers are split across compose files:
        # alerts-worker in core.yml, integrations-worker in core.yml
        worker_compose_files = {
            "alerts-worker": compose_dir / "core.yml",
            "integrations-worker": compose_dir / "core.yml",
        }

        for service_name, compose_path in worker_compose_files.items():
            assert compose_path.exists(), f"{compose_path.name} not found"

            with open(compose_path) as f:
                compose = yaml.safe_load(f)

            service = compose.get("services", {}).get(service_name)
            assert service is not None, (
                f"Service {service_name} not found in {compose_path.name}"
            )

            env = service.get("environment", {})
            assert "ANALYSI_SYSTEM_API_KEY" in env, (
                f"{service_name} is missing ANALYSI_SYSTEM_API_KEY in its environment block. "
                f"Without it, internal API calls fail with 403."
            )

    def test_external_port_naming_consistency(self, env_files):
        """Test that external ports follow *_EXTERNAL_PORT naming pattern.

        Allows protocol suffixes for multi-port services (e.g., SAMBA_EXTERNAL_PORT_SMB).
        """
        # Pattern allows both *_EXTERNAL_PORT and *_EXTERNAL_PORT_<PROTOCOL>
        external_port_pattern = re.compile(r"^[A-Z_]+_EXTERNAL_PORT(_[A-Z]+)?$")

        for env_name, env_path in env_files.items():
            variables = self.parse_env_file(env_path)

            # Find all external port variables
            external_ports = [v for v in variables if "EXTERNAL" in v and "PORT" in v]

            for var in external_ports:
                assert external_port_pattern.match(var), (
                    f"{env_name} has incorrectly named external port variable: {var}. "
                    f"Should follow pattern: *_EXTERNAL_PORT or *_EXTERNAL_PORT_<PROTOCOL>"
                )
