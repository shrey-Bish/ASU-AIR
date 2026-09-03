"""Command line entry point.

    python -m slidesight deck.pptx -o out/deck.remediated.pptx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .apply import ACTION_AUTO, ACTION_DECORATIVE, ACTION_REVIEW
from .pipeline import remediate

MARK = {ACTION_AUTO: "applied ", ACTION_DECORATIVE: "decor.  ", ACTION_REVIEW: "REVIEW  "}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="slidesight",
        description="Add real alt text to a PowerPoint deck using ASU AIR.",
    )
    p.add_argument("input", help="path to a .pptx file")
    p.add_argument("-o", "--output", help="where to write the remediated deck")
    p.add_argument("-r", "--report", help="where to write the JSON report")
    p.add_argument(
        "-c", "--concurrency", type=int, default=4, help="parallel calls (default 4)"
    )
    p.add_argument(
        "--no-summary", action="store_true", help="skip the per-deck summary call"
    )
    p.add_argument("--quiet", action="store_true", help="only print the final counts")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source = Path(args.input)
    if not source.is_file():
        print(f"error: no such file: {source}", file=sys.stderr)
        return 1
    if source.suffix.lower() != ".pptx":
        print(
            f"error: {source.suffix or 'this file'} is not supported -- PowerPoint "
            ".pptx only.\n"
            "       Legacy .ppt is a different (binary) format; convert it first:\n"
            f"       soffice --headless --convert-to pptx {source.name!r}",
            file=sys.stderr,
        )
        return 1

    output = Path(args.output) if args.output else source.with_suffix(".remediated.pptx")

    def on_progress(record: dict) -> None:
        if args.quiet:
            return
        mark = MARK.get(record["action"], "?       ")
        text = record["alt_text"] or (record["reason"] or "")
        print(
            f"  slide {record['slide']:>3}  {mark} c{record['confidence']}  {text[:88]}",
            flush=True,
        )

    if not args.quiet:
        print(f"Reading {source.name}", flush=True)

    try:
        report = asyncio.run(
            remediate(
                source,
                output,
                concurrency=args.concurrency,
                use_summary=not args.no_summary,
                on_progress=on_progress,
            )
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"\n{report['images_found']} images on {report['slides']} slides"
        f"  ->  {report['auto_applied']} applied,"
        f" {report['decorative']} decorative,"
        f" {report['review_queue']} to review"
        f"   ({report['runtime_seconds']}s)"
    )
    if report["tables_detected"]:
        print(
            f"{report['tables_detected']} table(s) detected -- reported, not "
            "remediated (tables need their own accessibility work)"
        )
    print(f"Wrote {output}")

    report_path = Path(args.report) if args.report else output.with_suffix(".json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
