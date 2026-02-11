from __future__ import annotations

import enum
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from picamera2 import Picamera2
from picamera2.encoders import LibavH264Encoder
from picamera2.outputs import CircularOutput2, PyavOutput

from .config import CameraConfig
from .motion import MotionDetector

log = logging.getLogger(__name__)

ClipCallback = Callable[[str, Path, datetime, float, float | None], None]


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TAIL = "tail"


class Camera:
    """Wraps one Picamera2 instance with motion-triggered recording.

    Designed to be started in its own thread via :meth:`start` — the Picamera2
    object is created inside the thread to avoid cross-thread issues.
    """

    def __init__(
        self,
        config: CameraConfig,
        storage_path: Path,
        on_clip_saved: ClipCallback | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.config = config
        self._storage_path = Path(storage_path)
        self._on_clip_saved = on_clip_saved
        self._stop_event = stop_event or threading.Event()

        self._state = State.IDLE
        self._tail_deadline: float = 0.0
        self._recording_start: datetime | None = None
        self._recording_start_mono: float | None = None
        self._current_clip: Path | None = None

        self._picam: Picamera2 | None = None
        self._encoder: LibavH264Encoder | None = None
        self._circular: CircularOutput2 | None = None
        self._thread: threading.Thread | None = None
        self._detector: MotionDetector | None = None
        self._lock = threading.Lock()

    # -- public API ----------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"cam-{self.config.name}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

    # -- internals -----------------------------------------------------------

    def _run(self) -> None:
        """Thread entry — create picamera2, configure, and loop."""
        name = self.config.name
        try:
            self._setup()
            log.info("[%s] camera running (device %d)", name, self.config.device)
            while not self._stop_event.is_set():
                self._stop_event.wait(0.1)
                self._check_tail()
        except Exception:
            log.exception("[%s] camera error", name)
        finally:
            self._teardown()
            log.info("[%s] camera stopped", name)

    def _setup(self) -> None:
        cfg = self.config
        self._detector = MotionDetector(
            resolution=cfg.lores_resolution,
            sensitivity=cfg.sensitivity,
            min_contour_area=cfg.min_contour_area,
            blur_kernel=cfg.blur_kernel,
            compare_frames=max(1, cfg.fps // 2),
        )

        self._picam = Picamera2(camera_num=cfg.device)
        video_config = self._picam.create_video_configuration(
            main={"size": cfg.resolution},
            lores={"size": cfg.lores_resolution, "format": "YUV420"},
        )
        self._picam.configure(video_config)

        buffer_ms = int(cfg.pre_motion_seconds * 1000)
        self._encoder = LibavH264Encoder(framerate=cfg.fps, iperiod=cfg.fps)
        self._circular = CircularOutput2(buffer_duration_ms=buffer_ms)
        self._encoder.output = self._circular

        self._picam.pre_callback = self._on_frame
        self._picam.start()
        self._picam.start_encoder(self._encoder)

    def _teardown(self) -> None:
        try:
            if self._state in (State.RECORDING, State.TAIL):
                self._stop_recording()
            if self._picam:
                self._picam.stop_encoder()
                self._picam.stop()
                self._picam.close()
        except Exception:
            log.exception("[%s] error during teardown", self.config.name)

    def _on_frame(self, request) -> None:
        """pre_callback — runs in picamera2's event loop for every frame."""
        try:
            frame = request.make_array("lores")
        except Exception:
            return

        motion, score = self._detector.detect(frame)

        with self._lock:
            if self._state == State.IDLE:
                if motion:
                    self._start_recording()
            elif self._state == State.RECORDING:
                if motion:
                    self._tail_deadline = 0.0
                else:
                    self._tail_deadline = time.monotonic() + self.config.post_motion_seconds
                    self._state = State.TAIL
            elif self._state == State.TAIL:
                if motion:
                    self._tail_deadline = 0.0
                    self._state = State.RECORDING

    def _check_tail(self) -> None:
        """Called from the main loop to stop recording when tail expires."""
        with self._lock:
            if self._state == State.TAIL and self._tail_deadline and time.monotonic() >= self._tail_deadline:
                self._stop_recording()

    def _clip_path(self, ts: datetime) -> Path:
        day_dir = self._storage_path / self.config.name / ts.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"{ts.strftime('%H-%M-%S')}.mp4"

    def _start_recording(self) -> None:
        ts = datetime.now()
        self._recording_start = ts
        self._recording_start_mono = time.monotonic()
        self._current_clip = self._clip_path(ts)
        log.info("[%s] motion started — recording to %s", self.config.name, self._current_clip)

        pyav_out = PyavOutput(str(self._current_clip))
        self._circular.open_output(pyav_out)
        self._state = State.RECORDING

    def _stop_recording(self) -> None:
        name = self.config.name
        clip = self._current_clip
        start = self._recording_start
        start_mono = self._recording_start_mono

        try:
            # stop() flushes all buffered frames then closes the output.
            # start() resumes buffering for the next clip.
            self._circular.stop()
            self._circular.start()
        except Exception:
            log.exception("[%s] error closing output", name)

        self._state = State.IDLE
        self._tail_deadline = 0.0
        self._current_clip = None
        self._recording_start = None
        self._recording_start_mono = None

        if clip and start and clip.exists():
            duration = (datetime.now() - start).total_seconds()
            size_kb = clip.stat().st_size / 1024
            log.info("[%s] clip saved: %s (%.1fs, %.0f KB)", name, clip, duration, size_kb)
            if self._on_clip_saved:
                try:
                    self._on_clip_saved(name, clip, start, duration, start_mono)
                except Exception:
                    log.exception("[%s] on_clip_saved callback error", name)
        else:
            log.warning("[%s] recording stopped but no clip file found", name)
