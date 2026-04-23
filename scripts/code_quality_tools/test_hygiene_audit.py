#!/usr/bin/env python3
"""
Test Hygiene Audit Script

This script analyzes test files to identify potential hygiene issues that could
cause flaky tests, contamination between tests, or other reliability problems.

Usage:
    python scripts/test_hygiene_audit.py                    # Audit all tests
    python scripts/test_hygiene_audit.py tests/integration  # Audit specific directory
    python scripts/test_hygiene_audit.py --help             # Show help
"""

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestIssue:
    file_path: str
    line_number: int
    issue_type: str
    description: str
    severity: str  # 'HIGH', 'MEDIUM', 'LOW'


class TestHygieneAuditor:
    """Audits test files for hygiene issues."""

    def __init__(self, test_directory: str):
        self.test_dir = Path(test_directory)
        self.issues: list[TestIssue] = []

    def audit_all_tests(self) -> list[TestIssue]:
        """Run all hygiene checks on all test files."""
        test_files = list(self.test_dir.rglob("test_*.py"))

        for test_file in test_files:
            self.audit_file(test_file)

        return self.issues

    def audit_file(self, file_path: Path):
        """Audit a single test file."""
        try:
            with open(file_path) as f:
                content = f.read()

            tree = ast.parse(content)

            # Run various hygiene checks
            self._check_hardcoded_ids(file_path, content)
            self._check_missing_isolation(file_path, tree, content)
            self._check_shared_state(file_path, tree, content)
            self._check_cleanup_patterns(file_path, tree, content)
            self._check_async_patterns(file_path, tree)
            self._check_fixture_usage(file_path, tree, content)
            self._check_database_patterns(file_path, content)

        except Exception as e:
            self.issues.append(
                TestIssue(
                    file_path=str(file_path),
                    line_number=0,
                    issue_type="PARSE_ERROR",
                    description=f"Failed to parse file: {e}",
                    severity="HIGH",
                )
            )

    def _check_hardcoded_ids(self, file_path: Path, content: str):
        """Check for hardcoded IDs that could cause conflicts."""
        patterns = [
            (
                r'"test-int"(?!\-[a-f0-9]{8})',
                "Hardcoded integration ID without UUID suffix",
            ),
            (
                r'"test-tenant"(?!\-[a-f0-9]{8})',
                "Hardcoded tenant ID - consider unique per test",
            ),
            (r'"test-user"(?!\-[a-f0-9]{8})', "Hardcoded user ID"),
            (r'"test-org"(?!\-[a-f0-9]{8})', "Hardcoded organization ID"),
            (
                r'tenant_id\s*=\s*"[^"]*"',
                "Direct tenant_id assignment - consider fixture",
            ),
        ]

        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            for pattern, description in patterns:
                if re.search(pattern, line):
                    self.issues.append(
                        TestIssue(
                            file_path=str(file_path),
                            line_number=i,
                            issue_type="HARDCODED_ID",
                            description=f"{description}: {line.strip()}",
                            severity="HIGH",
                        )
                    )

    def _check_missing_isolation(self, file_path: Path, tree: ast.AST, content: str):
        """Check for missing test isolation."""

        # Look for tests that don't use proper fixtures
        class TestMethodVisitor(ast.NodeVisitor):
            def __init__(self):
                self.test_methods = []
                self.current_class = None

            def visit_ClassDef(self, node):
                if node.name.startswith("Test"):
                    self.current_class = node.name
                self.generic_visit(node)
                self.current_class = None

            def visit_FunctionDef(self, node):
                if node.name.startswith("test_"):
                    self.test_methods.append(
                        {
                            "name": node.name,
                            "class": self.current_class,
                            "line": node.lineno,
                            "args": [arg.arg for arg in node.args.args],
                        }
                    )

        visitor = TestMethodVisitor()
        visitor.visit(tree)

        for test_method in visitor.test_methods:
            args = test_method["args"]

            # Check for database access without proper session fixture
            method_content = self._get_method_content(content, test_method["line"])

            if any(
                pattern in method_content
                for pattern in ["session.add", "session.commit", "session.execute"]
            ) and not any(
                fixture in args
                for fixture in [
                    "test_session",
                    "integration_test_session",
                    "db_session",
                ]
            ):
                self.issues.append(
                    TestIssue(
                        file_path=str(file_path),
                        line_number=test_method["line"],
                        issue_type="MISSING_DB_FIXTURE",
                        description=f"Test {test_method['name']} uses database but missing session fixture",
                        severity="HIGH",
                    )
                )

    def _check_shared_state(self, file_path: Path, tree: ast.AST, content: str):
        """Check for shared state that could cause test contamination."""

        # Look for class variables, global variables, module-level state
        class StateVisitor(ast.NodeVisitor):
            def __init__(self):
                self.class_vars = []
                self.global_vars = []

            def visit_ClassDef(self, node):
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                self.class_vars.append((target.id, node.lineno))
                self.generic_visit(node)

            def visit_Assign(self, node):
                # Global level assignments
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        self.global_vars.append((target.id, node.lineno))

        visitor = StateVisitor()
        visitor.visit(tree)

        for var_name, line_no in visitor.class_vars:
            if not var_name.startswith("_") and var_name not in ["maxDiff"]:
                self.issues.append(
                    TestIssue(
                        file_path=str(file_path),
                        line_number=line_no,
                        issue_type="SHARED_STATE",
                        description=f"Class variable '{var_name}' could cause test contamination",
                        severity="MEDIUM",
                    )
                )

        for var_name, line_no in visitor.global_vars:
            self.issues.append(
                TestIssue(
                    file_path=str(file_path),
                    line_number=line_no,
                    issue_type="GLOBAL_STATE",
                    description=f"Global variable '{var_name}' could cause test contamination",
                    severity="HIGH",
                )
            )

    def _check_cleanup_patterns(self, file_path: Path, tree: ast.AST, content: str):
        """Check for proper cleanup patterns."""
        lines = content.split("\n")

        # Check for manual cleanup without proper session management
        for i, line in enumerate(lines, 1):
            if re.search(r"session\.delete|session\.execute.*delete", line):
                # Look for surrounding try/finally or proper fixture usage
                context = "\n".join(lines[max(0, i - 5) : i + 5])
                if "finally:" not in context and "@pytest.fixture" not in context:
                    self.issues.append(
                        TestIssue(
                            file_path=str(file_path),
                            line_number=i,
                            issue_type="MANUAL_CLEANUP",
                            description="Manual cleanup without proper exception handling",
                            severity="MEDIUM",
                        )
                    )

    def _check_async_patterns(self, file_path: Path, tree: ast.AST):
        """Check for proper async test patterns."""

        def get_decorator_name(d):
            """Extract full decorator name from AST node."""
            if isinstance(d, ast.Name):
                return d.id
            if isinstance(d, ast.Attribute):
                # Handle chained attributes like pytest.mark.asyncio
                parts = []
                node = d
                while isinstance(node, ast.Attribute):
                    parts.append(node.attr)
                    node = node.value
                if isinstance(node, ast.Name):
                    parts.append(node.id)
                return ".".join(reversed(parts))
            if isinstance(d, ast.Call):
                # Handle decorator calls like @pytest.mark.parametrize(...)
                return get_decorator_name(d.func)
            return str(d)

        class AsyncTestVisitor(ast.NodeVisitor):
            def __init__(self):
                self.async_tests = []

            def visit_AsyncFunctionDef(self, node):
                if node.name.startswith("test_"):
                    self.async_tests.append(
                        {
                            "name": node.name,
                            "line": node.lineno,
                            "decorators": [
                                get_decorator_name(d) for d in node.decorator_list
                            ],
                        }
                    )

        visitor = AsyncTestVisitor()
        visitor.visit(tree)

        for test in visitor.async_tests:
            if "pytest.mark.asyncio" not in str(test["decorators"]):
                self.issues.append(
                    TestIssue(
                        file_path=str(file_path),
                        line_number=test["line"],
                        issue_type="MISSING_ASYNCIO_MARK",
                        description=f"Async test {test['name']} missing @pytest.mark.asyncio",
                        severity="HIGH",
                    )
                )

    def _check_fixture_usage(self, file_path: Path, tree: ast.AST, content: str):
        """Check for proper fixture usage."""
        # Check for direct database URL usage instead of fixtures
        if "postgresql://" in content or "sqlite://" in content:
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if "postgresql://" in line or "sqlite://" in line:
                    self.issues.append(
                        TestIssue(
                            file_path=str(file_path),
                            line_number=i,
                            issue_type="HARDCODED_DB_URL",
                            description="Hardcoded database URL instead of using test fixtures",
                            severity="HIGH",
                        )
                    )

    def _check_database_patterns(self, file_path: Path, content: str):
        """Check for database-specific patterns."""
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # Check for missing commit/rollback patterns
            if "session.add(" in line:
                # Look ahead for commit
                next_lines = lines[i : i + 10]
                if not any(
                    "commit()" in line or "flush()" in line for line in next_lines
                ):
                    self.issues.append(
                        TestIssue(
                            file_path=str(file_path),
                            line_number=i,
                            issue_type="MISSING_COMMIT",
                            description="session.add() without corresponding commit/flush",
                            severity="MEDIUM",
                        )
                    )

            # Check for SQLite usage in integration tests
            if "sqlite" in line.lower() and "integration" in str(file_path):
                self.issues.append(
                    TestIssue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type="SQLITE_IN_INTEGRATION",
                        description="SQLite usage in integration test - should use PostgreSQL",
                        severity="HIGH",
                    )
                )

    def _get_method_content(self, content: str, start_line: int) -> str:
        """Get the content of a method starting from a line number."""
        lines = content.split("\n")
        method_lines = []
        indent_level = None

        for i in range(start_line - 1, len(lines)):
            line = lines[i]

            if indent_level is None and line.strip():
                indent_level = len(line) - len(line.lstrip())

            if (
                line.strip()
                and len(line) - len(line.lstrip()) <= indent_level
                and i > start_line - 1
            ):
                break

            method_lines.append(line)

        return "\n".join(method_lines)

    def print_report(self):
        """Print a formatted report of all issues."""
        if not self.issues:
            print("✅ No test hygiene issues found!")
            return

        # Group by severity
        high_issues = [i for i in self.issues if i.severity == "HIGH"]
        medium_issues = [i for i in self.issues if i.severity == "MEDIUM"]
        low_issues = [i for i in self.issues if i.severity == "LOW"]

        print("\n🔍 Test Hygiene Audit Report")
        print("=" * 50)
        print(f"Total Issues: {len(self.issues)}")
        print(f"High Severity: {len(high_issues)}")
        print(f"Medium Severity: {len(medium_issues)}")
        print(f"Low Severity: {len(low_issues)}")
        print()

        for severity, issues in [
            ("HIGH", high_issues),
            ("MEDIUM", medium_issues),
            ("LOW", low_issues),
        ]:
            if not issues:
                continue

            print(f"🚨 {severity} SEVERITY ISSUES:")
            print("-" * 30)

            # Group by file
            by_file = {}
            for issue in issues:
                if issue.file_path not in by_file:
                    by_file[issue.file_path] = []
                by_file[issue.file_path].append(issue)

            for file_path, file_issues in sorted(by_file.items()):
                print(f"\n📁 {file_path}")
                for issue in sorted(file_issues, key=lambda x: x.line_number):
                    print(
                        f"  Line {issue.line_number}: [{issue.issue_type}] {issue.description}"
                    )
            print()


def main():
    """Run the test hygiene audit."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Audit test files for hygiene issues that could cause flakiness"
    )
    parser.add_argument(
        "test_dir",
        nargs="?",
        default="tests",
        help="Directory to audit (default: tests)",
    )
    parser.add_argument(
        "--fail-on-high",
        action="store_true",
        help="Exit with non-zero code if high-severity issues found",
    )

    args = parser.parse_args()

    if not os.path.exists(args.test_dir):
        print(f"❌ Test directory '{args.test_dir}' not found")
        sys.exit(1)

    print(f"🔍 Auditing tests in: {args.test_dir}")

    auditor = TestHygieneAuditor(args.test_dir)
    issues = auditor.audit_all_tests()
    auditor.print_report()

    # Exit with non-zero code if high-severity issues found
    high_severity_count = len([i for i in issues if i.severity == "HIGH"])
    if args.fail_on_high and high_severity_count > 0:
        print(
            f"\n❌ Found {high_severity_count} high-severity issues that should be addressed."
        )
        sys.exit(1)
    else:
        print(
            "\n✅ No high-severity issues found!"
            if high_severity_count == 0
            else f"\n⚠️  Found {high_severity_count} high-severity issues."
        )


if __name__ == "__main__":
    main()
