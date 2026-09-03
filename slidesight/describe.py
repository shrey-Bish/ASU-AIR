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

STEP 4. List what you can literally read in the image.

"visible_text" is the labels, numbers, axis titles and captions you can actually
make out in the image itself -- not what the slide text says should be there. If
nothing is legible, return an empty list. This list is checked against your
description, so do not pad it.

Return ONLY this JSON:
{{"description": "...", "decorative": false, "confidence": 4, "visible_text": ["axis label", "42"], "reason": "one line, only when confidence is 3 or below"}}"""

SUMMARY_PROMPT = """Summarize what this lecture deck covers in under 200 words:
subject, level, and the main topics in order. This summary gives an image
description model background context.

Deck text:
{text}"""


def prepare_image(
    blob: bytes, content_type: str, max_edge: int = config.MAX_IMAGE_EDGE_PX
) -> tuple[bytes, str] | None:
    """Get an image into a format the vision model accepts, or report it cannot be.

    Two jobs. Oversized images are downscaled -- an 833KB screenshot costs
    latency and vision tokens without adding legible detail. And formats the
    gateway will not accept (TIFF and BMP are common in academic decks full of
    scanned figures) are re-encoded as JPEG rather than being skipped.

    Returns None only when the bytes cannot be decoded at all, which in practice
    means vector art (EMF/WMF). Those go to the review queue instead of being
    sent as unreadable bytes.
    """
    web_ready = content_type in config.SUPPORTED_IMAGE_TYPES
    try:
        from PIL import Image
    except ImportError:
        return (blob, content_type) if web_ready else None

    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
    except Exception:
        # Undecodable by Pillow. If the gateway already accepts the type, let
        # it try; otherwise this is genuinely unreadable.
        return (blob, content_type) if web_ready else None

    if web_ready and max(img.size) <= max_edge:
        return blob, content_type

    if max(img.size) > max_edge:
        img.thumbnail((max_edge, max_edge), Image.LANCZOS)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def to_data_url(image: ImageRef) -> str:
    prepared = prepare_image(image.blob, image.content_type)
    if prepared is None:
        raise ValueError(f"cannot decode image format {image.content_type}")
    blob, content_type = prepared
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
    # The model can run out of output tokens mid-object, leaving valid content
    # inside an unterminated JSON string. Losing a good description to a missing
    # closing brace would mislabel it as low confidence, so salvage the fields.
    salvaged = _salvage(text)
    if salvaged:
        return salvaged
    raise ValueError(f"no JSON object in response: {text[:200]!r}")


DESC_RE = re.compile(r'"(?:description|alt_text)"\s*:\s*"((?:[^"\\]|\\.)*)', re.S)
CONF_RE = re.compile(r'"confidence"\s*:\s*(\d)')
DECOR_RE = re.compile(r'"decorative"\s*:\s*(true|false)', re.I)
REASON_RE = re.compile(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)', re.S)


def _salvage(text: str) -> dict[str, Any] | None:
    """Pull fields out of a truncated JSON object."""
    match = DESC_RE.search(text)
    if not match:
        return None
    description = match.group(1).encode().decode("unicode_escape", "replace").strip()
    if not description:
        return None
    conf = CONF_RE.search(text)
    decor = DECOR_RE.search(text)
    reason = REASON_RE.search(text)
    out: dict[str, Any] = {
        "description": description,
        "decorative": bool(decor and decor.group(1).lower() == "true"),
        # A truncated reply never showed us its confidence if the field was cut,
        # so assume it needs a human rather than assuming it was fine.
        "confidence": int(conf.group(1)) if conf else 3,
        "truncated": True,
    }
    if reason:
        out["reason"] = reason.group(1).strip()
    elif not conf:
        out["reason"] = "model response was cut off before it reported confidence"
    return out


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
    visible = raw.get("visible_text") or []
    if isinstance(visible, str):
        visible = [visible]
    visible = [str(v) for v in visible if str(v).strip()]
    return {
        "description": description,
        "decorative": decorative,
        "confidence": confidence,
        "reason": reason,
        "visible_text": visible,
    }


NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")

# Above this many legible items, trust the model's own confidence instead.
MAX_VISIBLE_FOR_LEAK_CHECK = 2


def _numbers(text: str) -> set[str]:
    """Numbers in a string, normalised so 1,200 and 1200 compare equal."""
    out = set()
    for match in NUMBER_RE.findall(text or ""):
        cleaned = match.replace(",", "").rstrip(".")
        if len(cleaned.lstrip("-")) >= 2:  # single digits are too noisy to judge
            out.add(cleaned)
    return out


def cross_check(result: dict[str, Any], context) -> dict[str, Any]:
    """Catch values copied out of the slide text instead of read from the image.

    The failure this defends against: given an illegible image, the model
    reports precise values it cannot possibly see, lifted from the slide text
    sitting next to it, and still scores itself 4 or 5. Feeding the same image
    a *different* slide's text made it describe the wrong subject entirely.

    So we ask the model what it can literally read, then check the numbers in
    its description against that list. A number that is absent from what it
    claims to see, but present in the slide text, is very likely copied. That
    caps confidence at 3, which routes the image to a human.
    """
    if result.get("decorative") or not result.get("description"):
        return result

    visible = result.get("visible_text") or []

    # If the model listed a real amount of legible detail, it demonstrably read
    # the image, and its own confidence and reason are better judges than this
    # heuristic. Overriding there produced false positives on clean diagrams
    # whose annotation values simply were not itemised. The check is aimed at
    # the opposite case: "I can barely read this" plus a description full of
    # precise values.
    if len(visible) > MAX_VISIBLE_FOR_LEAK_CHECK:
        return result

    claimed = _numbers(" ".join(visible))
    described = _numbers(result["description"])
    unread = described - claimed
    if not unread:
        return result

    slide_text = " ".join(
        filter(None, (context.title, context.body, context.notes))
    )
    copied = sorted(unread & _numbers(slide_text))
    if not copied:
        return result

    result["confidence"] = min(result.get("confidence", 5), 3)
    detail = ", ".join(copied[:4])
    existing = result.get("reason")
    note = (
        f"values {detail} appear in the slide text but not in what the model "
        "reported reading from the image -- possibly copied rather than read"
    )
    result["reason"] = f"{existing} | {note}" if existing else note
    result["context_leak"] = copied
    return result


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
        max_tokens=1000,
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
    result = normalize(parse_response(response.choices[0].message.content))
    return cross_check(result, image.context)


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
