"""Triage and write-back.

The confidence gate lives here. High-confidence descriptions are applied to the
file; low-confidence ones are held in the review queue with the model's stated
reason rather than written in silently.

Write-back touches image metadata only. Layouts, fonts, themes, and animations
are never modified.
"""

from __future__ import annotations

from typing import Any

from . import config
from .describe import is_photographic
from .extract import ImageRef, set_alt_text

ACTION_AUTO = "auto_applied"
ACTION_REVIEW = "review_queue"
ACTION_DECORATIVE = "decorative_empty_alt"


def triage(
    result: dict[str, Any],
    area_fraction: float | None = None,
    photographic: bool = False,
) -> str:
    """Route a description to one of the three outcomes.

    The confidence gate protects descriptions, but on its own nothing protects
    a *decorative* verdict -- and that is the more harmful mistake. Bad alt text
    gets read and corrected; a wrongly-silenced diagram is removed from the
    blind student's experience entirely and never reaches a human.

    So a decorative verdict is checked against two independent signals, and
    fails either one it goes to a human instead of being silenced:

    * **Size.** Anything covering more than ``DECORATIVE_MAX_AREA_FRACTION`` of
      the slide. Logos and dividers are small; a chart is not.
    * **Photograph or flat graphic.** The better signal of the two. Size alone
      missed a 1%-of-slide dog photograph that was the raw input in a
      feature-extraction diagram -- tiny, and entirely the point of the slide.
      Logos and icons are a few flat colours; photographs are thousands.
    """
    if result.get("decorative"):
        too_big = (
            area_fraction is not None
            and area_fraction > config.DECORATIVE_MAX_AREA_FRACTION
        )
        if too_big or photographic:
            return ACTION_REVIEW
        return ACTION_DECORATIVE
    if result.get("confidence", 0) >= config.AUTO_APPLY_MIN_CONFIDENCE:
        return ACTION_AUTO
    return ACTION_REVIEW


def make_record(image: ImageRef, result: dict[str, Any]) -> dict[str, Any]:
    """Build one row of the JSON contract shared with the UI."""
    photographic = is_photographic(image.blob) if image.blob else False
    action = triage(result, image.area_fraction, photographic)
    reason = result.get("reason")
    if action == ACTION_REVIEW and result.get("decorative"):
        pct = (image.area_fraction or 0) * 100
        if photographic:
            note = (
                "model called this decorative, but it is a photograph, not a "
                "logo or icon -- photographs on a lecture slide are usually the "
                "example being taught"
            )
        else:
            note = (
                f"model called this decorative, but it covers {pct:.0f}% of the "
                "slide -- too large to silence without a human looking"
            )
        reason = f"{reason} | {note}" if reason else note
    return {
        "slide": image.slide,
        "image_id": image.image_id,
        "alt_text": result.get("description", ""),
        "confidence": result.get("confidence", 1),
        "decorative": bool(result.get("decorative")),
        "reason": reason,
        "action": action,
    }


def failure_record(image: ImageRef, reason: str) -> dict[str, Any]:
    """A failed or unreadable image goes to a human, never to a guess."""
    return {
        "slide": image.slide,
        "image_id": image.image_id,
        "alt_text": "",
        "confidence": 1,
        "decorative": False,
        "reason": reason,
        "action": ACTION_REVIEW,
    }


def apply_records(images: list[ImageRef], records: list[dict[str, Any]]) -> int:
    """Write approved alt text into the shapes. Returns how many changed.

    Decorative images get empty alt so screen readers skip them entirely.
    Review-queue images are left untouched -- that is the whole point of the
    gate. The filename ``title`` attribute is stripped either way.
    """
    by_key = {(img.slide, img.image_id): img for img in images}
    changed = 0
    for record in records:
        image = by_key.get((record["slide"], record["image_id"]))
        if image is None or image.shape is None:
            continue
        action = record.get("action")
        if action == ACTION_AUTO:
            set_alt_text(image.shape, record["alt_text"])
            changed += 1
        elif action == ACTION_DECORATIVE:
            set_alt_text(image.shape, "")
            changed += 1
    return changed


def summarize(records: list[dict[str, Any]]) -> dict[str, int]:
    """Counts for the report and the pitch numbers."""
    return {
        "images_found": len(records),
        "auto_applied": sum(1 for r in records if r["action"] == ACTION_AUTO),
        "review_queue": sum(1 for r in records if r["action"] == ACTION_REVIEW),
        "decorative": sum(1 for r in records if r["action"] == ACTION_DECORATIVE),
    }
