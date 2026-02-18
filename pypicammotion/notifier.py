"""Optional MQTT notifier: publishes clip events and periodic heartbeat status."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt

    _HAS_MQTT = True
except ImportError:
    _HAS_MQTT = False


class MqttNotifier:
    """Publish clip events to an MQTT broker.

    Degrades gracefully if paho-mqtt is not installed.
    """

    def __init__(self, broker: str, port: int, topic_prefix: str) -> None:
        self._broker = broker
        self._port = port
        self._prefix = topic_prefix
        self._client: mqtt.Client | None = None

    def start(self) -> None:
        if not _HAS_MQTT:
            log.warning("paho-mqtt not installed — MQTT notifications disabled")
            return

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.enable_logger(log)
        self._client.reconnect_delay_set(min_delay=1, max_delay=60)
        try:
            self._client.connect(self._broker, self._port)
            self._client.loop_start()
            log.info("MQTT connected to %s:%d", self._broker, self._port)
        except OSError:
            log.exception("MQTT connection failed (will auto-reconnect)")
            self._client.loop_start()

    def publish_status(self, payload: dict) -> None:
        """Publish a status payload to {prefix}/status (retained, qos 1)."""
        if not self._client:
            return
        topic = f"{self._prefix}/status"
        try:
            self._client.publish(topic, json.dumps(payload), qos=1, retain=True)
        except Exception:
            log.exception("MQTT status publish failed")

    def publish_offline(self) -> None:
        """Publish an offline status (retained) — call before disconnect."""
        self.publish_status(
            {"status": "offline", "timestamp": datetime.now().isoformat(timespec="seconds")}
        )

    def stop(self) -> None:
        if self._client:
            self.publish_offline()
            self._client.loop_stop()
            self._client.disconnect()
            log.info("MQTT disconnected")

    def notify_clip_saved(
        self, camera: str, path: Path, timestamp: datetime, duration: float
    ) -> None:
        if not self._client:
            return

        topic = f"{self._prefix}/clips/{camera}"
        payload = json.dumps(
            {
                "camera": camera,
                "path": str(path),
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "duration": round(duration, 1),
            }
        )
        try:
            self._client.publish(topic, payload, qos=1)
        except Exception:
            log.exception("MQTT publish failed")
