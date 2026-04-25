"""
Unit tests for Cy language 0.21 null-safe navigation feature.

Tests the ?? operator for safe nested object access without defensive null checking.

Note: cy-language v0.38+ changed run()/run_async() to return JSON strings.
Use run_native() for raw Python values.
"""

from cy_language import Cy
from cy_language.parser import Parser


class TestCyNullSafeNavigation:
    """Test suite for Cy 0.21 null-safe navigation with ?? operator."""

    def test_parser_accepts_null_coalesce_operator(self):
        """Verify the parser recognizes the ?? operator syntax."""
        script = """
data = {"user": {"name": "Alice"}}
name = data.user.name ?? "Unknown"
return name
        """.strip()

        parser = Parser()
        # Should not raise any parsing errors
        ast = parser.parse_only(script)
        assert ast is not None

    def test_basic_null_safe_navigation(self):
        """Test basic null-safe navigation with existing nested fields."""
        script = """
data = {"user": {"profile": {"email": "test@example.com"}}}
email = data.user.profile.email ?? "default@example.com"
return email
        """.strip()

        cy = Cy()
        result = cy.run_native(script)
        assert result == "test@example.com"

    def test_null_safe_with_missing_intermediate_fields(self):
        """Test null-safe navigation returns default when intermediate fields are missing."""
        script = """
data = {"user": {}}
email = data.user.profile.email ?? "default@example.com"
return email
        """.strip()

        cy = Cy()
        result = cy.run_native(script)
        assert result == "default@example.com"

    def test_null_safe_with_input_data(self):
        """Test null-safe navigation with input data."""
        script = """
email = input.user.profile.email ?? "no-email@example.com"
return email
        """.strip()

        cy = Cy()

        # Test with complete data
        result1 = cy.run_native(
            script, {"user": {"profile": {"email": "alice@example.com"}}}
        )
        assert result1 == "alice@example.com"

        # Test with missing intermediate fields
        result2 = cy.run_native(script, {"user": {}})
        assert result2 == "no-email@example.com"

        # Test with null input
        result3 = cy.run_native(script, None)
        assert result3 == "no-email@example.com"

    def test_null_coalesce_vs_or_operator(self):
        """Test difference between ?? (null-coalesce) and 'or' for falsy values."""
        script = """
# Test with zero - ?? preserves it, 'or' replaces it
zero_nullsafe = input.count ?? 100
zero_or = input.count or 100

# Test with empty list - ?? preserves it, 'or' replaces it
empty_nullsafe = input.items ?? ["default"]
empty_or = input.items or ["default"]

# Test with null - both replace it
null_nullsafe = input.missing ?? "replaced"
null_or = input.missing or "replaced"

return {
    "nullsafe": {"zero": zero_nullsafe, "empty": empty_nullsafe, "null": null_nullsafe},
    "or": {"zero": zero_or, "empty": empty_or, "null": null_or}
}
        """.strip()

        cy = Cy()
        result = cy.run_native(script, {"count": 0, "items": [], "missing": None})

        # ?? preserves falsy values (0, []) but replaces null
        assert result["nullsafe"]["zero"] == 0
        assert result["nullsafe"]["empty"] == []
        assert result["nullsafe"]["null"] == "replaced"

        # or replaces all falsy values
        assert result["or"]["zero"] == 100
        assert result["or"]["empty"] == ["default"]
        assert result["or"]["null"] == "replaced"

    def test_chained_null_coalesce(self):
        """Test chaining multiple ?? operators for fallback values."""
        script = """
data = {"shipping": {}}

# Try multiple fallback paths
city = data.billing.address.city ?? data.shipping.address.city ?? "Unknown City"
return city
        """.strip()

        cy = Cy()
        result = cy.run_native(script)
        assert result == "Unknown City"

    def test_null_safe_on_primitives(self):
        """Test null-safe navigation on primitive types returns null."""
        script = """
# Access field on number - should return null
number = 42
num_field = number.some_field ?? "not-found"

# Access field on string - should return null
text = "hello"
text_field = text.some_property ?? "no-property"

# Access field on boolean - should return null
flag = True
flag_field = flag.attribute ?? "no-attribute"

return {
    "num": num_field,
    "text": text_field,
    "flag": flag_field
}
        """.strip()

        cy = Cy()
        result = cy.run_native(script)

        assert result["num"] == "not-found"
        assert result["text"] == "no-property"
        assert result["flag"] == "no-attribute"

    def test_complex_workflow_with_null_safe(self):
        """Test null-safe navigation in a realistic security alert workflow."""
        script = """
# Simulate alert with possibly missing enrichment fields
alert = {
    "id": "alert-123",
    "severity": "high",
    "enrichments": {
        "network": {"source_ip": "192.168.1.100"}
    }
}

# Safe navigation for all potentially missing fields
alert_id = alert.id ?? "unknown-id"
source_ip = alert.enrichments.network.source_ip ?? "0.0.0.0"
country = alert.enrichments.geo.country ?? "Unknown"
severity = alert.severity ?? "medium"
user_email = alert.user.email ?? "no-user@example.com"
tags = alert.metadata.tags ?? []

return {
    "alert_id": alert_id,
    "source_ip": source_ip,
    "country": country,
    "severity": severity,
    "user": user_email,
    "tags": tags
}
        """.strip()

        cy = Cy()
        result = cy.run_native(script)

        assert result["alert_id"] == "alert-123"
        assert result["source_ip"] == "192.168.1.100"
        assert result["country"] == "Unknown"  # Missing geo
        assert result["severity"] == "high"
        assert result["user"] == "no-user@example.com"  # Missing user
        assert result["tags"] == []  # Missing metadata.tags

    def test_null_safe_in_expressions(self):
        """Test null-safe navigation within larger expressions."""
        script = """
data = {"prices": {"item1": 10}}

# Use in arithmetic expressions
total = (data.prices.item1 ?? 0) + (data.prices.item2 ?? 0) + (data.prices.item3 ?? 0)

# Use in boolean expressions
has_discount = (data.discount.percentage ?? 0) > 0

# Use in string concatenation
message = "User: " + (data.user.name ?? "Guest")

return {
    "total": total,
    "has_discount": has_discount,
    "message": message
}
        """.strip()

        cy = Cy()
        result = cy.run_native(script)

        assert result["total"] == 10  # Only item1 exists
        assert not result["has_discount"]  # No discount field
        assert result["message"] == "User: Guest"  # No user field
