# Progress

## Current State

**Branch**: `implement-full-package` (pushed to origin)
**Status**: Core implementation complete. All modules functional. Three bugs
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
| `systemd/` | Done | Unit file written (not yet deployed) |
| `config.example.yaml` | Done | Fully commented example config |
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
| `PLAN.md` | `cfadb71`, updated `2b98ea8` | Full implementation plan, kept in sync |
| `TEST_PLAN.md` | `c31cf9b`, updated `2b98ea8` | Manual test plan, 40+ test cases |
| `README.md` | `cfadb71`, updated `e54e3ba` | User-facing docs |

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

### Live Camera Testing

- [x] `pypicammotion list-cameras` — both imx708 cameras detected
- [x] `pypicammotion test --camera 0` — motion detection, clip saving
- [x] `pypicammotion run --config ...` — dual camera, independent motion
- [x] MQTT notifications during live service (both cameras, 6 clips, all acknowledged)
- [x] SIGTERM clean shutdown — clips saved, MQTT disconnected, cameras closed
- [x] Clip files are valid playable MP4

### Features

| Commit | Feature | Description |
|---|---|---|
| — | USB/external storage mount validation | `require_mount: true` config option checks storage path is on a non-root mount at startup |

### Not Yet Tested

- [x] `require_mount` validation with USB drive at `/mnt/usb`
- [ ] systemd deployment
- [ ] Storage quota eviction with real clips
- [ ] MQTT broker disconnect/reconnect
- [ ] Service with paho-mqtt uninstalled
- [ ] Reboot auto-start

## Commit History

```
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
