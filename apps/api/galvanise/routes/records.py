from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from galvanise.database import get_db
from galvanise.dependencies import get_current_user, require_project
from galvanise.models import KnowledgeRecord, User, now
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/projects/{project_id}/records")


class Review(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["pending", "approved", "rejected"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    description: str | None = Field(default=None, max_length=100000)
    payload: dict | None = None


@router.get("")
def records(
    project_id: str,
    kind: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    query = select(KnowledgeRecord).where(KnowledgeRecord.project_id == project_id)
    if kind:
        query = query.where(KnowledgeRecord.kind == kind)
    return list(db.scalars(query.order_by(KnowledgeRecord.created_at)))


@router.patch("/{record_id}")
def review(
    project_id: str,
    record_id: str,
    body: Review,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    record = db.get(KnowledgeRecord, record_id)
    if not record or record.project_id != project_id:
        raise HTTPException(404, "Record not found")
    snapshot = jsonable_encoder(
        {
            c.name: getattr(record, c.name)
            for c in record.__table__.columns
            if c.name != "history"
        }
    )
    changes = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if k != "expected_version" and v is not None
    }
    # Keep design invariants on the existing human review path too.
    from galvanise.services.design import evidence_versions, is_design, validate_payload
    from galvanise.services.knowledge import records_for

    if record.version != body.expected_version:
        raise HTTPException(409, "Record changed; reload before reviewing")
    if (
        body.payload is not None
        and not is_design(record)
        and body.payload.get("design_engine") is True
    ):
        raise HTTPException(
            422,
            "design_engine is server-managed; generate design artifacts through the design workflow",
        )
    if is_design(record) and (
        body.payload is not None
        or body.title is not None
        or body.description is not None
        or body.status == "approved"
    ):
        if "payload" in changes:
            changes["payload"] = {
                k: v for k, v in changes["payload"].items() if k != "stale"
            }
        payload = changes.get("payload", record.payload)
        if "evidence_versions" in payload and payload[
            "evidence_versions"
        ] != record.payload.get("evidence_versions", {}):
            raise HTTPException(422, "evidence_versions is server-managed")
        if record.kind != "use_case":
            # Provenance belongs to the server, including version snapshots.
            for field in (
                "input_versions",
                "design_engine",
                "context_limits",
                "supersedes_id",
                "proposal_revision",
            ):
                if payload.get(field) != record.payload.get(field):
                    raise HTTPException(422, f"{field} is server-managed")
        try:
            validate_payload(
                db,
                project_id,
                record.kind,
                changes.get("title", record.title),
                changes.get("description", record.description),
                payload,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        if "payload" in changes:
            changes["payload"]["evidence_versions"] = evidence_versions(
                payload, records_for(db, project_id)
            )
    result = db.execute(
        update(KnowledgeRecord)
        .where(
            KnowledgeRecord.id == record_id,
            KnowledgeRecord.version == body.expected_version,
        )
        .values(
            **changes,
            version=body.expected_version + 1,
            history=record.history + [snapshot],
            updated_at=now(),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Record changed; reload before reviewing")
    db.commit()
    db.refresh(record)
    return record
