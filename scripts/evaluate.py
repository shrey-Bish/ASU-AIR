"""Run the pipeline over a folder of decks and write an evaluation summary.

    .venv/bin/python scripts/evaluate.py decks -o out/eval

Produces one JSON report per deck plus eval_summary.json with the aggregate
numbers, which is what the results table in the README is built from.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slidesight.pipeline import remediate  # noqa: E402


async def run(deck_dir: Path, out_dir: Path, concurrency: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Skip Office lock files (~$name.pptx) -- PowerPoint creates one for every
    # open document, and they are not decks.
    decks = sorted(d for d in deck_dir.glob("*.pptx") if not d.name.startswith("~$"))
    if not decks:
        raise SystemExit(f"no .pptx files in {deck_dir}")

    reports, failures = [], []
    started = time.time()

    for i, deck in enumerate(decks, start=1):
        print(f"[{i}/{len(decks)}] {deck.name}", flush=True)
        try:
            report = await remediate(
                deck,
                out_dir / f"{deck.stem}.remediated.pptx",
                concurrency=concurrency,
            )
        except Exception as exc:  # noqa: BLE001 - one bad deck must not stop the run
            print(f"    FAILED {type(exc).__name__}: {exc}", flush=True)
            failures.append({"deck": deck.name, "error": f"{type(exc).__name__}: {exc}"})
            continue

        (out_dir / f"{deck.stem}.json").write_text(json.dumps(report, indent=2))
        reports.append(report)
        print(
            f"    {report['images_found']:>3} images -> "
            f"{report['auto_applied']} applied, "
            f"{report['decorative']} decorative, "
            f"{report['review_queue']} review   "
            f"({report['runtime_seconds']}s, {report['wcag']['total_issues']} wcag)",
            flush=True,
        )

    confidence = Counter()
    wcag_counts = Counter()
    for report in reports:
        for image in report["images"]:
            confidence[image["confidence"]] += 1
        wcag_counts.update(report["wcag"]["by_check"])

    summary = {
        "decks_attempted": len(decks),
        "decks_succeeded": len(reports),
        "failures": failures,
        "slides": sum(r["slides"] for r in reports),
        "images_found": sum(r["images_found"] for r in reports),
        "auto_applied": sum(r["auto_applied"] for r in reports),
        "decorative": sum(r["decorative"] for r in reports),
        "review_queue": sum(r["review_queue"] for r in reports),
        "tables_detected": sum(r["tables_detected"] for r in reports),
        "confidence_spread": dict(sorted(confidence.items())),
        "wcag_by_check": dict(wcag_counts.most_common()),
        "wcag_total": sum(r["wcag"]["total_issues"] for r in reports),
        "total_runtime_seconds": round(time.time() - started, 1),
        "per_deck": [
            {
                "deck": r["source"],
                "slides": r["slides"],
                "images": r["images_found"],
                "auto_applied": r["auto_applied"],
                "decorative": r["decorative"],
                "review_queue": r["review_queue"],
                "wcag_issues": r["wcag"]["total_issues"],
                "runtime_seconds": r["runtime_seconds"],
            }
            for r in reports
        ],
    }
    (out_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch-evaluate SlideSight over a deck folder.")
    ap.add_argument("deck_dir", help="folder of .pptx files")
    ap.add_argument("-o", "--out", default="out/eval", help="output folder")
    ap.add_argument("-c", "--concurrency", type=int, default=5)
    args = ap.parse_args()

    summary = asyncio.run(run(Path(args.deck_dir), Path(args.out), args.concurrency))

    print("\n=== evaluation summary ===")
    print(
        f"{summary['decks_succeeded']}/{summary['decks_attempted']} decks, "
        f"{summary['slides']} slides, {summary['images_found']} images "
        f"in {summary['total_runtime_seconds']}s"
    )
    print(
        f"  applied {summary['auto_applied']}  "
        f"decorative {summary['decorative']}  "
        f"review {summary['review_queue']}"
    )
    print(f"  confidence spread: {summary['confidence_spread']}")
    print(f"  wcag issues: {summary['wcag_total']}  {summary['wcag_by_check']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
