# pypicammotion — Manual Test Plan

All commands assume you are in the project directory (`/home/pls/catpi/pypicammotion/`) and the package is installed via `poetry install`. Prefix commands with `poetry run` if the venv is not activated.

---

## 1. config.py — YAML Config Loading

### 1.1 Load example config

```bash
python3 -c "
from pypicammotion.config import load_config
cfg = load_config('config.example.yaml')
print(f'storage path: {cfg.storage.path}')
print(f'storage max_gb: {cfg.storage.max_gb}')
print(f'storage max_bytes: {cfg.storage.max_bytes}')
print(f'mqtt enabled: {cfg.mqtt.enabled}')
print(f'cameras: {list(cfg.cameras.keys())}')
for name, cam in cfg.cameras.items():
    print(f'  {name}: device={cam.device} res={cam.resolution} lores={cam.lores_resolution} '
          f'fps={cam.fps} sens={cam.sensitivity} pre={cam.pre_motion_seconds}s post={cam.post_motion_seconds}s')
"
```

- [ ] Prints storage path `/var/lib/pypicammotion/clips`, max_gb `10.0`
- [ ] max_bytes equals `10 * 1073741824`
- [ ] MQTT shows `enabled: False`
- [ ] Camera `front` listed with expected defaults from `config.example.yaml`

### 1.2 Defaults when no cameras defined

Create a minimal config:
```bash
echo "storage: {path: /tmp/test-clips}" > /tmp/minimal.yaml
python3 -c "
from pypicammotion.config import load_config
cfg = load_config('/tmp/minimal.yaml')
print(f'cameras: {list(cfg.cameras.keys())}')
print(f'cam0 device: {cfg.cameras[\"cam0\"].device}')
"
```

- [ ] Warning logged: `no cameras defined in config, adding default camera 0`
- [ ] Default camera `cam0` with `device=0` is created

### 1.3 Validation — sensitivity out of range

```bash
cat > /tmp/bad-sens.yaml << 'EOF'
cameras:
  bad:
    device: 0
    sensitivity: 1.5
EOF
python3 -c "
from pypicammotion.config import load_config
load_config('/tmp/bad-sens.yaml')
"
```

- [ ] Raises `ValueError` mentioning `sensitivity must be 0.0–1.0`

### 1.4 Validation — even blur kernel

```bash
cat > /tmp/bad-blur.yaml << 'EOF'
cameras:
  bad:
    device: 0
    blur_kernel: 20
EOF
python3 -c "
from pypicammotion.config import load_config
load_config('/tmp/bad-blur.yaml')
"
```

- [ ] Raises `ValueError` mentioning `blur_kernel must be odd`

### 1.5 Validation — bad resolution

```bash
cat > /tmp/bad-res.yaml << 'EOF'
cameras:
  bad:
    device: 0
    resolution: [1920]
EOF
python3 -c "
from pypicammotion.config import load_config
load_config('/tmp/bad-res.yaml')
"
```

- [ ] Raises `ValueError` mentioning `resolution must be [width, height]`

### 1.6 Non-mapping config file

```bash
echo '"just a string"' > /tmp/bad-type.yaml
python3 -c "
from pypicammotion.config import load_config
load_config('/tmp/bad-type.yaml')
"
```

- [ ] Raises `ValueError` mentioning `config file must be a YAML mapping`

---

## 2. motion.py — Motion Detection

### 2.1 No motion on identical frames

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480))
frame = np.full((720, 640), 128, dtype=np.uint8)  # YUV420: 480 * 3/2 = 720 rows

motion, score = det.detect(frame)
print(f'first frame:  motion={motion}, score={score}')

motion, score = det.detect(frame)
print(f'same frame:   motion={motion}, score={score}')
"
```

- [ ] First frame: `motion=False, score=0.0` (no previous frame to compare)
- [ ] Same frame: `motion=False, score=0.0` (no change)

### 2.2 Motion detected on changed frame

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), sensitivity=0.05, min_contour_area=500)
frame1 = np.full((720, 640), 128, dtype=np.uint8)
det.detect(frame1)  # prime

frame2 = frame1.copy()
frame2[100:350, 150:450] = 255  # large bright rectangle
motion, score = det.detect(frame2)
print(f'motion={motion}, score={score:.4f}')
"
```

- [ ] `motion=True`
- [ ] `score` is significantly above 0.05

### 2.3 Small contours filtered out

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), sensitivity=0.001, min_contour_area=5000)
frame1 = np.full((720, 640), 128, dtype=np.uint8)
det.detect(frame1)

frame2 = frame1.copy()
frame2[200:210, 200:210] = 255  # tiny 10x10 change
motion, score = det.detect(frame2)
print(f'motion={motion}, score={score:.6f}')
"
```

- [ ] `motion=False` — the 10x10 contour (100 pixels) is below `min_contour_area=5000`

### 2.4 Reset clears state

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480))
frame = np.full((720, 640), 128, dtype=np.uint8)
det.detect(frame)

det.reset()

motion, score = det.detect(frame)
print(f'after reset: motion={motion}, score={score}')
"
```

- [ ] After reset, first frame returns `motion=False, score=0.0` again (no previous frame)

### 2.5 BGR frame input (3-channel)

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480))
frame1 = np.full((480, 640, 3), 128, dtype=np.uint8)
motion, score = det.detect(frame1)
print(f'BGR first frame: motion={motion}, score={score}')

frame2 = frame1.copy()
frame2[100:300, 100:400] = [255, 0, 0]
motion, score = det.detect(frame2)
print(f'BGR motion: motion={motion}, score={score:.4f}')
"
```

- [ ] First frame: `motion=False`
- [ ] Changed frame: `motion=True` with nonzero score

---

## 3. storage.py — Disk Quota Management

### 3.1 Scan on startup

```bash
python3 -c "
import tempfile, os
from pathlib import Path
from pypicammotion.storage import StorageManager

with tempfile.TemporaryDirectory() as d:
    # Create some fake clips
    for i in range(5):
        p = Path(d) / f'cam/2026-01-0{i+1}'
        p.mkdir(parents=True)
        f = p / '12-00-00.mp4'
        f.write_bytes(b'x' * 1000)

    sm = StorageManager(d, max_bytes=100_000)
    print(f'clips tracked: {len(sm._clips)}')
    print(f'total bytes: {sm._total_bytes}')
"
```

- [ ] `clips tracked: 5`
- [ ] `total bytes: 5000`

### 3.2 Register clip

```bash
python3 -c "
import tempfile
from pathlib import Path
from pypicammotion.storage import StorageManager

with tempfile.TemporaryDirectory() as d:
    sm = StorageManager(d, max_bytes=100_000)

    clip = Path(d) / 'test.mp4'
    clip.write_bytes(b'x' * 2000)
    sm.register_clip(clip)

    print(f'clips: {len(sm._clips)}')
    print(f'total: {sm._total_bytes}')
"
```

- [ ] `clips: 1`, `total: 2000`

### 3.3 Quota eviction — oldest deleted first

```bash
python3 -c "
import tempfile, time
from pathlib import Path
from pypicammotion.storage import StorageManager

with tempfile.TemporaryDirectory() as d:
    # Max 3000 bytes
    sm = StorageManager(d, max_bytes=3000)

    clips = []
    for i in range(4):
        p = Path(d) / f'clip{i}.mp4'
        p.write_bytes(b'x' * 1000)
        time.sleep(0.05)  # ensure distinct mtime
        sm.register_clip(p)
        clips.append(p)

    # 4 clips * 1000 bytes = 4000, quota is 3000
    # Oldest should be evicted
    print(f'clip0 exists: {clips[0].exists()}')
    print(f'clip1 exists: {clips[1].exists()}')
    print(f'clip2 exists: {clips[2].exists()}')
    print(f'clip3 exists: {clips[3].exists()}')
    print(f'total: {sm._total_bytes}')
"
```

- [ ] `clip0 exists: False` (evicted)
- [ ] `clip1–clip3 exists: True`
- [ ] `total: 3000`

### 3.4 Empty parent directories removed

```bash
python3 -c "
import tempfile, time
from pathlib import Path
from pypicammotion.storage import StorageManager

with tempfile.TemporaryDirectory() as d:
    sm = StorageManager(d, max_bytes=500)

    nested = Path(d) / 'cam' / '2026-01-01'
    nested.mkdir(parents=True)
    clip = nested / '12-00-00.mp4'
    clip.write_bytes(b'x' * 1000)
    sm.register_clip(clip)

    # Over quota — clip evicted
    print(f'clip exists: {clip.exists()}')
    print(f'date dir exists: {nested.exists()}')
    print(f'cam dir exists: {nested.parent.exists()}')
"
```

- [ ] `clip exists: False`
- [ ] `date dir exists: False` (empty, removed)
- [ ] `cam dir exists: False` (empty, removed)

### 3.5 Creates base path if missing

```bash
python3 -c "
import tempfile
from pathlib import Path
from pypicammotion.storage import StorageManager

with tempfile.TemporaryDirectory() as d:
    new_path = Path(d) / 'nonexistent' / 'path'
    sm = StorageManager(new_path, max_bytes=100_000)
    print(f'path created: {new_path.exists()}')
"
```

- [ ] `path created: True`

---

## 4. notifier.py — MQTT Notifications

### 4.1 Graceful degradation without paho-mqtt

```bash
python3 -c "
import logging, sys
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

# Simulate missing paho-mqtt by testing the guard
from pypicammotion.notifier import _HAS_MQTT, MqttNotifier
print(f'paho-mqtt available: {_HAS_MQTT}')

n = MqttNotifier('localhost', 1883, 'test')
n.start()  # should log warning if not installed, not crash
n.stop()
print('no crash')
"
```

- [ ] If paho-mqtt not installed: prints `paho-mqtt available: False`, logs warning, prints `no crash`
- [ ] If paho-mqtt is installed: prints `paho-mqtt available: True`, attempts connection, prints `no crash`

### 4.2 Notify with no client (MQTT not started or unavailable)

```bash
python3 -c "
from datetime import datetime
from pathlib import Path
from pypicammotion.notifier import MqttNotifier

n = MqttNotifier('localhost', 1883, 'test')
# Don't call start() — _client is None
n.notify_clip_saved('cam0', Path('/tmp/clip.mp4'), datetime.now(), 5.0)
print('notify with no client: no crash')
"
```

- [ ] No exception, prints `no crash`

### 4.3 Full MQTT round-trip (requires mosquitto)

*Prerequisites: `sudo apt install mosquitto mosquitto-clients`, `poetry install -E mqtt`*

Terminal 1 — subscribe:
```bash
mosquitto_sub -t "pypicammotion/#" -v
```

Terminal 2 — publish a test notification:
```bash
python3 -c "
import time, logging, sys
from datetime import datetime
from pathlib import Path
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

from pypicammotion.notifier import MqttNotifier
n = MqttNotifier('localhost', 1883, 'pypicammotion')
n.start()
time.sleep(1)
n.notify_clip_saved('front', Path('/tmp/test.mp4'), datetime(2026, 2, 9, 14, 30), 8.5)
time.sleep(1)
n.stop()
"
```

- [ ] Terminal 1 receives: `pypicammotion/clips/front {"camera": "front", "path": "/tmp/test.mp4", "timestamp": "2026-02-09T14:30:00", "duration": 8.5}`

### 4.4 Broker unavailable — no crash

```bash
python3 -c "
import logging, sys
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

from pypicammotion.notifier import MqttNotifier
n = MqttNotifier('192.0.2.1', 1883, 'test')  # non-routable address
n.start()
n.stop()
print('no crash with unreachable broker')
"
```

- [ ] Logs connection error, does not crash

---

## 5. camera.py — Picamera2 Wrapper + State Machine

*All camera tests require a physical camera connected.*

### 5.1 Single camera test — motion triggers recording

```bash
pypicammotion test --camera 0 --sensitivity 0.05 --output-dir /tmp/cam-test
```

- [ ] Prints `testing camera 0 (sensitivity=0.05)` and `clips → /tmp/cam-test`
- [ ] Wave hand or move in front of camera
- [ ] Log shows `motion started — recording to /tmp/cam-test/test/YYYY-MM-DD/HH-MM-SS.mp4`
- [ ] After motion stops, log shows `clip saved: ... (Xs, Y KB)`
- [ ] Clip file exists at the logged path

### 5.2 Clip is playable MP4 with pre-buffer

```bash
ffprobe /tmp/cam-test/test/*//*.mp4 2>&1 | grep -E "Duration|Video"
# or play with:
ffplay /tmp/cam-test/test/*//*.mp4
```

- [ ] `ffprobe` shows valid H.264 video stream
- [ ] Duration is longer than just the motion period (pre-buffer included)

### 5.3 Multiple motion events produce separate clips

1. Run `pypicammotion test --camera 0 --output-dir /tmp/cam-multi`
2. Wave hand, wait for recording to stop
3. Wave hand again, wait for recording to stop
4. Ctrl+C

```bash
find /tmp/cam-multi -name "*.mp4" | wc -l
```

- [ ] At least 2 separate `.mp4` files

### 5.4 Ctrl+C clean shutdown

1. Run `pypicammotion test --camera 0 --output-dir /tmp/cam-shutdown`
2. Trigger motion so recording starts
3. Press Ctrl+C while still recording

- [ ] Prints `stopping…` then `done`
- [ ] No tracebacks
- [ ] If a clip was being recorded, it is saved and valid (or at least no crash)

### 5.5 High sensitivity — constant recording

```bash
pypicammotion test --camera 0 --sensitivity 0.001 --output-dir /tmp/cam-sensitive
```

- [ ] Recording starts almost immediately (very low threshold)
- [ ] Ctrl+C stops cleanly

### 5.6 Low sensitivity — no false triggers

```bash
pypicammotion test --camera 0 --sensitivity 0.8 --output-dir /tmp/cam-insensitive
```

- [ ] No recording triggered by normal ambient changes
- [ ] Only triggers if >80% of the frame changes (e.g. covering/uncovering the lens)

### 5.7 Invalid camera device

```bash
pypicammotion test --camera 99 --output-dir /tmp/cam-bad 2>&1
```

- [ ] Logs a camera error (not a bare traceback crash)
- [ ] Process exits or can be Ctrl+C'd

---

## 6. service.py — Multi-Camera Orchestrator

### 6.1 Run with example config (single camera)

```bash
cat > /tmp/svc-test.yaml << 'EOF'
storage:
  path: /tmp/svc-clips
  max_gb: 0.1
cameras:
  front:
    device: 0
    sensitivity: 0.05
EOF
pypicammotion run --config /tmp/svc-test.yaml
```

- [ ] Logs `started camera 'front'`
- [ ] Logs `service running with 1 camera(s)`
- [ ] Motion triggers recording and clips appear in `/tmp/svc-clips/front/`

### 6.2 SIGTERM clean shutdown

In one terminal:
```bash
pypicammotion run --config /tmp/svc-test.yaml &
SVC_PID=$!
sleep 5
kill $SVC_PID
wait $SVC_PID
```

- [ ] Logs `received SIGTERM — shutting down`
- [ ] Logs `stopping cameras…` then `shutdown complete`
- [ ] Process exits with code 0

### 6.3 Two cameras

*Requires two cameras connected (devices 0 and 1).*

```bash
cat > /tmp/svc-dual.yaml << 'EOF'
storage:
  path: /tmp/svc-dual-clips
  max_gb: 0.5
cameras:
  front:
    device: 0
    sensitivity: 0.05
  back:
    device: 1
    sensitivity: 0.05
EOF
pypicammotion run --config /tmp/svc-dual.yaml
```

- [ ] Both cameras start (logs show two `started camera` messages)
- [ ] Motion on camera 0 saves to `/tmp/svc-dual-clips/front/`
- [ ] Motion on camera 1 saves to `/tmp/svc-dual-clips/back/`
- [ ] Ctrl+C shuts down both cameras

### 6.4 One bad device — other camera survives

```bash
cat > /tmp/svc-mixed.yaml << 'EOF'
storage:
  path: /tmp/svc-mixed-clips
  max_gb: 0.1
cameras:
  good:
    device: 0
    sensitivity: 0.05
  bad:
    device: 99
    sensitivity: 0.05
EOF
pypicammotion run --config /tmp/svc-mixed.yaml
```

- [ ] Logs an error for device 99
- [ ] Camera `good` (device 0) continues to run and detect motion
- [ ] Service does not crash

### 6.5 Storage quota enforced during service run

```bash
cat > /tmp/svc-quota.yaml << 'EOF'
storage:
  path: /tmp/svc-quota-clips
  max_gb: 0.001
cameras:
  front:
    device: 0
    sensitivity: 0.03
EOF
pypicammotion run --config /tmp/svc-quota.yaml
```

1. Trigger several motion events to generate clips
2. Watch logs for `storage: evicted ...` messages

- [ ] Oldest clips are deleted when total exceeds ~1 MB
- [ ] Logs show eviction messages with file paths and sizes

---

## 7. cli.py — CLI Entry Points

### 7.1 Help output

```bash
pypicammotion --help
pypicammotion test --help
pypicammotion run --help
```

- [ ] Main help shows all three subcommands
- [ ] `test --help` shows `--camera`, `--sensitivity`, `--output-dir`
- [ ] `run --help` shows `--config`

### 7.2 list-cameras

```bash
pypicammotion list-cameras
```

- [ ] Lists all connected cameras with `[N] model  id=...`
- [ ] Camera numbers match what `libcamera-hello --list-cameras` reports

### 7.3 Verbose mode

```bash
pypicammotion -v list-cameras 2>&1 | head -5
```

- [ ] More detailed log output (DEBUG level) appears on stderr

### 7.4 No subcommand — prints help

```bash
pypicammotion
echo "exit code: $?"
```

- [ ] Prints usage/help text
- [ ] Exit code is 1

### 7.5 run without --config

```bash
pypicammotion run 2>&1
echo "exit code: $?"
```

- [ ] Prints error about required `--config` argument
- [ ] Exit code is 2 (argparse error)

---

## 8. systemd Integration

*Requires root access.*

### 8.1 Install and start service

```bash
sudo mkdir -p /etc/pypicammotion
sudo cp config.example.yaml /etc/pypicammotion/config.yaml
# Edit /etc/pypicammotion/config.yaml as needed

sudo cp systemd/pypicammotion.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start pypicammotion
systemctl status pypicammotion
```

- [ ] Service shows `active (running)`

### 8.2 Logs visible in journalctl

```bash
journalctl -u pypicammotion -f --no-pager
```

- [ ] Startup messages visible (camera started, service running)
- [ ] Motion events and clip saves appear in logs

### 8.3 Clean stop

```bash
sudo systemctl stop pypicammotion
systemctl status pypicammotion
```

- [ ] Service stops within 15 seconds (TimeoutStopSec)
- [ ] Logs show `received SIGTERM`, `stopping cameras`, `shutdown complete`
- [ ] Status shows `inactive (dead)`, not `failed`

### 8.4 Restart on failure

```bash
# Simulate a crash (if needed) or verify the Restart=on-failure setting:
cat /etc/systemd/system/pypicammotion.service | grep Restart
```

- [ ] `Restart=on-failure` and `RestartSec=5` are set

### 8.5 Enable on boot

```bash
sudo systemctl enable pypicammotion
sudo systemctl is-enabled pypicammotion
```

- [ ] Shows `enabled`
- [ ] After reboot, `systemctl status pypicammotion` shows `active (running)`

---

## 9. End-to-End Integration

### 9.1 Full pipeline: config → service → clips → quota

1. Create config with two cameras, small quota (50 MB), MQTT disabled
2. `pypicammotion run --config config.yaml`
3. Trigger motion on both cameras repeatedly over several minutes
4. Ctrl+C to stop

- [ ] Clips organized by `{storage_path}/{camera_name}/{YYYY-MM-DD}/{HH-MM-SS}.mp4`
- [ ] All clips are valid, playable MP4 files
- [ ] Each clip contains pre-motion buffer (starts before the motion event)
- [ ] Post-motion tail is present (recording continues briefly after motion stops)
- [ ] Old clips evicted when quota exceeded
- [ ] No error tracebacks in output

### 9.2 Full pipeline with MQTT

*Prerequisites: mosquitto running, `poetry install -E mqtt`*

1. Subscribe: `mosquitto_sub -t "pypicammotion/#" -v`
2. Create config with `mqtt.enabled: true`
3. `pypicammotion run --config config.yaml`
4. Trigger motion

- [ ] MQTT messages appear for each saved clip
- [ ] JSON payload contains `camera`, `path`, `timestamp`, `duration`
- [ ] Kill mosquitto → service continues saving clips without crashing
- [ ] Restart mosquitto → MQTT messages resume
