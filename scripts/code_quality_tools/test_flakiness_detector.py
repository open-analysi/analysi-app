#!/usr/bin/env python3
"""
Test Flakiness Detector

Focuses specifically on patterns that could cause test flakiness, isolation issues,
and the kind of problems we're seeing with run status changes.

Usage:
    python scripts/code-quality-tools/test_flakiness_detector.py                    # Detect in all tests
    python scripts/code-quality-tools/test_flakiness_detector.py tests/integration  # Detect in specific directory
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Flakinessissue:
    file_path: str
    line_number: int
    issue_type: str
    description: str
    risk_level: str  # 'CRITICAL', 'HIGH', 'MEDIUM'


class TestFlakinessDetector:
    """Detects patterns that commonly cause test flakiness."""

    def __init__(self, test_directory: str):
        self.test_dir = Path(test_directory)
        self.issues: list[Flakinessissue] = []

    def detect_all(self) -> list[Flakinessissue]:
        """Run all flakiness detection on all test files."""
        test_files = list(self.test_dir.rglob("test_*.py"))

        for test_file in test_files:
            self.detect_file(test_file)

        return self.issues

    def detect_file(self, file_path: Path):
        """Detect flakiness issues in a single test file."""
        try:
            with open(file_path) as f:
                content = f.read()

            # Focus on the most critical flakiness patterns
            self._detect_hardcoded_ids(file_path, content)
            self._detect_shared_integration_ids(file_path, content)
            self._detect_timing_dependencies(file_path, content)
            self._detect_background_interference(file_path, content)
            self._detect_database_state_leakage(file_path, content)
            self._detect_async_race_conditions(file_path, content)

        except Exception as e:
            self.issues.append(Flakinessissue(
                file_path=str(file_path),
                line_number=0,
                issue_type="PARSE_ERROR",
                description=f"Failed to parse file: {e}",
                risk_level="CRITICAL"
            ))

    def _detect_hardcoded_ids(self, file_path: Path, content: str):
        """Detect hardcoded IDs that cause conflicts between tests."""
        critical_patterns = [
            # These are the exact patterns causing our issues
            (r'"test-int"(?!\-[a-f0-9]{8})', "CRITICAL: Hardcoded integration ID without UUID suffix"),
            (r'"test-tenant"(?![^"]*[a-f0-9]{8})', "HIGH: Hardcoded tenant ID without unique suffix"),
            (r'integration_id\s*=\s*["\']test-', "CRITICAL: Hardcoded integration_id variable"),
            (r'tenant_id\s*=\s*["\']test-tenant["\']', "HIGH: Hardcoded tenant_id = 'test-tenant'"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern, description in critical_patterns:
                if re.search(pattern, line):
                    risk = "CRITICAL" if "CRITICAL" in description else "HIGH"
                    self.issues.append(Flakinessissue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type="HARDCODED_ID_CONFLICT",
                        description=f"{description}: {line.strip()}",
                        risk_level=risk
                    ))

    def _detect_shared_integration_ids(self, file_path: Path, content: str):
        """Detect multiple tests using the same integration ID."""
        # Look for multiple tests in the same file using same integration ID
        integration_id_patterns = re.findall(r'integration_id\s*=\s*["\']([^"\']+)["\']', content)
        test_functions = re.findall(r'def (test_[^(]+)\(', content)

        if len(set(integration_id_patterns)) < len(integration_id_patterns) and len(test_functions) > 1:
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                if 'integration_id' in line:
                    self.issues.append(Flakinessissue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type="SHARED_INTEGRATION_ID",
                        description=f"Multiple tests may share integration ID: {line.strip()}",
                        risk_level="CRITICAL"
                    ))

    def _detect_timing_dependencies(self, file_path: Path, content: str):
        """Detect timing dependencies that could cause flakiness."""
        timing_patterns = [
            (r'sleep\(\d*\.?\d+\)', "Sleep-based timing could cause flakiness"),
            (r'time\.sleep', "time.sleep usage could cause flakiness"),
            (r'asyncio\.sleep\([0-9.]+\)', "Fixed asyncio.sleep could cause timing issues"),
            (r'wait_for.*timeout=\d+', "Fixed timeout values could cause CI flakiness"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern, description in timing_patterns:
                if re.search(pattern, line):
                    self.issues.append(Flakinessissue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type="TIMING_DEPENDENCY",
                        description=f"{description}: {line.strip()}",
                        risk_level="HIGH"
                    ))

    def _detect_background_interference(self, file_path: Path, content: str):
        """Detect potential background process interference."""
        interference_patterns = [
            (r'run_integration|worker\.run_', "Background worker could interfere with test"),
            (r'schedule_executor|cron', "Scheduled jobs could interfere with test"),
            (r'arq|redis.*enqueue', "Background job queue could interfere"),
            (r'patch.*worker', "Worker mocking might not be effective"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern, description in interference_patterns:
                if re.search(pattern, line.lower()):
                    self.issues.append(Flakinessissue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type="BACKGROUND_INTERFERENCE",
                        description=f"{description}: {line.strip()}",
                        risk_level="HIGH"
                    ))

    def _detect_database_state_leakage(self, file_path: Path, content: str):
        """Detect database state that could leak between tests."""
        state_patterns = [
            (r'session\.add.*without.*commit', "Data added without commit could cause state leakage"),
            (r'CREATE TABLE|ALTER TABLE', "DDL changes could affect other tests"),
            (r'INSERT INTO.*VALUES', "Direct SQL inserts could bypass cleanup"),
            (r'session\.execute.*INSERT|UPDATE|DELETE', "Direct SQL execution could bypass cleanup"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # Check for session.add without nearby commit
            if 'session.add(' in line:
                # Look ahead 10 lines for commit
                next_lines = lines[i:i+10]
                if not any('commit()' in l or 'flush()' in l for l in next_lines):
                    self.issues.append(Flakinessissue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type="STATE_LEAKAGE",
                        description=f"session.add() without nearby commit: {line.strip()}",
                        risk_level="MEDIUM"
                    ))

            for pattern, description in state_patterns[1:]:  # Skip the first one, handled above
                if re.search(pattern, line, re.IGNORECASE):
                    self.issues.append(Flakinessissue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type="STATE_LEAKAGE",
                        description=f"{description}: {line.strip()}",
                        risk_level="HIGH"
                    ))

    def _detect_async_race_conditions(self, file_path: Path, content: str):
        """Detect potential async race conditions."""
        race_patterns = [
            (r'async.*for.*in', "Async loops could have race conditions"),
            (r'await.*asyncio\.gather', "Concurrent operations could race"),
            (r'create_task.*await', "Task creation without proper synchronization"),
        ]

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern, description in race_patterns:
                if re.search(pattern, line):
                    self.issues.append(Flakinessissue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type="RACE_CONDITION",
                        description=f"{description}: {line.strip()}",
                        risk_level="MEDIUM"
                    ))

    def print_report(self):
        """Print a focused flakiness report."""
        if not self.issues:
            print("✅ No flakiness patterns detected!")
            return

        # Group by risk level
        critical_issues = [i for i in self.issues if i.risk_level == "CRITICAL"]
        high_issues = [i for i in self.issues if i.risk_level == "HIGH"]
        medium_issues = [i for i in self.issues if i.risk_level == "MEDIUM"]

        print("\n🔍 Test Flakiness Detection Report")
        print("=" * 50)
        print(f"Total Flakiness Issues: {len(self.issues)}")
        print(f"Critical Risk: {len(critical_issues)}")
        print(f"High Risk: {len(high_issues)}")
        print(f"Medium Risk: {len(medium_issues)}")
        print()

        for risk_level, issues in [("CRITICAL", critical_issues), ("HIGH", high_issues), ("MEDIUM", medium_issues)]:
            if not issues:
                continue

            emoji = "🚨" if risk_level == "CRITICAL" else "⚠️" if risk_level == "HIGH" else "ℹ️"
            print(f"{emoji} {risk_level} RISK ISSUES:")
            print("-" * 30)

            # Group by file
            by_file = {}
            for issue in issues:
                if issue.file_path not in by_file:
                    by_file[issue.file_path] = []
                by_file[issue.file_path].append(issue)

            for file_path, file_issues in sorted(by_file.items()):
                rel_path = str(Path(file_path).relative_to(Path.cwd())) if Path(file_path).is_absolute() else file_path
                print(f"\n📁 {rel_path}")
                for issue in sorted(file_issues, key=lambda x: x.line_number):
                    print(f"  Line {issue.line_number}: [{issue.issue_type}] {issue.description}")
            print()

        # Provide specific recommendations for critical issues
        if critical_issues:
            print("🔧 RECOMMENDED ACTIONS:")
            print("-" * 30)
            print("1. Replace hardcoded integration IDs with UUID-suffixed versions")
            print("2. Use unique tenant IDs per test or test class")
            print("3. Ensure proper test isolation for shared resources")
            print("4. Review database cleanup between tests")
            print()


def main():
    """Run the flakiness detection."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Detect flakiness patterns in test files"
    )
    parser.add_argument(
        "test_dir",
        nargs="?",
        default="tests",
        help="Directory to analyze (default: tests)"
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit with non-zero code if critical issues found"
    )

    args = parser.parse_args()

    if not os.path.exists(args.test_dir):
        print(f"❌ Test directory '{args.test_dir}' not found")
        sys.exit(1)

    print(f"🔍 Detecting flakiness patterns in: {args.test_dir}")

    detector = TestFlakinessDetector(args.test_dir)
    issues = detector.detect_all()
    detector.print_report()

    # Exit with non-zero code if critical issues found
    critical_count = len([i for i in issues if i.risk_level == "CRITICAL"])
    if args.fail_on_critical and critical_count > 0:
        print(f"\n❌ Found {critical_count} critical flakiness risks that should be addressed immediately.")
        sys.exit(1)
    else:
        print("\n✅ No critical flakiness patterns detected!" if critical_count == 0 else f"\n⚠️  Found {critical_count} critical flakiness patterns.")


if __name__ == "__main__":
    main()
