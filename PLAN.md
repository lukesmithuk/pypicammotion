# Plan: pypicammotion — Full Implementation

## Context

pypicammotion is a motion-detection video recording service for Raspberry Pi cameras. The project is scaffolded with Poetry at `/home/pls/catpi/pypicammotion/` with picamera2 and opencv-python installed. We need to implement the full package: multi-camera motion detection, clip saving with pre-motion buffer, disk quota management, MQTT notifications, CLI test tool, and systemd service.

## Key Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Encoder | `LibavH264Encoder` (software/libx264) | Pi 5 has no V4L2 H264 hardware encoder |
| Motion detection stream | `lores` at 640x480 YUV420 | Y-plane is already grayscale — no `cvtColor` needed. 1/9th the pixels of 1080p |
| Frame access | picamera2 `pre_callback` | Runs in picamera2's event loop, no extra capture thread |
| Ring buffer | `CircularOutput2` + `PyavOutput` | Built into picamera2 — `open_output()` to start recording, `stop()` + `start()` to flush and close. Outputs MP4 |
| Threading | One thread per camera, Picamera2 created inside thread | picamera2 setup is not thread-safe across instances |
| Config | YAML via `pyyaml`, dataclasses | Minimal deps, natural for nested per-camera config |
| MQTT | Optional dep (`paho-mqtt`), graceful degradation | Service works without network; import is guarded |
| Storage tracking | In-memory sorted list, disk scan on startup | Clips are append-only FIFO — no database needed |

## Module Structure

```
pypicammotion/
├── __init__.py       # Package metadata + version
├── config.py         # YAML loading, validation, dataclasses
├── motion.py         # OpenCV frame differencing on YUV420 Y-plane
├── camera.py         # Picamera2 wrapper + IDLE/RECORDING/TAIL state machine
├── storage.py        # Disk quota enforcement, oldest-first eviction
├── notifier.py       # Optional MQTT notifications (paho-mqtt)
├── service.py        # Multi-camera orchestrator, signal handling
└── cli.py            # CLI entry points: list-cameras, test, run
```

## Dependencies to Add

- `pyproject.toml` `dependencies`: add `pyyaml>=6.0`
- `pyproject.toml` `[project.optional-dependencies]`: `mqtt = ["paho-mqtt>=2.0"]`
- `pyproject.toml` `[project.scripts]`: `pypicammotion = "pypicammotion.cli:main"`

---

## Phase 1: Single Camera Motion Detection + Clip Saving

**Goal**: One camera detects motion and saves MP4 clips with pre-motion buffer.

### Files to create/modify

**`pyproject.toml`** — Add pyyaml, optional paho-mqtt, CLI entry point.

**`config.py`** — Dataclasses for configuration:
- `CameraConfig`: name, device (int), resolution, lores_resolution, fps, pre_motion_seconds, post_motion_seconds, sensitivity (0.0–1.0), min_contour_area, blur_kernel
- `StorageConfig`: path (tilde-expanded via `expanduser()`), max_gb
- `MqttConfig`: broker, port, topic_prefix, enabled
- `AppConfig`: storage, mqtt, cameras dict
- `load_config(path) -> AppConfig` with defaults and validation

**`motion.py`** — `MotionDetector` class:
- `detect(frame) -> (bool, float)` — returns (motion_detected, motion_score)
- Uses a ring buffer of `compare_frames` blurred grayscale frames (default 15, ~0.5 s at 30 fps). Compares the current frame to the oldest in the buffer so continuous, steady motion keeps producing a large diff rather than vanishing between consecutive frames.
- Algorithm: extract Y-plane from YUV420 → GaussianBlur → absdiff with oldest buffered frame → threshold → dilate → findContours → filter by min_contour_area → motion_score = contour area / total pixels → compare to sensitivity
- `compare_frames` is derived from camera FPS: `max(1, fps // 2)` — always ~0.5 s
- `reset()` — clear frame buffer

**`camera.py`** — `Camera` class wrapping one Picamera2 instance:
- State machine: `IDLE → RECORDING → TAIL → IDLE`
  - IDLE + motion → start_recording → RECORDING
  - RECORDING + motion → reset tail timer
  - RECORDING + no motion → set tail deadline → TAIL
  - TAIL + motion → back to RECORDING
  - TAIL + deadline passed → stop_recording → IDLE
- Uses `pre_callback` on `lores` stream for motion detection (fast, <5ms)
- Recording: `CircularOutput2(buffer_duration_ms)` → `open_output(PyavOutput(...))` to start, `stop()` + `start()` to flush buffer and finalize MP4 (not `close_output()` which discards unflushed frames)
- Clip path: `{storage}/{camera_name}/{YYYY-MM-DD}/{HH-MM-SS}.mp4`
- `on_clip_saved` callback: (camera_name, path, timestamp, duration)

**`cli.py`** — Subcommands:
- `list-cameras` — print `Picamera2.global_camera_info()`
- `test --camera N --sensitivity F --output-dir PATH` — run single camera, print motion events to terminal

**`__init__.py`** — version string

### Verify
- `pypicammotion list-cameras` shows both cameras
- `pypicammotion test --camera 0 --output-dir /tmp/clips` — wave hand, see motion events printed, MP4 saved with pre-buffer, playable, Ctrl+C closes cleanly

---

## Phase 2: Storage Quota Management

**Goal**: Enforce disk limits, evict oldest clips.

### Files to create/modify

**`storage.py`** — `StorageManager` class:
- `_scan()` — walk base_path on startup, find all `.mp4`, build sorted list by mtime
- `register_clip(path)` — add to tracking, call `enforce_quota()`
- `enforce_quota()` — delete oldest clips until under max_bytes, remove empty dirs
- Thread-safe (shared across camera threads)

**`camera.py`** — Accept `StorageManager`, call `register_clip` after saving.

### Verify
- Set max_gb to 0.001 (1MB), record several clips, confirm oldest are deleted
- Restart service, confirm re-scan picks up existing clips

---

## Phase 3: Multi-Camera + Service Orchestrator

**Goal**: Run all cameras from one process with YAML config.

### Files to create/modify

**`service.py`** — `Service` class:
- Creates shared `StorageManager`
- Starts each `Camera` in its own thread (sequential startup to avoid libcamera races)
- `run()` — install SIGTERM/SIGINT handlers, block on shutdown event
- Error isolation: one camera failing doesn't crash the others

**`cli.py`** — Add `run --config PATH` subcommand.

**`camera.py`** — Refine threading: `start()` spawns thread, `_run()` creates Picamera2 inside thread.

### Verify
- YAML config with both cameras, `pypicammotion run --config config.yaml`
- Independent motion on each camera produces separate clips
- SIGTERM → clean shutdown, last clips are valid MP4
- One bad device number → other camera still runs

---

## Phase 4: MQTT Notifications

**Goal**: Publish clip events to MQTT broker.

### Files to create/modify

**`notifier.py`** — `MqttNotifier` class:
- `start()` — connect to broker, `loop_start()`. Guards `ImportError` for missing paho-mqtt
- `notify_clip_saved(camera, path, timestamp, duration)` — publish JSON to `{prefix}/clips/{camera}`
- `stop()` — disconnect
- Auto-reconnect via paho-mqtt's built-in mechanism

**`service.py`** — Wire notifier as `on_clip_saved` callback if MQTT enabled.

### MQTT message format
```json
{"camera": "front", "path": "/var/lib/.../clip.mp4", "timestamp": "2026-02-09T14:30:00", "duration": 8.5}
```

### Verify
- `mosquitto_sub -t "pypicammotion/#"` shows messages on motion
- Kill broker → service continues, clips still save
- Restart broker → auto-reconnect, notifications resume
- Without paho-mqtt installed → warning logged, service runs fine

---

## Phase 5: systemd + Polish

**Goal**: Production-ready deployment.

### Files to create

**`systemd/pypicammotion.service`** — Unit file:
- `Type=simple`, `ExecStart=pypicammotion run --config /etc/pypicammotion/config.yaml`
- `User=root`, `Group=video`, `Restart=on-failure`, `TimeoutStopSec=15`

**`config.example.yaml`** — Fully commented example config.

### Files to modify

**`cli.py`** — Add `--verbose` flag, configure Python logging (INFO default, simpler format under systemd).

**`README.md`** — Quick start, config reference, systemd install steps, CLI usage.

### Verify
- `systemctl enable --now pypicammotion` → service starts
- `journalctl -u pypicammotion -f` → logs visible
- `systemctl stop` → clean shutdown
- Reboot → auto-start
