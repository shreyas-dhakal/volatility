"""Source credential protection, OAuth state and bounded intake security."""

import io
import zipfile

import pytest
from auth_helpers import authenticate_as
from fastapi.testclient import TestClient

from galvanise.config import settings
from galvanise.database import Base, SessionLocal, engine
from galvanise.main import app
from galvanise.models import IngestionJob, Project, User
from galvanise.security import decrypt, encrypt
from galvanise.services.ingestion import extract, extract_bounded, recover_jobs


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_source_tokens_are_encrypted_and_extracted_secrets_are_redacted():
    value = "ghp_" + "a" * 30
    assert value not in encrypt(value)
    assert decrypt(encrypt(value)) == value
    assert value not in extract(("token " + value).encode(), "notes.md")
    assert "secret123" not in extract(b"api_key=secret123", "notes.txt")


def test_expanded_docx_is_rejected_before_parser():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"x" * 20_000_001)
    with pytest.raises(ValueError):
        extract(buffer.getvalue(), "bad.docx")


def test_running_ingestion_jobs_resume_after_restart():
    with SessionLocal() as db:
        user = User(email="job@example.com", name="A", clerk_user_id="user_job")
        db.add(user)
        db.flush()
        project = Project(name="P", user_id=user.id)
        db.add(project)
        db.flush()
        job = IngestionJob(
            project_id=project.id,
            kind="document",
            status="running",
            payload={"name": "a.txt"},
        )
        db.add(job)
        db.commit()
        job_id = job.id
    recover_jobs()
    with SessionLocal() as db:
        assert db.get(IngestionJob, job_id).status == "queued"


def test_bounded_extraction_redacts_and_rejects_invalid_documents():
    assert (
        extract_bounded(b"password=private\nhello", "hello.txt")
        == "password=[REDACTED]\nhello"
    )
    with pytest.raises(ValueError):
        extract_bounded(b"bad", "broken.pdf")


def test_upload_limit_and_cross_owner_routes(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    with TestClient(app) as client:
        authenticate_as(client, "owner@example.test", "Owner")
        project = client.post("/api/projects", json={"name": "P"}).json()
        path = f"/api/projects/{project['id']}"
        assert (
            client.post(
                path + "/documents", files={"file": ("large.txt", b"x" * 11)}
            ).status_code
            == 413
        )
        authenticate_as(client, "outsider@example.test", "Outsider")
        for suffix in ("/sources", "/documents", "/jobs", "/records", "/conversations"):
            assert client.get(path + suffix).status_code == 404
        assert (
            client.post(
                path + "/documents", files={"file": ("small.txt", b"text")}
            ).status_code
            == 404
        )
