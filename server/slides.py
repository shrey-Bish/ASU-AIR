"""Render slides to pictures, so an accessibility issue can be seen.

The WCAG checks are about the slide, not about any one image on it: a missing
title, text too small, boxes that read out in the wrong order. Telling a
professor "slide 15 has 13pt text" is far less useful than showing them slide 15.

There is no pure-Python way to render a .pptx. LibreOffice converts the deck to
PDF (about five seconds for fifty slides) and poppler's pdftoppm turns pages
into PNGs (about 150ms each). Both are already on the machine; if either is
missing this degrades to no thumbnails rather than failing.

Rendering happens once per job on a background thread after the descriptions are
done, so it never delays the part the user is waiting for.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger("slidesight.server.slides")

SOFFICE_CANDIDATES = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "soffice",
    "libreoffice",
)
RENDER_DPI = "60"
CONVERT_TIMEOUT = 180
RENDER_TIMEOUT = 120

# job_id -> directory of slide-NN.png, or None while a render is in flight.
_renders: dict[str, Path | None] = {}
_lock = threading.Lock()


def _soffice() -> str | None:
    for candidate in SOFFICE_CANDIDATES:
        found = candidate if Path(candidate).is_file() else shutil.which(candidate)
        if found:
            return found
    return None


def available() -> bool:
    return bool(_soffice()) and bool(shutil.which("pdftoppm"))


def _render(job_id: str, deck: Path, out_dir: Path) -> None:
    """Deck -> PDF -> one PNG per slide. Runs on a worker thread."""
    soffice = _soffice()
    if not soffice or not shutil.which("pdftoppm"):
        logger.info("slide rendering unavailable (soffice/pdftoppm missing)")
        with _lock:
            _renders[job_id] = None
        return
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(deck)],
            check=True, capture_output=True, timeout=CONVERT_TIMEOUT,
        )
        pdfs = list(out_dir.glob("*.pdf"))
        if not pdfs:
            raise RuntimeError("no PDF produced")
        subprocess.run(
            ["pdftoppm", "-png", "-r", RENDER_DPI, str(pdfs[0]), str(out_dir / "slide")],
            check=True, capture_output=True, timeout=RENDER_TIMEOUT,
        )
        pdfs[0].unlink(missing_ok=True)
        count = len(list(out_dir.glob("slide-*.png")))
        with _lock:
            _renders[job_id] = out_dir
        logger.info("rendered %s slides for job %s", count, job_id)
    except Exception as exc:  # noqa: BLE001 - thumbnails are a nicety
        logger.warning("slide render failed for job %s: %s", job_id, type(exc).__name__)
        with _lock:
            _renders[job_id] = None


def start(job_id: str, deck: Path, out_dir: Path) -> None:
    """Kick off a render if one is not already done or running."""
    with _lock:
        if job_id in _renders:
            return
        _renders[job_id] = None
    threading.Thread(
        target=_render, args=(job_id, deck, out_dir),
        name=f"render-{job_id[:8]}", daemon=True,
    ).start()


def slide_png(job_id: str, slide_no: int) -> Path | None:
    """The rendered PNG for one slide, or None if it is not ready."""
    with _lock:
        directory = _renders.get(job_id)
    if directory is None:
        return None
    # pdftoppm zero-pads to the width of the page count: slide-1, slide-01, ...
    for width in (1, 2, 3, 4):
        candidate = directory / f"slide-{slide_no:0{width}d}.png"
        if candidate.is_file():
            return candidate
    return None


def forget(job_id: str) -> None:
    with _lock:
        _renders.pop(job_id, None)
