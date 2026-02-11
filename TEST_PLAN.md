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
print(f'audio enabled: {cfg.audio.enabled}')
print(f'audio: device={cfg.audio.device} rate={cfg.audio.sample_rate} ch={cfg.audio.channels} buf={cfg.audio.buffer_seconds}s')
print(f'cameras: {list(cfg.cameras.keys())}')
for name, cam in cfg.cameras.items():
    print(f'  {name}: device={cam.device} res={cam.resolution} lores={cam.lores_resolution} '
          f'fps={cam.fps} sens={cam.sensitivity} pre={cam.pre_motion_seconds}s post={cam.post_motion_seconds}s audio={cam.audio}')
"
```

- [ ] Prints storage path `/mnt/usb/clips`, max_gb `200.0`
- [ ] max_bytes equals `200 * 1073741824` (214748364800)
- [ ] MQTT shows `enabled: False`
- [ ] Audio shows `enabled: False`
- [ ] Camera `front` listed with expected defaults from `config.example.yaml`

### 1.2 Tilde expansion in storage path

```bash
cat > /tmp/tilde-test.yaml << 'EOF'
storage:
  path: ~/my-clips
cameras:
  cam0:
    device: 0
EOF
python3 -c "
from pypicammotion.config import load_config
cfg = load_config('/tmp/tilde-test.yaml')
print(f'storage path: {cfg.storage.path}')
"
```

- [ ] Path is expanded to `/home/<user>/my-clips`, not literal `~/my-clips`

### 1.3 Defaults when no cameras defined

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

### 1.4 Validation — sensitivity out of range

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

### 1.5 Validation — even blur kernel

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

### 1.6 Validation — bad resolution

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

### 1.7 Non-mapping config file

```bash
echo '"just a string"' > /tmp/bad-type.yaml
python3 -c "
from pypicammotion.config import load_config
load_config('/tmp/bad-type.yaml')
"
```

- [ ] Raises `ValueError` mentioning `config file must be a YAML mapping`

### 1.8 Audio config parsing

```bash
cat > /tmp/audio-cfg.yaml << 'EOF'
audio:
  enabled: true
  device: 2
  sample_rate: 48000
  channels: 1
  buffer_seconds: 20.0
cameras:
  front:
    device: 0
  back:
    device: 1
    audio: false
EOF
python3 -c "
from pypicammotion.config import load_config
cfg = load_config('/tmp/audio-cfg.yaml')
print(f'audio enabled: {cfg.audio.enabled}')
print(f'audio device: {cfg.audio.device} (type={type(cfg.audio.device).__name__})')
print(f'audio rate: {cfg.audio.sample_rate}')
print(f'audio channels: {cfg.audio.channels}')
print(f'audio buffer: {cfg.audio.buffer_seconds}')
for name, cam in cfg.cameras.items():
    print(f'  {name}: audio={cam.audio}')
"
```

- [ ] `audio enabled: True`
- [ ] `audio device: 2 (type=int)` — numeric string converted to int
- [ ] `audio rate: 48000`, `channels: 1`, `buffer: 20.0`
- [ ] Camera `front`: `audio=True` (default)
- [ ] Camera `back`: `audio=False` (explicitly disabled)

### 1.9 Audio config defaults

```bash
cat > /tmp/audio-defaults.yaml << 'EOF'
cameras:
  cam0:
    device: 0
EOF
python3 -c "
from pypicammotion.config import load_config
cfg = load_config('/tmp/audio-defaults.yaml')
print(f'audio enabled: {cfg.audio.enabled}')
print(f'audio device: {cfg.audio.device}')
print(f'audio rate: {cfg.audio.sample_rate}')
print(f'cam0 audio: {cfg.cameras[\"cam0\"].audio}')
"
```

- [ ] `audio enabled: False` (default)
- [ ] `audio device: None` (default)
- [ ] `audio rate: 48000` (default)
- [ ] `cam0 audio: True` (default — all cameras get audio unless disabled)

---

## 2. motion.py — Motion Detection

The detector uses a ring buffer of blurred grayscale frames and compares the
current frame to one from `compare_frames` ago (~0.5 s at 30 fps). This keeps
the diff large during continuous, steady motion rather than comparing
consecutive frames which are nearly identical at high frame rates.

### 2.1 No motion on identical frames

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), compare_frames=3)
frame = np.full((720, 640), 128, dtype=np.uint8)  # YUV420: 480 * 3/2 = 720 rows

motion, score = det.detect(frame)
print(f'first frame:  motion={motion}, score={score}')

motion, score = det.detect(frame)
print(f'same frame:   motion={motion}, score={score}')
"
```

- [ ] First frame: `motion=False, score=0.0` (buffer empty, no comparison yet)
- [ ] Same frame: `motion=False, score=0.0` (no change from oldest buffered frame)

### 2.2 Motion detected on changed frame

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), sensitivity=0.05, min_contour_area=500, compare_frames=3)
frame1 = np.full((720, 640), 128, dtype=np.uint8)
det.detect(frame1)  # prime buffer

frame2 = frame1.copy()
frame2[100:350, 150:450] = 255  # large bright rectangle
motion, score = det.detect(frame2)
print(f'motion={motion}, score={score:.4f}')
"
```

- [ ] `motion=True`
- [ ] `score` is significantly above 0.05

### 2.3 Continuous motion holds detection

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), sensitivity=0.05, compare_frames=3)
still = np.full((720, 640), 128, dtype=np.uint8)
motion_frame = still.copy()
motion_frame[100:300, 200:400] = 255

# Prime with still frames
det.detect(still)
det.detect(still)
det.detect(still)

# Motion frame compared to still frame from 3 frames ago
m, s = det.detect(motion_frame)
print(f'frame 4 (motion):      motion={m}, score={s:.4f}')
m, s = det.detect(motion_frame)
print(f'frame 5 (motion cont): motion={m}, score={s:.4f}')
m, s = det.detect(motion_frame)
print(f'frame 6 (motion cont): motion={m}, score={s:.4f}')
"
```

- [ ] Frames 4–6 all show `motion=True` — detection holds across multiple frames
  because each is compared to a still frame from 3 frames ago

### 2.4 Scene change settles after buffer rotates

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), sensitivity=0.05, compare_frames=3)
still = np.full((720, 640), 128, dtype=np.uint8)
changed = still.copy()
changed[100:300, 200:400] = 255

# Prime with still
for _ in range(3):
    det.detect(still)

# Scene changes permanently
det.detect(changed)  # motion (compared to still)
det.detect(changed)  # motion (compared to still)
det.detect(changed)  # motion (compared to still)

# Buffer now full of changed frames — ref is also changed
m, s = det.detect(changed)
print(f'after buffer rotates: motion={m}, score={s:.4f}')
"
```

- [ ] After the buffer fills with the new scene, `motion=False` — the detector adapts

### 2.5 Small contours filtered out

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), sensitivity=0.001, min_contour_area=5000, compare_frames=3)
frame1 = np.full((720, 640), 128, dtype=np.uint8)
det.detect(frame1)

frame2 = frame1.copy()
frame2[200:210, 200:210] = 255  # tiny 10x10 change
motion, score = det.detect(frame2)
print(f'motion={motion}, score={score:.6f}')
"
```

- [ ] `motion=False` — the 10x10 contour (100 pixels) is below `min_contour_area=5000`

### 2.6 Reset clears buffer

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), compare_frames=3)
frame = np.full((720, 640), 128, dtype=np.uint8)
det.detect(frame)
det.detect(frame)

det.reset()

motion, score = det.detect(frame)
print(f'after reset: motion={motion}, score={score}')
"
```

- [ ] After reset, returns `motion=False, score=0.0` (buffer is empty again)

### 2.7 BGR frame input (3-channel)

```bash
python3 -c "
import numpy as np
from pypicammotion.motion import MotionDetector

det = MotionDetector(resolution=(640, 480), compare_frames=3)
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

### 2.8 compare_frames derived from FPS

```bash
python3 -c "
from pypicammotion.config import CameraConfig
from pypicammotion.motion import MotionDetector

for fps in (15, 24, 30, 60):
    compare = max(1, fps // 2)
    print(f'fps={fps} -> compare_frames={compare} ({compare/fps:.2f}s)')
"
```

- [ ] Each FPS produces ~0.5 s worth of frames (e.g. 30fps → 15, 60fps → 30)

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

### 3.5 Mount validation — rejects root filesystem when require_mount is true

Use a path on the root filesystem (not `/tmp` which is tmpfs on some systems):

```bash
python3 -c "
from pypicammotion.storage import StorageManager
try:
    sm = StorageManager('/var/lib/test-mount-clips', max_bytes=100_000, require_mount=True)
    print('ERROR: should have raised RuntimeError')
except RuntimeError as e:
    print(f'correctly rejected: {e}')
"
```

- [ ] Raises `RuntimeError` mentioning "root filesystem" and "is the external drive mounted?"
- [ ] Message includes the storage path and suggests `require_mount: false`

### 3.6 Mount validation — accepts USB mount

```bash
python3 -c "
from pypicammotion.storage import StorageManager
sm = StorageManager('/mnt/usb/test-clips', max_bytes=100_000, require_mount=True)
print('accepted: /mnt/usb is a non-root mount')
"
```

- [ ] Logs `storage: mount validated — /mnt/usb/test-clips is on /mnt/usb`
- [ ] Does not raise

### 3.7 Mount validation — skipped when require_mount is false

```bash
python3 -c "
from pypicammotion.storage import StorageManager
sm = StorageManager('/tmp/test-no-mount', max_bytes=100_000, require_mount=False)
print('accepted without mount validation')
"
```

- [ ] No error, no mount validation log message

### 3.8 Config loading — require_mount parsed from YAML

```bash
cat > /tmp/mount-cfg.yaml << 'EOF'
storage:
  path: /mnt/usb/clips
  max_gb: 200.0
  require_mount: true
cameras:
  cam0:
    device: 0
EOF
python3 -c "
from pypicammotion.config import load_config
cfg = load_config('/tmp/mount-cfg.yaml')
print(f'path: {cfg.storage.path}')
print(f'require_mount: {cfg.storage.require_mount}')
"
```

- [ ] Prints `path: /mnt/usb/clips`
- [ ] Prints `require_mount: True`

### 3.9 Config with require_mount — rejects unmounted path end-to-end

```bash
cat > /tmp/mount-reject-cfg.yaml << 'EOF'
storage:
  path: /var/lib/pypicammotion/clips
  max_gb: 10.0
  require_mount: true
cameras:
  cam0:
    device: 0
EOF
python3 -c "
from pypicammotion.config import load_config
from pypicammotion.storage import StorageManager
cfg = load_config('/tmp/mount-reject-cfg.yaml')
try:
    sm = StorageManager(cfg.storage.path, cfg.storage.max_bytes, require_mount=cfg.storage.require_mount)
    print('ERROR: should have raised RuntimeError')
except RuntimeError as e:
    print(f'correctly rejected: {e}')
"
```

- [ ] Raises `RuntimeError` mentioning "root filesystem" and "is the external drive mounted?"
- [ ] Demonstrates the full config → StorageManager validation path

### 3.10 Creates base path if missing

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

*Prerequisites: `sudo apt install mosquitto mosquitto-clients`*

### 4.1 Graceful degradation without paho-mqtt

```bash
python3 -c "
import logging, sys
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

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

### 4.3 Full MQTT round-trip

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
- [ ] Log shows `motion started (score=N.NNN) — recording to /tmp/cam-test/test/YYYY-MM-DD/HH-MM-SS.mp4`
- [ ] After motion stops, log shows `clip saved: ... (Xs, Y KB, peak=N.NNN)`
- [ ] Clip file exists at the logged path

### 5.2 Clip is playable MP4 with correct duration

```bash
ffprobe /tmp/cam-test/test/*//*.mp4 2>&1 | grep -E "Duration|Video"
# or play with:
ffplay /tmp/cam-test/test/*//*.mp4
```

- [ ] `ffprobe` shows valid H.264 video stream
- [ ] Duration includes pre-motion buffer (clip starts before the motion event)
- [ ] Duration includes post-motion tail (recording continues after motion stops)
- [ ] Video duration roughly matches the duration logged by the service

### 5.3 Continuous motion sustains recording

1. Run `pypicammotion test --camera 0 --output-dir /tmp/cam-continuous`
2. Walk around continuously in front of the camera for 15–20 seconds
3. Stop and wait for recording to end

- [ ] A single clip is saved (not split into multiple short clips)
- [ ] Clip duration roughly matches the time spent moving plus pre/post buffer

### 5.4 Multiple motion events produce separate clips

1. Run `pypicammotion test --camera 0 --output-dir /tmp/cam-multi`
2. Wave hand, wait for recording to stop (~3 s after motion ends)
3. Wave hand again, wait for recording to stop
4. Ctrl+C

```bash
find /tmp/cam-multi -name "*.mp4" | wc -l
```

- [ ] At least 2 separate `.mp4` files

### 5.5 Ctrl+C clean shutdown

1. Run `pypicammotion test --camera 0 --output-dir /tmp/cam-shutdown`
2. Trigger motion so recording starts
3. Press Ctrl+C while still recording

- [ ] Prints `stopping…` then `done`
- [ ] No tracebacks
- [ ] If a clip was being recorded, it is saved and valid

### 5.6 Verbose mode — motion score logging

```bash
pypicammotion -v test --camera 0 --sensitivity 0.01 --output-dir /tmp/cam-scores
```

1. Wave hand or move in front of camera, then stop and wait for clip to save

- [ ] `motion started (score=N.NNN)` at INFO level — score is above sensitivity threshold
- [ ] `motion ended (score=N.NNN), entering tail` at DEBUG level
- [ ] `motion resumed (score=N.NNN)` at DEBUG level (if motion resumes during tail)
- [ ] `clip saved: ... (peak=N.NNN)` — peak is the highest score seen during the clip
- [ ] Peak score >= the initial motion started score

### 5.7 High sensitivity — constant recording

```bash
pypicammotion test --camera 0 --sensitivity 0.001 --output-dir /tmp/cam-sensitive
```

- [ ] Recording starts almost immediately (very low threshold)
- [ ] Ctrl+C stops cleanly

### 5.8 Low sensitivity — no false triggers

```bash
pypicammotion test --camera 0 --sensitivity 0.8 --output-dir /tmp/cam-insensitive
```

- [ ] No recording triggered by normal ambient changes
- [ ] Only triggers if >80% of the frame changes (e.g. covering/uncovering the lens)

### 5.9 Invalid camera device

```bash
pypicammotion test --camera 99 --output-dir /tmp/cam-bad 2>&1
```

- [ ] Logs a camera error (not a bare traceback crash)
- [ ] Process exits or can be Ctrl+C'd

---

## 6. audio.py — Audio Capture & Post-Mux

*Prerequisites: `sudo apt install libportaudio2` and `poetry install --extras audio`. A USB microphone must be connected.*

### 6.1 Graceful degradation without sounddevice

```bash
python3 -c "
from pypicammotion.audio import _HAS_SOUNDDEVICE, _HAS_AV, AudioCapture
print(f'sounddevice available: {_HAS_SOUNDDEVICE}')
print(f'PyAV available: {_HAS_AV}')

ac = AudioCapture()
ac.start()   # should log warning, not crash
print(f'is_available: {ac.is_available()}')
ac.enqueue_mux('/tmp/fake.mp4', 0.0, 5.0)  # no-op when unavailable
ac.stop()
print('no crash')
"
```

- [ ] If sounddevice not installed: `sounddevice available: False`, logs warning, `is_available: False`
- [ ] If sounddevice installed but PyAV missing: logs warning, `is_available: False`
- [ ] No crash in either case

### 6.2 List audio devices

```bash
python -m sounddevice
```

- [ ] Lists available audio devices with device indices
- [ ] USB mic appears (e.g. "USB PnP Sound Device")

### 6.3 Audio capture and extract

*Requires sounddevice installed and a working mic.*

```bash
python3 -c "
import time
from pypicammotion.audio import AudioCapture

ac = AudioCapture(device=None, sample_rate=48000, channels=1, buffer_seconds=10.0)
ac.start()
print(f'is_available: {ac.is_available()}')
time.sleep(3)

now = time.monotonic()
pcm = ac.extract(now - 2.0, 2.0)
if pcm is not None:
    print(f'extracted {len(pcm)} samples ({len(pcm)/48000:.2f}s)')
    print(f'shape: {pcm.shape}, dtype: {pcm.dtype}')
    print(f'peak amplitude: {abs(pcm).max():.4f}')
else:
    print('ERROR: no audio data extracted')
ac.stop()
"
```

- [ ] `is_available: True`
- [ ] Extracts ~96000 samples (2 seconds at 48 kHz)
- [ ] Shape is `(N, 1)`, dtype is `float32`
- [ ] Peak amplitude > 0 (if there's any ambient noise)

### 6.4 Extract with no data in range

```bash
python3 -c "
import time
from pypicammotion.audio import AudioCapture

ac = AudioCapture(sample_rate=48000, channels=1, buffer_seconds=5.0)
ac.start()
time.sleep(0.5)

# Request audio from far in the past (outside buffer)
pcm = ac.extract(0.0, 1.0)
print(f'extract from past: {pcm}')

ac.stop()
"
```

- [ ] Returns `None` — requested time range is outside the rolling buffer

### 6.5 Mux audio onto a video-only MP4

*Requires PyAV installed. Uses a real video-only MP4 clip.*

First, generate a test clip:
```bash
pypicammotion test --camera 0 --sensitivity 0.001 --output-dir /tmp/mux-test
# Ctrl+C after one clip is saved
```

Then mux audio onto it:
```bash
python3 -c "
import time, numpy as np
from pathlib import Path
from pypicammotion.audio import mux_audio_onto_mp4

# Find the test clip
clips = sorted(Path('/tmp/mux-test').rglob('*.mp4'))
if not clips:
    print('ERROR: no test clips found — run pypicammotion test first')
    exit(1)
clip = clips[0]
print(f'clip: {clip}')

# Generate 5 seconds of 440 Hz sine wave as test audio
sr = 48000
duration = 5.0
t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
pcm = (0.5 * np.sin(2 * np.pi * 440 * t)).reshape(-1, 1)

size_before = clip.stat().st_size
mux_audio_onto_mp4(clip, pcm, sr, 1)
size_after = clip.stat().st_size
print(f'size before: {size_before}, after: {size_after}')
print(f'audio added: {size_after > size_before}')
"
```

Verify the result:
```bash
ffprobe /tmp/mux-test/test/*/*.mp4 2>&1 | grep -E "Stream|Duration"
```

- [ ] `mux_audio_onto_mp4` completes without error
- [ ] File size increased (audio data added)
- [ ] `ffprobe` shows both a video stream (H.264) and an audio stream (AAC)
- [ ] Playing the clip produces a 440 Hz tone

### 6.6 Mux failure leaves original intact

```bash
python3 -c "
import numpy as np
from pathlib import Path
from pypicammotion.audio import mux_audio_onto_mp4

# Create a fake (invalid) MP4 file
fake = Path('/tmp/fake-mux-test.mp4')
fake.write_bytes(b'not a real mp4 file')
original_content = fake.read_bytes()

pcm = np.zeros((48000, 1), dtype=np.float32)
try:
    mux_audio_onto_mp4(fake, pcm, 48000, 1)
    print('ERROR: should have raised an exception')
except Exception as e:
    print(f'correctly failed: {type(e).__name__}')

# Original should be untouched
print(f'original intact: {fake.read_bytes() == original_content}')

import glob
temps = glob.glob('/tmp/fake-mux-test*.mp4')
# Only the original should remain
print(f'temp files cleaned up: {len(temps) == 1}')
fake.unlink()
"
```

- [ ] Raises an exception (can't open invalid MP4)
- [ ] Original file is untouched
- [ ] No temp files left behind

### 6.7 Enqueue mux (integration with worker thread)

```bash
python3 -c "
import time, numpy as np
from pathlib import Path
from pypicammotion.audio import AudioCapture

ac = AudioCapture(sample_rate=48000, channels=1, buffer_seconds=10.0)
ac.start()
if not ac.is_available():
    print('audio not available — skipping')
    exit(0)

time.sleep(2)

# Create a test clip first
clips = sorted(Path('/tmp/mux-test').rglob('*.mp4'))
if not clips:
    print('no test clips — run pypicammotion test first')
    ac.stop()
    exit(1)

import shutil
test_clip = Path('/tmp/mux-worker-test.mp4')
shutil.copy2(clips[0], test_clip)

mono_now = time.monotonic()
ac.enqueue_mux(test_clip, mono_now - 1.5, 1.5)
time.sleep(3)  # wait for worker to process
ac.stop()

# Verify audio was muxed
import subprocess
result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', str(test_clip)],
                       capture_output=True, text=True)
has_audio = 'codec_type=audio' in result.stdout
print(f'audio stream present: {has_audio}')
test_clip.unlink()
"
```

- [ ] Worker thread picks up the job and muxes audio
- [ ] `ffprobe` confirms audio stream is present in the output file

---

## 7. service.py — Multi-Camera Orchestrator

### 7.1 Run with example config (single camera)

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

### 7.2 SIGTERM clean shutdown

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

### 7.3 Two cameras

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

### 7.4 One bad device — other camera survives

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

### 7.5 Storage quota enforced during service run

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

### 7.6 Audio muxing via service

*Prerequisites: `sudo apt install libportaudio2`, `poetry install --extras audio`, USB mic connected.*

```bash
cat > /tmp/svc-audio.yaml << 'EOF'
storage:
  path: /tmp/svc-audio-clips
  max_gb: 0.5
audio:
  enabled: true
  sample_rate: 48000
  channels: 1
  buffer_seconds: 15.0
cameras:
  front:
    device: 0
    sensitivity: 0.05
EOF
pypicammotion -v run --config /tmp/svc-audio.yaml
```

1. Verify audio starts: log shows `audio capture started`
2. Trigger motion, wait for clip to save
3. Watch for `muxed audio onto ...` log message
4. Ctrl+C to stop

```bash
ffprobe /tmp/svc-audio-clips/front/*/*.mp4 2>&1 | grep -E "Stream|Duration"
```

- [ ] Log shows `audio capture started (device=..., 48000Hz, 1ch)`
- [ ] After each clip save, log shows `muxed audio onto <path>`
- [ ] `ffprobe` shows both H.264 video and AAC audio streams
- [ ] Playing the clip has audible audio from the mic

### 7.7 Per-camera audio toggle

*Requires two cameras connected (devices 0 and 1).*

```bash
cat > /tmp/svc-audio-toggle.yaml << 'EOF'
storage:
  path: /tmp/svc-audio-toggle-clips
  max_gb: 0.5
audio:
  enabled: true
  sample_rate: 48000
  channels: 1
cameras:
  with_audio:
    device: 0
    sensitivity: 0.05
    audio: true
  without_audio:
    device: 1
    sensitivity: 0.05
    audio: false
EOF
pypicammotion -v run --config /tmp/svc-audio-toggle.yaml
```

- [ ] Clips from `with_audio` camera have audio muxed (log shows `muxed audio onto`)
- [ ] Clips from `without_audio` camera do NOT have audio muxed (no mux log for those clips)

### 7.8 Audio disabled — no impact on video

```bash
cat > /tmp/svc-noaudio.yaml << 'EOF'
storage:
  path: /tmp/svc-noaudio-clips
  max_gb: 0.5
audio:
  enabled: false
cameras:
  front:
    device: 0
    sensitivity: 0.05
EOF
pypicammotion run --config /tmp/svc-noaudio.yaml
```

- [ ] No audio-related log messages
- [ ] Video clips are saved normally (video-only)
- [ ] Service behaves identically to before audio feature was added

---

## 8. cli.py — CLI Entry Points

### 8.1 Help output

```bash
pypicammotion --help
pypicammotion test --help
pypicammotion run --help
```

- [ ] Main help shows all three subcommands
- [ ] `test --help` shows `--camera`, `--sensitivity`, `--output-dir`
- [ ] `run --help` shows `--config`

### 8.2 list-cameras

```bash
pypicammotion list-cameras
```

- [ ] Lists all connected cameras with `[N] model  id=...`
- [ ] Camera numbers match what `libcamera-hello --list-cameras` reports

### 8.3 Verbose mode

```bash
pypicammotion -v list-cameras 2>&1 | head -5
```

- [ ] More detailed log output (DEBUG level) appears on stderr

### 8.4 No subcommand — prints help

```bash
pypicammotion
echo "exit code: $?"
```

- [ ] Prints usage/help text
- [ ] Exit code is 1

### 8.5 run without --config

```bash
pypicammotion run 2>&1
echo "exit code: $?"
```

- [ ] Prints error about required `--config` argument
- [ ] Exit code is 2 (argparse error)

---

## 9. systemd Integration

*Requires root access.*

### 9.1 Install and start service

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

### 9.2 Logs visible in journalctl

```bash
journalctl -u pypicammotion -f --no-pager
```

- [ ] Startup messages visible (camera started, service running)
- [ ] Motion events and clip saves appear in logs

### 9.3 Clean stop

```bash
sudo systemctl stop pypicammotion
systemctl status pypicammotion
```

- [ ] Service stops within 15 seconds (TimeoutStopSec)
- [ ] Logs show `received SIGTERM`, `stopping cameras`, `shutdown complete`
- [ ] Status shows `inactive (dead)`, not `failed`

### 9.4 Restart on failure

```bash
# Simulate a crash (if needed) or verify the Restart=on-failure setting:
cat /etc/systemd/system/pypicammotion.service | grep Restart
```

- [ ] `Restart=on-failure` and `RestartSec=5` are set

### 9.5 Enable on boot

```bash
sudo systemctl enable pypicammotion
sudo systemctl is-enabled pypicammotion
```

- [ ] Shows `enabled`
- [ ] After reboot, `systemctl status pypicammotion` shows `active (running)`

---

## 10. End-to-End Integration

### 10.1 Full pipeline: config → service → clips → quota

1. Create config with two cameras, small quota (50 MB), MQTT disabled
2. `pypicammotion run --config config.yaml`
3. Trigger motion on both cameras repeatedly over several minutes
4. Ctrl+C to stop

- [ ] Clips organized by `{storage_path}/{camera_name}/{YYYY-MM-DD}/{HH-MM-SS}.mp4`
- [ ] All clips are valid, playable MP4 files
- [ ] Each clip contains pre-motion buffer (starts before the motion event)
- [ ] Post-motion tail is present (recording continues briefly after motion stops)
- [ ] Continuous motion produces a single long clip, not multiple short ones
- [ ] Video duration in file roughly matches duration logged by the service
- [ ] Old clips evicted when quota exceeded
- [ ] No error tracebacks in output

### 10.2 Full pipeline with MQTT

*Prerequisites: mosquitto running (`sudo apt install mosquitto mosquitto-clients`)*

Terminal 1 — subscribe:
```bash
mosquitto_sub -t "pypicammotion/#" -v
```

Terminal 2 — run service with MQTT enabled:
```bash
cat > /tmp/svc-mqtt.yaml << 'EOF'
storage:
  path: /tmp/svc-mqtt-clips
  max_gb: 0.5
mqtt:
  enabled: true
  broker: localhost
  port: 1883
  topic_prefix: pypicammotion
cameras:
  front:
    device: 0
    sensitivity: 0.05
EOF
pypicammotion run --config /tmp/svc-mqtt.yaml
```

Trigger motion, then verify:

- [ ] MQTT messages appear in Terminal 1 for each saved clip
- [ ] JSON payload contains `camera`, `path`, `timestamp`, `duration`
- [ ] Kill mosquitto (`sudo systemctl stop mosquitto`) → service continues saving clips without crashing
- [ ] Restart mosquitto (`sudo systemctl start mosquitto`) → MQTT messages resume on next clip

### 10.3 Full pipeline with audio

*Prerequisites: `sudo apt install libportaudio2`, `poetry install --extras audio`, USB mic connected.*

```bash
cat > /tmp/svc-full-audio.yaml << 'EOF'
storage:
  path: /tmp/svc-full-audio-clips
  max_gb: 0.5
audio:
  enabled: true
  sample_rate: 48000
  channels: 1
  buffer_seconds: 15.0
cameras:
  front:
    device: 0
    sensitivity: 0.05
    pre_motion_seconds: 5.0
    post_motion_seconds: 3.0
EOF
pypicammotion -v run --config /tmp/svc-full-audio.yaml
```

1. Wait for `audio capture started` and `service running` messages
2. Trigger motion (speak or clap while moving in front of camera)
3. Wait for clip to save and audio to mux
4. Ctrl+C to stop

Verify clips:
```bash
for f in /tmp/svc-full-audio-clips/front/*/*.mp4; do
    echo "=== $f ==="
    ffprobe -v error -show_entries stream=codec_type,codec_name,duration "$f" 2>&1
done
```

- [ ] Each clip has both a video stream (h264) and an audio stream (aac)
- [ ] Audio duration roughly matches video duration
- [ ] Audio covers the pre-motion period (sound from before motion started is audible)
- [ ] Playing clips back, audio and video are in sync
- [ ] Logs show `muxed audio onto` for each clip
- [ ] No audio-related error tracebacks
- [ ] Ctrl+C shuts down cleanly: `audio capture stopped` appears in logs
- [ ] Unplugging the USB mic mid-run does not crash the service (clips continue without audio)

---

## 11. Clip Metadata Embedding

### 11.1 Metadata present on video-only clips

```bash
pypicammotion test --camera 0 --sensitivity 0.01 --output-dir /tmp/meta-test
# Trigger motion, Ctrl+C after a clip is saved
ffprobe -v quiet -show_entries format_tags /tmp/meta-test/test/*/*.mp4
```

- [ ] `TAG:title=test motion clip`
- [ ] `TAG:date` is an ISO 8601 timestamp matching the clip filename
- [ ] `TAG:comment` is valid JSON containing `camera`, `peak_score`, and `sensitivity`
- [ ] `peak_score` is a positive number above the sensitivity threshold
- [ ] `sensitivity` matches the `--sensitivity` value (0.01)

### 11.2 Metadata survives audio post-mux

*Prerequisites: audio enabled, USB mic connected.*

```bash
cat > /tmp/meta-audio.yaml << 'EOF'
storage:
  path: /tmp/meta-audio-clips
  max_gb: 0.5
audio:
  enabled: true
  sample_rate: 48000
  channels: 1
cameras:
  front:
    device: 0
    sensitivity: 0.05
EOF
pypicammotion -v run --config /tmp/meta-audio.yaml
# Trigger motion, wait for "muxed audio onto" log, Ctrl+C
ffprobe -v quiet -show_entries format_tags /tmp/meta-audio-clips/front/*/*.mp4
```

- [ ] Clip has both video and audio streams (audio mux completed)
- [ ] `TAG:title=front motion clip`
- [ ] `TAG:date` and `TAG:comment` are present and correct
- [ ] JSON in `comment` contains `"camera": "front"`

### 11.3 Metadata failure does not prevent clip saving

```bash
# Verify by checking logs — if metadata write fails, a warning is logged
# but the clip and callback proceed normally
pypicammotion -v test --camera 0 --sensitivity 0.01 --output-dir /tmp/meta-fail-test
```

- [ ] Clips are saved even if metadata write were to fail (warning logged, clip intact)
