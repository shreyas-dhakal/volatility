import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from galvanise.config import settings
from galvanise.database import get_db
from galvanise.dependencies import get_current_user
from galvanise.integrations.github import account_token, api, repositories
from galvanise.models import Account, OAuthState, User, now
from galvanise.security import aware, digest, encrypt

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
@router.get("/github/start")
def github_start(request: Request, db: Session = Depends(get_db)):
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(503, "Configure GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET")
    if not settings.source_token_encryption_key:
        raise HTTPException(503, "Configure SOURCE_TOKEN_ENCRYPTION_KEY")
    user_id = get_current_user(request, db).id
    state = secrets.token_urlsafe(48)
    db.add(
        OAuthState(
            state_hash=digest(state),
            user_id=user_id,
            expires_at=now() + timedelta(minutes=10),
        )
    )
    db.commit()
    authorization_url = "https://github.com/login/oauth/authorize?" + urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_callback_url,
            "scope": "read:user user:email",
            "state": state,
        }
    )
    response = JSONResponse({"url": authorization_url})
    response.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.app_env not in ("development", "test"),
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
    target_user = row.user_id
    db.delete(row)
    db.commit()
    if not target_user or not db.get(User, target_user):
        raise HTTPException(400, "Start GitHub linking from your signed-in workspace")
    try:
        response = httpx.post(
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
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise ValueError()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "GitHub OAuth exchange failed")
    profile = api(token, "/user")
    account = db.scalar(select(Account).where(Account.github_id == str(profile["id"])))
    if account:
        if target_user and account.user_id != target_user:
            raise HTTPException(409, "GitHub account already linked")
        user = db.get(User, account.user_id)
        account.token_ciphertext = encrypt(token)
    else:
        user = db.get(User, target_user)
        if not user:
            raise HTTPException(400, "Sign in with Clerk before linking GitHub")
        if db.scalar(select(Account.id).where(Account.user_id == user.id)):
            raise HTTPException(409, "An account is already connected")
        db.add(
            Account(
                user_id=user.id,
                github_id=str(profile["id"]),
                token_ciphertext=encrypt(token),
            )
        )
    db.commit()
    result = RedirectResponse(settings.web_url)
    result.delete_cookie("oauth_state", path="/api/auth/github")
    return result


@router.get("/github/repos")
def repos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repositories(account_token(db, user.id))
