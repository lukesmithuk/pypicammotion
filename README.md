# pypicammotion

Motion-detection video recording for Raspberry Pi cameras. Uses picamera2 + OpenCV to detect motion on a low-res stream and save H.264 MP4 clips with a pre-motion buffer. Supports multiple cameras, disk quota management, optional audio recording from a USB microphone, and optional MQTT notifications.

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
| `cameras.*.audio` | `true` | Mux audio onto this camera's clips (requires global audio enabled) |
| `audio.enabled` | `false` | Enable audio capture from a microphone |
| `audio.device` | `null` | Audio device name or index (`python -m sounddevice` to list) |
| `audio.sample_rate` | `48000` | Sample rate in Hz |
| `audio.channels` | `1` | Number of channels (1=mono, 2=stereo) |
| `audio.buffer_seconds` | `15.0` | Rolling buffer size (must be >= `pre_motion_seconds`) |
| `mqtt.enabled` | `false` | Enable MQTT clip notifications |
| `mqtt.heartbeat_interval` | `30` | Publish service status every N seconds (0 to disable) |

## Audio

Install with audio support:

```bash
sudo apt install libportaudio2
poetry install -E audio
```

When enabled, audio is captured continuously from a USB microphone into a rolling buffer. After each video clip is saved, matching audio is extracted and muxed onto the MP4 as an AAC stream (video is codec-copied, not re-encoded). Audio can be disabled per-camera with `audio: false` in the camera config.

List available audio devices:

```bash
python -m sounddevice
```

## MQTT

Install with MQTT support:

```bash
poetry install -E mqtt
```

When enabled, each saved clip publishes a JSON message to `{topic_prefix}/clips/{camera_name}`:

```json
{"camera": "front", "path": "/var/lib/.../clip.mp4", "timestamp": "2026-02-09T14:30:00", "duration": 8.5}
```

A retained status message is published to `{topic_prefix}/status` on start, every `heartbeat_interval` seconds, and on shutdown. New subscribers immediately get the last known state:

```json
{"status": "online", "uptime_seconds": 3600, "cameras": {"front": {"state": "idle", "last_clip": "..."}}, "storage": {"clips": 42, "used_mb": 1234.5, "max_mb": 5120.0}, "features": {"audio": true, "mqtt": true}}
```

On shutdown, `{"status": "offline", "timestamp": "..."}` is published (also retained). Set `heartbeat_interval: 0` to disable periodic status.

## systemd

```bash
# Copy config
sudo mkdir -p /etc/pypicammotion
sudo cp config.example.yaml /etc/pypicammotion/config.yaml
# Edit /etc/pypicammotion/config.yaml

# Install service — edit ExecStart to use the full path to the venv binary:
#   ExecStart=/path/to/venv/bin/pypicammotion run --config /etc/pypicammotion/config.yaml
# Find your venv path with: poetry env info -p
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
- Audio is post-muxed: a shared capture thread records to a rolling buffer, then a background worker muxes AAC audio onto each saved MP4 via PyAV (codec-copy video, no re-encode). Failures never affect video clips
- Clips embed MP4 container metadata (title, date, motion score) — inspect with `ffprobe -show_entries format_tags clip.mp4`

## License

CC0-1.0
