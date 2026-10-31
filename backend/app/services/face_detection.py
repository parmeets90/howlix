from __future__ import annotations

import logging
from pathlib import Path

from app.services.framing import FaceBox, FaceObservation, stable_face_focus


logger = logging.getLogger("howlix.face_detection")


def detect_face_focus(
    video_path: Path,
    *,
    start_ms: int,
    end_ms: int,
    sample_frequency_hz: float,
    max_samples: int,
) -> tuple[float, float] | None:
    """Return a stable normalized focus or None when OpenCV/faces are unavailable."""
    try:
        import cv2
    except ImportError:
        logger.info("OpenCV is not installed; face-aware framing is using center crop.")
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None
    classifier = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    interval_ms = max(500, round(1000 / sample_frequency_hz))
    positions = list(range(start_ms, end_ms, interval_ms))[:max_samples]
    observations: list[FaceObservation] = []
    try:
        for timestamp_ms in positions:
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)
            ok, frame = capture.read()
            if not ok:
                continue
            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = classifier.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=5, minSize=(36, 36)
            )
            faces = tuple(
                FaceBox(x / width, y / height, w / width, h / height)
                for x, y, w, h in detections
            )
            observations.append(FaceObservation(timestamp_ms, faces))
    except Exception:
        logger.warning("Face sampling failed; using center crop.")
        return None
    finally:
        capture.release()
    return stable_face_focus(observations)
