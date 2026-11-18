"""Clerk identities map to stable application owners, never to browser-supplied IDs."""

from functools import lru_cache

from clerk_backend_api import Clerk
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from galvanise.config import settings
from galvanise.models import User


class IdentityProvider:
    def __init__(self, sdk):
        self.sdk = sdk

    def get(self, subject):
        return self.sdk.users.get(user_id=subject)

    def update(self, subject, external_id):
        return self.sdk.users.update(user_id=subject, external_id=external_id)

    def find(self, external_id):
        return self.sdk.users.list(request={"external_id": [external_id], "limit": 2})

    def create(self, **payload):
        return self.sdk.users.create(**payload)


@lru_cache(maxsize=1)
def provider():
    if not settings.clerk_secret_key:
        raise HTTPException(503, "Clerk server configuration is missing")
    return IdentityProvider(Clerk(bearer_auth=settings.clerk_secret_key))


def primary_email(remote):
    return next(
        (e for e in remote.email_addresses if e.id == remote.primary_email_address_id),
        None,
    )


def resolve_user(db, subject, identity_provider=None):
    upstream = identity_provider or provider()
    try:
        remote = upstream.get(subject)
    except Exception:  # noqa: BLE001 -- sanitize SDK errors at the identity boundary
        raise HTTPException(503, "Identity service unavailable") from None
    if remote.id != subject or remote.banned or remote.locked:
        raise HTTPException(401, "Sign in required")
    user = db.scalar(select(User).where(User.clerk_user_id == subject))
    if user is None:
        # Existing owner records require an explicit mapping, never an email guess.
        if remote.external_id and db.get(User, remote.external_id) is not None:
            raise HTTPException(409, "Account identity conflict")
        email = primary_email(remote)
        if (
            not email
            or not email.verification
            or email.verification.status != "verified"
        ):
            raise HTTPException(403, "Verify your email before opening the workspace")
        address = email.email_address.strip().lower()
        if db.scalar(select(User.id).where(User.email == address)):
            raise HTTPException(
                409, "Sign in to your original account or request account recovery"
            )
        user = User(
            id=remote.external_id,
            clerk_user_id=subject,
            email=address,
            name=" ".join(filter(None, [remote.first_name, remote.last_name]))
            or address.split("@")[0],
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.clerk_user_id == subject))
            if user is None:
                raise HTTPException(409, "Account identity conflict") from None
    # Also retry this after a previous external-ID update failed. Never expose an unsynced owner.
    if remote.external_id and remote.external_id != user.id:
        raise HTTPException(409, "Account identity conflict")
    if remote.external_id != user.id:
        try:
            upstream.update(subject, user.id)
        except Exception:  # noqa: BLE001 -- sanitize SDK errors at the identity boundary
            raise HTTPException(
                503, "Account synchronization pending; retry shortly"
            ) from None
    email = primary_email(remote)
    if email and email.verification and email.verification.status == "verified":
        address = email.email_address.strip().lower()
        if address != user.email:
            if db.scalar(
                select(User.id).where(User.email == address, User.id != user.id)
            ):
                raise HTTPException(
                    409,
                    "Profile email conflicts with another account; request recovery",
                )
            user.email = address
    name = " ".join(filter(None, [remote.first_name, remote.last_name])).strip()
    if name:
        user.name = name
    if db.is_modified(user):
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                409, "Profile email conflicts with another account; request recovery"
            ) from None
    return user
