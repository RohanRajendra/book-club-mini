#!/usr/bin/env python3
"""Apply the per-package coverage thresholds.

`pytest-cov` accepts one global --cov-fail-under, but this project sets four
different targets. This reads the coverage data pytest already wrote and applies
them per package.

    pytest --cov=app --cov-branch
    python scripts/check_coverage.py

Uses `coverage` directly, which pytest-cov already installs. No new dependency.
"""

from __future__ import annotations

import sys
from pathlib import Path

from coverage import Coverage
from coverage.exceptions import NoDataError

BACKEND = Path(__file__).resolve().parents[1]

# ports/ holds abstract base classes only and is excluded.
THRESHOLDS = {
    "app/domain": 100.0,
    "app/application": 100.0,
    "app/adapters": 90.0,
    "app/interface": 90.0,
}


def rate(measured: int, missing: int) -> float:
    total = measured + missing
    return 100.0 if total == 0 else 100.0 * measured / total


def main() -> int:
    coverage = Coverage(data_file=str(BACKEND / ".coverage"))
    try:
        coverage.load()
    except NoDataError:
        print("No coverage data. Run: pytest --cov=app --cov-branch", file=sys.stderr)
        return 2

    data = coverage.get_data()
    if not data.measured_files():
        print("No coverage data. Run: pytest --cov=app --cov-branch", file=sys.stderr)
        return 2

    failures = []
    print(f"{'package':<20}{'lines':>9}{'branches':>11}{'target':>9}")

    for package, target in THRESHOLDS.items():
        files = [
            path
            for path in data.measured_files()
            if Path(path).is_relative_to(BACKEND / package)
        ]
        if not files:
            print(f"{package:<20}{'—':>9}{'—':>11}{target:>8.0f}%   (not built yet)")
            continue

        statements = missing_statements = branches = missing_branches = 0
        for path in files:
            analysis = coverage.analysis2(path)
            statements += len(analysis[1])
            missing_statements += len(analysis[3])
            numbers = coverage._analyze(path).numbers
            branches += numbers.n_branches
            missing_branches += numbers.n_missing_branches

        line_rate = rate(statements - missing_statements, missing_statements)
        branch_rate = rate(branches - missing_branches, missing_branches)
        worst = min(line_rate, branch_rate)
        mark = "ok" if worst >= target else "FAIL"
        print(
            f"{package:<20}{line_rate:>8.1f}%{branch_rate:>10.1f}%"
            f"{target:>8.0f}%   {mark}"
        )
        if worst < target:
            failures.append(f"{package}: {worst:.1f}% < {target:.0f}%")

    if failures:
        print("\nCoverage below target:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("\nAll coverage targets met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
