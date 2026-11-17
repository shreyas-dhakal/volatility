from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from galvanise.database import get_db
from galvanise.models import Project, User, now
from galvanise.models import Session as AuthSession
from galvanise.security import aware, digest


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("session", "")
    session = (
        db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(token)))
        if token
        else None
    )
    if not session or aware(session.expires_at) <= now():
        raise HTTPException(401, "Sign in required")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "Sign in required")
    return user


def require_project(project_id: str, db: Session, user: User) -> Project:
    project = db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(404, "Project not found")
    return project
