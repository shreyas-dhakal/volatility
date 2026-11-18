import base64
import hashlib
import secrets
from datetime import timezone

from cryptography.fernet import Fernet
from fastapi import HTTPException

from galvanise.config import settings


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


def check_origin(request):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if (
            origin and origin.rstrip("/") != settings.web_url.rstrip("/")
        ) or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Untrusted request origin")
