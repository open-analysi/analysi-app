#!/usr/bin/env python3
"""API response-time benchmark for key endpoints.

Measures latency across health checks and tenant-scoped list endpoints
(the read-heavy calls the UI makes). Useful for:
  - Spotting regressions after code changes
  - Comparing before/after with --save and --compare
  - CI gates with --ci (fails if median exceeds threshold)

Environment variables:
  ANALYSI_BENCHMARK_BASE_URL  (default: http://localhost:8001)
  ANALYSI_BENCHMARK_TENANT    (default: default)
  ANALYSI_BENCHMARK_API_KEY   (default: dev-owner-api-key-change-in-production)

Examples:
  # Quick local run
  python scripts/code_quality_tools/api_benchmark.py

  # Save baseline, make changes, compare
  python scripts/code_quality_tools/api_benchmark.py --save /tmp/before.json
  python scripts/code_quality_tools/api_benchmark.py --save /tmp/after.json
  python scripts/code_quality_tools/api_benchmark.py --compare /tmp/before.json /tmp/after.json

  # CI mode — fail if any endpoint median > 500ms or total > 3000ms
  python scripts/code_quality_tools/api_benchmark.py --ci
"""

import argparse
import json
import os
import statistics
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("ANALYSI_BENCHMARK_BASE_URL", "http://localhost:8001")
TENANT = os.environ.get("ANALYSI_BENCHMARK_TENANT", "default")
API_KEY = os.environ.get(
    "ANALYSI_BENCHMARK_API_KEY", "dev-owner-api-key-change-in-production"
)

# CI thresholds (milliseconds)
CI_MAX_MEDIAN_MS = 500  # per-endpoint median
CI_MAX_TOTAL_MEDIAN_MS = 3000  # sum of all medians

# Endpoints: (method, path, body_or_none)
ENDPOINTS = [
    # Health
    ("GET", "/healthz", None),
    ("GET", "/readyz", None),
    # Tenant-scoped list endpoints (read-heavy, typical UI calls)
    ("GET", f"/v1/{TENANT}/alerts", None),
    ("GET", f"/v1/{TENANT}/alerts/search", None),
    ("GET", f"/v1/{TENANT}/integrations", None),
    ("GET", f"/v1/{TENANT}/tasks", None),
    ("GET", f"/v1/{TENANT}/workflows", None),
    ("GET", f"/v1/{TENANT}/dispositions", None),
    ("GET", f"/v1/{TENANT}/credentials", None),
    ("GET", f"/v1/{TENANT}/artifacts", None),
    ("GET", f"/v1/{TENANT}/audit-trail", None),
    ("GET", f"/v1/{TENANT}/alert-routing-rules", None),
    ("GET", f"/v1/{TENANT}/control-event-rules", None),
    ("GET", f"/v1/{TENANT}/integrations/tools/all", None),
]


def do_request(method: str, path: str, body: dict | None = None) -> tuple[int, float]:
    """Single request → (status_code, elapsed_seconds)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"X-API-Key": API_KEY}
    if body:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        resp = urlopen(req, timeout=30)  # nosec B310 - URL built from local config
        status = resp.status
        resp.read()
    except URLError as e:
        status = getattr(e, "code", 0) or 0
    return status, time.perf_counter() - start


def warmup(rounds: int = 5):
    """Warm up connections and server caches."""
    for _ in range(rounds):
        do_request("GET", "/healthz")


def benchmark(rounds: int = 10) -> dict:
    """Run all endpoints, return results dict keyed by endpoint string."""
    warmup()
    results = {}
    for method, path, body in ENDPOINTS:
        timings = []
        statuses = []
        for _ in range(rounds):
            status, elapsed = do_request(method, path, body)
            timings.append(elapsed * 1000)
            statuses.append(status)

        ok_count = sum(1 for s in statuses if 200 <= s < 300)
        results[f"{method} {path}"] = {
            "min_ms": round(min(timings), 2),
            "max_ms": round(max(timings), 2),
            "mean_ms": round(statistics.mean(timings), 2),
            "median_ms": round(statistics.median(timings), 2),
            "p95_ms": round(sorted(timings)[int(len(timings) * 0.95)], 2),
            "stdev_ms": (
                round(statistics.stdev(timings), 2) if len(timings) > 1 else 0
            ),
            "ok_rate": f"{ok_count}/{rounds}",
        }
    return results


def print_results(results: dict, label: str = ""):
    if label:
        print(f"\n{'=' * 80}")
        print(f"  {label}")
        print(f"{'=' * 80}")

    header = (
        f"{'Endpoint':<55} {'Mean':>8} {'Med':>8} "
        f"{'P95':>8} {'Min':>8} {'Max':>8} {'OK':>6}"
    )
    print(f"\n{header}")
    print("-" * 103)

    total_mean = 0.0
    total_median = 0.0
    for endpoint, s in results.items():
        total_mean += s["mean_ms"]
        total_median += s["median_ms"]
        print(
            f"{endpoint:<55} "
            f"{s['mean_ms']:>7.1f}ms "
            f"{s['median_ms']:>7.1f}ms "
            f"{s['p95_ms']:>7.1f}ms "
            f"{s['min_ms']:>7.1f}ms "
            f"{s['max_ms']:>7.1f}ms "
            f"{s['ok_rate']:>6}"
        )

    print("-" * 103)
    print(
        f"{'TOTAL (sum of means / medians)':<55} "
        f"{total_mean:>7.1f}ms {total_median:>7.1f}ms"
    )
    print()


def save_results(results: dict, filepath: str):
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {filepath}")


def compare(file_a: str, file_b: str):
    with open(file_a) as f:
        a = json.load(f)
    with open(file_b) as f:
        b = json.load(f)

    print(f"\n{'=' * 90}")
    print(f"  Comparison: {file_a} vs {file_b}")
    print(f"{'=' * 90}")
    print(f"\n{'Endpoint':<55} {'Before':>8} {'After':>8} {'Diff':>8} {'%':>7}")
    print("-" * 90)

    total_before = 0.0
    total_after = 0.0
    for endpoint in a:
        if endpoint not in b:
            continue
        before = a[endpoint]["median_ms"]
        after = b[endpoint]["median_ms"]
        total_before += before
        total_after += after
        diff = after - before
        pct = ((diff) / before * 100) if before > 0 else 0
        tag = "SLOWER" if pct > 20 else ("faster" if pct < -20 else "~same")
        print(
            f"{endpoint:<55} "
            f"{before:>7.1f}ms "
            f"{after:>7.1f}ms "
            f"{diff:>+7.1f}ms "
            f"{pct:>+6.1f}% "
            f"{tag}"
        )

    diff_total = total_after - total_before
    pct_total = ((diff_total) / total_before * 100) if total_before > 0 else 0
    print("-" * 90)
    print(
        f"{'TOTAL (medians)':<55} "
        f"{total_before:>7.1f}ms "
        f"{total_after:>7.1f}ms "
        f"{diff_total:>+7.1f}ms "
        f"{pct_total:>+6.1f}%"
    )
    print()


def ci_check(results: dict) -> bool:
    """Return True if all endpoints pass CI thresholds."""
    failures = []
    total_median = 0.0

    for endpoint, s in results.items():
        total_median += s["median_ms"]
        if s["median_ms"] > CI_MAX_MEDIAN_MS:
            failures.append(
                f"  FAIL: {endpoint} median {s['median_ms']:.1f}ms "
                f"> {CI_MAX_MEDIAN_MS}ms"
            )

    if total_median > CI_MAX_TOTAL_MEDIAN_MS:
        failures.append(
            f"  FAIL: total median {total_median:.1f}ms > {CI_MAX_TOTAL_MEDIAN_MS}ms"
        )

    if failures:
        print("\nCI threshold violations:")
        for f in failures:
            print(f)
        return False

    print(
        f"\nCI check passed: total median {total_median:.1f}ms "
        f"<= {CI_MAX_TOTAL_MEDIAN_MS}ms"
    )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="API response-time benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=10,
        help="Requests per endpoint (default: 10)",
    )
    parser.add_argument("--label", type=str, default="", help="Run label")
    parser.add_argument("--save", type=str, help="Save results to JSON file")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="Compare two saved results (uses median)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help=f"CI mode: fail if median > {CI_MAX_MEDIAN_MS}ms "
        f"or total > {CI_MAX_TOTAL_MEDIAN_MS}ms",
    )
    args = parser.parse_args()

    if args.compare:
        compare(args.compare[0], args.compare[1])
        return

    results = benchmark(rounds=args.rounds)
    print_results(results, label=args.label or "API Benchmark")

    if args.save:
        save_results(results, args.save)

    if args.ci and not ci_check(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
