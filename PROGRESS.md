# Progress

## Current State

**Branch**: `implement-full-package` (pushed to origin)
**Status**: Core implementation complete with audio support. All modules
functional. Full manual test plan passed (all 10 sections). Three bugs
found during testing and fixed.

## What's Done

### Implementation (all in commit `cfadb71`)

| Module | Status | Description |
|---|---|---|
| `pyproject.toml` | Done | pyyaml dep, optional paho-mqtt, CLI entry point |
| `config.py` | Done | YAML loading, dataclasses, validation, tilde expansion |
| `motion.py` | Done | Ring buffer frame differencing on Y-plane |
| `camera.py` | Done | Picamera2 wrapper, IDLE/RECORDING/TAIL state machine |
| `storage.py` | Done | Disk scan, clip tracking, oldest-first eviction |
| `notifier.py` | Done | Optional MQTT via paho-mqtt, guarded import |
| `service.py` | Done | Multi-camera orchestrator, signal handling |
| `cli.py` | Done | list-cameras, test, run subcommands |
| `systemd/` | Done | Unit file written and tested |
| `audio.py` | Done | Audio capture, rolling buffer, post-mux worker |
| `config.example.yaml` | Done | Fully commented example config |
| `check-deps.sh` | Done | System dependency checker |
| `README.md` | Done | Quick start, config reference, systemd, architecture |

### Bug Fixes

| Commit | Issue | Fix |
|---|---|---|
| `0a8c7e8` | Storage path `~/...` created literal `~` directory | Apply `expanduser()` in config loading |
| `6a65817` | Recording stopped during continuous motion | Ring buffer comparing to frame from ~0.5s ago instead of previous frame |
| `7c12052` | Clips missing last ~5 seconds of video | Use `stop()`+`start()` instead of `close_output()` to flush circular buffer |
| `2bc98d6` | compare_frames was hardcoded to 15 | Derive from FPS: `max(1, fps // 2)` |

### Documentation

| File | Commit | Description |
|---|---|---|
| `PLAN.md` | `cfadb71`, updated `a4a7e13` | Full implementation plan with audio phase |
| `TEST_PLAN.md` | `c31cf9b`, updated `a4a7e13` | Manual test plan, 60+ test cases, all passing |
| `README.md` | `cfadb71`, updated `a4a7e13` | User-facing docs with audio and systemd |
| `CLAUDE.md` | `0f761a8`, updated `a4a7e13` | Claude Code onboarding guide |
| `DECISIONS.md` | `48a72f9`, updated `a4a7e13` | Architectural decisions with rationale |
| `TODO.md` | `48a72f9`, updated `a4a7e13` | Known issues, untested items, future work |
| `PROGRESS.md` | `48a72f9`, updated `a4a7e13` | Implementation and test status tracker |

## What's Been Tested

### Automated / Scripted

- [x] All module imports succeed
- [x] Config loading from example YAML
- [x] Config validation errors (sensitivity, blur_kernel, resolution, type)
- [x] MotionDetector with synthetic frames (no motion, motion, contour filtering, reset, BGR input)
- [x] MotionDetector continuous motion holds detection (ring buffer)
- [x] StorageManager scan, register, eviction, empty dir cleanup (synthetic)
- [x] MQTT notifier round-trip with mosquitto (pub/sub verified)
- [x] CLI help, list-cameras
- [x] Audio config parsing (device type coercion, per-camera toggle, defaults)
- [x] AudioCapture start/stop, extract from rolling buffer
- [x] mux_audio_onto_mp4 (codec-copy video + AAC audio, atomic replace)
- [x] Mux failure leaves original video-only MP4 intact
- [x] Mux worker thread processes enqueued jobs

### Live Camera Testing

- [x] `pypicammotion list-cameras` — both imx708 cameras detected
- [x] `pypicammotion test --camera 0` — motion detection, clip saving
- [x] `pypicammotion run --config ...` — dual camera, independent motion
- [x] MQTT notifications during live service (both cameras, 6 clips, all acknowledged)
- [x] SIGTERM clean shutdown — clips saved, MQTT disconnected, cameras closed
- [x] Clip files are valid playable MP4
- [x] Audio muxing via service — clips have H.264 video + AAC audio streams
- [x] Per-camera audio toggle — only `audio: true` cameras get muxed
- [x] Audio disabled — no impact on video pipeline
- [x] Full E2E with audio — pre-motion audio coverage, clean shutdown
- [x] Storage quota eviction during live service
- [x] systemd start/stop/enable — clean lifecycle, logs in journalctl
- [x] Service with paho-mqtt uninstalled — warning logged, clips saved, clean shutdown
- [x] MQTT broker disconnect/reconnect — service survives, messages resume after restart
- [x] USB storage with require_mount — clips saved to /mnt/usb, eviction works, root FS rejected

### Features

| Commit | Feature | Description |
|---|---|---|
| — | USB/external storage mount validation | `require_mount: true` config option checks storage path is on a non-root mount at startup |
| — | Audio recording (post-mux) | sounddevice capture + PyAV AAC mux onto clips, per-camera toggle, graceful degradation |

### Not Yet Tested

- [x] `require_mount` validation with USB drive at `/mnt/usb`
- [x] Storage quota eviction with real clips
- [x] systemd deployment (start, stop, enable, journalctl logs)
- [x] MQTT broker disconnect/reconnect (auto-reconnects, queued messages delivered)
- [x] Service with paho-mqtt uninstalled (warning logged, no crash)
- [x] Reboot auto-start (`systemctl enable` verified, symlink created)

## Commit History

```
a4a7e13 Add audio recording via post-mux onto saved clips
88ece19 Add storage mount validation for USB drives
7d458e7 Add USB storage support to TODO list
ae824d8 Add audio recording to TODO list
0f761a8 Add CLAUDE.md for Claude Code onboarding
48a72f9 Add project continuity docs: DECISIONS.md, TODO.md, PROGRESS.md
e54e3ba Update README with ring buffer and tilde expansion details
2b98ea8 Update PLAN.md and TEST_PLAN.md to reflect bug fixes
2bc98d6 Set motion compare_frames to 0.5s based on camera FPS
7c12052 Fix clips truncated by unflushed circular buffer
6a65817 Fix motion detection dropping during continuous movement
0a8c7e8 Fix storage path not expanding tilde (~) in config
c31cf9b Add manual test plan covering all modules
cfadb71 Implement motion-detection video recording package
7eba06a Initial commit
```
