from __future__ import annotations

import uuid
from pathlib import Path

from app.services.storage import ObjectHead, StorageError, StorageService


def export_object_key(project_id: uuid.UUID, export_id: uuid.UUID) -> str:
    return f"projects/{project_id}/exports/{export_id}.mp4"


def upload_export(
    storage: StorageService,
    *,
    object_key: str,
    source: Path,
    project_id: uuid.UUID,
    export_id: uuid.UUID,
) -> ObjectHead:
    storage.upload_object(
        object_key,
        source,
        "video/mp4",
        {"project-id": str(project_id), "export-id": str(export_id), "kind": "clip-export"},
    )
    head = storage.head_object(object_key)
    if head.content_length != source.stat().st_size:
        try:
            storage.delete_object(object_key)
        finally:
            raise StorageError("R2 export size verification failed.")
    return head
