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
from .extract import ImageRef, set_alt_text

ACTION_AUTO = "auto_applied"
ACTION_REVIEW = "review_queue"
ACTION_DECORATIVE = "decorative_empty_alt"


def triage(result: dict[str, Any]) -> str:
    """Route a description to one of the three outcomes."""
    if result.get("decorative"):
        return ACTION_DECORATIVE
    if result.get("confidence", 0) >= config.AUTO_APPLY_MIN_CONFIDENCE:
        return ACTION_AUTO
    return ACTION_REVIEW


def make_record(image: ImageRef, result: dict[str, Any]) -> dict[str, Any]:
    """Build one row of the JSON contract shared with the UI."""
    action = triage(result)
    return {
        "slide": image.slide,
        "image_id": image.image_id,
        "alt_text": result.get("description", ""),
        "confidence": result.get("confidence", 1),
        "decorative": bool(result.get("decorative")),
        "reason": result.get("reason"),
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
