from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class CropRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class FaceBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2


@dataclass(frozen=True)
class FaceObservation:
    timestamp_ms: int
    faces: tuple[FaceBox, ...]


OUTPUT_DIMENSIONS = {
    ("9:16", "720p"): (720, 1280),
    ("1:1", "720p"): (720, 720),
    ("16:9", "720p"): (1280, 720),
    ("9:16", "1080p"): (1080, 1920),
    ("1:1", "1080p"): (1080, 1080),
    ("16:9", "1080p"): (1920, 1080),
}


def output_dimensions(aspect_ratio: str, quality: str) -> tuple[int, int]:
    try:
        return OUTPUT_DIMENSIONS[(aspect_ratio, quality)]
    except KeyError as exc:
        raise ValueError("Unsupported aspect ratio or export quality.") from exc


def validate_normalized_focus(x: float, y: float) -> tuple[float, float]:
    if not 0 <= x <= 1 or not 0 <= y <= 1:
        raise ValueError("Manual crop coordinates must be between 0 and 1.")
    return x, y


def calculate_crop(
    source_width: int,
    source_height: int,
    output_width: int,
    output_height: int,
    *,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
) -> CropRect:
    if min(source_width, source_height, output_width, output_height) <= 0:
        raise ValueError("Video dimensions must be positive.")
    focus_x, focus_y = validate_normalized_focus(focus_x, focus_y)
    target_ratio = output_width / output_height
    source_ratio = source_width / source_height
    if source_ratio > target_ratio:
        crop_height = source_height
        crop_width = max(2, int(source_height * target_ratio) // 2 * 2)
    else:
        crop_width = source_width
        crop_height = max(2, int(source_width / target_ratio) // 2 * 2)
    desired_x = round(focus_x * source_width - crop_width / 2)
    desired_y = round(focus_y * source_height - crop_height / 2)
    x = max(0, min(source_width - crop_width, desired_x))
    y = max(0, min(source_height - crop_height, desired_y))
    return CropRect(x // 2 * 2, y // 2 * 2, crop_width, crop_height)


def stable_face_focus(observations: list[FaceObservation]) -> tuple[float, float] | None:
    sample_centers: list[tuple[float, float]] = []
    for observation in sorted(observations, key=lambda item: item.timestamp_ms):
        faces = [face for face in observation.faces if face.width > 0 and face.height > 0]
        if not faces:
            continue
        if len(faces) == 1:
            sample_centers.append(faces[0].center)
            continue
        left = min(face.x for face in faces)
        right = max(face.x + face.width for face in faces)
        top = min(face.y for face in faces)
        bottom = max(face.y + face.height for face in faces)
        sample_centers.append(((left + right) / 2, (top + bottom) / 2))
    if not sample_centers:
        return None
    # A single stable composition avoids visible crop jitter on low-frequency samples.
    return (
        max(0.0, min(1.0, median(point[0] for point in sample_centers))),
        max(0.0, min(1.0, median(point[1] for point in sample_centers))),
    )
