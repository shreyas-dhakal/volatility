import base64
import hashlib
import secrets
from datetime import timedelta, timezone

from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from fastapi import HTTPException

from galvanise.config import settings
from galvanise.models import Session, now

hasher = PasswordHasher()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cipher():
    return Fernet(
        base64.urlsafe_b64encode(hashlib.sha256(settings.auth_secret.encode()).digest())
    )


def encrypt(value):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value):
    return cipher().decrypt(value.encode()).decode()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def issue_session(db, user, response):
    token = secrets.token_urlsafe(48)
    db.add(
        Session(
            user_id=user.id,
            token_hash=digest(token),
            expires_at=now() + timedelta(days=14),
        )
    )
    db.commit()
    response.set_cookie(
        "session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=1209600,
        path="/",
    )


def check_origin(request):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if (
            origin and origin.rstrip("/") != settings.web_url.rstrip("/")
        ) or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Untrusted request origin")
