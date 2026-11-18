import base64
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from galvanise.config import settings
from galvanise.database import get_db
from galvanise.dependencies import get_current_user, require_project
from galvanise.integrations.github import accessible_repo
from galvanise.models import (
    ConnectedSource,
    IngestionJob,
    SourceDocument,
    TechnicalGraph,
    User,
)
from galvanise.security import encrypt
from galvanise.services.ingestion import ALLOWED, relative_path

router = APIRouter(prefix="/api/projects/{project_id}")


def public_job(job):
    return jsonable_encoder(
        {
            k: getattr(job, k)
            for k in (
                "id",
                "project_id",
                "kind",
                "status",
                "error",
                "created_at",
                "updated_at",
            )
        }
        | {
            "source_id": job.payload.get("source_id"),
            "archive": job.payload.get("name")
            if job.payload.get("name", "").lower().endswith(".zip")
            else None,
            "upload_id": job.payload.get("upload_id"),
        }
    )


@router.get("/sources")
def sources(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    return list(
        db.scalars(
            select(ConnectedSource).where(ConnectedSource.project_id == project_id)
        )
    )


@router.delete("/sources/github/{source_id}", status_code=204)
def delete_repository(
    project_id: str,
    source_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    require_project(project_id, db, user)
    repository = (
        ConnectedSource.project_id == project_id,
        ConnectedSource.id == source_id,
        ConnectedSource.kind == "github",
    )
    if db.scalar(select(ConnectedSource.id).where(*repository)) is None:
        raise HTTPException(404, "Repository not found")

    db.execute(
        delete(IngestionJob).where(
            IngestionJob.project_id == project_id,
            IngestionJob.kind.in_(["github", "graphify"]),
            IngestionJob.payload["source_id"].as_string() == source_id,
        )
    )
    for model in (SourceDocument, TechnicalGraph):
        db.execute(
            delete(model).where(
                model.project_id == project_id, model.source_id == source_id
            )
        )
    db.execute(delete(ConnectedSource).where(*repository))
    db.commit()


@router.post("/sources/github/{source_id}/retry")
def retry_repository(
    project_id: str,
    source_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    source = db.scalar(
        select(ConnectedSource)
        .where(
            ConnectedSource.project_id == project_id,
            ConnectedSource.id == source_id,
            ConnectedSource.kind == "github",
        )
        .with_for_update()
    )
    if source is None:
        raise HTTPException(404, "Repository not found")
    job = db.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.project_id == project_id,
            IngestionJob.kind == "github",
            IngestionJob.payload["source_id"].as_string() == source_id,
        )
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    if job is None or source.status not in ("failed", "empty", "pending"):
        raise HTTPException(409, "This repository cannot be retried.")
    if source.status != "pending":
        job.status = "queued"
        job.error = None
        source.status = "pending"
        db.commit()
    return public_job(job)


@router.post("/sources/github/{source_id}/graph")
def build_graph(
    project_id: str,
    source_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    source = db.scalar(
        select(ConnectedSource)
        .where(
            ConnectedSource.id == source_id,
            ConnectedSource.project_id == project_id,
            ConnectedSource.kind == "github",
        )
        .with_for_update()
    )
    if source is None:
        raise HTTPException(404, "Repository not found")
    if source.status != "ready":
        raise HTTPException(
            409, "Repository indexing must finish before building the map."
        )
    job = db.scalar(
        select(IngestionJob).where(
            IngestionJob.project_id == project_id,
            IngestionJob.kind == "graphify",
            IngestionJob.payload["source_id"].as_string() == source_id,
            IngestionJob.status.in_(["queued", "running"]),
        )
    )
    if job is not None:
        return public_job(job)
    existing = db.scalar(
        select(TechnicalGraph.id).where(
            TechnicalGraph.project_id == project_id,
            TechnicalGraph.source_id == source_id,
            TechnicalGraph.metadata_json["generator"].as_string() == "graphify",
        )
    )
    if existing:
        return {"graph_id": existing}
    job = IngestionJob(
        project_id=project_id, kind="graphify", payload={"source_id": source_id}
    )
    db.add(job)
    db.commit()
    return public_job(job)


@router.post("/documents")
async def upload(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    name = relative_path(file.filename or "document")[:1024]
    if PurePosixPath(name).suffix.lower() not in ALLOWED:
        raise HTTPException(
            415,
            "Supported uploads include text, source code, PDF, DOCX and ZIP projects",
        )
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File exceeds upload size limit")
    if not data:
        raise HTTPException(422, "File is empty")
    job = IngestionJob(
        project_id=project_id,
        kind="document",
        payload={
            "name": name,
            "media_type": file.content_type or "application/octet-stream",
            "content_ciphertext": encrypt(base64.b64encode(data).decode()),
        },
    )
    db.add(job)
    db.commit()
    return public_job(job)


@router.get("/documents")
def documents(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    return [
        jsonable_encoder(
            {
                c.name: getattr(d, c.name)
                for c in d.__table__.columns
                if c.name != "content"
            }
        )
        for d in db.scalars(
            select(SourceDocument)
            .where(SourceDocument.project_id == project_id)
            .order_by(SourceDocument.created_at)
        )
    ]


@router.get("/documents/{document_id}")
def document(
    project_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    d = db.get(SourceDocument, document_id)
    if not d or d.project_id != project_id:
        raise HTTPException(404, "Document not found")
    return d


class Repo(BaseModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)


@router.post("/sources/github")
def connect(
    project_id: str,
    body: Repo,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    repo = accessible_repo(user, body.full_name)
    job = queue_repository(db, project_id, user, repo)
    db.commit()
    return public_job(job)


def queue_repository(db, project_id, user, repo):
    source = ConnectedSource(
        project_id=project_id,
        kind="github",
        name=repo["full_name"],
        status="pending",
        metadata_json={"full_name": repo["full_name"]},
    )
    db.add(source)
    db.flush()
    job = IngestionJob(
        project_id=project_id,
        kind="github",
        payload={
            "full_name": repo["full_name"],
            "source_id": source.id,
            "repository_id": repo["id"],
            "user_id": user.id,
        },
    )
    db.add(job)
    return job


@router.get("/jobs")
def jobs(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    return [
        public_job(j)
        for j in db.scalars(
            select(IngestionJob)
            .where(IngestionJob.project_id == project_id)
            .order_by(IngestionJob.created_at)
        )
    ]
