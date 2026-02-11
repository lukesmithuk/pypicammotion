# TODO

## Known Issues

- [ ] `Camera was not started` debug message during teardown — harmless but
  noisy. Comes from picamera2 when `stop()` is called on an already-stopped
  camera during cleanup. Could be fixed with a state check before calling
  `picam.stop()`.

## Not Yet Tested

- [x] systemd integration (start, stop, enable, journalctl logs)
- [x] Reboot auto-start via `systemctl enable` (symlink created, not rebooted)
- [x] Storage quota eviction during live service run
- [x] Behaviour with paho-mqtt uninstalled (graceful degradation path)
- [x] MQTT broker disconnect/reconnect during live service
- [x] Full service run with USB storage (`require_mount: true`, clips saving
  to `/mnt/usb`)

## Future Improvements

- [ ] **Configurable compare_frames** — currently hardcoded to `fps // 2`
  (~0.5s). Could be exposed as a config option for users who want to tune
  the motion detection window (e.g. longer for very slow motion).

- [x] **Motion event logging with scores** — log the motion score at state
  transitions (INFO on start/save, DEBUG on tail enter/resume) and track
  peak score per clip. Visible with `-v` for sensitivity tuning.

- [ ] **Health check endpoint** — expose a simple HTTP or MQTT heartbeat so
  monitoring systems can verify the service is alive and cameras are running.

- [x] **Clip metadata** — embed motion score, camera name, and timestamps in
  the MP4 container metadata via PyAV (title, date, comment with JSON).

- [ ] **Web UI / clip browser** — simple web interface to browse and preview
  saved clips, grouped by camera and date.

- [ ] **Unit tests** — the project has a manual test plan but no automated
  tests. Synthetic frame tests for `MotionDetector` and `StorageManager`
  could be automated easily. Camera/service tests would need mocking.

- [ ] **Configurable resolution per-camera for lores stream** — already
  supported in config (`lores_resolution`) but not documented as a tuning
  knob. Lower resolution = faster detection but less spatial precision.

- [ ] **Notification on service start/stop** — MQTT message when the service
  starts or stops, not just on clip saves.

- [x] **Audio recording** — post-mux audio from USB mic onto saved clips
  via sounddevice + PyAV. Shared AudioCapture thread with rolling buffer,
  background mux worker, per-camera audio toggle, graceful degradation.

- [x] **USB storage support** — `storage.path` can point to any mounted
  filesystem including USB drives. Added `require_mount: true` config option
  that validates the storage path is on a non-root mount at startup, preventing
  silent writes to the SD card when a USB drive isn't mounted.

- [ ] **Rate limiting on motion events** — if a camera triggers constantly
  (e.g. a tree blowing in the wind), clips pile up quickly. Could add a
  minimum cooldown between recordings or a max-clips-per-hour limit.
