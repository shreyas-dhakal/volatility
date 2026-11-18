"""Application profile and separately authorized GitHub source connections."""

import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from galvanise.config import settings
from galvanise.database import get_db
from galvanise.dependencies import get_current_user
from galvanise.integrations.github import account_token, api, repositories
from galvanise.models import Account, OAuthState, User, now
from galvanise.security import aware, digest, encrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/auth", tags=["auth"])


def public_user(user, db):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "github_connected": db.scalar(
            select(Account.id).where(Account.user_id == user.id)
        )
        is not None,
    }


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return public_user(user, db)


@router.post("/github/start")
def github_start(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(503, "Configure GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET")
    state = secrets.token_urlsafe(48)
    db.add(
        OAuthState(
            state_hash=digest(state),
            user_id=user.id,
            expires_at=now() + timedelta(minutes=10),
        )
    )
    db.commit()
    url = "https://github.com/login/oauth/authorize?" + urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_callback_url,
            "scope": "read:user user:email",
            "state": state,
        }
    )
    response = JSONResponse({"url": url})
    response.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/auth/github",
    )
    return response


@router.get("/github/callback")
def github_callback(
    request: Request, code: str = "", state: str = "", db: Session = Depends(get_db)
):
    row = (
        db.scalar(
            select(OAuthState)
            .where(OAuthState.state_hash == digest(state))
            .with_for_update()
        )
        if state
        else None
    )
    if (
        not row
        or not secrets.compare_digest(request.cookies.get("oauth_state", ""), state)
        or aware(row.expires_at) <= now()
    ):
        raise HTTPException(400, "Invalid or expired OAuth state")
    owner = db.get(User, row.user_id) if row.user_id else None
    db.delete(row)
    db.commit()
    if not owner or not owner.clerk_user_id:
        raise HTTPException(400, "Start GitHub linking from your signed-in workspace")
    # The single-use state/cookie capability was created under Clerk authentication.
    # A provider redirect cannot send a bearer header; it may only link this owner.
    try:
        exchange = httpx.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_callback_url,
            },
            headers={"Accept": "application/json"},
            timeout=25,
        )
        exchange.raise_for_status()
        token = exchange.json().get("access_token")
        if not token:
            raise ValueError()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "GitHub OAuth exchange failed") from None
    profile = api(token, "/user")
    account = db.scalar(select(Account).where(Account.github_id == str(profile["id"])))
    if account:
        if account.user_id != owner.id:
            raise HTTPException(409, "GitHub account already linked")
        account.token_ciphertext = encrypt(token)
    else:
        if db.scalar(select(Account.id).where(Account.user_id == owner.id)):
            raise HTTPException(409, "An account is already connected")
        db.add(
            Account(
                user_id=owner.id,
                github_id=str(profile["id"]),
                token_ciphertext=encrypt(token),
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "GitHub account already linked") from None
    response = RedirectResponse(settings.web_url)
    response.delete_cookie("oauth_state", path="/api/auth/github")
    return response


@router.get("/github/repos")
def repos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repositories(account_token(db, user.id))
