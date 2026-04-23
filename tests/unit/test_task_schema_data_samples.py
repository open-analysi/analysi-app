"""
Unit tests to verify that task schema accepts any JSON-serializable type in data_samples.

This test ensures that the constraint removal for data_samples remains in place,
allowing tasks to accept strings, numbers, arrays, objects, etc., not just dictionaries.
"""

from analysi.models.auth import SYSTEM_USER_ID
from analysi.schemas.task import TaskCreate, TaskUpdate


class TestTaskSchemaDataSamples:
    """Test that task schemas accept any type in data_samples field."""

    def test_task_create_accepts_string_data_samples(self):
        """Test that TaskCreate accepts strings in data_samples."""
        task_data = {
            "name": "Test Task",
            "script": "return input",
            "data_samples": ["192.168.1.1", "10.0.0.1", "localhost"],
        }

        task = TaskCreate(**task_data)
        assert task.data_samples == ["192.168.1.1", "10.0.0.1", "localhost"]

    def test_task_create_accepts_number_data_samples(self):
        """Test that TaskCreate accepts numbers in data_samples."""
        task_data = {
            "name": "Test Task",
            "script": "return input * 2",
            "data_samples": [42, 3.14, -10, 0],
        }

        task = TaskCreate(**task_data)
        assert task.data_samples == [42, 3.14, -10, 0]

    def test_task_create_accepts_dict_data_samples(self):
        """Test that TaskCreate still accepts dictionaries in data_samples."""
        task_data = {
            "name": "Test Task",
            "script": "return input",
            "data_samples": [
                {"ip": "192.168.1.1", "port": 8080},
                {"user": "alice", "role": "admin"},
            ],
        }

        task = TaskCreate(**task_data)
        assert task.data_samples[0]["ip"] == "192.168.1.1"
        assert task.data_samples[1]["user"] == "alice"

    def test_task_create_accepts_list_data_samples(self):
        """Test that TaskCreate accepts nested lists in data_samples."""
        task_data = {
            "name": "Test Task",
            "script": "return input",
            "data_samples": [
                ["item1", "item2"],
                [1, 2, 3],
                [{"nested": "object"}],
            ],
        }

        task = TaskCreate(**task_data)
        assert task.data_samples[0] == ["item1", "item2"]
        assert task.data_samples[1] == [1, 2, 3]
        assert task.data_samples[2] == [{"nested": "object"}]

    def test_task_create_accepts_mixed_data_samples(self):
        """Test that TaskCreate accepts mixed types in data_samples."""
        task_data = {
            "name": "Test Task",
            "script": "return input",
            "data_samples": [
                "string_value",
                42,
                {"key": "value"},
                ["list", "of", "items"],
                3.14159,
                True,
                False,
                None,
            ],
        }

        task = TaskCreate(**task_data)
        assert len(task.data_samples) == 8
        assert task.data_samples[0] == "string_value"
        assert task.data_samples[1] == 42
        assert task.data_samples[2] == {"key": "value"}
        assert task.data_samples[3] == ["list", "of", "items"]
        assert task.data_samples[4] == 3.14159
        assert task.data_samples[5] is True
        assert task.data_samples[6] is False
        assert task.data_samples[7] is None

    def test_task_update_accepts_any_data_samples(self):
        """Test that TaskUpdate also accepts any type in data_samples."""
        task_update = TaskUpdate(
            data_samples=["string", 123, {"dict": "value"}, [1, 2, 3]]
        )

        assert task_update.data_samples == ["string", 123, {"dict": "value"}, [1, 2, 3]]

    def test_task_create_with_empty_data_samples(self):
        """Test that TaskCreate accepts empty data_samples list."""
        task_data = {
            "name": "Test Task",
            "script": "return 'no input'",
            "data_samples": [],
        }

        task = TaskCreate(**task_data)
        assert task.data_samples == []

    def test_task_create_with_none_data_samples(self):
        """Test that TaskCreate accepts None for data_samples (optional field)."""
        task_data = {
            "name": "Test Task",
            "script": "return 'no samples'",
            "data_samples": None,
        }

        task = TaskCreate(**task_data)
        assert task.data_samples is None

    def test_task_create_without_data_samples(self):
        """Test that TaskCreate works without data_samples field."""
        task_data = {
            "name": "Test Task",
            "script": "return 'minimal task'",
        }

        task = TaskCreate(**task_data)
        assert task.data_samples is None

    def test_real_world_edr_example(self):
        """Test a real-world example with IP addresses as strings."""
        task_data = {
            "name": "Echo EDR Pull Demo",
            "description": "Pull EDR data for IP addresses",
            "script": """
ip = input
processes = app::echo_edr::pull_processes(ip=ip)
browser = app::echo_edr::pull_browser_history(ip=ip)
return {"processes": processes, "browser": browser}
""",
            "data_samples": [
                "192.168.1.100",  # Simple IP string
                "10.0.0.50",  # Another IP
                "172.16.20.8",  # Internal IP
            ],
            "categories": ["Security", "EDR"],
            "created_by": str(SYSTEM_USER_ID),
        }

        task = TaskCreate(**task_data)
        assert task.data_samples == ["192.168.1.100", "10.0.0.50", "172.16.20.8"]
        assert all(isinstance(ip, str) for ip in task.data_samples)

    def test_complex_nested_structures(self):
        """Test that deeply nested structures work in data_samples."""
        complex_data = {
            "alert": {
                "id": "alert-123",
                "ips": ["192.168.1.1", "10.0.0.1"],
                "metadata": {
                    "severity": 9,
                    "tags": ["malware", "edr"],
                    "nested": {"deep": {"value": "works"}},
                },
            }
        }

        task_data = {
            "name": "Complex Task",
            "script": "return input",
            "data_samples": [complex_data],
        }

        task = TaskCreate(**task_data)
        assert (
            task.data_samples[0]["alert"]["metadata"]["nested"]["deep"]["value"]
            == "works"
        )
