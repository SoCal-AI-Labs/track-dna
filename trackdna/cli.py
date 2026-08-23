from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trackdna.analyze import analyze_track
from trackdna.compare import compare_tracks, format_compare
from trackdna.ingest import resolve_bundle, resolve_source
from trackdna.report import format_report
from trackdna.suno import format_suno


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="track_dna",
        description="Measured song analysis and Suno-ready copy/paste prompts.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    analyze = sub.add_parser("analyze", help="Analyze a local file or URL")
    analyze.add_argument("source", help="WAV/MP3/FLAC path or audio URL")
    analyze.add_argument("--json", dest="json_path", help="Write machine-readable JSON")
    analyze.add_argument("--suno", action="store_true", help="Print Suno Style + structure blocks")
    analyze.add_argument("--segments", type=int, default=None, help="Target section count")
    analyze.add_argument("--min-len", type=float, default=8.0, help="Minimum section length (sec)")

    compare = sub.add_parser("compare", help="A/B deltas between two mixes")
    compare.add_argument("a")
    compare.add_argument("b")

    sub.add_parser("app", help="Launch the desktop app")

    args = parser.parse_args(argv)

    if args.cmd == "app":
        from trackdna.gui import main as gui_main

        gui_main()
        return 0

    try:
        if args.cmd == "analyze":
            return _cmd_analyze(args)
        if args.cmd == "compare":
            return _cmd_compare(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_analyze(args) -> int:
    path, meta = resolve_bundle(args.source)
    dna = analyze_track(
        path,
        segments=args.segments,
        min_len=args.min_len,
        source_meta=meta,
        progress=_print_progress,
    )
    print(format_report(dna))
    if args.suno:
        suno = format_suno(dna)
        print()
        print(suno["paste"])
    if args.json_path:
        dest = Path(args.json_path)
        dest.write_text(json.dumps(dna, indent=2), encoding="utf-8")
        print(f"\nWrote {dest}")
    return 0


def _cmd_compare(args) -> int:
    a = resolve_source(args.a)
    b = resolve_source(args.b)
    result = compare_tracks(a, b, progress=_print_progress)
    print(format_compare(result))
    return 0


def _print_progress(message: str) -> None:
    print(f"… {message}", file=sys.stderr)
