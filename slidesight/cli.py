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
from .pipeline import audit_only, remediate

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
    p.add_argument(
        "--wcag-only",
        action="store_true",
        help="run the WCAG checks only, no model calls",
    )
    p.add_argument("--quiet", action="store_true", help="only print the final counts")
    return p


CHECK_LABEL = {
    "missing_title": "slides with no title",
    "small_text": "slides with text under 18pt",
    "table_no_header": "tables with no header row",
    "vague_link": "vague link text",
    "reading_order": "slides that read out of visual order",
}


def print_wcag(report: dict) -> None:
    audit = report.get("wcag") or {}
    total = audit.get("total_issues", 0)
    print(f"\nAccessibility report -- {total} issue(s) detected, none modified")
    for check, count in sorted(audit.get("by_check", {}).items(), key=lambda kv: -kv[1]):
        print(f"  {count:>4}  {CHECK_LABEL.get(check, check)}")
    for issue in audit.get("issues", [])[:8]:
        print(f"        slide {issue['slide']:>3}  {issue['check']}: {issue['detail'][:80]}")
    if total > 8:
        print(f"        ... {total - 8} more in the JSON report")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source = Path(args.input)
    if not source.is_file():
        print(f"error: no such file: {source}", file=sys.stderr)
        return 1
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        print(
            "error: PDF is not supported. SlideSight remediates PowerPoint only.\n"
            "       PDF accessibility needs tag trees and reading order, which is a\n"
            "       different and much larger problem. ASU's Cloud Innovation Center\n"
            "       already ships a PDF tool: github.com/ASUCICREPO/PDF_Accessibility",
            file=sys.stderr,
        )
        return 1
    if suffix in (".ppt", ".pps", ".odp", ".key"):
        print(
            f"error: {suffix} is a different file format -- SlideSight reads .pptx.\n"
            "       Convert it first, then run again:\n"
            f"       soffice --headless --convert-to pptx {source.name!r}",
            file=sys.stderr,
        )
        return 1
    if suffix != ".pptx":
        print(
            f"error: {suffix or 'this file'} is not a PowerPoint file. "
            "SlideSight reads .pptx only.",
            file=sys.stderr,
        )
        return 1

    if args.wcag_only:
        report = audit_only(source)
        print(
            f"{report['source']}: {report['slides']} slides, "
            f"{report['images_found']} images, {report['tables_detected']} tables"
        )
        print_wcag(report)
        report_path = Path(args.report) if args.report else source.with_suffix(".wcag.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {report_path}")
        return 0

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
    except (RuntimeError, ValueError) as exc:
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
    print_wcag(report)
    print(f"\nWrote {output}")

    report_path = Path(args.report) if args.report else output.with_suffix(".json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
