"""Trusted test identities; no password/session endpoints or production bypasses."""

from sqlalchemy import select
from galvanise.database import SessionLocal
from galvanise.models import User


def sign_in(client, email="owner@example.com", name="Owner"):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name=name)
            db.add(user)
            db.flush()
            user.clerk_user_id = "user_test_" + user.id
            db.commit()
        if not user.clerk_user_id:
            user.clerk_user_id = "user_test_" + user.id
            db.commit()
        client.headers["Authorization"] = "Bearer isolated:" + user.id
        return {"id": user.id, "email": user.email, "name": user.name}


def sign_out(client):
    client.headers.pop("Authorization", None)
