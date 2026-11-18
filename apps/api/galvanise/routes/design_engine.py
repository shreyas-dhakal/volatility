from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from galvanise.database import get_db
from galvanise.dependencies import get_current_user
from galvanise.design_engine import service
from galvanise.models import User

router = APIRouter(
    prefix="/api/projects/{project_id}/design-engine", tags=["design-engine"]
)
Database = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class Analyze(BaseModel):
    selected_upload_ids: list[str] | None = None
    request_message_id: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=256)


class Revise(BaseModel):
    base_revision_id: str
    correction_message_id: str
    idempotency_key: str = Field(min_length=1, max_length=256)


class Plan(BaseModel):
    revision_id: str
    planning_inputs: dict


@router.get("")
def overview(project_id: str, db: Database, user: CurrentUser):
    return service.overview(db, project_id, user)


@router.get("/revisions/{revision_id}")
def revision(project_id: str, revision_id: str, db: Database, user: CurrentUser):
    return service.get_revision(db, project_id, user, revision_id)


@router.get("/chunks/{chunk_id}")
def chunk(project_id: str, chunk_id: str, db: Database, user: CurrentUser):
    return service.get_chunk(db, project_id, user, chunk_id)


@router.post("/analyze", status_code=202)
def analyze(project_id: str, body: Analyze, db: Database, user: CurrentUser):
    return service.analyze_design(db, project_id, user, **body.model_dump())


@router.post("/revise", status_code=202)
def revise(project_id: str, body: Revise, db: Database, user: CurrentUser):
    return service.revise_design(db, project_id, user, **body.model_dump())


@router.post("/runs/{run_id}/retry", status_code=202)
def retry(project_id: str, run_id: str, db: Database, user: CurrentUser):
    return service.retry(db, project_id, user, run_id)


@router.post("/plan")
def plan(project_id: str, body: Plan, db: Database, user: CurrentUser):
    return service.plan_project(db, project_id, user, **body.model_dump())
