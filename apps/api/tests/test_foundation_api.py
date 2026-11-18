import os

os.environ.update(
    DATABASE_URL="sqlite://",
    APP_ENV="test",
    AUTH_SECRET="test-secret-that-is-at-least-32-characters",
    AUTO_CREATE_TABLES="true",
)
from fastapi.testclient import TestClient
from tests.auth_helpers import sign_in,sign_out
from galvanise.main import app
from galvanise.database import Base, engine, SessionLocal
from galvanise.models import KnowledgeRecord, IngestionJob
from galvanise.services.ingestion import process_next_job


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def signup(c, email="owner@example.com"):
    sign_in(c,email)


def project(c):
    return c.post(
        "/api/projects",
        json={
            "name": "ERP",
            "description": "Legacy",
            "system_type": "existing",
            "objective": "Improve",
        },
    ).json()


def test_auth_ownership_sessions_and_origins():
    with TestClient(app) as c:
        signup(c)
        p = project(c)
        assert c.get("/api/auth/me").status_code == 200
        assert (
            c.post(
                "/api/projects",
                headers={"Origin": "https://evil.test"},
                json={"name": "bad"},
            ).status_code
            == 403
        )
        sign_out(c)
        assert c.get("/api/auth/me").status_code == 401
        signup(c, "other@example.com")
        assert c.get("/api/projects/" + p["id"]).status_code == 404



def test_review_is_versioned_and_stale_updates_rejected():
    with TestClient(app) as c:
        signup(c)
        p = project(c)
        with SessionLocal() as db:
            r = KnowledgeRecord(
                project_id=p["id"], kind="decision", title="Old", description="Reason"
            )
            db.add(r)
            db.commit()
            rid = r.id
        path = f"/api/projects/{p['id']}/records/{rid}"
        r = c.patch(
            path, json={"expected_version": 1, "status": "approved", "title": "New"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 2
        assert r.json()["history"][0]["title"] == "Old"
        assert (
            c.patch(
                path, json={"expected_version": 1, "status": "rejected"}
            ).status_code
            == 409
        )


def test_upload_is_durable_bounded_and_redacted():
    with TestClient(app) as c:
        signup(c)
        p = project(c)
        r = c.post(
            f"/api/projects/{p['id']}/documents",
            files={
                "file": (
                    "notes.txt",
                    b"password=supersecret\nSupplier needs",
                    "text/plain",
                )
            },
        )
        assert r.status_code == 200, r.text
        assert "supersecret" not in str(r.json())
        process_next_job()
        docs = c.get(f"/api/projects/{p['id']}/documents").json()
        assert docs
        doc = c.get(f"/api/projects/{p['id']}/documents/{docs[0]['id']}").json()
        assert "supersecret" not in doc["content"]
        assert (
            c.post(
                f"/api/projects/{p['id']}/documents",
                files={"file": ("script.exe", b"bad")},
            ).status_code
            == 415
        )
