# TODO

## Known Issues

- [ ] `Camera was not started` debug message during teardown — harmless but
  noisy. Comes from picamera2 when `stop()` is called on an already-stopped
  camera during cleanup. Could be fixed with a state check before calling
  `picam.stop()`.

## Not Yet Tested

- [ ] systemd integration (service unit file written but not deployed/tested)
- [ ] Reboot auto-start via `systemctl enable`
- [ ] Storage quota eviction during live service run (unit-tested with
  synthetic files, not verified with real clips under quota pressure)
- [ ] Behaviour with paho-mqtt uninstalled (graceful degradation path)
- [ ] MQTT broker disconnect/reconnect during live service

## Future Improvements

- [ ] **Configurable compare_frames** — currently hardcoded to `fps // 2`
  (~0.5s). Could be exposed as a config option for users who want to tune
  the motion detection window (e.g. longer for very slow motion).

- [ ] **Motion event logging with scores** — log the motion score periodically
  or on state transitions to help users tune sensitivity without trial and
  error.

- [ ] **Health check endpoint** — expose a simple HTTP or MQTT heartbeat so
  monitoring systems can verify the service is alive and cameras are running.

- [ ] **Clip metadata** — embed motion score, camera name, or timestamps in
  the MP4 metadata (e.g. via PyAV container metadata).

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

- [ ] **Audio recording** — capture audio alongside video in saved clips.
  Requires attaching a USB microphone or I2S mic, recording via ALSA/PulseAudio,
  and muxing the audio stream into the MP4 output alongside the H.264 video
  (e.g. via PyAV). Needs config options for audio device selection and
  enable/disable per camera.

- [ ] **Rate limiting on motion events** — if a camera triggers constantly
  (e.g. a tree blowing in the wind), clips pile up quickly. Could add a
  minimum cooldown between recordings or a max-clips-per-hour limit.
