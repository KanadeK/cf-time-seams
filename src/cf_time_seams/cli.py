"""Command-line interface with explicit cadence and stable exit statuses."""

import argparse
import glob
import json
import sys

from . import __version__
from .core import InputError, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preflight local NetCDF time-axis collections.")
    parser.add_argument("files", nargs="+", help="local files or quoted glob patterns")
    cadence = parser.add_mutually_exclusive_group(required=True)
    cadence.add_argument("--step-seconds", help="expected positive fixed step")
    cadence.add_argument("--monthly", action="store_true", help="same day/time each calendar month")
    parser.add_argument("--tolerance-seconds", default="0")
    parser.add_argument("--time", default="time", help="root time variable name")
    parser.add_argument("--check-bounds", action="store_true")
    parser.add_argument("--max-points", type=int, default=1_000_000)
    parser.add_argument("--max-findings", type=int, default=100)
    parser.add_argument("--json", action="store_true", help="write a JSON report to stdout")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        files = []
        for value in args.files:
            matches = sorted(glob.glob(value)) if glob.has_magic(value) else [value]
            if not matches:
                raise InputError(f"no files match {value!r}")
            files.extend(matches)
        report = audit(
            files,
            step_seconds=args.step_seconds,
            monthly=args.monthly,
            tolerance_seconds=args.tolerance_seconds,
            time_name=args.time,
            check_bounds=args.check_bounds,
            max_points=args.max_points,
            max_findings=args.max_findings,
        )
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
        else:
            print(
                f"{'PASS' if report['ok'] else 'FAIL'}: {report['files']} files, "
                f"{report['points']} points, {report['finding_count']} findings"
            )
            for item in report["findings"]:
                print(json.dumps(item, ensure_ascii=True))
            if report["findings_omitted"]:
                print(f"{report['findings_omitted']} more findings omitted")
        return 0 if report["ok"] else 1
    except (InputError, OSError) as exc:
        if args.json:
            print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}))
        else:
            print(f"Input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
