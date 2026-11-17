"""``ipap-validate`` / ``scripts/validate_spec.py``: run all static SPEC consistency checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..data import RepoData
from ..paths import repo_root
from .spec_checks import run_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: auto-detect)")
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else repo_root()
    report = run_all(RepoData(root=root))
    for result in report.results:
        print(f"{'OK  ' if result.ok else 'FAIL'} {result.name}")
        for problem in result.problems:
            print(f"     - {problem}")
    data = RepoData(root=root)
    if report.ok:
        n_items = len(data.preview_manifest["items"])
        print(
            f"OK: 41 legacy mappings + 14 NEW + 10 APP with prompts; 48 styles / 8 groups; "
            f"{n_items} planned previews (none claimed generated unless approved with real files)."
        )
        return 0
    print(f"FAILED: {len(report.problems)} problem(s)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
