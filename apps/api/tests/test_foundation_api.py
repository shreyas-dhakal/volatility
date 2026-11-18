import os

os.environ.update(
    DATABASE_URL="sqlite://",
    APP_ENV="test",
    SOURCE_TOKEN_ENCRYPTION_KEY="test-source-token-encryption-key",
    AUTO_CREATE_TABLES="true",
)
from fastapi.testclient import TestClient
from galvanise.main import app
from galvanise.database import Base, engine, SessionLocal
from galvanise.models import KnowledgeRecord, IngestionJob
from galvanise.services.ingestion import process_next_job
from auth_helpers import authenticate_as, sign_out_test_user


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def authenticate(c, email="owner@example.com"):
    return authenticate_as(c, email, "Owner")


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


def test_clerk_identity_ownership_and_origins():
    with TestClient(app) as c:
        authenticate(c)
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
        sign_out_test_user(c)
        assert c.get("/api/auth/me").status_code == 401
        authenticate(c, "other@example.com")
        assert c.get("/api/projects/" + p["id"]).status_code == 404



def test_review_is_versioned_and_stale_updates_rejected():
    with TestClient(app) as c:
        authenticate(c)
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
        authenticate(c)
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


def test_removing_a_repository_is_project_scoped_and_keeps_design_evidence():
    from sqlalchemy import select

    from galvanise.design_engine.sources import store_document
    from galvanise.models import (
        ConnectedSource,
        DesignChunk,
        SourceDocument,
        TechnicalGraph,
    )

    with TestClient(app) as owner, TestClient(app) as outsider:
        authenticate(owner)
        authenticate(outsider, "other@example.com")
        pid = project(owner)["id"]
        other_project = project(owner)["id"]
        with SessionLocal() as db:
            src = ConnectedSource(project_id=pid, kind="github", name="example/parking")
            other = ConnectedSource(
                project_id=pid, kind="github", name="example/second"
            )
            db.add_all([src, other])
            db.flush()
            kept = SourceDocument(project_id=pid, name="brief.md", content="Exit brief")
            doc = SourceDocument(
                project_id=pid, source_id=src.id, name="fee.py", content="rate = 5"
            )
            graph = TechnicalGraph(
                project_id=pid, source_id=src.id, name="Parking index"
            )
            jobs = [
                IngestionJob(project_id=pid, kind="github", payload={"source_id": s.id})
                for s in (src, other)
            ]
            db.add_all([doc, kept, graph, *jobs])
            db.flush()
            store_document(db, doc)
            db.commit()
            chunk_id = db.scalar(select(DesignChunk.id))
            sid, other_id, kept_id, job_id = src.id, other.id, kept.id, jobs[1].id

        base = f"/api/projects/{pid}"
        path = f"{base}/sources/github/{sid}"
        assert outsider.delete(path).status_code == 404
        assert (
            owner.delete(
                f"/api/projects/{other_project}/sources/github/{sid}"
            ).status_code
            == 404
        )
        assert owner.delete(path).status_code == 204
        assert [s["id"] for s in owner.get(base + "/sources").json()] == [other_id]
        assert [d["id"] for d in owner.get(base + "/documents").json()] == [kept_id]
        assert owner.get(base + "/graphs").json() == []
        assert [j["id"] for j in owner.get(base + "/jobs").json()] == [job_id]
        assert (
            owner.get(base + "/design-engine/chunks/" + chunk_id).json()["text"]
            == "rate = 5"
        )
        assert owner.delete(path).status_code == 404


def test_removed_running_import_cannot_publish_files(monkeypatch):
    from galvanise.models import ConnectedSource, SourceDocument
    from galvanise.services import ingestion

    with TestClient(app) as client:
        authenticate(client)
        pid = project(client)["id"]
        base = f"/api/projects/{pid}"
        with SessionLocal() as db:
            src = ConnectedSource(project_id=pid, kind="github", name="example/busy")
            db.add(src)
            db.flush()
            sid = src.id
            db.add(
                IngestionJob(project_id=pid, kind="github", payload={"source_id": sid})
            )
            db.commit()

        def remove_while_indexing(db, job):
            assert job.status == "running"
            db.add(
                SourceDocument(
                    project_id=pid, source_id=sid, name="late.py", content="pass"
                )
            )
            assert client.delete(f"{base}/sources/github/{sid}").status_code == 204

        monkeypatch.setattr(ingestion, "ingest_repository", remove_while_indexing)
        assert process_next_job()
        for endpoint in ("sources", "documents", "jobs"):
            assert client.get(f"{base}/{endpoint}").json() == []


def test_build_and_reopen_repository_code_map():
    from galvanise.models import ConnectedSource, SourceDocument

    with TestClient(app) as client:
        authenticate(client)
        pid = project(client)["id"]
        base = f"/api/projects/{pid}"
        with SessionLocal() as db:
            repo = ConnectedSource(project_id=pid, kind="github", name="shop/cart", status="ready")
            db.add(repo)
            db.flush()
            sid = repo.id
            db.add_all([
                SourceDocument(project_id=pid, source_id=sid, name="shop/price.py",
                               content="def price():\n    return 10\n"),
                SourceDocument(project_id=pid, source_id=sid, name="shop/cart.py",
                               content="from .price import price\ndef total():\n    return price()\n"),
            ])
            db.commit()
        path = base + "/sources/github/" + sid + "/graph"
        assert client.get(base + "/graphs").json() == []
        job = client.post(path).json()
        assert client.post(path).json()["id"] == job["id"]
        assert process_next_job()
        assert client.get(base + "/jobs").json()[0]["status"] == "completed"
        graph, = client.get(base + "/graphs").json()
        assert client.post(path).json() == {"graph_id": graph["id"]}
        graph_path = base + "/graphs/" + graph["id"]
        assert client.get(graph_path).json()["edges"]
        export = client.get(graph_path + "/export").json()
        assert any(n.get("source_file") == "shop/cart.py" for n in export["nodes"])
        assert any(e["relation"] == "calls" for e in export["links"])
        authenticate(client, "outsider@example.com")
        assert client.get(graph_path + "/export").status_code == 404
        assert client.post(path).status_code == 404


def test_failed_map_build_leaves_repository_ready_for_retry():
    from galvanise.models import ConnectedSource

    with TestClient(app) as client:
        authenticate(client)
        pid = project(client)["id"]
        base = f"/api/projects/{pid}"
        with SessionLocal() as db:
            repo = ConnectedSource(project_id=pid, kind="github", name="empty/repo", status="ready")
            db.add(repo)
            db.commit()
            path = f"{base}/sources/github/{repo.id}/graph"
        job = client.post(path).json()
        assert process_next_job()
        failed, = client.get(base + "/jobs").json()
        assert failed["status"] == "failed"
        assert "no supported code" in failed["error"]
        assert client.get(base + "/sources").json()[0]["status"] == "ready"
        assert client.get(base + "/graphs").json() == []
        assert job["id"] != client.post(path).json()["id"]


def test_empty_repository_can_be_checked_again_after_first_commit(monkeypatch):
    import httpx
    from galvanise.integrations import github
    from galvanise.services import ingestion
    from galvanise.models import User, ConnectedSource
    from sqlalchemy import select

    empty = True

    def github_get(url, **kwargs):
        if "/git/trees/" in url:
            status, body = ((409, {"message": "Git Repository is empty."}) if empty
                            else (200, {"sha": "tree", "tree": [{"type": "blob", "path": "code.py", "sha": "blob", "size": 4}]}))
        elif "/git/blobs/" in url:
            status, body = 200, {"content": "cGFzcw=="}
        else:
            status, body = 200, {"id": 1, "default_branch": "main"}
        return httpx.Response(status, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(github.httpx, "get", github_get)
    monkeypatch.setattr(ingestion, "resolve_user", lambda db, subject: None)
    monkeypatch.setattr(ingestion, "account_token", lambda user: None)
    with TestClient(app) as client:
        authenticate(client)
        pid = project(client)["id"]
        base = f"/api/projects/{pid}"
        with SessionLocal() as db:
            src = ConnectedSource(project_id=pid, kind="github", name="test/empty", status="failed")
            db.add(src)
            db.flush()
            db.add(IngestionJob(project_id=pid, kind="github", status="failed", payload={
                "user_id": db.scalar(select(User.id)), "repository_id": 1, "full_name": src.name, "source_id": src.id,
            }))
            db.commit()
            path = f"{base}/sources/github/{src.id}/retry"
        assert client.post(path).json()["status"] == "queued"
        assert process_next_job()
        assert client.get(base + "/sources").json()[0]["status"] == "empty"
        assert client.get(base + "/jobs").json()[0]["error"] is None
        assert client.get(base + "/graphs").json() == []
        empty = False
        assert client.post(path).json()["status"] == "queued"
        assert process_next_job()
        assert client.get(base + "/sources").json()[0]["status"] == "ready"
        assert len(client.get(base + "/documents").json()) == 1
        assert client.post(path).status_code == 409
