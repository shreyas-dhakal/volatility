"""Select stable Clerk-backed identities for domain tests without exercising login."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from galvanise.database import SessionLocal, get_db
from galvanise.dependencies import get_current_user
from galvanise.main import app
from galvanise.models import User


def _test_identity(request: Request, db: Session = Depends(get_db)) -> User:
    email = request.headers.get("x-test-user")
    if not email:
        raise HTTPException(401, "Sign in required")
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(401, "Sign in required")
    return user


def authenticate_as(
    client, email: str, name: str = "Test owner", session_factory=SessionLocal
) -> User:
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(name=name, email=email, clerk_user_id="test_" + email)
            db.add(user)
            db.commit()
            db.refresh(user)
    app.dependency_overrides[get_current_user] = _test_identity
    client.headers["x-test-user"] = email
    return user


def sign_out_test_user(client) -> None:
    client.headers.pop("x-test-user", None)
