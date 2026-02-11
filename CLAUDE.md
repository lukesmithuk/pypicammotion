# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

pypicammotion — motion-detection video recording service for Raspberry Pi cameras using picamera2 + OpenCV. Runs on a Raspberry Pi 5 (arm64, Debian Trixie).

## Build & Run Commands

```bash
# Install dependencies (Poetry 2.x, installed via pipx)
poetry install                    # core deps only
poetry install --extras mqtt      # include paho-mqtt

# Run the service
poetry run pypicammotion run --config /path/to/config.yaml

# List connected cameras
poetry run pypicammotion list-cameras

# Test a single camera
poetry run pypicammotion test --camera 0 --sensitivity 0.5 --output-dir ./clips

# Debug logging
poetry run pypicammotion -v run --config config.yaml
```

There are no automated tests yet — only a manual test plan in `TEST_PLAN.md`.

## Architecture

The service follows a **one-thread-per-camera** model with a shared storage manager:

```
cli.py → Service → Camera(s) → MotionDetector
           │                        ↓ (pre_callback on lores stream)
           ├── StorageManager  ← registers clips, enforces disk quota
           └── MqttNotifier    ← optional, publishes clip-saved events
```

**Camera state machine**: `IDLE → RECORDING → TAIL → IDLE`
- IDLE: monitoring lores stream for motion via `pre_callback`
- RECORDING: writing H.264 to CircularOutput2 + PyavOutput (MP4)
- TAIL: post-motion grace period before stopping

**Motion detection** (`motion.py`): Extracts Y-plane from YUV420 lores frames → Gaussian blur → absdiff against ring buffer frame (~0.5s ago) → threshold → dilate → contour filtering. Score = fraction of frame area with significant contours.

**Key design decisions** (see `DECISIONS.md` for rationale):
- LibavH264Encoder (software) — Pi 5 has no V4L2 H.264 hardware encoder
- Picamera2 objects created inside their thread (not thread-safe across threads)
- Cameras start sequentially with 1s delay to avoid libcamera init races
- `stop()+start()` (not `close_output()`) to flush circular buffer on clip save
- paho-mqtt is an optional dependency with graceful ImportError handling

## Key Files

| File | Purpose |
|------|---------|
| `pypicammotion/cli.py` | Entry point, argparse commands |
| `pypicammotion/service.py` | Multi-camera orchestrator, signal handling |
| `pypicammotion/camera.py` | Camera thread, state machine, recording logic |
| `pypicammotion/motion.py` | Frame differencing motion detector |
| `pypicammotion/storage.py` | Disk quota enforcement, oldest-first eviction |
| `pypicammotion/notifier.py` | Optional MQTT notifications |
| `pypicammotion/config.py` | YAML config loading, dataclasses, validation |
| `config.example.yaml` | Annotated example configuration |
| `systemd/pypicammotion.service` | systemd unit for deployment |

## Environment Notes

- Python is externally-managed (PEP 668) — use `pipx` for global tools, `poetry` for project deps
- `libcap-dev` must be installed for `python-prctl` (transitive dep of picamera2)
- Clip storage path: `{storage}/{camera_name}/{YYYY-MM-DD}/{HH-MM-SS}.mp4`
