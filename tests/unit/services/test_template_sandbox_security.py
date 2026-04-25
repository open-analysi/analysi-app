"""Tests for template sandbox security — prevents exec() escape via __subclasses__().

The TransformationNodeExecutor uses exec() with restricted builtins.
These tests verify that common sandbox escape techniques are blocked.
"""

import pytest

from analysi.services.workflow_execution import TransformationNodeExecutor


@pytest.mark.asyncio
class TestTemplateSandboxSecurity:
    """Verify sandbox blocks known escape vectors."""

    @pytest.fixture
    def executor(self):
        return TransformationNodeExecutor()

    async def test_subclasses_escape_blocked(self, executor):
        """Classic escape: ().__class__.__bases__[0].__subclasses__() → import os."""
        malicious_code = """
# Attempt to reach builtins via __subclasses__
for cls in ().__class__.__bases__[0].__subclasses__():
    if 'BuiltinImporter' in str(cls):
        return str(cls)
return "no escape found"
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_dunder_class_access_blocked(self, executor):
        """Block access to __class__ attribute."""
        malicious_code = """
return ().__class__.__name__
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_dunder_bases_access_blocked(self, executor):
        """Block access to __bases__ attribute."""
        malicious_code = """
return object.__bases__
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_getattr_dunder_escape_blocked(self, executor):
        """Block getattr() used to access dunder attributes."""
        malicious_code = """
return getattr((), '__class__')
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_import_blocked(self, executor):
        """Block direct import statements."""
        malicious_code = """
import os
return os.getcwd()
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_builtins_import_blocked(self, executor):
        """Block __import__ builtin."""
        malicious_code = """
return __import__('os').getcwd()
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_exec_inside_template_blocked(self, executor):
        """Block nested exec() calls."""
        malicious_code = """
exec("import os")
return "escaped"
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_eval_inside_template_blocked(self, executor):
        """Block eval() calls."""
        malicious_code = """
return eval("__import__('os').getcwd()")
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_globals_access_blocked(self, executor):
        """Block access to globals()."""
        malicious_code = """
return globals()
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_legitimate_template_works(self, executor):
        """Normal data transformation templates must still work."""
        code = """
result = {}
for key, value in inp.items():
    result[key] = str(value).upper()
return result
"""
        result = await executor.execute_template(
            code, {"name": "test", "value": "hello"}
        )
        assert result["result"]["name"] == "TEST"
        assert result["result"]["value"] == "HELLO"

    async def test_legitimate_list_operations_work(self, executor):
        """List operations (len, sum, min, max, enumerate) must work."""
        code = """
items = inp.get("items", [])
return {
    "count": len(items),
    "total": sum(items),
    "minimum": min(items) if items else None,
    "maximum": max(items) if items else None,
    "indexed": list(enumerate(items)),
}
"""
        result = await executor.execute_template(code, {"items": [3, 1, 4, 1, 5]})
        assert result["result"]["count"] == 5
        assert result["result"]["total"] == 14
        assert result["result"]["minimum"] == 1
        assert result["result"]["maximum"] == 5

    async def test_legitimate_type_checking_works(self, executor):
        """Type checking via isinstance and type() must still work."""
        code = """
if isinstance(inp, dict):
    return {"type_name": type(inp).__name__, "keys": list(inp.keys())}
return {"type_name": "other"}
"""
        result = await executor.execute_template(code, {"a": 1})
        assert result["result"]["type_name"] == "dict"

    async def test_type_subclasses_blocked(self, executor):
        """type().__subclasses__() escape is blocked by dunder attribute check."""
        malicious_code = """
return type.__subclasses__(object)
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_getattribute_mro_escape_blocked(self, executor):
        """Block type.__getattribute__(obj, '__mro__') indirection escape."""
        malicious_code = """
mro = type.__getattribute__(int, "__mro__")
return str(mro)
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_getattribute_subclasses_escape_blocked(self, executor):
        """Block type.__getattribute__(obj, '__subclasses__') indirection escape."""
        malicious_code = """
sub = type.__getattribute__(object, "__subclasses__")
return str(sub())
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_object_getattribute_escape_blocked(self, executor):
        """Block object.__getattribute__ indirection."""
        malicious_code = """
cls = object.__getattribute__((), "__class__")
return str(cls)
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_arbitrary_dunder_via_string_blocked(self, executor):
        """Any dunder attribute access pattern should be blocked, not just a known list."""
        malicious_code = """
x = ().__class__.__bases__
return str(x)
"""
        with pytest.raises((ValueError, NameError)):
            await executor.execute_template(malicious_code, {"test": 1})

    async def test_legitimate_dict_copy_works(self, executor):
        """Dict copy patterns used in templates must work."""
        code = """
result = inp.copy()
result['added'] = True
return result
"""
        result = await executor.execute_template(code, {"original": True})
        assert result["result"]["original"] is True
        assert result["result"]["added"] is True
