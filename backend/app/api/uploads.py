from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.responses import upload_session_response
from app.config import Settings, get_settings
from app.database import get_db
from app.models import (
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobType,
    Project,
    UploadSession,
    UploadSessionStatus,
    utc_now,
)
from app.rate_limit import upload_rate_limiter
from app.schemas import (
    CompleteUploadRequest,
    UploadCompletionResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
    UploadedPartResponse,
    UploadedPartsResponse,
    UploadPartSignRequest,
    UploadPartSignResponse,
    UploadSessionResponse,
)
from app.services.storage import StorageError, StorageService, UploadedPart, get_storage_service
from app.services.upload_policy import (
    UploadPolicyError,
    calculate_total_parts,
    expected_part_size,
    make_object_key,
    normalize_etag,
    validate_declared_video,
)


router = APIRouter(tags=["uploads"])
ACTIVE_ASSET_STATUSES = (
    MediaAssetStatus.PENDING_UPLOAD,
    MediaAssetStatus.UPLOADING,
    MediaAssetStatus.UPLOADED,
    MediaAssetStatus.VALIDATING,
    MediaAssetStatus.READY,
)
ACTIVE_SESSION_STATUSES = (
    UploadSessionStatus.INITIATED,
    UploadSessionStatus.UPLOADING,
)


def _client_key(request: Request, action: str) -> str:
    host = request.client.host if request.client else "local"
    return f"{host}:{action}"


def _enforce_rate_limit(request: Request, action: str, limit: int) -> None:
    result = upload_rate_limiter.check(_client_key(request, action), limit)
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many upload requests. Try again shortly.",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _get_session(db: Session, session_id: uuid.UUID, lock: bool = False) -> UploadSession:
    statement = select(UploadSession).where(UploadSession.id == session_id)
    if lock:
        statement = statement.with_for_update()
    session = db.scalar(statement)
    if session is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return session


def _get_asset(db: Session, session: UploadSession) -> MediaAsset:
    asset = db.get(MediaAsset, session.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return asset


def _active_session_or_error(session: UploadSession) -> None:
    if session.status not in ACTIVE_SESSION_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Upload session is {session.status.value} and cannot accept this operation.",
        )
    if _as_utc(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Upload session has expired")


@router.post(
    "/projects/{project_id}/uploads/initiate",
    response_model=UploadInitiateResponse,
    status_code=status.HTTP_201_CREATED,
)
def initiate_upload(
    project_id: uuid.UUID,
    payload: UploadInitiateRequest,
    request: Request,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    settings: Settings = Depends(get_settings),
) -> UploadInitiateResponse:
    _enforce_rate_limit(
        request, "upload-initiate", settings.upload_init_rate_limit_per_minute
    )
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.file_size_bytes > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Videos may not exceed {settings.max_upload_size_mb} MiB.",
        )
    try:
        filename, extension = validate_declared_video(
            payload.original_filename,
            payload.mime_type,
            payload.file_size_bytes,
            settings.max_upload_size_bytes,
        )
    except UploadPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    used_bytes = db.scalar(
        select(func.coalesce(func.sum(MediaAsset.file_size_bytes), 0)).where(
            MediaAsset.project_id == project_id,
            MediaAsset.status.in_(ACTIVE_ASSET_STATUSES),
        )
    )
    if int(used_bytes or 0) + payload.file_size_bytes > settings.max_project_storage_bytes:
        raise HTTPException(status_code=409, detail="This project has reached its storage quota.")

    asset_id = uuid.uuid4()
    object_key = make_object_key(project_id, asset_id, extension)
    try:
        r2_upload_id = storage.create_multipart_upload(
            object_key,
            payload.mime_type.lower(),
            {"project-id": str(project_id), "asset-id": str(asset_id)},
        )
    except StorageError as exc:
        raise HTTPException(status_code=502, detail="Could not create the R2 upload.") from exc

    now = utc_now()
    asset = MediaAsset(
        id=asset_id,
        project_id=project_id,
        original_filename=filename,
        object_key=object_key,
        bucket_name=storage.bucket_name,
        mime_type=payload.mime_type.lower(),
        file_size_bytes=payload.file_size_bytes,
        status=MediaAssetStatus.PENDING_UPLOAD,
    )
    session = UploadSession(
        asset_id=asset_id,
        r2_upload_id=r2_upload_id,
        status=UploadSessionStatus.INITIATED,
        part_size_bytes=settings.upload_part_size_bytes,
        expected_size_bytes=payload.file_size_bytes,
        expires_at=now + timedelta(hours=settings.upload_session_expiry_hours),
    )
    db.add_all([asset, session])
    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage.abort_multipart_upload(object_key, r2_upload_id)
        except StorageError:
            pass
        raise
    db.refresh(session)
    return UploadInitiateResponse(session=upload_session_response(session))


@router.post(
    "/uploads/{session_id}/parts/sign", response_model=UploadPartSignResponse
)
def sign_upload_part(
    session_id: uuid.UUID,
    payload: UploadPartSignRequest,
    request: Request,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    settings: Settings = Depends(get_settings),
) -> UploadPartSignResponse:
    _enforce_rate_limit(request, "upload-sign", settings.upload_sign_rate_limit_per_minute)
    session = _get_session(db, session_id, lock=True)
    _active_session_or_error(session)
    asset = _get_asset(db, session)
    total_parts = calculate_total_parts(
        session.expected_size_bytes, session.part_size_bytes
    )
    if payload.part_number > total_parts:
        raise HTTPException(status_code=400, detail="Part number is outside this upload.")
    try:
        upload_url = storage.generate_upload_part_url(
            asset.object_key,
            session.r2_upload_id,
            payload.part_number,
            settings.signed_url_expiry_seconds,
        )
    except StorageError as exc:
        raise HTTPException(status_code=502, detail="Could not sign this upload part.") from exc

    if session.status == UploadSessionStatus.INITIATED:
        session.status = UploadSessionStatus.UPLOADING
        asset.status = MediaAssetStatus.UPLOADING
        db.commit()
    return UploadPartSignResponse(
        part_number=payload.part_number,
        upload_url=upload_url,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.signed_url_expiry_seconds),
    )


@router.get("/uploads/{session_id}/parts", response_model=UploadedPartsResponse)
def list_upload_parts(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> UploadedPartsResponse:
    session = _get_session(db, session_id)
    if session.status == UploadSessionStatus.COMPLETED:
        return UploadedPartsResponse(session_id=session.id, parts=[])
    _active_session_or_error(session)
    asset = _get_asset(db, session)
    try:
        parts = storage.list_uploaded_parts(asset.object_key, session.r2_upload_id)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail="Could not list uploaded parts.") from exc
    return UploadedPartsResponse(
        session_id=session.id,
        parts=[UploadedPartResponse(**part.__dict__) for part in parts],
    )


@router.post(
    "/uploads/{session_id}/complete", response_model=UploadCompletionResponse
)
def complete_upload(
    session_id: uuid.UUID,
    payload: CompleteUploadRequest,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> UploadCompletionResponse:
    session = _get_session(db, session_id, lock=True)
    asset = _get_asset(db, session)
    existing_job = db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.asset_id == asset.id,
            ProcessingJob.job_type == ProcessingJobType.VALIDATE_MEDIA,
        )
    )
    if session.status == UploadSessionStatus.COMPLETED:
        return UploadCompletionResponse(
            session=upload_session_response(session),
            asset_id=asset.id,
            asset_status=asset.status,
            validation_job_id=existing_job.id if existing_job else None,
        )
    _active_session_or_error(session)

    total_parts = calculate_total_parts(
        session.expected_size_bytes, session.part_size_bytes
    )
    supplied_numbers = [part.part_number for part in payload.parts]
    if supplied_numbers != list(range(1, total_parts + 1)):
        raise HTTPException(
            status_code=400,
            detail="Completion parts must be ordered and include every expected part exactly once.",
        )
    try:
        remote_parts = storage.list_uploaded_parts(asset.object_key, session.r2_upload_id)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail="Could not reconcile R2 upload parts.") from exc

    if [part.part_number for part in remote_parts] != supplied_numbers:
        raise HTTPException(status_code=409, detail="R2 does not contain every expected part.")
    for supplied, remote in zip(payload.parts, remote_parts, strict=True):
        if normalize_etag(supplied.etag) != normalize_etag(remote.etag):
            raise HTTPException(status_code=409, detail="An uploaded part ETag does not match R2.")
        expected_size = expected_part_size(
            remote.part_number,
            total_parts,
            session.part_size_bytes,
            session.expected_size_bytes,
        )
        if remote.size != expected_size:
            raise HTTPException(status_code=409, detail="An uploaded part has an unexpected size.")

    completion_parts = [
        UploadedPart(part.part_number, part.etag, remote.size)
        for part, remote in zip(payload.parts, remote_parts, strict=True)
    ]
    try:
        storage.complete_multipart_upload(
            asset.object_key, session.r2_upload_id, completion_parts
        )
        head = storage.head_object(asset.object_key)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail="Could not complete the R2 upload.") from exc

    if head.content_length != session.expected_size_bytes:
        try:
            storage.delete_object(asset.object_key)
        except StorageError:
            pass
        session.status = UploadSessionStatus.FAILED
        asset.status = MediaAssetStatus.FAILED
        db.commit()
        raise HTTPException(status_code=409, detail="The completed R2 object size is incorrect.")

    session.status = UploadSessionStatus.COMPLETED
    session.completed_at = utc_now()
    asset.status = MediaAssetStatus.UPLOADED
    job = existing_job or ProcessingJob(
        asset_id=asset.id,
        job_type=ProcessingJobType.VALIDATE_MEDIA,
        status=ProcessingJobStatus.QUEUED,
        attempts=0,
        max_attempts=3,
    )
    if existing_job is None:
        db.add(job)
    db.commit()
    db.refresh(session)
    db.refresh(asset)
    db.refresh(job)
    return UploadCompletionResponse(
        session=upload_session_response(session),
        asset_id=asset.id,
        asset_status=asset.status,
        validation_job_id=job.id,
    )


@router.post("/uploads/{session_id}/abort", response_model=UploadSessionResponse)
def abort_upload(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> UploadSessionResponse:
    session = _get_session(db, session_id, lock=True)
    asset = _get_asset(db, session)
    if session.status in (UploadSessionStatus.ABORTED, UploadSessionStatus.EXPIRED):
        return upload_session_response(session)
    if session.status == UploadSessionStatus.COMPLETED:
        return upload_session_response(session)
    try:
        storage.abort_multipart_upload(asset.object_key, session.r2_upload_id)
    except StorageError as exc:
        if exc.code not in {"NoSuchUpload", "404", "10024"}:
            raise HTTPException(status_code=502, detail="Could not abort the R2 upload.") from exc
    session.status = UploadSessionStatus.ABORTED
    asset.status = MediaAssetStatus.ABORTED
    db.commit()
    db.refresh(session)
    return upload_session_response(session)


@router.get("/uploads/{session_id}", response_model=UploadSessionResponse)
def get_upload_session(
    session_id: uuid.UUID, db: Session = Depends(get_db)
) -> UploadSessionResponse:
    return upload_session_response(_get_session(db, session_id))
