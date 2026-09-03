"""Vision pass: image + slide context -> description, confidence, decorative flag.

One call per image returning all four fields. Not two calls -- asking a model to
score work it cannot see in the same breath is what makes the confidence signal
meaningful.
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from . import config
from .extract import ImageRef

PROMPT = """You are an expert accessibility remediator. Analyze this image from a
university lecture slide.

Slide title: {title}
Slide text: {body}
Speaker notes: {notes}
Deck summary: {summary}

STEP 1. Decide whether this image is decorative, before describing anything.

Decorative means it carries no teaching content, even if you can identify it
perfectly. Mark decorative and set "description" to "":
  - institutional or brand logos (a university logo, Discord, Google Drive)
  - icons, bullets, arrows, dividers, borders, background textures
  - stock photos and clip art used only for visual interest

A blind student navigating a deck should not hear a logo announced on every
slide. Being able to recognize a logo confidently is not a reason to describe
it -- it is a reason to silence it.

Not decorative: charts, graphs, diagrams, screenshots of forms or interfaces,
handwritten work, equations, photographs that illustrate a concept.

STEP 2. If it is not decorative, write alt text for a blind student using a
screen reader. Never begin with "an image of" or "a picture of". Focus on the
data, the educational takeaway, and structural relationships. Include specific
values, labels, and comparisons visible in the image. Keep it under 50 words --
a screen reader reads it aloud.

Examples of good alt text:
"Line graph comparing Q1 to Q4 retention. Q1 starts at 85%, dipping to 72% in Q3
before recovering to 78% in Q4."
"Diagram of a cell. The nucleus is highlighted in red at the center, surrounded
by the rough endoplasmic reticulum."

STEP 3. Score your confidence in the description you just wrote.

The slide text above is background only. It often repeats values that also
appear in the image -- and it is sometimes about a different part of the lesson
entirely. Do not copy a number, label, or subject from the slide text into your
description unless you can also read it in the image itself.

Before scoring, apply this test: if you had been given this image with no slide
text at all, would your description still be the same? If any part of it would
change or disappear, score 3 or below and say which part in "reason".

Confidence measures whether a sighted reader could verify your description
against the image alone -- not how sharp the image is, and not how well you
understand the topic. An honest 2 is more useful than a confident guess: low
scores send the image to a human instead of writing something wrong into the
file.

5 - every value and label in the description is legible in the image
4 - clear image, minor ambiguity in labels or units
3 - readable, but I inferred purpose or values from context rather than reading them
2 - blurry, cropped, partially cut off, or unfamiliar subject matter
1 - cannot determine what this shows

Return ONLY this JSON:
{{"description": "...", "decorative": false, "confidence": 4, "reason": "one line, only when confidence is 3 or below"}}"""

SUMMARY_PROMPT = """Summarize what this lecture deck covers in under 200 words:
subject, level, and the main topics in order. This summary gives an image
description model background context.

Deck text:
{text}"""


def downscale(blob: bytes, max_edge: int = config.MAX_IMAGE_EDGE_PX) -> tuple[bytes, str]:
    """Shrink oversized images before base64 encoding.

    Falls back to the original bytes if Pillow is unavailable or the image
    cannot be decoded -- never fail a description over a resize.
    """
    try:
        from PIL import Image
    except ImportError:
        return blob, ""
    try:
        img = Image.open(io.BytesIO(blob))
        if max(img.size) <= max_edge:
            return blob, ""
        img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return blob, ""


def to_data_url(image: ImageRef) -> str:
    blob, new_type = downscale(image.blob)
    content_type = new_type or image.content_type
    return f"data:{content_type};base64,{base64.b64encode(blob).decode()}"


def parse_response(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a model response.

    Models wrap JSON in prose or ```json fences often enough that finding the
    first balanced object is more reliable than json.loads on the raw string.
    """
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"no JSON object in response: {text[:200]!r}")


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)


def _as_confidence(value: Any) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return 1
    return max(1, min(5, n))


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a model response into the shape the rest of the pipeline expects."""
    description = str(raw.get("description") or raw.get("alt_text") or "").strip()
    decorative = _as_bool(raw.get("decorative"))
    confidence = _as_confidence(raw.get("confidence"))
    reason = raw.get("reason")
    reason = str(reason).strip() if reason not in (None, "", "null") else None
    return {
        "description": description,
        "decorative": decorative,
        "confidence": confidence,
        "reason": reason,
    }


async def describe_image(client, image: ImageRef, summary: str = "") -> dict[str, Any]:
    """Describe one image. Raises on transport or parse failure."""
    prompt = PROMPT.format(
        title=image.context.title or "(none)",
        body=image.context.body or "(none)",
        notes=image.context.notes or "(none)",
        summary=summary or "(none)",
    )
    response = await client.chat.completions.create(
        model=config.MODEL_VISION,
        max_tokens=600,
        temperature=0.2,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": to_data_url(image)}},
                ],
            }
        ],
    )
    return normalize(parse_response(response.choices[0].message.content))


async def summarize_deck(client, text: str) -> str:
    """One text-only call per deck, prepended to every image prompt."""
    if not text.strip():
        return ""
    response = await client.chat.completions.create(
        model=config.MODEL_TEXT,
        max_tokens=400,
        temperature=0.3,
        messages=[{"role": "user", "content": SUMMARY_PROMPT.format(text=text)}],
    )
    return (response.choices[0].message.content or "").strip()
