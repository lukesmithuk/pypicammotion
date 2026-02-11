# Architectural & Implementation Decisions

Decisions made during development, with rationale. Useful context for
future changes.

---

## Encoder: LibavH264Encoder (software)

The Raspberry Pi 5 has no V4L2 H.264 hardware encoder. Earlier Pis had one,
but on Pi 5 the only option is software encoding via libx264 through
`LibavH264Encoder`. This works fine at 1080p30 but uses more CPU than
hardware encoding would.

## Motion detection stream: lores at 640x480 YUV420

Picamera2 supports a secondary `lores` stream that runs in parallel with the
main recording stream. We use 640x480 YUV420 — the Y-plane is already
grayscale, so no `cvtColor` conversion is needed. At 1/9th the pixels of
1080p, motion detection takes <5ms per frame.

## Motion detection: ring buffer, not frame-to-frame

**Problem**: Comparing consecutive frames at 30fps produces tiny diffs during
smooth, continuous motion (a person walking shifts only a few pixels per
frame). Recording would stop mid-motion.

**Solution**: Keep a ring buffer of `compare_frames` blurred grayscale frames
(default: `fps // 2`, i.e. ~0.5 seconds) and compare the current frame to
the oldest one in the buffer. A person's position 0.5 seconds ago differs
substantially from their current position, so the diff stays large throughout
the motion.

**Trade-off**: After a permanent scene change (e.g. an object placed in
frame), detection stays active until the buffer rotates through (~0.5s), then
settles. This is acceptable — it just adds a brief extension to the recording
tail.

**Alternative considered**: Freezing the background frame during motion and
only updating when still. Rejected because permanent scene changes would
cause the detector to get stuck in a permanent motion state, never adapting.

## Frame access: pre_callback

The `pre_callback` runs in picamera2's event loop before encoders process
each frame. This avoids needing a separate capture thread and gives us access
to the lores frame with minimal latency.

## Recording: CircularOutput2 + PyavOutput

Picamera2's `CircularOutput2` maintains a ring buffer of encoded packets. When
motion is detected, `open_output(PyavOutput(...))` starts dumping the buffer
(pre-motion footage) plus live frames into an MP4 file.

## Clip finalization: stop() + start(), not close_output()

**Problem**: `CircularOutput2.close_output()` does not flush its internal
buffer before closing the output. Frames within the buffer window (up to
`buffer_duration_ms`, typically 5 seconds) are silently discarded. Clips were
missing their trailing seconds.

**Solution**: Call `stop()` (which flushes all remaining frames via
`_flush(None, output)` then closes the MP4) followed by `start()` to resume
buffering for the next clip. The encoder keeps running throughout — only a
few milliseconds of frames are dropped during the stop/start gap.

**Alternative considered**: Accessing CircularOutput2's private `_flush`
method directly. Rejected as fragile — private internals could change with
any picamera2 update.

## Threading: one thread per camera, Picamera2 created inside thread

Picamera2 setup is not thread-safe across instances. Each camera runs in its
own thread, with the `Picamera2` object created inside `_run()` rather than
in `__init__()`. Cameras start sequentially (1 second apart) to avoid
libcamera initialization races.

## Config: YAML via pyyaml, dataclasses

YAML is natural for nested per-camera config. Dataclasses provide defaults,
type safety, and clear structure without extra dependencies. Storage paths
are expanded via `Path.expanduser()` to support `~` in config files.

## MQTT: optional dependency, guarded import

`paho-mqtt` is an optional dependency (`poetry install -E mqtt`). The import
is wrapped in a `try/except ImportError`. If not installed, a warning is
logged and the service runs without notifications. The broker connection uses
paho-mqtt's built-in auto-reconnect mechanism.

## USB/external storage: mount validation, not auto-detection

**Problem**: If a user configures `storage.path` to point at a USB mount (e.g.
`/mnt/usb/clips`) and the drive isn't mounted, the service silently creates
directories on the root filesystem, wasting SD card space.

**Solution**: Optional `require_mount: true` config flag. When set,
`StorageManager` resolves the storage path, walks up to find its mount point
via `Path.is_mount()`, and raises `RuntimeError` if the mount point is `/`.
The error message names the path and suggests checking the drive mount.

**Alternative considered**: Auto-detecting USB block devices and auto-mounting.
Rejected as over-engineered — users already manage mounts via `fstab` or
`udisks2`. The existing `storage.path` config already supports any filesystem
path; mount validation just adds a safety check.

## Storage: in-memory sorted list, disk scan on startup

Clips are append-only and evicted FIFO (oldest first). A simple sorted list
of `(mtime, path)` tuples is sufficient — no database needed. On startup,
`StorageManager` walks the base path and indexes all existing `.mp4` files.
Empty parent directories are cleaned up after eviction.

## Audio: post-mux, not inline recording

**Problem**: The cameras record via picamera2's CircularOutput2 + PyavOutput
pipeline, which writes video-only MP4s. There's one USB microphone shared
across two cameras.

**Solution**: Post-mux approach. A single `AudioCapture` thread records
continuously from the mic into a rolling `deque` of timestamped PCM chunks
(using `sounddevice`). After each video clip is saved, a background mux
worker extracts matching audio from the buffer (aligned by
`time.monotonic()` timestamps) and remuxes it onto the MP4: the video stream
is codec-copied (no re-encode) and the audio is encoded as AAC via PyAV.
The original file is atomically replaced with `os.replace()`.

**Failure isolation**: Audio failures never affect video. If the mic isn't
available or muxing fails, the original video-only MP4 is left intact.

**Pre-motion audio**: The audio extraction starts at
`start_mono - pre_motion_seconds` so the audio covers the same pre-motion
buffer as the video.

**Per-camera toggle**: Global `audio.enabled` controls whether capture runs.
Each camera has an `audio: true/false` flag (default true) to opt out of
muxing.

**Alternative considered**: Recording audio inline by creating a custom
picamera2 output that interleaves audio and video packets. Rejected because
picamera2's encoder pipeline doesn't support audio streams, and modifying
CircularOutput2 would be fragile. Post-mux is simpler and keeps the video
pipeline completely untouched.

## Audio library: sounddevice (PortAudio)

`sounddevice` is a thin wrapper around PortAudio with a callback-based API
that integrates well with a rolling buffer design. It's an optional
dependency (`poetry install -E audio`) with a guarded import, following the
same pattern as paho-mqtt. Requires `libportaudio2` system package.
