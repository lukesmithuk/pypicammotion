from __future__ import annotations

import logging
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

from .audio import AudioCapture
from .camera import Camera
from .config import AppConfig
from .notifier import MqttNotifier
from .storage import StorageManager

log = logging.getLogger(__name__)


class Service:
    """Multi-camera orchestrator.

    Creates a shared :class:`StorageManager`, starts each camera in its own
    thread (sequentially to avoid libcamera race conditions), and blocks
    until a shutdown signal is received.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._cameras: list[Camera] = []
        self._camera_names: list[str] = []
        self._storage: StorageManager | None = None
        self._notifier: MqttNotifier | None = None
        self._audio: AudioCapture | None = None
        self._start_time: float = 0.0

    def run(self) -> None:
        self._install_signals()

        # Storage
        self._storage = StorageManager(
            self._config.storage.path,
            self._config.storage.max_bytes,
            require_mount=self._config.storage.require_mount,
        )

        # MQTT (optional)
        if self._config.mqtt.enabled:
            self._notifier = MqttNotifier(
                self._config.mqtt.broker,
                self._config.mqtt.port,
                self._config.mqtt.topic_prefix,
            )
            self._notifier.start()

        # Audio (optional)
        if self._config.audio.enabled:
            self._audio = AudioCapture(
                device=self._config.audio.device,
                sample_rate=self._config.audio.sample_rate,
                channels=self._config.audio.channels,
                buffer_seconds=self._config.audio.buffer_seconds,
            )
            self._audio.start()

        # Start cameras sequentially
        for name, cam_cfg in self._config.cameras.items():
            storage_path = Path(self._config.storage.path)
            cam = Camera(
                config=cam_cfg,
                storage_path=storage_path,
                on_clip_saved=self._on_clip_saved,
                stop_event=self._stop_event,
            )
            self._cameras.append(cam)
            self._camera_names.append(name)
            try:
                cam.start()
                log.info("started camera '%s' (device %d)", name, cam_cfg.device)
                # Small delay between camera starts to avoid libcamera races
                time.sleep(1.0)
            except Exception:
                log.exception("failed to start camera '%s'", name)

        if not self._cameras:
            log.error("no cameras started — exiting")
            return

        log.info("service running with %d camera(s)", len(self._cameras))

        self._start_time = time.monotonic()
        interval = self._config.mqtt.heartbeat_interval

        # Publish initial online status
        if self._notifier and interval > 0:
            self._publish_status()

        # Block until shutdown
        try:
            heartbeat_due = 0.0
            while not self._stop_event.is_set():
                self._stop_event.wait(1.0)
                if self._notifier and interval > 0:
                    heartbeat_due += 1.0
                    if heartbeat_due >= interval:
                        self._publish_status()
                        heartbeat_due = 0.0
        except KeyboardInterrupt:
            pass

        self._shutdown()

    def _build_status(self) -> dict:
        cameras = {}
        for name, cam in zip(self._camera_names, self._cameras):
            cameras[name] = cam.status()
        payload: dict = {
            "status": "online",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "uptime_seconds": round(time.monotonic() - self._start_time),
            "cameras": cameras,
        }
        if self._storage:
            payload["storage"] = self._storage.status()
        payload["features"] = {
            "audio": self._audio is not None,
            "mqtt": self._notifier is not None,
        }
        return payload

    def _publish_status(self) -> None:
        if self._notifier:
            self._notifier.publish_status(self._build_status())

    def _on_clip_saved(
        self,
        camera: str,
        path: Path,
        timestamp: datetime,
        duration: float,
        start_mono: float | None = None,
    ) -> None:
        # Mux audio before registering with storage (file size may change)
        if (
            self._audio
            and start_mono is not None
            and self._config.cameras[camera].audio
        ):
            pre = self._config.cameras[camera].pre_motion_seconds
            self._audio.enqueue_mux(path, start_mono - pre, duration + pre)
        if self._storage:
            self._storage.register_clip(path)
        if self._notifier:
            self._notifier.notify_clip_saved(camera, path, timestamp, duration)

    def _install_signals(self) -> None:
        def _handler(signum, frame):
            signame = signal.Signals(signum).name
            log.info("received %s — shutting down", signame)
            self._stop_event.set()

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)

    def _shutdown(self) -> None:
        log.info("stopping cameras…")
        for cam in self._cameras:
            cam.stop()
        if self._audio:
            self._audio.stop()
        if self._notifier:
            self._notifier.stop()  # publishes offline status before disconnecting
        log.info("shutdown complete")
