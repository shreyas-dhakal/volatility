from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from galvanise.database import get_db
from galvanise.dependencies import get_current_user, require_project
from galvanise.integrations.github import accessible_repo, project_id_for_repo
from galvanise.routes.sources import Repo, queue_repository
from galvanise.models import Conversation, Message, Project, User

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)
    system_type: Literal["existing", "new"] = "existing"
    objective: str = Field(default="", max_length=20000)


class ConversationInput(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)


@router.get("")
def projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(
        db.scalars(
            select(Project)
            .where(Project.user_id == user.id)
            .order_by(Project.created_at)
        )
    )


@router.post("")
def create_project(
    body: ProjectInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = Project(user_id=user.id, **body.model_dump())
    db.add(p)
    db.commit()
    return p


@router.post("/github")
def open_repository(
    body: Repo, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    repo = accessible_repo(user, body.full_name)
    project_id = project_id_for_repo(user, repo["id"])
    project = db.get(Project, project_id)
    if project:
        return require_project(project_id, db, user)
    project = Project(
        id=project_id,
        user_id=user.id,
        name=repo["full_name"],
        description=repo.get("description") or "",
        system_type="existing",
    )
    try:
        db.add(project)
        db.flush()
        queue_repository(db, project_id, user, repo)
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.get(Project, project_id) is None:
            raise
        return require_project(project_id, db, user)
    return project


@router.get("/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return require_project(project_id, db, user)


@router.get("/{project_id}/conversations")
def conversations(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.created_at)
        )
    )


@router.post("/{project_id}/conversations")
def create_conversation(
    project_id: str,
    body: ConversationInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    c = Conversation(project_id=project_id, **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.get("/{project_id}/conversations/{conversation_id}/messages")
def messages(
    project_id: str,
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(project_id, db, user)
    c = db.get(Conversation, conversation_id)
    if not c or c.project_id != project_id:
        raise HTTPException(404, "Conversation not found")
    return list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    )
