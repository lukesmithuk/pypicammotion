from __future__ import annotations

from collections import deque

import cv2
import numpy as np


class MotionDetector:
    """Detect motion by frame-differencing on the Y-plane of YUV420 frames.

    Compares the current frame to one from *compare_frames* ago (default 15,
    i.e. ~0.5 s at 30 fps) so that continuous, steady motion keeps producing
    a large diff rather than vanishing between consecutive frames.
    """

    def __init__(
        self,
        resolution: tuple[int, int] = (640, 480),
        sensitivity: float = 0.05,
        min_contour_area: int = 500,
        blur_kernel: int = 21,
        compare_frames: int = 15,
    ) -> None:
        self._width, self._height = resolution
        self._sensitivity = sensitivity
        self._min_contour_area = min_contour_area
        self._blur_kernel = blur_kernel
        self._buffer: deque[np.ndarray] = deque(maxlen=compare_frames)

    def detect(self, frame: np.ndarray) -> tuple[bool, float]:
        """Analyse a YUV420 frame and return (motion_detected, motion_score).

        *frame* is the raw YUV420p array from picamera2's lores stream
        (shape ``(height * 3 // 2, width)`` for planar, or ``(height, width, 3)``
        if already converted).  We only use the Y-plane (first *height* rows).
        """
        # Extract Y-plane (luminance) — first height rows of YUV420 planar
        if frame.ndim == 2:
            gray = frame[: self._height, :]
        elif frame.shape[2] == 3:
            # Already BGR or similar — convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame[: self._height, :]

        gray = cv2.GaussianBlur(gray, (self._blur_kernel, self._blur_kernel), 0)

        if not self._buffer:
            self._buffer.append(gray)
            return False, 0.0

        # Compare to the oldest frame in the buffer (~0.5 s ago once full)
        ref = self._buffer[0]
        self._buffer.append(gray)

        diff = cv2.absdiff(ref, gray)

        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_area = sum(
            cv2.contourArea(c) for c in contours if cv2.contourArea(c) >= self._min_contour_area
        )
        total_pixels = self._height * self._width
        score = motion_area / total_pixels if total_pixels else 0.0

        return score >= self._sensitivity, score

    def reset(self) -> None:
        """Clear frame buffer so next call starts fresh."""
        self._buffer.clear()
