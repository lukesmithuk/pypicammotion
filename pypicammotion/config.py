from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    name: str
    device: int = 0
    resolution: tuple[int, int] = (1920, 1080)
    lores_resolution: tuple[int, int] = (640, 480)
    fps: int = 30
    pre_motion_seconds: float = 5.0
    post_motion_seconds: float = 3.0
    sensitivity: float = 0.05
    min_contour_area: int = 500
    blur_kernel: int = 21


@dataclass
class StorageConfig:
    path: str = "/var/lib/pypicammotion/clips"
    max_gb: float = 10.0
    require_mount: bool = False

    @property
    def max_bytes(self) -> int:
        return int(self.max_gb * 1_073_741_824)


@dataclass
class MqttConfig:
    enabled: bool = False
    broker: str = "localhost"
    port: int = 1883
    topic_prefix: str = "pypicammotion"


@dataclass
class AppConfig:
    storage: StorageConfig = field(default_factory=StorageConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    cameras: dict[str, CameraConfig] = field(default_factory=dict)


def _parse_resolution(val: list | tuple) -> tuple[int, int]:
    if len(val) != 2:
        raise ValueError(f"resolution must be [width, height], got {val}")
    return (int(val[0]), int(val[1]))


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"config file must be a YAML mapping, got {type(raw).__name__}")

    storage_raw = raw.get("storage", {})
    storage_path = str(Path(storage_raw.get("path", StorageConfig.path)).expanduser())
    storage = StorageConfig(
        path=storage_path,
        max_gb=float(storage_raw.get("max_gb", StorageConfig.max_gb)),
        require_mount=bool(storage_raw.get("require_mount", StorageConfig.require_mount)),
    )

    mqtt_raw = raw.get("mqtt", {})
    mqtt = MqttConfig(
        enabled=bool(mqtt_raw.get("enabled", MqttConfig.enabled)),
        broker=mqtt_raw.get("broker", MqttConfig.broker),
        port=int(mqtt_raw.get("port", MqttConfig.port)),
        topic_prefix=mqtt_raw.get("topic_prefix", MqttConfig.topic_prefix),
    )

    cameras: dict[str, CameraConfig] = {}
    for name, cam_raw in raw.get("cameras", {}).items():
        if not isinstance(cam_raw, dict):
            raise ValueError(f"camera '{name}' config must be a mapping")
        kw: dict = {"name": str(name)}
        if "device" in cam_raw:
            kw["device"] = int(cam_raw["device"])
        if "resolution" in cam_raw:
            kw["resolution"] = _parse_resolution(cam_raw["resolution"])
        if "lores_resolution" in cam_raw:
            kw["lores_resolution"] = _parse_resolution(cam_raw["lores_resolution"])
        for key in ("fps", "min_contour_area", "blur_kernel"):
            if key in cam_raw:
                kw[key] = int(cam_raw[key])
        for key in ("pre_motion_seconds", "post_motion_seconds", "sensitivity"):
            if key in cam_raw:
                kw[key] = float(cam_raw[key])
        cam = CameraConfig(**kw)
        if not 0.0 <= cam.sensitivity <= 1.0:
            raise ValueError(f"camera '{name}': sensitivity must be 0.0–1.0, got {cam.sensitivity}")
        if cam.blur_kernel % 2 == 0:
            raise ValueError(f"camera '{name}': blur_kernel must be odd, got {cam.blur_kernel}")
        cameras[name] = cam

    if not cameras:
        log.warning("no cameras defined in config, adding default camera 0")
        cameras["cam0"] = CameraConfig(name="cam0")

    return AppConfig(storage=storage, mqtt=mqtt, cameras=cameras)
