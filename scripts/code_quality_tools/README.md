# Code Quality Tools

This directory contains tools to help maintain code quality, prevent common issues in our test suite, and track project metrics.

## Tools

### 🔍 Test Hygiene Audit (`test_hygiene_audit.py`)
Comprehensive analysis of test files to identify hygiene issues that could cause flaky tests, contamination between tests, or other reliability problems.

**Usage:**
```bash
# Audit all tests
python scripts/code-quality-tools/test_hygiene_audit.py

# Audit specific directory
python scripts/code-quality-tools/test_hygiene_audit.py tests/integration

# Fail CI if high-severity issues found
python scripts/code-quality-tools/test_hygiene_audit.py --fail-on-high
```

**Checks for:**
- Hardcoded IDs that could cause conflicts
- Missing test isolation patterns
- Shared state between tests
- Improper cleanup patterns
- Missing async test decorators
- Database hygiene issues

### 🚨 Test Flakiness Detector (`test_flakiness_detector.py`)
Focused detection of patterns that commonly cause test flakiness and isolation issues.

**Usage:**
```bash
# Detect flakiness patterns in all tests
python scripts/code-quality-tools/test_flakiness_detector.py

# Detect in specific directory
python scripts/code-quality-tools/test_flakiness_detector.py tests/integration

# Fail CI if critical issues found
python scripts/code-quality-tools/test_flakiness_detector.py --fail-on-critical
```

**Detects:**
- Hardcoded IDs causing test conflicts (CRITICAL)
- Shared integration IDs between tests (CRITICAL)
- Timing dependencies and sleep-based logic (HIGH)
- Background worker interference (HIGH)
- Database state leakage (MEDIUM-HIGH)
- Async race conditions (MEDIUM)

### 📊 Lines of Code Counter (`count_lines_of_code.py`)
Detailed analysis of codebase size with breakdown by file type and directory.

**Usage:**
```bash
# Count lines with detailed breakdown
python scripts/code_quality_tools/count_lines_of_code.py
```

**Features:**
- Tracks lines of code over time (appends to `code_metrics.json`)
- Excludes vendor code, cache directories, and virtual environments
- Breaks down by Python source, tests, scripts, and other file types
- Calculates test coverage ratios
- Keeps historical measurements (last 50 runs)

## Make Targets

Use these convenient make targets to run the tools:

```bash
# Run comprehensive test hygiene audit
make audit-test-hygiene

# Run flakiness detection
make detect-flakiness

# Count lines of code with detailed breakdown
make count-lines

# Run both test quality tools
make code-quality-check

# Run in CI mode (fails on critical/high severity issues)
make code-quality-ci
```

## Integration

### Pre-commit Hook
Add to `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
    - id: test-flakiness-check
      name: Check for test flakiness patterns
      entry: python scripts/code-quality-tools/test_flakiness_detector.py
      language: system
      args: [--fail-on-critical]
      pass_filenames: false
```

### CI/CD Integration
Add to your CI pipeline:
```bash
# Fail build if critical test hygiene issues found
make code-quality-ci
```

## Contributing

When adding new patterns to detect:

1. Add the pattern detection logic to the appropriate `_detect_*` method
2. Include the risk level (CRITICAL/HIGH/MEDIUM/LOW)
3. Provide a clear description of why this pattern is problematic
4. Add test cases to verify the detection works
5. Update this README with the new pattern

## Examples

### Critical Issues Fixed
- **Hardcoded Integration IDs**: Changed `"test-int"` to `f"test-int-{uuid4().hex[:8]}"` to prevent conflicts
- **Background Worker Interference**: Added `DISABLE_INTEGRATION_WORKER=true` to test environment
- **Shared State**: Identified class variables causing contamination between tests

### Recommended Patterns
```python
# ❌ Bad: Hardcoded ID
integration_id = "test-integration"

# ✅ Good: Unique ID
integration_id = f"test-integration-{uuid4().hex[:8]}"

# ❌ Bad: Shared state
class TestIntegrations:
    shared_data = {}  # This persists between tests!

# ✅ Good: Isolated state
class TestIntegrations:
    def setUp(self):
        self.test_data = {}  # Fresh for each test
```