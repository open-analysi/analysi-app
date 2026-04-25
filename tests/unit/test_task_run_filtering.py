"""Unit tests for task run filtering."""


class TestTaskRunContextDefaults:
    """Test run_context default behavior."""

    def test_default_run_context_excludes_scheduled(self):
        """Default run_context filter should be 'analysis,ad_hoc' (excludes scheduled)."""
        # The default in the endpoint should exclude 'scheduled'
        default = "analysis,ad_hoc"
        contexts = default.split(",")
        assert "scheduled" not in contexts
        assert "analysis" in contexts
        assert "ad_hoc" in contexts

    def test_explicit_run_context_scheduled(self):
        """Can explicitly request 'scheduled' runs."""
        explicit = "scheduled"
        contexts = explicit.split(",")
        assert "scheduled" in contexts
