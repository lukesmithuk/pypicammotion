"""Disk storage manager: registers saved clips and enforces quota via oldest-first eviction."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)


class StorageManager:
    """Track clip files and enforce a disk quota by evicting oldest clips first."""

    def __init__(
        self, base_path: str | Path, max_bytes: int, require_mount: bool = False
    ) -> None:
        self._base = Path(base_path)
        self._max_bytes = max_bytes
        self._lock = threading.Lock()
        # Sorted list of (mtime, path) — oldest first
        self._clips: list[tuple[float, Path]] = []
        self._total_bytes: int = 0

        if require_mount:
            self._validate_mount()

        self._scan()

    def _validate_mount(self) -> None:
        """Check that base_path is on a non-root mount (e.g. USB drive)."""
        p = self._base.resolve()
        while not p.is_mount():
            p = p.parent
        if p == Path("/"):
            raise RuntimeError(
                f"storage path {self._base} is on the root filesystem — "
                f"is the external drive mounted? "
                f"(set require_mount: false to disable this check)"
            )
        log.info("storage: mount validated — %s is on %s", self._base, p)

    def _scan(self) -> None:
        """Walk base_path on startup and index existing .mp4 files."""
        if not self._base.exists():
            self._base.mkdir(parents=True, exist_ok=True)
            return

        clips: list[tuple[float, Path]] = []
        total = 0
        for root, _dirs, files in os.walk(self._base):
            for fname in files:
                if fname.endswith(".mp4"):
                    p = Path(root) / fname
                    try:
                        st = p.stat()
                        clips.append((st.st_mtime, p))
                        total += st.st_size
                    except OSError:
                        pass

        clips.sort()
        with self._lock:
            self._clips = clips
            self._total_bytes = total

        log.info(
            "storage: scanned %d clips, %.1f MB / %.1f MB",
            len(clips),
            total / 1_048_576,
            self._max_bytes / 1_048_576,
        )

    def register_clip(self, path: Path) -> None:
        """Add a newly saved clip to tracking and enforce quota."""
        try:
            st = path.stat()
        except OSError:
            log.warning("storage: cannot stat %s", path)
            return

        with self._lock:
            self._clips.append((st.st_mtime, path))
            self._clips.sort()
            self._total_bytes += st.st_size

        self._enforce_quota()

    def _enforce_quota(self) -> None:
        """Delete oldest clips until total size is under max_bytes."""
        with self._lock:
            while self._total_bytes > self._max_bytes and self._clips:
                _mtime, oldest = self._clips.pop(0)
                try:
                    size = oldest.stat().st_size
                    oldest.unlink()
                    self._total_bytes -= size
                    log.info("storage: evicted %s (%.0f KB)", oldest, size / 1024)
                    self._remove_empty_parents(oldest.parent)
                except OSError:
                    log.warning("storage: failed to evict %s", oldest)

    def status(self) -> dict:
        """Return storage stats for heartbeat reporting."""
        with self._lock:
            return {
                "clips": len(self._clips),
                "used_mb": round(self._total_bytes / 1_048_576, 1),
                "max_mb": round(self._max_bytes / 1_048_576, 1),
            }

    def _remove_empty_parents(self, d: Path) -> None:
        """Remove empty directories up to (but not including) base_path."""
        while d != self._base and d.is_dir():
            try:
                d.rmdir()  # fails if non-empty
                d = d.parent
            except OSError:
                break
