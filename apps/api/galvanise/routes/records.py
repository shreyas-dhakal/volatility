from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from galvanise.database import get_db
from galvanise.dependencies import get_current_user, require_project
from galvanise.models import KnowledgeRecord, User, now

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
