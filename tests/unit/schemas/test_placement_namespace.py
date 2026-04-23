"""Unit tests for PlacementDecision namespace normalization."""

import pytest

from analysi.schemas.knowledge_extraction import VALID_NAMESPACES, PlacementDecision


class TestPlacementNamespaceNormalization:
    """Verify that target_namespace is always normalized to a known value with trailing slash."""

    def _make(self, namespace: str) -> PlacementDecision:
        return PlacementDecision(
            target_namespace=namespace,
            target_filename="test-doc.md",
            merge_strategy="create_new",
        )

    @pytest.mark.parametrize("ns", list(VALID_NAMESPACES))
    def test_valid_namespaces_pass_through(self, ns: str):
        """Known namespaces with trailing slash are unchanged."""
        assert self._make(ns).target_namespace == ns

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("repository", "repository/"),
            ("common/evidence", "common/evidence/"),
            ("common/by_source", "common/by_source/"),
            ("common/by_type", "common/by_type/"),
            ("common/universal", "common/universal/"),
            ("references", "references/"),
        ],
    )
    def test_missing_trailing_slash_normalized(self, raw: str, expected: str):
        """Namespaces without trailing slash get one added and match known values."""
        assert self._make(raw).target_namespace == expected

    def test_unknown_namespace_gets_trailing_slash(self):
        """Unknown namespace still gets trailing slash even if not in known list."""
        result = self._make("custom/path").target_namespace
        assert result.endswith("/")

    def test_namespace_path_concatenation_correct(self):
        """End-to-end: namespace + filename produces valid path."""
        p = self._make("common/evidence")
        path = f"{p.target_namespace}{p.target_filename}"
        assert path == "common/evidence/test-doc.md"
