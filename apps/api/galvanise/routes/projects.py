from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from galvanise.database import get_db
from galvanise.dependencies import get_current_user, require_project
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
