"""Exercise the API, persistence and worker using separate database connections."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import sessionmaker

from galvanise.database import Base, get_db
from galvanise.design_engine import service, worker
from galvanise.main import app
from galvanise.models import (
    DesignPlan,
    DesignRevision,
    DesignRun,
    Message,
    now,
)
from galvanise.services import ingestion


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'runs.db'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def pragmas(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    def connection():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = connection
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(ingestion, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "generate", generate)
    try:
        with TestClient(app) as client:
            register(client)
            yield client, project(client), sessions
    finally:
        del app.dependency_overrides[get_db]
        engine.dispose()


def register(client, email="owner@example.org"):
    result = client.post(
        "/api/auth/register",
        json={"email": email, "password": "sample-password-123", "name": "Owner"},
    )
    assert result.status_code == 200, result.text


def project(client):
    response = client.post(
        "/api/projects", json={"name": "Parking", "objective": "Allow exit"}
    )
    assert response.status_code == 200, response.text
    return f"/api/projects/{response.json()['id']}/design-engine"


def analyze(client, url, key="analysis", **request):
    response = client.post(url + "/analyze", json={"idempotency_key": key, **request})
    assert response.status_code == 202, response.text
    return response.json()


def add_message(client, url, sessions, text, role="user", conversation=None):
    root = url.removesuffix("/design-engine")
    if not conversation:
        conversation = client.post(
            root + "/conversations", json={"title": "Design"}
        ).json()["id"]
    with sessions() as db:
        msg = Message(
            project_id=root.rsplit("/", 1)[1],
            role=role,
            conversation_id=conversation,
            content=text,
        )
        db.add(msg)
        db.commit()
        return msg.id, conversation


async def generate(
    *, chunks, manifest, base, correction, start_stage, checkpoint, save_checkpoint
):
    actor = {"id": "driver", "name": "Driver"}
    return {
        "actors": [actor],
        "volatilities": [
            {
                "id": "tariff",
                "decision": correction["text"] if correction else "Site tariff",
            }
        ],
        "manifest": manifest,
        "sample_citation": chunks[0]["id"],
    }


def test_queue_freezes_extracted_uploads_and_authorized_chat_context(api):
    client, url, sessions = api
    root = url.removesuffix("/design-engine")
    upload = client.post(
        root + "/documents",
        files={"file": ("src/gate.py", b"def open_gate():\n    pass\n")},
    ).json()
    first, conversation = add_message(client, url, sessions, "A gate must allow exit")
    assistant, _ = add_message(
        client, url, sessions, "Unverified", "assistant", conversation
    )
    request, _ = add_message(
        client, url, sessions, "Design this system", conversation=conversation
    )
    later, _ = add_message(
        client, url, sessions, "A later turn", conversation=conversation
    )
    assert client.get(url).json() == {"revision": None, "plan": None, "run": None}
    body = {"selected_upload_ids": [upload["id"]], "request_message_id": request}
    run = analyze(client, url, **body)
    assert not worker.process_next_run()  # extraction is still queued
    assert ingestion.process_next_job()
    assert analyze(client, url, **body)["id"] == run["id"]
    assert (
        client.post(url + "/analyze", json={"idempotency_key": "analysis"}).status_code
        == 409
    )
    assert worker.process_next_run()
    view = client.get(url).json()
    assert view["run"]["status"] == "completed", view
    published = view["revision"]
    entries = published["snapshot"]["manifest"]
    assert {
        entry["message_id"] for entry in entries if entry.get("kind") == "message"
    } == {first, request}
    assert assistant not in str(entries) and later not in str(entries)
    assert any(e.get("section") == "objective" for e in entries)
    c = client.get(url + "/chunks/" + published["snapshot"]["sample_citation"]).json()
    assert c["locator"]["path"] == "src/gate.py" and c["locator"]["line_end"] == 2
    assert c["text"] == "def open_gate():\n    pass\n"
    assert analyze(client, url, **body)["revision_id"] == published["id"]
    assert client.get(url + "/revisions/" + published["id"]).json() == published
    analyze(client, url, key="again", **body)
    assert worker.process_next_run()
    assert client.get(url).json()["revision"]["snapshot"]["sample_citation"] == c["id"]


def test_scope_checks_include_messages_chunks_runs_and_plan_inputs(api):
    client, url, sessions = api
    run = analyze(client, url)
    assert worker.process_next_run()
    rev = client.get(url).json()["revision"]
    chunk = rev["snapshot"]["sample_citation"]
    msg, _ = add_message(client, url, sessions, "New goal")
    assistant, _ = add_message(client, url, sessions, "Fabricated", role="assistant")
    assert (
        client.post(
            url + "/revise",
            json={
                "base_revision_id": rev["id"],
                "idempotency_key": "no",
                "correction_message_id": assistant,
            },
        ).status_code
        == 404
    )
    with TestClient(app) as other:
        register(other, "other@example.org")
        second = project(other)
        assert other.get(url).status_code == 404
        assert other.get(second + "/chunks/" + chunk).status_code == 404
        assert other.get(second + "/revisions/" + rev["id"]).status_code == 404
        assert other.post(second + "/runs/" + run["id"] + "/retry").status_code == 404
        assert (
            other.post(
                second + "/analyze",
                json={"idempotency_key": "x", "request_message_id": msg},
            ).status_code
            == 404
        )
        upload = client.post(
            url.removesuffix("/design-engine") + "/documents",
            files={"file": ("one.txt", b"secret")},
        ).json()
        assert (
            other.post(
                second + "/analyze",
                json={"idempotency_key": "x", "selected_upload_ids": [upload["id"]]},
            ).status_code
            == 404
        )
        assert (
            other.post(
                second + "/plan", json={"revision_id": rev["id"], "planning_inputs": {}}
            ).status_code
            == 404
        )


def test_failed_repair_preserves_head_and_retry_keeps_checkpoint_and_diagnostics(
    api, monkeypatch
):
    client, url, sessions = api
    analyze(client, url)
    worker.process_next_run()
    old = client.get(url).json()["revision"]
    msg, _ = add_message(client, url, sessions, "All sites will use one tariff")
    body = {
        "base_revision_id": old["id"],
        "correction_message_id": msg,
        "idempotency_key": "correct",
    }
    run = client.post(url + "/revise", json=body).json()
    assert run["stage"] == "volatility"
    ckpt = {"completed_stage": "volatility", "snapshot": {"saved": True}}

    async def fail(**arguments):
        assert arguments["correction"]["chunk_id"] in {
            c["id"] for c in arguments["chunks"]
        }
        arguments["save_checkpoint"]("volatility", ckpt)
        raise ValueError(
            "boundaries failed validation after one repair: unknown operation and fabricated citation"
        )

    monkeypatch.setattr(worker, "generate", fail)
    worker.process_next_run()
    failed = client.get(url).json()
    assert failed["revision"] == old and failed["run"]["status"] == "failed"
    assert (
        failed["run"]["stage"] == "boundaries"
        and "fabricated citation" in failed["run"]["error"]
    )

    async def resume(**arguments):
        assert arguments["checkpoint"] == ckpt
        return await generate(**arguments)

    monkeypatch.setattr(worker, "generate", resume)
    retried = client.post(url + "/runs/" + run["id"] + "/retry").json()
    assert retried["id"] == run["id"] and retried["status"] == "queued"
    worker.process_next_run()
    view = client.get(url).json()
    assert view["run"]["status"] == "completed" and len(view["run"]["diagnostics"]) == 1
    new = view["revision"]
    assert (
        new["parent_revision_id"] == old["id"]
        and new["snapshot"]["actors"] == old["snapshot"]["actors"]
    )
    assert (
        new["diff"]["changed"][0]["id"] == "tariff"
        and "one tariff" in new["diff"]["changed"][0]["reason"]
    )
    assert client.get(url + "/revisions/" + old["id"]).json() == old
    assert client.post(url + "/revise", json=body).json()["id"] == run["id"]
    assert (
        client.post(
            url + "/revise", json={**body, "idempotency_key": "another"}
        ).status_code
        == 409
    )

    def planner(snapshot, inputs):
        assert snapshot == old["snapshot"]
        inputs["extra"] = True  # ensure the persisted request remains exact
        return {"estimated": True}

    monkeypatch.setattr(service, "calculate_plan", planner)
    result = client.post(
        url + "/plan", json={"revision_id": old["id"], "planning_inputs": {"effort": 4}}
    ).json()
    assert result["revision_id"] == old["id"] and result["input"] == {"effort": 4}
    with sessions() as db:
        stored = db.get(DesignPlan, result["id"])
        assert stored.revision_id == old["id"] and stored.input_json == {"effort": 4}
    assert client.get(url).json()["plan"] is None
    monkeypatch.setattr(service, "calculate_plan", lambda *_: {"missing": ["effort"]})
    current_plan = client.post(
        url + "/plan", json={"revision_id": new["id"], "planning_inputs": {}}
    ).json()
    assert client.get(url).json()["plan"] == current_plan


def test_expired_claim_resumes_same_run_and_fences_old_worker(api):
    client, url, sessions = api
    run = analyze(client, url)
    old = worker.claim()
    assert worker.claim() is None
    args = worker.prepare(*old)
    worker.save(*old, "inventory", {"saved": "inventory"})
    with sessions() as db:
        db.execute(
            update(DesignRun)
            .where(DesignRun.id == run["id"])
            .values(lease_until=now() - timedelta(seconds=1))
        )
        db.commit()
    new = worker.claim()
    assert old[0] == new[0] and old[1] != new[1]
    assert worker.prepare(*new)["checkpoint"] == {"saved": "inventory"}
    with pytest.raises(worker.LostClaim):
        worker.save(*old, "boundaries", {"wrong": True})
    with pytest.raises(worker.LostClaim):
        worker.publish(*old, {}, args)
    with pytest.raises(worker.LostClaim):
        worker.record_failure(*old, "failed", "discarded claim")
    asyncio.run(worker.execute(*new))
    assert client.get(url).json()["run"]["status"] == "completed"


@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_publish_compare_and_swap_and_stale_rerun(
    api, monkeypatch, existing
):
    client, url, sessions = api
    if existing:
        analyze(client, url)
        worker.process_next_run()
    history = client.get(url).json()["revision"]
    for key in ("one", "two"):
        analyze(client, url, key)
    rendezvous = Barrier(2)

    async def parallel(**args):
        rendezvous.wait(timeout=10)
        return await generate(**args)

    monkeypatch.setattr(worker, "generate", parallel)
    claims = [worker.claim(), worker.claim()]
    with ThreadPoolExecutor(2) as pool:
        results = [pool.submit(asyncio.run, worker.execute(*c)) for c in claims]
        for result in results:
            result.result(timeout=20)
    with sessions() as db:
        pair = list(
            db.scalars(select(DesignRun).where(DesignRun.id.in_(c[0] for c in claims)))
        )
        assert sorted(r.status for r in pair) == ["completed", "stale"]
        stale = next(r for r in pair if r.status == "stale")
        count = db.scalar(select(func.count()).select_from(DesignRevision))
        assert count == (2 if existing else 1)
    winner = client.get(url).json()["revision"]
    assert winner["parent_revision_id"] == (history["id"] if existing else None)
    retry = client.post(url + "/runs/" + stale.id + "/retry").json()
    assert retry["id"] != stale.id and retry["base_revision_id"] == winner["id"]
    monkeypatch.setattr(worker, "generate", generate)
    assert worker.process_next_run()
    assert client.get(url).json()["revision"]["parent_revision_id"] == winner["id"]


def test_concurrent_duplicate_request_is_one_run(api):
    client, url, sessions = api
    rendezvous = Barrier(4)

    def send():
        rendezvous.wait(timeout=10)
        return analyze(client, url)["id"]

    with ThreadPoolExecutor(4) as pool:
        ids = [f.result(timeout=20) for f in [pool.submit(send) for _ in range(4)]]
    assert len(set(ids)) == 1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DesignRun)) == 1


@pytest.mark.parametrize(
    ("text", "stage"),
    [
        ("The business goal is different", "use_cases"),
        ("All sites use one tariff", "volatility"),
        ("Change the contract input", "boundaries"),
        ("Change the goal and policy", "use_cases"),
    ],
)
def test_correction_stage(text, stage):
    assert service.correction_stage(text) == stage


def test_narrower_selection_excludes_prior_uploads_from_model_context(api, monkeypatch):
    client, url, _sessions = api
    root = url.removesuffix("/design-engine")
    ids = []
    for name in ("first.txt", "second.txt"):
        ids.append(
            client.post(
                root + "/documents", files={"file": (name, name.encode())}
            ).json()["id"]
        )
        assert ingestion.process_next_job()
    analyze(client, url)
    assert worker.process_next_run()
    old = client.get(url).json()["revision"]

    async def narrowed(**arguments):
        assert arguments["base"] is None
        assert "first.txt" not in str(arguments["chunks"])
        return await generate(**arguments)

    monkeypatch.setattr(worker, "generate", narrowed)
    analyze(client, url, "narrower", selected_upload_ids=ids[1:])
    assert worker.process_next_run()
    view = client.get(url).json()
    assert view["run"]["status"] == "completed", view
    assert view["revision"]["parent_revision_id"] == old["id"]


def test_provider_and_sql_exceptions_do_not_store_secret_parameters():
    import httpx
    from openai import BadRequestError
    from sqlalchemy.exc import StatementError

    response = httpx.Response(400, request=httpx.Request("POST", "https://example.org"))
    provider = BadRequestError(
        "private response text", response=response, body={"detail": "private"}
    )
    database = StatementError(
        "statement failed", "UPDATE ..", {"secret": "private"}, ValueError()
    )
    assert (
        worker.failure_message(provider)
        == "BadRequestError: Model service returned HTTP 400."
    )
    assert (
        worker.failure_message(database) == "StatementError: Design persistence failed."
    )
    assert worker.failure_message(ValueError("fabricated citation")).endswith(
        "fabricated citation"
    )


def test_long_correction_is_a_single_citable_utterance(api, monkeypatch):
    client, url, sessions = api
    analyze(client, url)
    worker.process_next_run()
    old = client.get(url).json()["revision"]
    text = (
        "The original policy had several variants. " * 260
        + "All sites will now use one tariff."
    )
    assert 4800 < len(text) <= 12000
    msg, _ = add_message(client, url, sessions, text)
    run = client.post(
        url + "/revise",
        json={
            "base_revision_id": old["id"],
            "correction_message_id": msg,
            "idempotency_key": "full correction",
        },
    ).json()
    captured = {}

    async def record(**args):
        captured.update(args["correction"])
        return await generate(**args)

    monkeypatch.setattr(worker, "generate", record)
    assert worker.process_next_run()
    assert client.get(url).json()["run"]["id"] == run["id"]
    assert captured["text"] == text
    chunk = client.get(url + "/chunks/" + captured["chunk_id"]).json()
    assert chunk["text"] == text and chunk["locator"]["message_id"] == msg


def test_archived_pdf_pages_and_manifest_of_unreadable_and_unsupported_members(
    api, monkeypatch
):
    from io import BytesIO
    from zipfile import ZipFile

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    pdf = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for label in ("First page", "", "Third page"):
        page = pdf.add_blank_page(width=200, height=200)
        if label:
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 10 100 Td ({label}) Tj ET".encode())
            page[NameObject("/Contents")] = pdf._add_object(stream)
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): pdf._add_object(font)}
                    )
                }
            )
    pdf_content, archive_content = BytesIO(), BytesIO()
    pdf.write(pdf_content)
    with ZipFile(archive_content, "w") as archive:
        archive.writestr("docs/rules.pdf", pdf_content.getvalue())
        archive.writestr("src/gate.py", "pass\n")
        archive.writestr("assets/logo.png", b"logo")
        archive.writestr("bad.txt", bytes([255]))
    client, url, _ = api
    upload = client.post(
        url.removesuffix("/design-engine") + "/documents",
        files={"file": ("parking.zip", archive_content.getvalue())},
    ).json()
    assert ingestion.process_next_job()
    seen = []

    async def capture(**args):
        seen.extend(args["chunks"])
        return await generate(**args)

    monkeypatch.setattr(worker, "generate", capture)
    analyze(client, url, selected_upload_ids=[upload["id"]])
    worker.process_next_run()
    view = client.get(url).json()
    assert view["run"]["status"] == "completed", view
    assert {
        m["path"]: m["status"]
        for m in view["revision"]["snapshot"]["manifest"]
        if "path" in m
    } == {
        "docs/rules.pdf": "partially analyzed",
        "src/gate.py": "analyzed",
        "bad.txt": "unreadable",
        "assets/logo.png": "unsupported",
    }
    pages = [
        (c["locator"]["page"], c["text"])
        for c in seen
        if c["locator"].get("path") == "docs/rules.pdf"
    ]
    assert pages == [(1, "First page"), (3, "Third page")]
