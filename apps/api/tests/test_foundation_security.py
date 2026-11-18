import os

os.environ.update(
    DATABASE_URL="sqlite://",
    APP_ENV="test",
    AUTH_SECRET="test-secret-that-is-at-least-32-characters",
    AUTO_CREATE_TABLES="true",
)
from datetime import timedelta
from fastapi.testclient import TestClient
from tests.auth_helpers import sign_in,sign_out
from sqlalchemy import select
from galvanise.main import app
from galvanise.database import Base, engine, SessionLocal
from galvanise.models import OAuthState, IngestionJob, now
from galvanise.config import settings
from galvanise.security import encrypt, decrypt, digest
from galvanise.services.ingestion import recover_jobs, extract
import pytest


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_oauth_state_rejects_missing_cookie_expired_and_replay():
    with TestClient(app) as c:
        with SessionLocal() as db:
            db.add(
                OAuthState(
                    state_hash=digest("state"), expires_at=now() - timedelta(seconds=1)
                )
            )
            db.commit()
        assert (
            c.get("/api/auth/github/callback?state=state&code=test").status_code == 400
        )
        c.cookies.set("oauth_state", "state")
        assert (
            c.get("/api/auth/github/callback?state=state&code=test").status_code == 400
        )


def test_redaction_and_encryption():
    value = "ghp_" + "a" * 30
    assert value not in encrypt(value)
    assert decrypt(encrypt(value)) == value
    assert value not in extract(("token " + value).encode(), "notes.md")
    assert "secret123" not in extract(b"api_key=secret123", "notes.txt")


def test_expanded_docx_rejected_before_parser():
    import io, zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"x" * 20_000_001)
    with pytest.raises(ValueError):
        extract(buf.getvalue(), "bad.docx")


def test_jobs_resume_after_restart_without_losing_payload():
    from galvanise.models import User, Project

    with SessionLocal() as db:
        u = User(email="job@example.com", name="A")
        db.add(u)
        db.flush()
        p = Project(name="P", user_id=u.id)
        db.add(p)
        db.flush()
        j = IngestionJob(
            project_id=p.id,
            kind="document",
            status="running",
            payload={"name": "a.txt"},
        )
        db.add(j)
        db.commit()
        jid = j.id
    recover_jobs()
    with SessionLocal() as db:
        assert db.get(IngestionJob, jid).status == "queued"


def test_bounded_extraction_runs_real_parser_in_child():
    from galvanise.services.ingestion import extract_bounded

    assert (
        extract_bounded(b"password=private\nhello", "hello.txt")
        == "password=[REDACTED]\nhello"
    )
    with pytest.raises(ValueError):
        extract_bounded(b"bad", "broken.pdf")


def test_oauth_requests_readonly_identity_scopes_and_hashes_state(monkeypatch):
    from urllib.parse import urlparse, parse_qs

    monkeypatch.setattr(settings, "github_client_id", "test-client")
    monkeypatch.setattr(settings, "github_client_secret", "test-secret")
    with TestClient(app) as c:
        sign_in(c)
        r = c.post("/api/auth/github/start")
        assert r.status_code == 200
        query = parse_qs(urlparse(r.json()["url"]).query)
        assert set(query["scope"][0].split()) == {"read:user", "user:email"}
        state = query["state"][0]
        with SessionLocal() as db:
            row = db.scalar(select(OAuthState))
            assert row.state_hash == digest(state) and row.state_hash != state
        assert "HttpOnly" in r.headers["set-cookie"]


def test_upload_limit_and_foreign_project_routes(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    with TestClient(app) as c:
        sign_in(c,"a@example.com")
        p = c.post("/api/projects", json={"name": "P"}).json()
        path = f"/api/projects/{p['id']}"
        assert (
            c.post(
                path + "/documents", files={"file": ("large.txt", b"x" * 11)}
            ).status_code
            == 413
        )
        sign_out(c)
        sign_in(c,"b@example.com")
        for suffix in ("/sources", "/documents", "/jobs", "/records", "/conversations"):
            assert c.get(path + suffix).status_code == 404
        assert (
            c.post(
                path + "/documents", files={"file": ("small.txt", b"text")}
            ).status_code
            == 404
        )


def test_github_source_link_uses_existing_owner_and_consumes_state(monkeypatch):
    from galvanise.routes import auth
    from types import SimpleNamespace
    from galvanise.models import User
    from urllib.parse import urlparse, parse_qs

    monkeypatch.setattr(settings, "github_client_id", "test-client")
    monkeypatch.setattr(settings, "github_client_secret", "test-secret")
    monkeypatch.setattr(
        auth.httpx,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"access_token": "sensitive-token"},
        ),
    )
    monkeypatch.setattr(
        auth,
        "api",
        lambda token, path: (
            {"id": 99, "login": "github-user"}
            if path == "/user"
            else [{"email": "existing@example.com", "primary": True, "verified": True}]
        ),
    )
    with SessionLocal() as db:
        db.add(User(email="existing@example.com", name="Local user"))
        db.commit()
    with TestClient(app) as c:
        sign_in(c,"existing@example.com")
        start = c.post("/api/auth/github/start")
        state = parse_qs(urlparse(start.json()["url"]).query)["state"][0]
        r = c.get("/api/auth/github/callback", params={"state": state, "code": "test"},follow_redirects=False)
        assert r.status_code == 307
        assert "sensitive-token" not in r.text
        assert "session=" not in r.headers.get("set-cookie", "")
        with SessionLocal() as db: assert len(db.scalars(select(User)).all())==1
        assert (
            c.get(
                "/api/auth/github/callback", params={"state": state, "code": "test"}
            ).status_code
            == 400
        )
        assert c.get("/api/auth/me").status_code == 200
