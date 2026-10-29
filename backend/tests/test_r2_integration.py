from __future__ import annotations

import uuid

import httpx
import pytest

from app.config import get_settings
from app.services.storage import R2StorageService, StorageError, UploadedPart


pytestmark = pytest.mark.integration


def test_real_r2_multipart_round_trip_only_when_explicitly_enabled() -> None:
    settings = get_settings()
    if not settings.run_r2_integration_tests:
        pytest.skip("Set RUN_R2_INTEGRATION_TESTS=true to allow real R2 writes.")
    settings.require_r2()
    storage = R2StorageService(settings)
    object_key = f"integration-tests/{uuid.uuid4()}.bin"
    upload_id = storage.create_multipart_upload(
        object_key, "application/octet-stream", {"purpose": "howlix-integration-test"}
    )
    completed = False
    try:
        payload = b"howlix-r2-integration-test"
        url = storage.generate_upload_part_url(object_key, upload_id, 1, 300)
        response = httpx.put(url, content=payload, timeout=30)
        response.raise_for_status()
        etag = response.headers["etag"]
        parts = storage.list_uploaded_parts(object_key, upload_id)
        assert parts == [UploadedPart(1, etag, len(payload))]
        storage.complete_multipart_upload(object_key, upload_id, parts)
        completed = True
        assert storage.head_object(object_key).content_length == len(payload)
    finally:
        if completed:
            storage.delete_object(object_key)
        else:
            try:
                storage.abort_multipart_upload(object_key, upload_id)
            except StorageError:
                pass
