"""Combine multiple coverage.json files by unioning executed lines per file.

Coverage.py's own ``coverage combine`` operates on ``.coverage.*`` SQLite
data files, but our CI uploads ``coverage.json`` artifacts (one per
suite — unit, alert_normalizer, integration). This script lets us reason
about the *combined* coverage that any one PR achieves across suites,
which is the picture that matters when picking the next test gap to
close.

Each input file is a coverage.json (the format produced by
``pytest --cov-report=json``). The output is the same format, with each
file's ``executed_lines`` set to the union across inputs and
``missing_lines`` set to ``(union of missing) - (union of executed)``.

Usage::

    poetry run python scripts/code_quality_tools/combine_coverage.py \
        out.json unit.json integration.json

Then::

    jq '.totals.percent_covered_display' out.json   # combined %
    jq '.files["src/foo.py"].summary' out.json      # per-file combined

See ``docs/projects/coverage-uplift.md`` for context.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def combine(inputs: list[Path]) -> dict:
    """Return a coverage.json-shaped dict that is the union of *inputs*."""
    per_file: dict[str, dict[str, set[int]]] = {}

    for src in inputs:
        with src.open() as fh:
            data = json.load(fh)
        for fname, fdata in data.get("files", {}).items():
            entry = per_file.setdefault(
                fname,
                {"executed": set(), "missing": set(), "excluded": set()},
            )
            entry["executed"].update(fdata.get("executed_lines", []))
            entry["missing"].update(fdata.get("missing_lines", []))
            entry["excluded"].update(fdata.get("excluded_lines", []))

    # missing = union(missing) - union(executed) — a line that's missing in
    # one suite but executed in another is genuinely covered.
    out_files: dict[str, dict] = {}
    total_executed = 0
    total_missing = 0
    total_excluded = 0
    for fname, entry in per_file.items():
        executed = entry["executed"]
        missing = entry["missing"] - executed
        excluded = entry["excluded"]
        statements = len(executed) + len(missing)
        pct = 100.0 if statements == 0 else len(executed) * 100.0 / statements
        out_files[fname] = {
            "executed_lines": sorted(executed),
            "missing_lines": sorted(missing),
            "excluded_lines": sorted(excluded),
            "summary": {
                "covered_lines": len(executed),
                "missing_lines": len(missing),
                "excluded_lines": len(excluded),
                "num_statements": statements,
                "percent_covered": pct,
                "percent_covered_display": f"{pct:.2f}",
            },
        }
        total_executed += len(executed)
        total_missing += len(missing)
        total_excluded += len(excluded)

    grand = total_executed + total_missing
    total_pct = 100.0 if grand == 0 else total_executed * 100.0 / grand
    return {
        "files": out_files,
        "totals": {
            "covered_lines": total_executed,
            "missing_lines": total_missing,
            "excluded_lines": total_excluded,
            "num_statements": grand,
            "percent_covered": total_pct,
            "percent_covered_display": f"{total_pct:.2f}",
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "Usage: combine_coverage.py output.json input1.json [input2.json ...]",
            file=sys.stderr,
        )
        return 1
    out_path = Path(argv[1])
    inputs = [Path(p) for p in argv[2:]]
    output = combine(inputs)
    out_path.write_text(json.dumps(output, indent=2))
    totals = output["totals"]
    print(
        f"Wrote {out_path}: {totals['percent_covered']:.2f}% "
        f"({totals['covered_lines']}/{totals['num_statements']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
