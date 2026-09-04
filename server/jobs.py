"""In-memory, thread-safe job registry.

The remediation pipeline runs synchronously in a worker thread (it wraps an
async pipeline via asyncio.run) while FastAPI handlers read job state from the
event-loop thread, so every read/write goes through a threading.Lock. State is
intentionally in-memory only: jobs die with the process, which is fine for a
single-day demo and avoids persisting uploaded student/faculty decks.
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

# Fields a job tracks. Anything outside this set is rejected on update so a
# stray callback key cannot silently grow the state dict.
_JOB_FIELDS = (
    "job_id",
    "filename",
    "status",  # "processing" | "complete" | "failed"
    "created_at",
    "progress_pct",
    "total_slides",
    "total_images",
    "current_slide",
    "current_image_id",
    "current_alt_text",
    "current_confidence",
    "current_action",
    "records_so_far",
    "report",
    "output_path",
    "output_filename",
    "error",
)


class JobRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    # -- lifecycle ---------------------------------------------------------

    def create_job(self, filename: str, total_slides: int | None = None,
                   total_images: int | None = None,
                   job_id: str | None = None) -> dict[str, Any]:
        # The caller may pass an id it has already used for the job's temp
        # directory; without that the registry would mint a second id and the
        # id handed to the client would address nothing.
        job_id = job_id or uuid.uuid4().hex
        job: dict[str, Any] = {
            "job_id": job_id,
            "filename": filename,
            "status": "processing",
            "created_at": time.time(),
            "progress_pct": 0,
            "total_slides": total_slides,
            "total_images": total_images,
            "current_slide": None,
            "current_image_id": None,
            "current_alt_text": None,
            "current_confidence": None,
            "current_action": None,
            "records_so_far": [],
            "report": None,
            "output_path": None,
            "output_filename": None,
            "error": None,
        }
        with self._lock:
            self._jobs[job_id] = job
        return self.snapshot(job_id) or job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {k: (v.copy() if isinstance(v, list) else v) for k, v in job.items()}

    def update_job(self, job_id: str, **kwargs: Any) -> bool:
        """Set allowed fields on a job. Returns False if the job is unknown."""
        unknown = set(kwargs) - set(_JOB_FIELDS)
        if unknown:
            raise ValueError(f"unknown job fields: {sorted(unknown)}")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.update(kwargs)
        return True

    def record_progress(self, job_id: str, record: dict[str, Any]) -> None:
        """Fold one pipeline progress record into the job state.

        The callback from slidesight.remediate receives one record per image as
        it lands: {slide, image_id, alt_text, confidence, decorative, reason,
        action}. It carries no totals, so progress_pct is computed from
        total_images captured at upload time.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["status"] != "processing":
                return
            job["records_so_far"].append(dict(record))
            job["current_slide"] = record.get("slide")
            job["current_image_id"] = record.get("image_id")
            job["current_alt_text"] = record.get("alt_text")
            job["current_confidence"] = record.get("confidence")
            job["current_action"] = record.get("action")
            total = job.get("total_images")
            done = len(job["records_so_far"])
            if total:
                # Cap at 99 while processing; 100 is set on completion.
                job["progress_pct"] = min(99, round(done / total * 100))

    def complete_job(self, job_id: str, report: dict[str, Any], output_path: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job["status"] = "complete"
            job["progress_pct"] = 100
            job["report"] = report
            job["output_path"] = output_path
            job["output_filename"] = Path(output_path).name
            job["total_slides"] = report.get("slides", job.get("total_slides"))
            # Clear transient fields so a poll right after completion shows a
            # clean payload.
            job["current_image_id"] = None
            job["current_alt_text"] = None
            return True

    def fail_job(self, job_id: str, error: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job["status"] = "failed"
            job["error"] = error
            return True

    def jobs_older_than(self, age_seconds: float) -> list[dict[str, Any]]:
        """Snapshots of jobs created more than age_seconds ago (for cleanup)."""
        cutoff = time.time() - age_seconds
        with self._lock:
            return [
                {k: (v.copy() if isinstance(v, list) else v) for k, v in j.items()}
                for j in self._jobs.values()
                if j["created_at"] < cutoff
            ]

    def drop_job(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def snapshot(self, job_id: str) -> dict[str, Any] | None:
        return self.get_job(job_id)


# Module-level singleton shared by all requests.
registry = JobRegistry()
