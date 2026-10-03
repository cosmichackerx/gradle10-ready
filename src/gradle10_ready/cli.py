"""Command line interface."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .report import RENDERERS, meets_threshold
from .rules import RULES
from .diffmode import GitError, scan_against_base
from .scan import Result, apply_fixes, scan


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="gradle10-ready", description="Find what Gradle 10 removes in your build scripts, without running Gradle.")
    p.add_argument("path", nargs="*", default=["."], help="project directory or build file(s) (default: .); several files are what pre-commit passes")
    p.add_argument("-f", "--format", choices=sorted(RENDERERS), default="text")
    p.add_argument("-o", "--output", help="write the report to a file instead of stdout")
    p.add_argument("--fail-on", choices=["error", "warning", "never"], default="error", help="lowest severity that gives exit code 1 (default: error)")
    p.add_argument("--ignore", action="append", default=[], metavar="GLOB", help="path glob to skip (repeatable)")
    p.add_argument("--disable", action="append", default=[], metavar="RULE", help="turn a rule off (repeatable)")
    p.add_argument("--only", action="append", default=[], metavar="RULE", help="run only this rule (repeatable)")
    p.add_argument("--base", metavar="REF", help="PR mode: report only findings that are new compared to this git revision (merge base with HEAD)")
    p.add_argument("--fix", action="store_true", help="rewrite files in place for the rules that have a safe automatic fix")
    p.add_argument("--list-rules", action="store_true")
    p.add_argument("--version", action="version", version=f"gradle10-ready {__version__}")
    a = p.parse_args(argv)
    if a.list_rules:
        for r in RULES.values():
            print(f"{r.id:<30} {r.severity:<8} {'fix ' if r.fixable else '    '}{'oracle ' if r.oracle else 'docs   '}{r.summary}")
        return 0
    for rid in a.disable + a.only:
        if rid not in RULES:
            print(f"unknown rule: {rid} (see --list-rules)", file=sys.stderr)
            return 2
    if len(a.path) > 1 and a.base:
        print("--base takes a single path", file=sys.stderr)
        return 2
    if a.base and a.fix:
        print("--base and --fix cannot be combined", file=sys.stderr)
        return 2
    if a.fix:
        files = edits = 0
        for path in a.path:
            f, e = apply_fixes(path, a.ignore, a.disable, a.only)
            files, edits = files + f, edits + e
        print(f"fixed {edits} place(s) in {files} file(s)", file=sys.stderr)
    if a.base:
        try:
            r = scan_against_base(a.path[0], a.base, a.ignore, a.disable, a.only)
        except GitError as e:
            print(f"gradle10-ready: {e}", file=sys.stderr)
            return 2
    else:
        r = Result()
        for path in a.path:
            one = scan(path, a.ignore, a.disable, a.only)
            if os.path.isfile(path) and len(a.path) > 1:  # a single file is reported as its basename; several files keep the path they were given
                for f in one.findings:
                    f.file = os.path.normpath(path).replace(os.sep, "/")
            r.findings += one.findings
            r.files_scanned += one.files_scanned
    text = RENDERERS[a.format](r)
    if a.output:
        with open(a.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 1 if meets_threshold(r, a.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
