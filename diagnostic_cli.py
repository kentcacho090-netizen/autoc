"""Command-line diagnostics entry point for AutoC."""
from __future__ import annotations

import argparse

from diagnostic_report import DiagnosticReporter


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect AutoC's latest local diagnostic snapshot.")
    parser.add_argument("--directory", default="diagnostics", help="Diagnostic directory")
    args = parser.parse_args()
    reporter = DiagnosticReporter(args.directory)
    print(reporter.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
