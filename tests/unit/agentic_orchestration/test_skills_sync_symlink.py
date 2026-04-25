"""Regression tests for symlink exfiltration prevention in skills_sync.

A malicious agent run can create symlinks (e.g., loot.md -> /etc/hosts)
inside the workspace. Without guards, _build_manifest() and
submit_new_files_to_hydra() would transparently read those files and
ingest host data into tenant knowledge docs.
"""

from unittest.mock import AsyncMock

import pytest

from analysi.agentic_orchestration.skills_sync import TenantSkillsSyncer


@pytest.fixture
def syncer():
    return TenantSkillsSyncer(
        tenant_id="test-tenant",
        session_factory=AsyncMock(),
    )


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace with regular files and a symlink."""
    # Regular file
    regular = tmp_path / "regular.md"
    regular.write_text("# Normal content")

    # Symlink pointing to a host file
    symlink = tmp_path / "loot.md"
    symlink.symlink_to("/etc/hosts")

    return tmp_path


class TestBuildManifestRejectsSymlinks:
    """Verify _build_manifest() skips symlinks."""

    def test_manifest_excludes_symlinks(self, syncer, workspace):
        """Symlinks must not appear in the manifest."""
        manifest = syncer._build_manifest(workspace)

        assert "regular.md" in manifest
        assert "loot.md" not in manifest, (
            "Symlink must be excluded from manifest to prevent "
            "exfiltration of host files into tenant knowledge."
        )

    def test_manifest_includes_regular_files(self, syncer, workspace):
        """Regular files should still be included."""
        manifest = syncer._build_manifest(workspace)
        assert len(manifest) == 1
        assert "regular.md" in manifest

    def test_manifest_skips_nested_symlinks(self, syncer, tmp_path):
        """Nested symlinks in subdirectories must also be skipped."""
        subdir = tmp_path / "nested"
        subdir.mkdir()
        (subdir / "real.md").write_text("real content")
        (subdir / "sneaky.md").symlink_to("/etc/passwd")

        manifest = syncer._build_manifest(tmp_path)
        assert "nested/real.md" in manifest
        assert "nested/sneaky.md" not in manifest


class TestDetectNewFilesRejectsSymlinks:
    """Verify detect_new_files() does not report symlinks as new files."""

    def test_new_symlinks_not_detected(self, syncer, tmp_path):
        """Symlinks created by agent must not be detected as new files."""
        # Set up baseline with a regular file
        (tmp_path / "baseline.md").write_text("baseline")
        syncer._baseline_manifest = syncer._build_manifest(tmp_path)
        syncer._baseline_timestamp = "2026-04-26"

        # Agent creates a symlink (attacker's move)
        (tmp_path / "exfil.md").symlink_to("/etc/hosts")
        # Agent also creates a legit new file
        (tmp_path / "legit.md").write_text("new legit content")

        new_files = syncer.detect_new_files(tmp_path)

        new_names = [f.name for f in new_files]
        assert "legit.md" in new_names
        assert "exfil.md" not in new_names

    def test_symlink_replacing_regular_file_not_detected(self, syncer, tmp_path):
        """A regular file replaced with a symlink must not be detected."""
        (tmp_path / "baseline.md").write_text("original")
        syncer._baseline_manifest = syncer._build_manifest(tmp_path)
        syncer._baseline_timestamp = "2026-04-26"

        # Agent replaces regular file with symlink
        (tmp_path / "baseline.md").unlink()
        (tmp_path / "baseline.md").symlink_to("/etc/hosts")

        new_files = syncer.detect_new_files(tmp_path)
        new_names = [f.name for f in new_files]
        assert "baseline.md" not in new_names
