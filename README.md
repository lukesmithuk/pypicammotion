# pypicammotion

Motion-detection video recording for Raspberry Pi cameras. Uses picamera2 + OpenCV to detect motion on a low-res stream and save H.264 MP4 clips with a pre-motion buffer. Supports multiple cameras, disk quota management, and optional MQTT notifications.

## Quick Start

```bash
# Install (inside the project directory)
poetry install

# List connected cameras
pypicammotion list-cameras

# Test a single camera — saves clips to /tmp, prints events
pypicammotion test --camera 0 --output-dir /tmp/clips

# Run with a config file
cp config.example.yaml config.yaml   # edit to taste
pypicammotion run --config config.yaml
```

## CLI Usage

```
pypicammotion [-v] <command>

Commands:
  list-cameras              List connected cameras
  test                      Test a single camera with live output
    --camera N              Camera device number (default: 0)
    --sensitivity F         Motion sensitivity 0.0–1.0 (default: 0.05)
    --output-dir PATH       Directory for clips (default: /tmp/pypicammotion-test)
  run                       Run the full service
    --config PATH           Path to YAML config file (required)

Flags:
  -v, --verbose             Enable debug logging
```

## Configuration

See [`config.example.yaml`](config.example.yaml) for a fully commented example. Key settings:

| Setting | Default | Description |
|---|---|---|
| `storage.path` | `/var/lib/pypicammotion/clips` | Where clips are saved (supports `~`) |
| `storage.max_gb` | `10.0` | Disk quota — oldest clips evicted first |
| `storage.require_mount` | `false` | Refuse to start if path is on root filesystem (for USB drives) |
| `cameras.*.device` | `0` | Camera index from `list-cameras` |
| `cameras.*.resolution` | `[1920, 1080]` | Recording resolution |
| `cameras.*.fps` | `30` | Framerate |
| `cameras.*.pre_motion_seconds` | `5.0` | Buffer before motion |
| `cameras.*.post_motion_seconds` | `3.0` | Recording tail after motion stops |
| `cameras.*.sensitivity` | `0.05` | Fraction of frame that must change (lower = more sensitive) |
| `mqtt.enabled` | `false` | Enable MQTT clip notifications |

## MQTT

Install with MQTT support:

```bash
poetry install -E mqtt
```

When enabled, each saved clip publishes a JSON message to `{topic_prefix}/clips/{camera_name}`:

```json
{"camera": "front", "path": "/var/lib/.../clip.mp4", "timestamp": "2026-02-09T14:30:00", "duration": 8.5}
```

## systemd

```bash
# Copy config
sudo mkdir -p /etc/pypicammotion
sudo cp config.example.yaml /etc/pypicammotion/config.yaml
# Edit /etc/pypicammotion/config.yaml

# Install service
sudo cp systemd/pypicammotion.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pypicammotion

# Check status
systemctl status pypicammotion
journalctl -u pypicammotion -f
```

## Architecture

- One thread per camera, Picamera2 created inside its thread
- Motion detection runs on the `lores` stream (640x480 YUV420) via `pre_callback` — the Y-plane is already grayscale. Compares each frame to one from ~0.5 s ago (ring buffer) so continuous motion sustains detection
- Recording uses `CircularOutput2` + `PyavOutput` for MP4 with pre-motion buffer
- `LibavH264Encoder` (software H.264) — Pi 5 has no hardware H.264 encoder
- Storage manager tracks clips in-memory, rescans on startup, evicts oldest-first

## License

CC0-1.0
