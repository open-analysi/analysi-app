"""Test the safe_get helper function."""

from alert_normalizer.mappers.splunk_notable import safe_get


class TestSafeGet:
    """Test the safe_get function for safely accessing nested dictionary values."""

    def test_simple_get(self):
        """Test getting a simple top-level value."""
        data = {"key": "value"}
        assert safe_get(data, "key") == "value"

    def test_nested_get(self):
        """Test getting a nested value."""
        data = {"level1": {"level2": {"level3": "deep_value"}}}
        assert safe_get(data, "level1.level2.level3") == "deep_value"

    def test_none_object(self):
        """Test that None object returns default."""
        assert safe_get(None, "any.path") is None
        assert safe_get(None, "any.path", "default") == "default"

    def test_missing_key(self):
        """Test that missing key returns default."""
        data = {"key": "value"}
        assert safe_get(data, "missing") is None
        assert safe_get(data, "missing", "default") == "default"

    def test_missing_nested_key(self):
        """Test that missing nested key returns default."""
        data = {"level1": {"level2": "value"}}
        assert safe_get(data, "level1.level3") is None
        assert safe_get(data, "level1.level3", "default") == "default"

    def test_partial_path_missing(self):
        """Test that partially missing path returns default."""
        data = {"level1": {}}
        assert safe_get(data, "level1.level2.level3") is None
        assert safe_get(data, "level1.level2.level3", "default") == "default"

    def test_non_dict_in_path(self):
        """Test that encountering non-dict in path returns default."""
        data = {"level1": "string_value"}
        assert safe_get(data, "level1.level2") is None
        assert safe_get(data, "level1.level2", "default") == "default"

    def test_empty_path(self):
        """Test that empty path returns the object itself."""
        data = {"key": "value"}
        # Empty string path should return the original object
        assert safe_get(data, "") == {"key": "value"}

    def test_none_value(self):
        """Test that None values are handled correctly."""
        data = {"key": None}
        # None is a valid value, not missing
        assert safe_get(data, "key") is None
        assert safe_get(data, "key", "default") == "default"

    def test_zero_value(self):
        """Test that zero/false values are returned correctly."""
        data = {"zero": 0, "false": False, "empty": ""}
        assert safe_get(data, "zero") == 0
        assert safe_get(data, "false") is False
        assert safe_get(data, "empty") == ""

    def test_list_in_data(self):
        """Test behavior with lists in the data structure."""
        data = {"items": ["a", "b", "c"]}
        # Should return the list itself
        assert safe_get(data, "items") == ["a", "b", "c"]
        # Can't traverse into list with dot notation
        assert safe_get(data, "items.0") is None

    def test_real_world_network_info(self):
        """Test with real-world network_info structure."""
        data = {
            "network_info": {
                "src_ip": "192.168.1.1",
                "dest_ip": "10.0.0.1",
                "src_port": "12345",
                "dest_port": "443",
            }
        }
        assert safe_get(data, "network_info.src_ip") == "192.168.1.1"
        assert safe_get(data, "network_info.dest_port") == "443"
        assert safe_get(data, "network_info.protocol") is None
        assert safe_get(data, "network_info.protocol", "tcp") == "tcp"

    def test_real_world_process_info(self):
        """Test with real-world process_info structure."""
        data = {
            "process_info": {
                "command_line": "C:\\Windows\\System32\\cmd.exe /c whoami",
                "name": "cmd.exe",
            }
        }
        assert (
            safe_get(data, "process_info.command_line")
            == "C:\\Windows\\System32\\cmd.exe /c whoami"
        )
        assert safe_get(data, "process_info.name") == "cmd.exe"
        assert safe_get(data, "process_info.pid") is None

    def test_complex_nested_with_defaults(self):
        """Test complex nested access with various defaults."""
        data = {
            "primary_risk_entity_type": "user",
            "primary_risk_entity_value": "admin",
            "network_info": {"dest_hostname": "server01"},
        }

        # Should get user value
        assert safe_get(data, "primary_risk_entity_value") == "admin"

        # Should get hostname
        assert safe_get(data, "network_info.dest_hostname") == "server01"

        # Missing nested field with default
        assert safe_get(data, "network_info.src_hostname", "unknown") == "unknown"

        # Completely missing branch
        assert safe_get(data, "process_info.command_line", "") == ""
