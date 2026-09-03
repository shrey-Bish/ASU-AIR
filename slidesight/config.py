"""Configuration and credentials for the ASU AIR gateway.

All inference runs on ASU Research Computing hardware. No external providers.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_URL_DEFAULT = "https://openai.rc.asu.edu/v1"

# Exact model IDs, confirmed present on the gateway. See MODELS.md.
MODEL_VISION = "qwen3-vl-32b-instruct"
MODEL_TEXT = "gemma4-31b-it"

# Triage thresholds. Confidence is 1-5, never 0-100 -- models do not calibrate
# to a hundred points and cluster meaninglessly at 85/90/95.
AUTO_APPLY_MIN_CONFIDENCE = 4

# A "decorative" verdict silences an image permanently and never reaches a
# human, so it is not trusted on large images. Above this fraction of the slide
# area, a decorative call is routed to review instead. Measured against real
# decks: logos and template icons run 1-8% of slide area, so this fires on
# content-sized images without flooding the queue.
DECORATIVE_MAX_AREA_FRACTION = 0.12

# Images are sent as base64 data URLs. Downscale first: an 833KB screenshot
# costs latency and vision tokens without adding legible detail.
MAX_IMAGE_EDGE_PX = 1280

# The gateway rate-limits parallel requests; a semaphore keeps us under it.
DEFAULT_CONCURRENCY = 4

# Formats a vision model can actually decode. Old decks carry EMF/WMF vector
# art that would be sent as unreadable bytes, so those are routed to review
# instead of being guessed at.
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def load_env(path: str | Path = ".env") -> None:
    """Load KEY=value pairs from a .env file into os.environ.

    Existing environment variables win, so an exported key overrides the file.
    """
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def get_api_key() -> str:
    """Return the RC gateway key, or raise with an actionable message."""
    load_env()
    for name in ("RC_LLM_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise RuntimeError(
        "No API key found. Put RC_LLM_API_KEY=<your key> in .env "
        "(get one from https://voyager.rc.asu.edu)."
    )


def get_base_url() -> str:
    load_env()
    return os.environ.get("RC_LLM_BASE_URL", "").strip() or BASE_URL_DEFAULT
