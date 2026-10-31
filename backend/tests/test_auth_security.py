from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy import update

from app.auth import AuthenticatedUser, SupabaseJWTVerifier, get_auth_verifier, require_user
from app.config import Settings
from app.main import app
from app.models import (
    ClipExport,
    ClipExportStatus,
    ExportAspectRatio,
    CaptionPreset,
    FramingMode,
    MediaAsset,
    MediaAssetStatus,
    MomentAnalysisRun,
    MomentAnalysisStatus,
    MomentCandidate,
    MomentReviewStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
    Transcript,
    TranscriptStatus,
    UploadSession,
    UploadSessionStatus,
)
from app.services.legacy_ownership import claim_legacy_projects
from tests.conftest import SECOND_USER_ID, TEST_USER_ID


ISSUER = "https://example.supabase.co/auth/v1"


def _settings() -> Settings:
    return Settings(
        HOWLIX_DATABASE_URL="sqlite:///:memory:",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_AUDIENCE="authenticated",
        SUPABASE_JWT_ISSUER=ISSUER,
        SUPABASE_JWKS_URL="https://example.supabase.co/auth/v1/.well-known/jwks.json",
        SUPABASE_JWT_VERIFICATION_MODE="jwks",
    )


def _verifier():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = SupabaseJWTVerifier(_settings())
    verifier._jwks_client = SimpleNamespace(  # noqa: SLF001
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())
    )
    return verifier, private_key


def _token(private_key, **overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(TEST_USER_ID),
        "email": "user-a@example.test",
        "role": "authenticated",
        "iss": ISSUER,
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **overrides,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


def test_supabase_jwt_verifies_signature_issuer_audience_and_expiry() -> None:
    verifier, private_key = _verifier()
    assert verifier.verify(_token(private_key)).id == TEST_USER_ID
    with pytest.raises(HTTPException) as expired:
        verifier.verify(_token(private_key, exp=datetime.now(timezone.utc) - timedelta(seconds=1)))
    assert expired.value.status_code == 401
    with pytest.raises(HTTPException) as audience:
        verifier.verify(_token(private_key, aud="wrong"))
    assert audience.value.status_code == 401
    with pytest.raises(HTTPException) as invalid:
        verifier.verify("not-a-jwt")
    assert invalid.value.status_code == 401


def test_private_api_rejects_missing_token(client) -> None:
    app.dependency_overrides.pop(require_user)
    app.dependency_overrides[get_auth_verifier] = lambda: SimpleNamespace(
        verify=lambda _token: AuthenticatedUser(TEST_USER_ID, None, "authenticated")
    )
    response = client.get("/api/v1/projects")
    assert response.status_code == 401


def test_every_versioned_api_route_declares_authentication() -> None:
    def contains_auth(dependant) -> bool:
        return dependant.call is require_user or any(
            contains_auth(child) for child in dependant.dependencies
        )

    private_routes = [
        route
        for included in app.routes
        if getattr(included, "original_router", None) is not None
        for route in included.original_router.routes
    ]
    assert private_routes
    assert all(contains_auth(route.dependant) for route in private_routes)


def test_two_users_are_isolated_across_projects_media_uploads_and_exports(
    client, testing_session_factory
) -> None:
    project = client.post("/api/v1/projects", json={"title": "User A project"}).json()
    with testing_session_factory() as db:
        asset = MediaAsset(
            owner_id=TEST_USER_ID,
            project_id=uuid.UUID(project["id"]),
            original_filename="private.mp4",
            object_key="projects/a/originals/private.mp4",
            bucket_name="test",
            mime_type="video/mp4",
            file_size_bytes=100,
            duration_seconds=40,
            width=1920,
            height=1080,
            status=MediaAssetStatus.READY,
        )
        db.add(asset)
        db.flush()
        upload = UploadSession(
            owner_id=TEST_USER_ID,
            asset_id=asset.id,
            r2_upload_id="private-upload",
            status=UploadSessionStatus.UPLOADING,
            part_size_bytes=5 * 1024 * 1024,
            expected_size_bytes=100,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        transcript = Transcript(
            owner_id=TEST_USER_ID,
            asset_id=asset.id,
            provider="fixture",
            model="fixture",
            status=TranscriptStatus.COMPLETED,
        )
        db.add_all([upload, transcript])
        db.flush()
        run = MomentAnalysisRun(
            owner_id=TEST_USER_ID,
            asset_id=asset.id,
            transcript_id=transcript.id,
            status=MomentAnalysisStatus.COMPLETED,
            provider="fixture",
            model="fixture",
            prompt_version="test",
            analysis_version="test",
            settings_json={},
        )
        db.add(run)
        db.flush()
        moment = MomentCandidate(
            owner_id=TEST_USER_ID,
            analysis_run_id=run.id,
            asset_id=asset.id,
            start_ms=0,
            end_ms=30_000,
            ai_start_ms=0,
            ai_end_ms=30_000,
            suggested_title="Private",
            hook_text="Private",
            topic="Private",
            category="test",
            overall_score=80,
            score_breakdown_json={},
            explanation="Private",
            confidence_notes="Private",
            rank=1,
            review_status=MomentReviewStatus.APPROVED,
        )
        db.add(moment)
        db.flush()
        export = ClipExport(
            owner_id=TEST_USER_ID,
            moment_id=moment.id,
            asset_id=asset.id,
            status=ClipExportStatus.COMPLETED,
            aspect_ratio=ExportAspectRatio.VERTICAL,
            resolution="720x1280",
            fps=30,
            caption_preset=CaptionPreset.BOLD,
            framing_mode=FramingMode.CENTER,
            render_settings_json={},
            settings_hash="a" * 64,
            r2_object_key="projects/a/exports/private.mp4",
            file_size_bytes=50,
            duration_ms=30_000,
        )
        db.add(export)
        db.commit()
        ids = asset.id, upload.id, moment.id, export.id

    app.dependency_overrides[require_user] = lambda: AuthenticatedUser(
        SECOND_USER_ID, "user-b@example.test", "authenticated"
    )
    asset_id, upload_id, moment_id, export_id = ids
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert client.get(f"/api/v1/media/{asset_id}").status_code == 404
    assert client.get(f"/api/v1/media/{asset_id}/transcript").status_code == 404
    assert client.get(f"/api/v1/moments/{moment_id}").status_code == 404
    assert client.post(
        f"/api/v1/uploads/{upload_id}/complete",
        json={"parts": [{"part_number": 1, "etag": "private"}]},
    ).status_code == 404
    assert client.get(f"/api/v1/exports/{export_id}/download").status_code == 404
    assert client.post(f"/api/v1/exports/{export_id}/cancel").status_code == 404


def test_project_quota_is_enforced_server_side(client) -> None:
    for index in range(10):
        assert client.post("/api/v1/projects", json={"title": f"Project {index}"}).status_code == 201
    limited = client.post("/api/v1/projects", json={"title": "One too many"})
    assert limited.status_code == 429
    assert "Project limit reached" in limited.json()["error"]["message"]


def test_legacy_records_remain_unowned_until_explicit_claim(testing_session_factory) -> None:
    with testing_session_factory() as db:
        project = Project(title="Legacy")
        db.add(project)
        db.flush()
        asset = MediaAsset(
            project_id=project.id,
            original_filename="legacy.mp4",
            object_key="legacy/source.mp4",
            bucket_name="test",
            mime_type="video/mp4",
            file_size_bytes=321,
            status=MediaAssetStatus.READY,
        )
        db.add(asset)
        db.flush()
        job = ProcessingJob(
            asset_id=asset.id,
            job_type=ProcessingJobType.VALIDATE_MEDIA,
            status=ProcessingJobStatus.SUCCEEDED,
        )
        db.add(job)
        db.commit()
        db.execute(update(Project).values(owner_id=None))
        db.execute(update(MediaAsset).values(owner_id=None))
        db.execute(update(ProcessingJob).values(owner_id=None))
        db.commit()
        assert db.get(Project, project.id).owner_id is None

        assert claim_legacy_projects(db, TEST_USER_ID, [project.id]) == 1
        db.commit()
        db.expire_all()
        assert db.get(Project, project.id).owner_id == TEST_USER_ID
        assert db.get(MediaAsset, asset.id).owner_id == TEST_USER_ID
        assert db.get(ProcessingJob, job.id).owner_id == TEST_USER_ID
