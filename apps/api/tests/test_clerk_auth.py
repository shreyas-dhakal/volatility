"""Real SDK verification of locally signed tokens; no network or real users."""

import os

os.environ.update(
    APP_ENV="test",
    DATABASE_URL="sqlite://",
    AUTO_CREATE_TABLES="true",
)
import time
from types import SimpleNamespace as NS

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from galvanise import clerk_identity
from galvanise.config import settings
from galvanise.database import Base, SessionLocal, engine
from galvanise.main import app
from galvanise.models import Project, User

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


def test_verified_clerk_github_connection_is_scoped_to_its_owner(client, monkeypatch):
    from galvanise.integrations import github

    upstream = clerk_identity.provider()
    get = upstream.get
    account = NS(
        id="external_test",
        provider="oauth_github",
        provider_user_id="123",
        verification=NS(status="verified"),
    )

    def profile(subject):
        remote = get(subject)
        remote.external_accounts = [account] if subject == "user_owner" else []
        return remote

    monkeypatch.setattr(upstream, "get", profile)
    monkeypatch.setattr(clerk_identity, "provider", lambda: upstream)
    monkeypatch.setattr(github, "provider", lambda: upstream)
    monkeypatch.setattr(
        upstream,
        "github_tokens",
        lambda subject: (
            [NS(external_account_id=account.id, token="synthetic")]
            if subject == "user_owner"
            else []
        ),
        raising=False,
    )

    def list_repos(token, path, params):
        assert (
            token == "synthetic"
            and path == "/user/repos"
            and params["visibility"] == "all"
        )
        return [
            {"id": 51, "full_name": "owner/public", "private": False},
            {"id": 52, "full_name": "owner/private", "private": True},
        ]

    monkeypatch.setattr(github, "api", list_repos)
    auth(client)
    assert client.get("/api/auth/me").json()["github_connected"]
    assert [r["full_name"] for r in client.get("/api/auth/github/repos").json()] == [
        "owner/public",
        "owner/private",
    ]
    private_repo = {"full_name": "owner/private"}
    opened = client.post("/api/projects/github", json=private_repo)
    assert opened.status_code == 200
    project_id = opened.json()["id"]
    assert (
        client.post("/api/projects/github", json=private_repo).json()["id"]
        == project_id
    )
    assert len(client.get(f"/api/projects/{project_id}/jobs").json()) == 1
    assert (
        client.post(
            "/api/projects/github", json={"full_name": "outside/hidden"}
        ).status_code
        == 403
    )
    account.verification.status = "unverified"
    assert not client.get("/api/auth/me").json()["github_connected"]
    auth(client, sub="user_other")
    assert client.get("/api/auth/github/repos").status_code == 400


@pytest.mark.parametrize("shared_credentials", [True, False])
def test_public_repository_lookup_uses_the_verified_numeric_id(
    monkeypatch, shared_credentials
):
    import httpx
    from clerk_backend_api.models import SDKError
    from galvanise.integrations import github

    user = NS(
        clerk_user_id="user_owner",
        github_account=NS(id="external_test", provider_user_id="123"),
    )

    def github_tokens(subject):
        if shared_credentials:
            response = httpx.Response(
                403,
                json={
                    "errors": [
                        {
                            "code": "oauth_shared_credentials_stored_token_not_retrievable"
                        }
                    ]
                },
            )
            raise SDKError("Forbidden", response)
        return []

    monkeypatch.setattr(github, "provider", lambda: NS(github_tokens=github_tokens))

    def public_api(token, path, params=None):
        assert token is None
        if path == "/user/123":
            return {"login": "renamed"}
        assert path == "/users/renamed/repos"
        return [{"full_name": "renamed/public", "private": False}]

    monkeypatch.setattr(github, "api", public_api)
    assert github.repositories(user)[0]["full_name"] == "renamed/public"


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
