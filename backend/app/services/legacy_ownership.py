from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ClipExport,
    ClipExportStatus,
    MediaAsset,
    MediaAssetStatus,
    MomentAnalysisRun,
    MomentCandidate,
    ProcessingJob,
    Project,
    Transcript,
    UploadSession,
    UserUsage,
)


class LegacyOwnershipError(ValueError):
    pass


def claim_legacy_projects(
    db: Session, owner_id: uuid.UUID, project_ids: list[uuid.UUID]
) -> int:
    if not project_ids:
        raise LegacyOwnershipError("At least one explicit project ID is required.")
    projects = list(
        db.scalars(
            select(Project)
            .where(Project.id.in_(project_ids))
            .options(selectinload(Project.media_assets))
            .with_for_update()
        )
    )
    if {project.id for project in projects} != set(project_ids):
        raise LegacyOwnershipError("One or more project IDs do not exist.")
    for project in projects:
        if project.owner_id not in {None, owner_id}:
            raise LegacyOwnershipError(f"Project {project.id} already belongs to another user.")
        project.owner_id = owner_id
        for asset in project.media_assets:
            if asset.owner_id not in {None, owner_id}:
                raise LegacyOwnershipError(f"Asset {asset.id} has conflicting ownership.")
            asset.owner_id = owner_id
            for model in (
                UploadSession,
                ProcessingJob,
                Transcript,
                MomentAnalysisRun,
                MomentCandidate,
                ClipExport,
            ):
                conflict = db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(
                        model.asset_id == asset.id,
                        model.owner_id.is_not(None),
                        model.owner_id != owner_id,
                    )
                )
                if conflict:
                    raise LegacyOwnershipError(
                        f"Asset {asset.id} has conflicting {model.__tablename__} ownership."
                    )
            db.execute(
                UploadSession.__table__.update()
                .where(UploadSession.asset_id == asset.id, UploadSession.owner_id.is_(None))
                .values(owner_id=owner_id)
            )
            db.execute(
                ProcessingJob.__table__.update()
                .where(ProcessingJob.asset_id == asset.id, ProcessingJob.owner_id.is_(None))
                .values(owner_id=owner_id)
            )
            db.execute(
                Transcript.__table__.update()
                .where(Transcript.asset_id == asset.id, Transcript.owner_id.is_(None))
                .values(owner_id=owner_id)
            )
            db.execute(
                MomentAnalysisRun.__table__.update()
                .where(
                    MomentAnalysisRun.asset_id == asset.id,
                    MomentAnalysisRun.owner_id.is_(None),
                )
                .values(owner_id=owner_id)
            )
            db.execute(
                MomentCandidate.__table__.update()
                .where(
                    MomentCandidate.asset_id == asset.id,
                    MomentCandidate.owner_id.is_(None),
                )
                .values(owner_id=owner_id)
            )
            db.execute(
                ClipExport.__table__.update()
                .where(ClipExport.asset_id == asset.id, ClipExport.owner_id.is_(None))
                .values(owner_id=owner_id)
            )

    source_bytes = db.scalar(
        select(func.coalesce(func.sum(MediaAsset.file_size_bytes), 0)).where(
            MediaAsset.owner_id == owner_id,
            MediaAsset.status.not_in(
                [
                    MediaAssetStatus.ABORTED,
                    MediaAssetStatus.REJECTED,
                    MediaAssetStatus.FAILED,
                ]
            ),
        )
    ) or 0
    export_bytes = db.scalar(
        select(func.coalesce(func.sum(ClipExport.file_size_bytes), 0)).where(
            ClipExport.owner_id == owner_id,
            ClipExport.status == ClipExportStatus.COMPLETED,
        )
    ) or 0
    usage = db.get(UserUsage, owner_id)
    if usage is None:
        usage = UserUsage(owner_id=owner_id)
        db.add(usage)
    usage.stored_media_bytes = int(source_bytes) + int(export_bytes)
    db.flush()
    return len(projects)
