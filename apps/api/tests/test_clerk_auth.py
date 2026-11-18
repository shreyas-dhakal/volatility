"""Real SDK verification of locally signed tokens; no network or real users."""

import os

os.environ.update(
    APP_ENV="test",
    DATABASE_URL="sqlite://",
    AUTO_CREATE_TABLES="true",
)
import time
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select

from galvanise import clerk_identity
from galvanise.config import settings
from galvanise.database import Base, SessionLocal, engine
from galvanise.main import app
from galvanise.models import Account, Project, User
from galvanise.security import encrypt

PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = (
    PRIVATE.public_key()
    .public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    .decode()
)


def token(**changes):
    t = int(time.time())
    payload = {
        "iss": "https://test.clerk.accounts.dev",
        "sub": "user_owner",
        "sid": "sess_test",
        "azp": "http://localhost:3091",
        "iat": t,
        "nbf": t - 1,
        "exp": t + 60,
        "v": 2,
    }
    payload.update(changes)
    return jwt.encode(payload, PRIVATE, algorithm="RS256")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "clerk_issuer", "https://test.clerk.accounts.dev")
    monkeypatch.setattr(settings, "clerk_jwt_key", PUBLIC)
    monkeypatch.setattr(settings, "clerk_authorized_parties", ["http://localhost:3091"])
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    id="owner",
                    clerk_user_id="user_owner",
                    name="Owner",
                    email="owner@example.com",
                ),
                User(
                    id="other",
                    clerk_user_id="user_other",
                    name="Other",
                    email="other@example.com",
                ),
            ]
        )
        db.flush()
        db.add(Project(id="private", name="Private project", user_id="owner"))
        db.commit()

    class Provider:
        def get(self, subject):
            return NS(
                id=subject,
                external_id={"user_owner": "owner", "user_other": "other"}[subject],
                banned=False,
                locked=False,
                first_name="Owner" if subject == "user_owner" else "Other",
                last_name=None,
                primary_email_address_id="email_test",
                email_addresses=[
                    NS(
                        id="email_test",
                        email_address="owner@example.com"
                        if subject == "user_owner"
                        else "other@example.com",
                        verification=NS(status="verified"),
                    )
                ],
            )

    monkeypatch.setattr(clerk_identity, "provider", lambda: Provider())
    with TestClient(app) as c:
        yield c


def auth(c, **claims):
    c.headers["Authorization"] = "Bearer " + token(**claims)


def test_signed_token_maps_to_original_owner_and_preserves_404(client):
    auth(client)
    assert client.get("/api/auth/me").json()["id"] == "owner"
    assert client.get("/api/projects/private").status_code == 200
    auth(client, sub="user_other")
    assert client.get("/api/projects/private").status_code == 404


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": 1},
        {"nbf": int(time.time()) + 120},
        {"iat": int(time.time()) + 120},
        {"iss": "https://other.clerk.accounts.dev"},
        {"azp": "https://evil.example"},
        {"sid": None},
        {"sub": "machine_1"},
        {"exp": None},
    ],
)
def test_invalid_signed_tokens_cannot_access_api(client, claims):
    auth(client, **claims)
    assert client.get("/api/projects").status_code == 401


def test_tampered_and_machine_tokens_are_rejected(client):
    for value in ["bad", "ak_test_fake", "m2m_fake", token()[:-10] + "tamperedAA"]:
        client.headers["Authorization"] = "Bearer " + value
        assert client.get("/api/auth/me").status_code == 401


def test_cookie_alone_never_authenticates(client):
    client.cookies.set("session", "untrusted-cookie-value")
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/health").status_code == 200
    for route in [
        "/api/projects/private/conversations",
        "/api/projects/private/records",
        "/api/projects/private/sources",
        "/api/projects/private/jobs",
        "/api/projects/private/graphs",
        "/api/projects/private/design",
        "/api/auth/github/repos",
    ]:
        assert client.get(route).status_code == 401, route


def test_github_source_start_requires_bearer_and_returns_navigation_url(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "github_client_id", "synthetic-client")
    monkeypatch.setattr(settings, "github_client_secret", "synthetic-secret")
    assert client.get("/api/auth/github/start").status_code == 401
    auth(client)
    response = client.post("/api/auth/github/start")
    assert response.status_code == 200
    url = response.json()["url"]
    assert urlparse(url).netloc == "github.com"
    assert parse_qs(urlparse(url).query)["scope"] == ["read:user user:email"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_source_callback_links_without_issuing_session_or_changing_owner(
    client, monkeypatch
):
    from galvanise.routes import auth as routes

    monkeypatch.setattr(settings, "github_client_id", "synthetic-client")
    monkeypatch.setattr(settings, "github_client_secret", "synthetic-secret")
    auth(client)
    start = client.post("/api/auth/github/start")
    state = parse_qs(urlparse(start.json()["url"]).query)["state"][0]
    monkeypatch.setattr(
        routes.httpx,
        "post",
        lambda *a, **kw: NS(
            raise_for_status=lambda: None,
            json=lambda: {"access_token": "synthetic-source-token"},
        ),
    )
    monkeypatch.setattr(
        routes,
        "api",
        lambda t, path: {"id": 123, "login": "test"} if path == "/user" else [],
    )
    client.headers.pop("Authorization")
    response = client.get(
        "/api/auth/github/callback",
        params={"state": state, "code": "synthetic"},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert "session=" not in response.headers.get("set-cookie", "")
    with SessionLocal() as db:
        account = db.scalar(select(Account))
        assert account.user_id == "owner"
        assert len(db.scalars(select(User)).all()) == 2
    assert (
        client.get(
            "/api/auth/github/callback",
            params={"state": state, "code": "synthetic"},
            follow_redirects=False,
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/projects", {"name": "Unauthorized"}),
        (
            "/api/projects/private/conversations/missing/chat",
            {"content": "Unauthorized"},
        ),
        ("/api/projects/private/analyse", {}),
        ("/api/projects/private/design/generate", {"stage": "core"}),
        ("/api/projects/private/design/use-cases", {"title": "Unauthorized"}),
    ],
)
def test_direct_mutation_routes_require_clerk_before_processing(client, path, body):
    assert client.post(path, json=body).status_code == 401


def test_upload_requires_clerk_before_persisting_source(client):
    response = client.post(
        "/api/projects/private/documents",
        files={"file": ("synthetic.txt", b"synthetic", "text/plain")},
    )
    assert response.status_code == 401


def test_source_link_cannot_steal_another_owners_github_account(client, monkeypatch):
    from galvanise.routes import auth as routes

    monkeypatch.setattr(settings, "github_client_id", "synthetic-client")
    monkeypatch.setattr(settings, "github_client_secret", "synthetic-secret")
    with SessionLocal() as db:
        db.add(
            Account(
                user_id="other",
                github_id="123",
                token_ciphertext=encrypt("original-synthetic"),
            )
        )
        db.commit()
    auth(client)
    start = client.post("/api/auth/github/start")
    state = parse_qs(urlparse(start.json()["url"]).query)["state"][0]
    monkeypatch.setattr(
        routes.httpx,
        "post",
        lambda *a, **kw: NS(
            raise_for_status=lambda: None, json=lambda: {"access_token": "synthetic"}
        ),
    )
    monkeypatch.setattr(
        routes,
        "api",
        lambda t, path: {"id": 123, "login": "test"} if path == "/user" else [],
    )
    response = client.get(
        "/api/auth/github/callback",
        params={"state": state, "code": "synthetic"},
        follow_redirects=False,
    )
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(Account)).user_id == "other"
