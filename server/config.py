"""Server-side configuration.

Loads the project-root .env (same file slidesight/config.py reads) and exposes
the ASU AIR gateway settings. The pipeline reads these itself via
slidesight.config.get_api_key()/get_base_url(); this module exists so the
server can (a) guarantee .env is loaded before any pipeline call and
(b) surface a fail-fast health check without printing the key.

Secrets are never logged or echoed in API responses.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# Existing environment variables win over the file, matching slidesight's
# behaviour (its load_env uses os.environ.setdefault).
load_dotenv(dotenv_path=ENV_PATH, override=False)

BASE_URL_DEFAULT = "https://openai.rc.asu.edu/v1"

# Where uploaded decks and remediated outputs live. Defaults to the system
# temp dir (outside the repo, so nothing lands in git); one subdirectory per
# job. Override with SLIDESIGHT_UPLOAD_DIR if persistence is wanted.
UPLOAD_ROOT = Path(
    os.environ.get("SLIDESIGHT_UPLOAD_DIR", Path(tempfile.gettempdir()) / "slidesight_uploads")
)

# Jobs older than this are eligible for file cleanup on the next upload.
MAX_JOB_AGE_SECONDS = 2 * 60 * 60  # 2 hours

# The web UI is served by this same app (see the StaticFiles mount in main.py),
# so browser calls are same-origin and need no CORS grant. These entries only
# cover running the front end from a separate dev server.
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


def get_api_key() -> str:
    """Return the RC gateway key, or "" if unset (pipeline raises its own
    actionable error in that case)."""
    for name in ("RC_LLM_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def get_base_url() -> str:
    """ASU AIR gateway base URL."""
    return os.environ.get("RC_LLM_BASE_URL", "").strip() or BASE_URL_DEFAULT


def has_api_key() -> bool:
    return bool(get_api_key())
