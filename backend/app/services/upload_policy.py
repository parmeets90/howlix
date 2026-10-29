from __future__ import annotations

import math
import re
import uuid
from pathlib import PurePosixPath


ALLOWED_VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}


class UploadPolicyError(ValueError):
    pass


def sanitize_filename(filename: str) -> tuple[str, str]:
    basename = filename.replace("\\", "/").split("/")[-1].strip()
    if not basename:
        raise UploadPolicyError("A filename is required.")
    extension = PurePosixPath(basename).suffix.lower()
    if extension not in ALLOWED_VIDEO_TYPES:
        raise UploadPolicyError("Only MP4, MOV, and WebM files are supported.")
    stem = basename[: -len(extension)]
    stem = re.sub(r"[^\w .()\-]", "_", stem, flags=re.UNICODE).strip(" .")
    stem = re.sub(r"\s+", " ", stem)[: 240 - len(extension)].strip()
    if not stem:
        stem = "video"
    return f"{stem}{extension}", extension


def validate_declared_video(
    filename: str,
    mime_type: str,
    file_size_bytes: int,
    max_upload_size_bytes: int,
) -> tuple[str, str]:
    sanitized, extension = sanitize_filename(filename)
    if mime_type.lower().strip() != ALLOWED_VIDEO_TYPES[extension]:
        raise UploadPolicyError(
            f"The declared MIME type does not match the {extension} file extension."
        )
    if file_size_bytes <= 0:
        raise UploadPolicyError("The selected file is empty.")
    if file_size_bytes > max_upload_size_bytes:
        raise UploadPolicyError("The selected file exceeds the configured upload limit.")
    return sanitized, extension


def make_object_key(project_id: uuid.UUID, asset_id: uuid.UUID, extension: str) -> str:
    return f"projects/{project_id}/originals/{asset_id}{extension}"


def calculate_total_parts(file_size_bytes: int, part_size_bytes: int) -> int:
    return math.ceil(file_size_bytes / part_size_bytes)


def expected_part_size(
    part_number: int, total_parts: int, part_size_bytes: int, file_size_bytes: int
) -> int:
    if part_number < total_parts:
        return part_size_bytes
    return file_size_bytes - (total_parts - 1) * part_size_bytes


def normalize_etag(etag: str) -> str:
    return etag.strip().strip('"')
