from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from galvanise.clerk_auth import verified_subject
from galvanise.clerk_identity import resolve_user
from galvanise.database import get_db
from galvanise.models import Project, User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    return resolve_user(db, verified_subject(request))


def require_project(project_id: str, db: Session, user: User) -> Project:
    project = db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(404, "Project not found")
    return project
