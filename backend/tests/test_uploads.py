from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import MediaAsset, ProcessingJob, ProcessingJobStatus, UploadSession
from app.services.storage import UploadedPart
from tests.conftest import MockStorageService


MIB = 1024 * 1024


def create_project(client: TestClient) -> str:
    response = client.post("/api/v1/projects", json={"title": "Upload test"})
    assert response.status_code == 201
    return response.json()["id"]


def initiate(
    client: TestClient,
    project_id: str,
    filename: str = "interview.mp4",
    mime_type: str = "video/mp4",
    size: int = 20 * MIB,
):
    return client.post(
        f"/api/v1/projects/{project_id}/uploads/initiate",
        json={
            "original_filename": filename,
            "mime_type": mime_type,
            "file_size_bytes": size,
        },
    )


def prepare_two_parts(mock_storage: MockStorageService, size: int = 20 * MIB) -> None:
    mock_storage.parts["upload-1"] = [
        UploadedPart(1, '"etag-1"', 16 * MIB),
        UploadedPart(2, '"etag-2"', size - 16 * MIB),
    ]


def completion_payload() -> dict[str, list[dict[str, object]]]:
    return {
        "parts": [
            {"part_number": 1, "etag": '"etag-1"'},
            {"part_number": 2, "etag": '"etag-2"'},
        ]
    }


def test_multipart_upload_initiation_persists_server_key(
    client: TestClient, testing_session_factory, mock_storage: MockStorageService
) -> None:
    project_id = create_project(client)
    response = initiate(client, project_id, filename="../../Founder Final.mp4")
    assert response.status_code == 201
    body = response.json()
    assert body["session"]["total_parts"] == 2
    assert body["session"]["part_size_bytes"] == 16 * MIB

    with testing_session_factory() as db:
        asset = db.scalar(select(MediaAsset))
        session = db.scalar(select(UploadSession))
        assert asset is not None and session is not None
        assert asset.original_filename == "Founder Final.mp4"
        assert asset.object_key == f"projects/{project_id}/originals/{asset.id}.mp4"
        assert "Founder" not in asset.object_key
        assert asset.bucket_name == mock_storage.bucket_name
        assert session.r2_upload_id == "upload-1"


def test_presigned_part_url_is_scoped_to_session(
    client: TestClient, mock_storage: MockStorageService
) -> None:
    project_id = create_project(client)
    session_id = initiate(client, project_id).json()["session"]["id"]
    response = client.post(
        f"/api/v1/uploads/{session_id}/parts/sign", json={"part_number": 1}
    )
    assert response.status_code == 200
    assert "uploadId=upload-1" in response.json()["upload_url"]
    assert "partNumber=1" in response.json()["upload_url"]
    assert client.post(
        f"/api/v1/uploads/{session_id}/parts/sign", json={"part_number": 3}
    ).status_code == 400


def test_valid_completion_creates_one_validation_job_and_is_idempotent(
    client: TestClient, testing_session_factory, mock_storage: MockStorageService
) -> None:
    project_id = create_project(client)
    session_id = initiate(client, project_id).json()["session"]["id"]
    prepare_two_parts(mock_storage)

    first = client.post(
        f"/api/v1/uploads/{session_id}/complete", json=completion_payload()
    )
    second = client.post(
        f"/api/v1/uploads/{session_id}/complete", json=completion_payload()
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["validation_job_id"] == second.json()["validation_job_id"]
    assert mock_storage.completed == ["upload-1"]
    with testing_session_factory() as db:
        jobs = list(db.scalars(select(ProcessingJob)))
        assert len(jobs) == 1
        assert jobs[0].status == ProcessingJobStatus.QUEUED


def test_upload_cancellation_is_repeatable(
    client: TestClient, mock_storage: MockStorageService
) -> None:
    project_id = create_project(client)
    session_id = initiate(client, project_id).json()["session"]["id"]
    first = client.post(f"/api/v1/uploads/{session_id}/abort")
    second = client.post(f"/api/v1/uploads/{session_id}/abort")
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "aborted"
    assert mock_storage.aborted == ["upload-1"]


def test_invalid_extension_is_rejected_before_r2(client: TestClient) -> None:
    project_id = create_project(client)
    response = initiate(client, project_id, filename="notes.exe", mime_type="video/mp4")
    assert response.status_code == 400


def test_oversized_upload_is_rejected_before_r2(client: TestClient) -> None:
    project_id = create_project(client)
    response = initiate(client, project_id, size=1024 * MIB + 1)
    assert response.status_code == 413


def test_r2_object_size_mismatch_fails_and_deletes_object(
    client: TestClient, mock_storage: MockStorageService
) -> None:
    project_id = create_project(client)
    session_id = initiate(client, project_id).json()["session"]["id"]
    prepare_two_parts(mock_storage)
    mock_storage.forced_head_size = 20 * MIB - 1
    response = client.post(
        f"/api/v1/uploads/{session_id}/complete", json=completion_payload()
    )
    assert response.status_code == 409
    assert len(mock_storage.deleted) == 1


def test_r2_api_failure_returns_sanitized_gateway_error(
    client: TestClient, mock_storage: MockStorageService
) -> None:
    project_id = create_project(client)
    mock_storage.fail_on.add("create")
    response = initiate(client, project_id)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "storage_error"
    assert "MockFailure" not in response.text


def test_unknown_project_cannot_initiate_upload(client: TestClient) -> None:
    response = initiate(client, str(uuid.uuid4()))
    assert response.status_code == 404
