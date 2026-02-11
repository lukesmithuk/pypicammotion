from __future__ import annotations

import logging
import os
import queue
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

try:
    import sounddevice as sd

    _HAS_SOUNDDEVICE = True
except ImportError:
    _HAS_SOUNDDEVICE = False

try:
    import av

    _HAS_AV = True
except ImportError:
    _HAS_AV = False


class AudioCapture:
    """Capture audio from a microphone into a rolling buffer.

    After a video clip is saved, :meth:`enqueue_mux` queues a background job
    that extracts matching audio from the buffer and muxes it onto the MP4.

    Degrades gracefully: if sounddevice is not installed or the mic fails,
    video clips are saved without audio.
    """

    def __init__(
        self,
        device: str | int | None = None,
        sample_rate: int = 48000,
        channels: int = 1,
        buffer_seconds: float = 15.0,
        blocksize: int = 0,
    ) -> None:
        self._device = device
        self._sample_rate = sample_rate
        self._channels = channels
        self._buffer_seconds = buffer_seconds
        self._blocksize = blocksize

        # Rolling buffer of (monotonic_timestamp, pcm_chunk) tuples
        max_chunks = int(buffer_seconds * sample_rate / max(blocksize, 1024)) + 100
        self._buffer: deque[tuple[float, np.ndarray]] = deque(maxlen=max_chunks)
        self._lock = threading.Lock()

        self._stream: sd.InputStream | None = None
        self._running = False

        self._mux_queue: queue.Queue[tuple[Path, float, float] | None] = queue.Queue()
        self._mux_thread: threading.Thread | None = None

    def start(self) -> None:
        if not _HAS_SOUNDDEVICE:
            log.warning("sounddevice not installed — audio capture disabled")
            return
        if not _HAS_AV:
            log.warning("PyAV not installed — audio muxing disabled")
            return

        try:
            self._stream = sd.InputStream(
                device=self._device,
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="float32",
                blocksize=self._blocksize,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._running = True
            log.info(
                "audio capture started (device=%s, %dHz, %dch)",
                self._device,
                self._sample_rate,
                self._channels,
            )
        except Exception:
            log.exception("failed to start audio capture — continuing without audio")
            self._running = False
            return

        self._mux_thread = threading.Thread(
            target=self._mux_worker, name="audio-mux", daemon=True
        )
        self._mux_thread.start()

    def stop(self) -> None:
        self._running = False

        # Signal mux worker to drain and exit
        self._mux_queue.put(None)
        if self._mux_thread and self._mux_thread.is_alive():
            self._mux_thread.join(timeout=30)

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.exception("error stopping audio stream")
            self._stream = None

        log.info("audio capture stopped")

    def is_available(self) -> bool:
        return self._running and self._stream is not None

    def extract(self, start_mono: float, duration: float) -> np.ndarray | None:
        """Extract a PCM segment from the rolling buffer.

        Returns a float32 ndarray of shape (samples, channels) or None if
        insufficient data is available.
        """
        end_mono = start_mono + duration

        with self._lock:
            chunks = list(self._buffer)

        if not chunks:
            return None

        # Find chunks that overlap [start_mono, end_mono]
        selected: list[np.ndarray] = []
        for ts, pcm in chunks:
            chunk_duration = len(pcm) / self._sample_rate
            chunk_end = ts + chunk_duration
            if chunk_end > start_mono and ts < end_mono:
                # Trim leading samples if chunk starts before our window
                if ts < start_mono:
                    skip = int((start_mono - ts) * self._sample_rate)
                    pcm = pcm[skip:]
                # Trim trailing samples if chunk extends past our window
                if chunk_end > end_mono:
                    keep = int((end_mono - ts) * self._sample_rate)
                    if ts < start_mono:
                        keep -= int((start_mono - ts) * self._sample_rate)
                    pcm = pcm[:keep]
                selected.append(pcm)

        if not selected:
            return None

        return np.concatenate(selected, axis=0)

    def enqueue_mux(self, video_path: Path, start_mono: float, duration: float) -> None:
        """Queue a post-mux job (non-blocking)."""
        if not self.is_available():
            return
        self._mux_queue.put((video_path, start_mono, duration))

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log.debug("audio callback status: %s", status)
        with self._lock:
            self._buffer.append((time.monotonic(), indata.copy()))

    def _mux_worker(self) -> None:
        """Background thread that processes mux jobs."""
        while True:
            job = self._mux_queue.get()
            if job is None:
                break

            video_path, start_mono, duration = job
            try:
                pcm = self.extract(start_mono, duration)
                if pcm is None or len(pcm) == 0:
                    log.warning("no audio data for %s — skipping mux", video_path)
                    continue
                mux_audio_onto_mp4(
                    video_path, pcm, self._sample_rate, self._channels
                )
                log.info("muxed audio onto %s", video_path)
            except Exception:
                log.exception("audio mux failed for %s — video-only clip kept", video_path)


def mux_audio_onto_mp4(
    video_path: Path,
    pcm: np.ndarray,
    sample_rate: int,
    channels: int,
) -> None:
    """Remux a video-only MP4, adding AAC audio from PCM data.

    The original video stream is codec-copied (no re-encode). On failure the
    temp file is removed and the original MP4 is left intact.
    """
    video_path = Path(video_path)
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4", dir=video_path.parent)
    os.close(fd)

    try:
        input_container = av.open(str(video_path))
        output_container = av.open(tmp_path, mode="w")

        # Copy video stream
        in_video = input_container.streams.video[0]
        out_video = output_container.add_stream_from_template(in_video)

        # Add AAC audio stream
        out_audio = output_container.add_stream("aac", rate=sample_rate)
        out_audio.layout = "mono" if channels == 1 else "stereo"

        # Write video packets (codec copy)
        for packet in input_container.demux(in_video):
            if packet.dts is None:
                continue
            packet.stream = out_video
            output_container.mux(packet)

        # Encode PCM as AAC
        # Convert float32 [-1, 1] to signed 16-bit PCM for the encoder
        pcm_s16 = (pcm * 32767).clip(-32768, 32767).astype(np.int16)
        if pcm_s16.ndim == 1:
            pcm_s16 = pcm_s16.reshape(-1, 1)

        frame_size = out_audio.codec_context.frame_size or 1024
        offset = 0
        pts = 0
        while offset < len(pcm_s16):
            chunk = pcm_s16[offset : offset + frame_size]
            frame = av.AudioFrame.from_ndarray(
                chunk.T, format="s16", layout="mono" if channels == 1 else "stereo"
            )
            frame.sample_rate = sample_rate
            frame.pts = pts
            for packet in out_audio.encode(frame):
                output_container.mux(packet)
            pts += len(chunk)
            offset += frame_size

        # Flush encoder
        for packet in out_audio.encode(None):
            output_container.mux(packet)

        output_container.close()
        input_container.close()

        os.replace(tmp_path, str(video_path))
    except BaseException:
        # Clean up temp file, leave original intact
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
