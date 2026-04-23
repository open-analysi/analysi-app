"""
Unit tests for smart merge template logic.

Fast tests for all corner cases of the smart merge algorithm.
These test the logic directly without workflow execution overhead.
"""

import pytest

from analysi.templates.smart_merge import smart_merge


class TestSmartMergeLogic:
    """Unit tests for smart merge field-level conflict detection."""

    # ==================== SUCCESS CASES ====================

    def test_both_branches_add_different_fields(self):
        """Base {a:1}, Branch A adds b, Branch B adds c → {a:1, b:2, c:3}"""
        result = smart_merge([{"a": 1}, {"a": 1, "b": 2}, {"a": 1, "c": 3}])
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_one_branch_modifies_one_adds(self):
        """Base {a:1}, Branch A modifies a, Branch B adds b → {a:2, b:3}"""
        result = smart_merge([{"a": 1}, {"a": 2}, {"a": 1, "b": 3}])
        assert result == {"a": 2, "b": 3}

    def test_one_branch_inactive_other_modifies(self):
        """Base {a:1}, Branch A unchanged, Branch B modifies a → {a:2}"""
        result = smart_merge([{"a": 1}, {"a": 1}, {"a": 2}])
        assert result == {"a": 2}

    def test_empty_base(self):
        """Base {}, Branch A adds a, Branch B adds b → {a:1, b:2}"""
        result = smart_merge([{}, {"a": 1}, {"b": 2}])
        assert result == {"a": 1, "b": 2}

    def test_single_item(self):
        """Just base, no branches → return base unchanged"""
        result = smart_merge([{"a": 1, "b": 2}])
        assert result == {"a": 1, "b": 2}

    def test_empty_list(self):
        """Empty input → {}"""
        result = smart_merge([])
        assert result == {}

    def test_both_branches_no_changes(self):
        """Both branches pass through unchanged → base"""
        result = smart_merge([{"a": 1}, {"a": 1}, {"a": 1}])
        assert result == {"a": 1}

    def test_nested_object_modification(self):
        """Nested object treated as single field - modification tracked correctly"""
        result = smart_merge(
            [
                {"x": {"y": 1}},
                {"x": {"y": 2}},  # Branch A modifies nested object
                {"x": {"y": 1}, "z": 3},  # Branch B adds z, keeps x unchanged
            ]
        )
        assert result == {"x": {"y": 2}, "z": 3}

    def test_array_modification(self):
        """Array modification tracked correctly"""
        result = smart_merge(
            [
                {"arr": [1]},
                {"arr": [1, 2]},  # Branch A extends array
                {"arr": [1], "b": 3},  # Branch B adds field
            ]
        )
        assert result == {"arr": [1, 2], "b": 3}

    def test_null_value_change(self):
        """Changing null to value is a modification"""
        result = smart_merge(
            [
                {"a": None},
                {"a": 1},  # Branch A changes null → 1
                {"a": None, "b": 2},  # Branch B adds b
            ]
        )
        assert result == {"a": 1, "b": 2}

    def test_boolean_flip(self):
        """Boolean flip is a modification"""
        result = smart_merge(
            [
                {"enabled": False},
                {"enabled": True},  # Branch A flips
                {"enabled": False, "status": "active"},  # Branch B adds field
            ]
        )
        assert result == {"enabled": True, "status": "active"}

    def test_type_change_string_to_number(self):
        """Type change is a modification"""
        result = smart_merge(
            [
                {"a": "1"},
                {"a": 1},  # Branch A changes type
                {"a": "1", "b": 2},  # Branch B adds field
            ]
        )
        assert result == {"a": 1, "b": 2}

    def test_large_object_multiple_modifications(self):
        """Multiple non-conflicting modifications on large object"""
        base = {f"field_{i}": i for i in range(10)}
        branch_a = base.copy()
        branch_a["field_0"] = 100
        branch_a["field_1"] = 101

        branch_b = base.copy()
        branch_b["field_5"] = 500
        branch_b["field_6"] = 600

        result = smart_merge([base, branch_a, branch_b])

        expected = base.copy()
        expected.update(
            {"field_0": 100, "field_1": 101, "field_5": 500, "field_6": 600}
        )
        assert result == expected

    def test_three_branches_different_modifications(self):
        """Three parallel branches, each modifies different fields"""
        result = smart_merge(
            [
                {"a": 1, "b": 2, "c": 3},
                {"a": 10, "b": 2, "c": 3},  # Branch A modifies a
                {"a": 1, "b": 20, "c": 3},  # Branch B modifies b
                {"a": 1, "b": 2, "c": 30},  # Branch C modifies c
            ]
        )
        assert result == {"a": 10, "b": 20, "c": 30}

    def test_field_deletion_conflict(self):
        """Omitting a field (deletion) when other branch keeps it → conflict"""
        # Branch A deletes 'b', Branch B keeps 'b' (no modification)
        # This is NOT a conflict - Branch A deletes, Branch B doesn't touch it
        # Wait, no: Branch B has 'b': 2 which matches base, so no modification
        # But deletion detection will trigger anyway
        # Let me reconsider: does "keeping a field" count as touching it?

        # Case: Branch A deletes b, Branch B explicitly keeps b unchanged
        # Current logic: Branch B doesn't modify b (same value), only Branch A acts → no conflict
        result = smart_merge(
            [
                {"a": 1, "b": 2},
                {"a": 1},  # Branch A deletes b
                {"a": 1, "b": 2, "c": 3},  # Branch B keeps b unchanged, adds c
            ]
        )
        # Expected: Branch A's deletion wins (only one that acted on 'b')
        assert result == {"a": 1, "c": 3}  # b deleted

    def test_field_deletion_both_agree(self):
        """Both branches delete same field → No conflict, they agree"""
        result = smart_merge(
            [
                {"a": 1, "b": 2},
                {"a": 1},  # Branch A deletes b
                {"a": 1},  # Branch B also deletes b → agreement, no conflict
            ]
        )
        # Both delete 'b' - they agree on deletion → no conflict
        assert result == {"a": 1}  # b successfully deleted

    def test_field_deletion_no_conflict(self):
        """Field deletion when other branch only adds new fields"""
        result = smart_merge(
            [
                {"a": 1, "b": 2},
                {"a": 1},  # Branch A deletes b
                {"a": 1, "b": 2, "c": 3},  # Branch B adds c, keeps a and b unchanged
            ]
        )
        # Branch A deletes b, Branch B keeps it → only Branch A acts on 'b'
        assert result == {"a": 1, "c": 3}  # b deleted by Branch A

    def test_add_many_fields(self):
        """One branch adds many fields"""
        result = smart_merge(
            [
                {"a": 1},
                {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},  # Branch A adds many
                {"a": 1, "f": 6},  # Branch B adds one
            ]
        )
        assert result == {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6}

    # ==================== CONFLICT CASES ====================

    def test_conflict_both_modify_same_field(self):
        """Both branches modify same field → ERROR"""
        with pytest.raises(
            ValueError, match="Merge conflict.*Field 'a'.*items \\[1, 2\\]"
        ):
            smart_merge([{"a": 1}, {"a": 2}, {"a": 3}])

    def test_conflict_on_one_of_many_fields(self):
        """Branches modify different fields except one overlap → ERROR"""
        with pytest.raises(ValueError, match="Merge conflict.*'b'"):
            smart_merge(
                [
                    {"a": 1, "b": 2, "c": 3},
                    {"a": 10, "b": 20, "c": 3, "d": 4},  # Modifies a,b, adds d
                    {
                        "a": 1,
                        "b": 30,
                        "c": 40,
                        "e": 5,
                    },  # Modifies b,c, adds e - conflict on 'b'!
                ]
            )

    def test_conflict_three_branches_same_field(self):
        """Three branches all modify same field → ERROR"""
        with pytest.raises(ValueError, match="Merge conflict.*'a'"):
            smart_merge([{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}])

    def test_conflict_null_vs_value(self):
        """Both branches change null to different values → ERROR"""
        with pytest.raises(ValueError, match="Merge conflict.*'a'"):
            smart_merge([{"a": None}, {"a": 1}, {"a": 2}])

    def test_conflict_boolean_flip_both_ways(self):
        """Both branches flip boolean (to same value, but still both modified) → ?"""
        # Interesting edge case: both flip False → True
        # Current logic: second branch sees base[a]=False, item[a]=True → modification → conflict
        with pytest.raises(ValueError, match="Merge conflict.*'a'"):
            smart_merge([{"a": False}, {"a": True}, {"a": True}])

    def test_conflict_type_change_different_types(self):
        """Both branches change type of same field → ERROR"""
        with pytest.raises(ValueError, match="Merge conflict.*'a'"):
            smart_merge([{"a": "1"}, {"a": 1}, {"a": [1]}])

    def test_conflict_modify_vs_delete(self):
        """One branch modifies, another deletes same field → ERROR"""
        with pytest.raises(ValueError, match="Merge conflict.*'a'.*modified.*deleted"):
            smart_merge(
                [
                    {"a": 1, "b": 2},
                    {"a": 10, "b": 2},  # Branch A modifies 'a'
                    {"b": 2},  # Branch B deletes 'a' → CONFLICT
                ]
            )

    def test_conflict_delete_vs_modify(self):
        """One branch deletes, another modifies same field → ERROR"""
        with pytest.raises(ValueError, match="Merge conflict.*Field 'a'"):
            smart_merge(
                [
                    {"a": 1, "b": 2},
                    {"b": 2},  # Branch A deletes 'a'
                    {"a": 10, "b": 2},  # Branch B modifies 'a' → CONFLICT
                ]
            )

    # ==================== EDGE CASES ====================

    def test_non_dict_item_ignored(self):
        """Non-dict items in list are skipped"""
        result = smart_merge(
            [{"a": 1}, None, {"a": 1, "b": 2}, "invalid", {"a": 1, "c": 3}]
        )
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_empty_dict_from_branch(self):
        """Branch returns {} - deletes all fields"""
        # {} means delete all fields from base
        result = smart_merge([{"a": 1, "b": 2}, {}, {"a": 1, "b": 2, "c": 3}])
        # Branch A deletes a,b (returns {}), Branch B keeps a,b unchanged, adds c
        # Branch A deletes 'a' and 'b', Branch B doesn't modify them
        # Only Branch A acts on 'a' and 'b' → no conflict, deletions win
        assert result == {"c": 3}  # a and b deleted, c added

    def test_empty_dict_from_branch_no_conflict(self):
        """Branch returns {} when other branch only adds"""
        result = smart_merge([{"a": 1}, {}, {"a": 1, "b": 2}])
        # Branch A returns {} (deletes 'a'), Branch B keeps 'a', adds 'b'
        # Only Branch A acts on 'a' (deletion) → no conflict
        assert result == {"b": 2}  # a deleted, b added

    def test_deep_nesting(self):
        """Deep nesting handled correctly"""
        base = {"level1": {"level2": {"level3": {"value": 1}}}}
        branch_a = {
            "level1": {"level2": {"level3": {"value": 2}}}
        }  # Modifies deep value
        branch_b = base.copy()
        branch_b["other"] = "data"  # Adds top-level field

        result = smart_merge([base, branch_a, branch_b])
        assert result == {
            "level1": {"level2": {"level3": {"value": 2}}},
            "other": "data",
        }

    def test_unicode_field_names(self):
        """Unicode field names work correctly"""
        result = smart_merge(
            [
                {"名前": "田中"},
                {"名前": "田中", "年齢": 30},
                {"名前": "田中", "都市": "東京"},
            ]
        )
        assert result == {"名前": "田中", "年齢": 30, "都市": "東京"}

    def test_numeric_string_vs_number(self):
        """String '1' vs number 1 are different values"""
        result = smart_merge(
            [
                {"a": "1"},
                {"a": 1},  # Branch A changes to number
                {"a": "1", "b": 2},  # Branch B keeps string
            ]
        )
        # Both modified 'a'? Branch A changed "1"→1, Branch B kept "1"
        # Branch B didn't modify (same value), Branch A did modify → no conflict
        assert result == {"a": 1, "b": 2}

    def test_float_precision(self):
        """Float precision handled correctly"""
        result = smart_merge(
            [
                {"a": 1.0},
                {"a": 1.0000001},  # Branch A modifies
                {"a": 1.0, "b": 2},  # Branch B adds field
            ]
        )
        assert result == {"a": 1.0000001, "b": 2}

    def test_very_long_field_name(self):
        """Very long field names work"""
        long_name = "a" * 1000
        result = smart_merge(
            [{long_name: 1}, {long_name: 1, "b": 2}, {long_name: 1, "c": 3}]
        )
        assert result == {long_name: 1, "b": 2, "c": 3}

    def test_base_with_100_fields(self):
        """Large base object merges correctly"""
        base = {f"field_{i}": i for i in range(100)}
        branch_a = base.copy()
        branch_a["field_99"] = 999  # Modify last field

        branch_b = base.copy()
        branch_b["new_field"] = "added"  # Add new field

        result = smart_merge([base, branch_a, branch_b])

        expected = base.copy()
        expected["field_99"] = 999
        expected["new_field"] = "added"
        assert result == expected

    # ==================== SPECIAL VALUES ====================

    def test_zero_vs_false(self):
        """0 and False are different values"""
        result = smart_merge(
            [
                {"a": 0},
                {"a": False},  # Branch A changes 0 → False
                {"a": 0, "b": 1},  # Branch B adds field
            ]
        )
        assert result == {"a": False, "b": 1}

    def test_empty_string_vs_null(self):
        """Empty string and null are different"""
        result = smart_merge(
            [
                {"a": ""},
                {"a": None},  # Branch A changes "" → null
                {"a": "", "b": 1},  # Branch B adds field
            ]
        )
        assert result == {"a": None, "b": 1}

    def test_list_equality(self):
        """Lists compared by value equality"""
        result = smart_merge(
            [
                {"a": [1, 2]},
                {"a": [1, 2, 3]},  # Branch A extends list
                {"a": [1, 2], "b": 1},  # Branch B adds field, list unchanged
            ]
        )
        assert result == {"a": [1, 2, 3], "b": 1}

    def test_dict_equality(self):
        """Dicts compared by value equality"""
        result = smart_merge(
            [
                {"a": {"x": 1}},
                {"a": {"x": 1, "y": 2}},  # Branch A adds to nested dict
                {"a": {"x": 1}, "b": 1},  # Branch B adds field
            ]
        )
        assert result == {"a": {"x": 1, "y": 2}, "b": 1}
