from __future__ import annotations

import uuid
from pathlib import Path

import httpx
from pydantic import SecretStr

from app.config import get_settings
from app.auth import AuthenticatedUser, require_user
from app.main import app
from app.models import (
    JobDispatchStatus,
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
)
from app.services.github_dispatch import DispatchResult, dispatch_job
from app.worker import MediaValidationWorker, claim_job_by_id
from tests.conftest import SECOND_USER_ID, TEST_USER_ID, MockStorageService
from tests.test_worker import valid_probe


class DispatchClient:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.calls = 0

    def post(self, url, *, headers, json):  # noqa: ANN001
        assert url.endswith("/actions/workflows/howlix-worker.yml/dispatches")
        assert headers["Authorization"].startswith("Bearer ")
        uuid.UUID(json["inputs"]["job_id"])
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return httpx.Response(
            status,
            request=httpx.Request("POST", url),
            text="sensitive-upstream-response-must-not-be-persisted",
        )


def _queued_job(session_factory, storage: MockStorageService) -> uuid.UUID:
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    key = f"projects/{project_id}/media/{asset_id}.mp4"
    storage.download_payloads[key] = b"video"
    with session_factory() as db:
        db.add(Project(id=project_id, owner_id=TEST_USER_ID, title="Dispatch"))
        db.add(
            MediaAsset(
                id=asset_id,
                owner_id=TEST_USER_ID,
                project_id=project_id,
                original_filename="source.mp4",
                object_key=key,
                bucket_name=storage.bucket_name,
                mime_type="video/mp4",
                file_size_bytes=5,
                status=MediaAssetStatus.UPLOADED,
            )
        )
        job = ProcessingJob(
            owner_id=TEST_USER_ID,
            asset_id=asset_id,
            job_type=ProcessingJobType.VALIDATE_MEDIA,
            status=ProcessingJobStatus.QUEUED,
            progress_stage="queued",
        )
        db.add(job)
        db.commit()
        return job.id


def _settings():
    return get_settings().model_copy(
        update={
            "github_actions_dispatch_enabled": True,
            "github_actions_token": SecretStr("placeholder-test-token"),
            "github_dispatch_max_attempts": 2,
        }
    )


def test_dispatch_is_idempotent(testing_session_factory, mock_storage) -> None:
    job_id = _queued_job(testing_session_factory, mock_storage)
    client = DispatchClient([204])
    with testing_session_factory() as db:
        assert dispatch_job(db, job_id, _settings(), client=client) == DispatchResult.DISPATCHED
        assert (
            dispatch_job(db, job_id, _settings(), client=client)
            == DispatchResult.ALREADY_DISPATCHED
        )
        job = db.get(ProcessingJob, job_id)
        assert job.dispatch_status == JobDispatchStatus.DISPATCHED
        assert job.progress_stage == "starting_runner"
    assert client.calls == 1


def test_dispatch_failure_is_persisted_without_response_body(
    testing_session_factory, mock_storage
) -> None:
    job_id = _queued_job(testing_session_factory, mock_storage)
    client = DispatchClient([503, 503])
    with testing_session_factory() as db:
        result = dispatch_job(db, job_id, _settings(), client=client, sleep=lambda _n: None)
        job = db.get(ProcessingJob, job_id)
        assert result == DispatchResult.FAILED
        assert job.dispatch_status == JobDispatchStatus.FAILED
        assert job.progress_stage == "dispatch_failed"
        assert job.dispatch_error_message == "GitHub workflow dispatch returned HTTP 503."
        assert "sensitive-upstream" not in job.dispatch_error_message


def test_specific_claim_rejects_duplicate_and_one_shot_completes(
    testing_session_factory, mock_storage, tmp_path
) -> None:
    job_id = _queued_job(testing_session_factory, mock_storage)
    settings = get_settings().model_copy(update={"processing_temp_dir": tmp_path})
    with testing_session_factory() as db:
        assert claim_job_by_id(db, job_id, "gha-first", settings) == job_id
    with testing_session_factory() as db:
        assert claim_job_by_id(db, job_id, "gha-duplicate", settings) is None

    worker = MediaValidationWorker(
        settings,
        mock_storage,
        testing_session_factory,
        probe=valid_probe,
        worker_id="gha-first",
    )
    worker._process_claimed_job(job_id)
    with testing_session_factory() as db:
        assert db.get(ProcessingJob, job_id).status == ProcessingJobStatus.SUCCEEDED


def test_invalid_job_id_is_ineligible(testing_session_factory) -> None:
    with testing_session_factory() as db:
        assert (
            dispatch_job(db, uuid.uuid4(), _settings(), client=DispatchClient([204]))
            == DispatchResult.INELIGIBLE
        )


def test_dispatch_recovery_endpoint_is_owner_scoped(client, testing_session_factory, mock_storage):
    job_id = _queued_job(testing_session_factory, mock_storage)
    app.dependency_overrides[require_user] = lambda: AuthenticatedUser(
        SECOND_USER_ID, "user-b@example.test", "authenticated"
    )
    try:
        assert client.post(f"/api/v1/jobs/{job_id}/dispatch").status_code == 404
    finally:
        app.dependency_overrides[require_user] = lambda: AuthenticatedUser(
            TEST_USER_ID, "user-a@example.test", "authenticated"
        )


def test_workflow_uses_trusted_main_and_scopes_secrets_to_worker_step() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/howlix-worker.yml").read_text(encoding="utf-8")
    assert "pull_request" not in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "ref: main" in workflow
    assert "persist-credentials: false" in workflow
    process_step = workflow.index("- name: Process exactly one persisted job")
    assert workflow.index("${{ secrets.") > process_step
    assert "generate_get_url" not in workflow
