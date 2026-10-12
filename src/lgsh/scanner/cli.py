"""Command-line entry point for the scanner."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .report import render_text
from .scan import run_scan
from .snapshot import collect, load_snapshot, save_capture
from .storage import NotResultsFile, default_results_path, write_results


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lgsh-scan",
        description="Check whether this PC is set up for gaming on Linux. Read-only.",
    )
    p.add_argument("--json", action="store_true",
                   help="print the results as JSON instead of the text report")
    p.add_argument("--output", metavar="PATH",
                   help="where to save the results (default: the lgsh state folder, "
                        "or nowhere with --from-capture); '-' means don't save")
    p.add_argument("--capture", metavar="FOLDER",
                   help="also save the raw scan data in FOLDER")
    p.add_argument("--from-capture", metavar="FILE",
                   help="scan a saved capture instead of this PC")
    return p


def main(argv: list[str] | None = None, *, collect_fn=collect, euid_fn=os.geteuid) -> int:
    if euid_fn() == 0:
        print("Run this as your normal user, without sudo.", file=sys.stderr)
        return 2
    args = _parser().parse_args(argv)

    if args.from_capture:
        try:
            snapshot = load_snapshot(Path(args.from_capture))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            print(f"Couldn't read the capture file: {exc}", file=sys.stderr)
            return 1
    else:
        snapshot = collect_fn()

    if args.capture:
        try:
            save_capture(snapshot, Path(args.capture))
        except FileExistsError:
            print(f"A capture already exists in {args.capture}. Choose an empty folder.",
                  file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"Couldn't save the capture: {exc}", file=sys.stderr)
            return 1

    result = run_scan(snapshot)
    data = result.to_dict()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(render_text(result))

    # A scan of a saved capture is not this PC's state: save it only on request.
    save = args.output != "-" and (args.output or not args.from_capture)
    if save:
        path = Path(args.output) if args.output else default_results_path()
        try:
            write_results(path, data)
        except NotResultsFile:
            print(f"{path} already exists and isn't an lgsh results file.", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"Couldn't save results: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
