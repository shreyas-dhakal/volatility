import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from galvanise.config import settings
from galvanise.database import get_db
from galvanise.dependencies import get_current_user
from galvanise.integrations.github import account_token, api, repositories
from galvanise.models import Account, OAuthState, User, now
from galvanise.models import Session as AuthSession
from galvanise.security import aware, digest, encrypt, hasher, issue_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class Register(Login):
    name: str = Field(min_length=1, max_length=100)


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


@router.post("/register")
def register(body: Register, response: Response, db: Session = Depends(get_db)):
    if settings.auth_mode == "clerk":
        raise HTTPException(410, "Use Clerk sign-up")
    email = body.email.strip().lower()
    if "@" not in email or len(body.password) < 10:
        raise HTTPException(
            422, "Use a valid email and a password of at least 10 characters"
        )
    user = User(
        email=email, name=body.name.strip(), password_hash=hasher.hash(body.password)
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already registered")
    issue_session(db, user, response)
    return public_user(user, db)


@router.post("/login")
def login(body: Login, response: Response, db: Session = Depends(get_db)):
    if settings.auth_mode == "clerk":
        raise HTTPException(410, "Use Clerk sign-in")
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    try:
        if not user or not user.password_hash:
            raise VerificationError("invalid")
        hasher.verify(user.password_hash, body.password)
    except VerificationError:
        raise HTTPException(401, "Invalid email or password")
    issue_session(db, user, response)
    return public_user(user, db)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return public_user(user, db)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    db.execute(
        delete(AuthSession).where(
            AuthSession.token_hash == digest(request.cookies.get("session", ""))
        )
    )
    db.commit()
    response.delete_cookie("session", path="/")
    return {"status": "ok"}


@router.post("/github/start")
@router.get("/github/start")
def github_start(request: Request, db: Session = Depends(get_db)):
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(503, "Configure GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET")
    user_id = get_current_user(request, db).id if settings.auth_mode == "clerk" else None
    if settings.auth_mode == "legacy" and request.cookies.get("session"):
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
    authorization_url = (
        "https://github.com/login/oauth/authorize?"
        + urlencode(
            {
                "client_id": settings.github_client_id,
                "redirect_uri": settings.github_callback_url,
                "scope": "read:user user:email",
                "state": state,
            }
        )
    )
    response = JSONResponse({"url": authorization_url}) if settings.auth_mode == "clerk" else RedirectResponse(authorization_url)
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
    target_user = row.user_id
    db.delete(row)
    db.commit()
    if settings.auth_mode == "clerk" and (not target_user or not db.get(User, target_user)):
        raise HTTPException(400, "Start GitHub linking from your signed-in workspace")
    if settings.auth_mode == "legacy" and target_user and get_current_user(request, db).id != target_user:
        raise HTTPException(400, "Account linking session changed")
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
    emails = api(token, "/user/emails")
    account = db.scalar(select(Account).where(Account.github_id == str(profile["id"])))
    if account:
        if target_user and account.user_id != target_user:
            raise HTTPException(409, "GitHub account already linked")
        user = db.get(User, account.user_id)
        account.token_ciphertext = encrypt(token)
    else:
        user = db.get(User, target_user) if target_user else None
        if not user:
            email = next(
                (
                    e["email"].lower()
                    for e in emails
                    if e.get("verified") and e.get("primary")
                ),
                None,
            )
            if not email:
                raise HTTPException(400, "GitHub needs a verified primary email")
            if db.scalar(select(User.id).where(User.email == email)):
                raise HTTPException(
                    409, "Sign in to your existing account before linking GitHub"
                )
            user = User(email=email, name=profile.get("name") or profile["login"])
            db.add(user)
            db.flush()
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
    if settings.auth_mode == "legacy":
        issue_session(db, user, result)
    return result


@router.get("/github/repos")
def repos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return repositories(account_token(db, user.id))
