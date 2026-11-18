"""Acceptance A–G through authenticated HTTP, queued ingestion, and the design worker."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event

import pytest
from fastapi.testclient import TestClient
from parking_model import (
    CORRECTION_TEXT,
    DUPLICATE_RECEIPT_TEXT,
    FIXED_TARIFF_CODE,
    PARKING_TEXT,
    ParkingModel,
)

from galvanise.database import Base, engine
from galvanise.main import app
from galvanise.services.ingestion import process_next_job
from auth_helpers import authenticate_as


def run_design_worker():
    from galvanise.design_engine.worker import process_next_run

    assert process_next_run(), "No pending design run"


def payload(response):
    assert response.is_success, (response.status_code, response.text)
    return response.json()


def authenticate(client, email):
    return authenticate_as(client, email, "Parking operator")


def create_project(client):
    project = payload(client.post("/api/projects", json={"name": "Synthetic parking"}))
    return ParkingProject(client, f"/api/projects/{project['id']}")


@dataclass
class ParkingProject:
    client: TestClient
    path: str

    @property
    def design(self):
        return f"{self.path}/design-engine"

    def overview(self):
        return payload(self.client.get(self.design))

    def upload(self, filename, text):
        job = payload(
            self.client.post(
                f"{self.path}/documents",
                files={
                    "file": (filename, text.encode(), "text/plain"),
                },
            )
        )
        assert process_next_job()
        jobs = payload(self.client.get(f"{self.path}/jobs"))
        completed = next(item for item in jobs if item["id"] == job["id"])
        assert completed["status"] == "completed", completed
        return job["id"]

    def analyze(self, upload_id, key="acceptance-analysis"):
        return payload(
            self.client.post(
                f"{self.design}/analyze",
                json={
                    "selected_upload_ids": [upload_id],
                    "idempotency_key": key,
                },
            )
        )

    def chunk(self, citation):
        return payload(self.client.get(f"{self.design}/chunks/{citation['chunk_id']}"))

    def publish(self, filename="parking.md", text=PARKING_TEXT):
        job = self.upload(filename, text)
        queued = self.analyze(job)
        run_design_worker()
        view = self.overview()
        assert view["run"]["id"] == queued["id"]
        assert view["revision"], view["run"]
        return view["revision"]

    def correct_in_chat(self):
        conversation = payload(self.client.post(f"{self.path}/conversations", json={}))
        url = f"{self.path}/conversations/{conversation['id']}"
        content = f"Correction: {CORRECTION_TEXT}"
        reply = self.client.post(f"{url}/chat", json={"content": content})
        assert reply.is_success and "event: done" in reply.text, reply.text
        messages = payload(self.client.get(f"{url}/messages"))
        return next(
            m["id"] for m in messages if m["role"] == "user" and m["content"] == content
        )


@contextmanager
def synthetic_project():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        authenticate(client, "parking@example.test")
        yield create_project(client)


@pytest.fixture
def parking_project():
    with synthetic_project() as project:
        yield project


@pytest.fixture
def parking_model(monkeypatch):
    from galvanise.design_engine import pipeline

    model = ParkingModel()
    monkeypatch.setattr(pipeline, "call_model", model)
    return model


def citations(value):
    if isinstance(value, list):
        for item in value:
            yield from citations(item)
    elif isinstance(value, dict):
        if "excerpt" in value and "chunk_id" in value:
            yield value
        else:
            for child in value.values():
                yield from citations(child)


def normalized(text):
    return " ".join(text.split())


def test_a_requirements_only_has_grounded_tariffs_vendors_and_exit(
    parking_project, parking_model
):
    project = parking_project
    snapshot = project.publish()["snapshot"]
    observed = [v for v in snapshot["volatilities"] if v["status"] == "observed"]
    for topic, alternatives in (
        ("tariff", ("hourly", "per visit")),
        ("gate", ("LiftCo", "PivotWorks")),
    ):
        decision = next(v for v in observed if topic in v["decision"].lower())
        assert len(decision["alternatives"]) >= 2
        quoted = " ".join(ref["excerpt"] for ref in decision["evidence"])
        assert all(alternative in quoted for alternative in alternatives)
    exit_case = next(u for u in snapshot["use_cases"] if "exit" in u["name"].lower())
    walkthrough = next(
        w for w in snapshot["walkthroughs"] if w["use_case_id"] == exit_case["id"]
    )
    assert walkthrough["outcome"] and any(
        s["dependency_id"] for s in walkthrough["steps"]
    )
    refs = list(citations(snapshot))
    assert refs
    for ref in refs:
        chunk = project.chunk(ref)
        assert chunk["locator"]["path"] == "parking.md"
        assert normalized(ref["excerpt"]) in normalized(chunk["text"])
        assert normalized(ref["excerpt"]) in normalized(PARKING_TEXT)
    assert len(snapshot["manifest"]) == 1
    assert snapshot["manifest"][0]["status"] == "analyzed"
    assert snapshot["manifest"][0]["path"] == "parking.md"


def test_b_fixed_tariff_code_does_not_establish_site_variation(
    parking_project, parking_model
):
    project = parking_project
    snapshot = project.publish("parking.py", FIXED_TARIFF_CODE)["snapshot"]
    assert len(snapshot["manifest"]) == 1
    assert snapshot["manifest"][0]["path"] == "parking.py"
    assert snapshot["implementation_findings"]
    for ref in citations(snapshot):
        chunk = project.chunk(ref)
        assert chunk["locator"]["path"] == "parking.py"
        first, last = chunk["locator"]["line_start"], chunk["locator"]["line_end"]
        assert 1 <= first <= last <= len(FIXED_TARIFF_CODE.splitlines())
        assert normalized(ref["excerpt"]) in normalized(
            "\n".join(FIXED_TARIFF_CODE.splitlines()[first - 1 : last])
        )
    pricing = [
        v
        for v in snapshot["volatilities"]
        if any(term in v["decision"].lower() for term in ("tariff", "pricing"))
    ]
    assert pricing and all(v["status"] == "hypothesis" for v in pricing)


@pytest.mark.parametrize(
    "source,duplicate",
    [(PARKING_TEXT, False), (DUPLICATE_RECEIPT_TEXT, True)],
    ids=["receipt-consumes-price", "receipt-recalculates-price"],
)
def test_c_weekend_cap_distinguishes_rule_owner_and_consumer(
    parking_project, parking_model, source, duplicate
):
    snapshot = parking_project.publish("receipts.md", source)["snapshot"]
    pricing = next(c for c in snapshot["components"] if c["name"] == "Pricing")
    cap = next(p for p in snapshot["change_probes"] if "weekend" in p["change"].lower())
    assert cap["volatility_id"] in pricing["owns"]
    assert cap["predicted_owner_ids"] == [pricing["id"]]
    duplicate_findings = [
        f for f in snapshot["findings"] if f["code"] == "duplicate_knowledge"
    ]
    receipt = next(c for c in snapshot["components"] if c["name"] == "Receipt")
    if duplicate:
        assert any(
            {receipt["id"], pricing["id"]} <= set(f["target_ids"]) and f["evidence"]
            for f in duplicate_findings
        )
        assert receipt["id"] in cap["predicted_edit_ids"]
        assert any(leak["component_id"] == receipt["id"] for leak in cap["leaks"])
    else:
        receipt_operations = {
            op["id"]
            for contract in snapshot["contracts"]
            if contract["owner_id"] == receipt["id"]
            for op in contract["operations"]
            if "Final amount" in op["inputs"]
        }
        assert any(
            step["callee_id"] == receipt["id"]
            and step["operation_id"] in receipt_operations
            for walk in snapshot["walkthroughs"]
            for step in walk["steps"]
        )
        assert cap["predicted_edit_ids"] == [pricing["id"]]
        assert [c["component_id"] for c in cap["consumers"]] == [receipt["id"]]
        assert not duplicate_findings


def test_d_correction_preserves_current_evidence_gate_ids_and_prior_revision(
    parking_project, parking_model
):
    project = parking_project
    base = project.publish()
    parking_model.stages.clear()
    message_id = project.correct_in_chat()
    run_design_worker()
    view = project.overview()
    revised = view["revision"]
    assert revised["parent_revision_id"] == base["id"], view["run"]
    assert parking_model.stages == [
        "volatility",
        "boundaries",
        "walkthroughs",
        "review",
    ]
    before, after = base["snapshot"], revised["snapshot"]
    for collection, label in (
        ("components", "name"),
        ("volatilities", "decision"),
        ("contracts", "name"),
    ):
        gate_ids = {e["id"] for e in before[collection] if "gate" in e[label].lower()}
        assert gate_ids
        assert gate_ids == {
            e["id"] for e in after[collection] if "gate" in e[label].lower()
        }
    confirmed = next(
        v for v in after["volatilities"] if v["status"] == "user_confirmed"
    )
    assert "one tariff" in confirmed["driver"].lower()
    assert any(
        project.chunk(ref)["locator"].get("message_id") == message_id
        and normalized(ref["excerpt"]) in normalized(f"Correction: {CORRECTION_TEXT}")
        for ref in confirmed["evidence"]
    )
    assert any(
        change["collection"] == "volatilities"
        and change["id"] == confirmed["id"]
        and change["reason"]
        for change in [*revised["diff"]["added"], *revised["diff"]["changed"]]
    )
    assert (
        before["implementation_findings"]
        and before["implementation_findings"] == after["implementation_findings"]
    )
    for ref in citations(after["implementation_findings"]):
        assert normalized(ref["excerpt"]) in normalized(project.chunk(ref)["text"])
    assert (
        payload(project.client.get(f"{project.design}/revisions/{base['id']}")) == base
    )


@pytest.mark.parametrize(
    "fault", ["fabricated_excerpt", "missing_operation", "partial_repair"]
)
def test_e_invalid_response_gets_one_repair_and_preserves_head(
    parking_project, parking_model, monkeypatch, fault
):
    from galvanise.design_engine import pipeline

    project = parking_project
    base = project.publish()
    attempts = []

    async def invalid(stage, context):
        result = await parking_model(stage, context)
        if stage == "walkthroughs":
            attempts.append(context)
            walkthrough = result["walkthroughs"][0]
            if fault == "fabricated_excerpt" or (
                fault == "partial_repair" and len(attempts) == 1
            ):
                ref = next(citations(base["snapshot"]))
                walkthrough["evidence"] = [
                    {
                        "chunk_id": ref["chunk_id"],
                        "excerpt": "The moon prints parking tickets.",
                    }
                ]
            if fault in ("missing_operation", "partial_repair"):
                crossed = next(
                    step for step in walkthrough["steps"] if step["operation_id"]
                )
                crossed["operation_id"] = "nonexistent-operation"
        return result

    monkeypatch.setattr(pipeline, "call_model", invalid)
    project.correct_in_chat()
    run_design_worker()
    view = project.overview()
    assert len(attempts) == 2 and "repair" not in attempts[0]
    diagnostics = attempts[1]["repair"]["diagnostics"]
    assert diagnostics
    if fault == "partial_repair":
        assert "inexact excerpt" in diagnostics and "operation" in diagnostics
    assert attempts[1]["repair"]["previous_response"]["walkthroughs"]
    assert view["run"]["status"] == "failed" and view["run"]["error"]
    assert view["revision"] == base
    assert (
        payload(project.client.get(f"{project.design}/revisions/{base['id']}")) == base
    )


def test_f_idempotent_request_retry_and_reload(
    parking_project, parking_model, monkeypatch
):
    from galvanise.design_engine import pipeline

    project = parking_project
    upload = project.upload("parking.md", PARKING_TEXT)
    submitted = project.analyze(upload)
    assert project.analyze(upload)["id"] == submitted["id"]
    calls = []

    async def interrupted(stage, context):
        calls.append(stage)
        if stage == "boundaries":
            raise RuntimeError("Synthetic provider interruption")
        return await parking_model(stage, context)

    monkeypatch.setattr(pipeline, "call_model", interrupted)
    run_design_worker()
    failed = project.overview()
    assert failed["run"]["status"] == "failed" and failed["revision"] is None
    assert calls[:3] == ["inventory", "use_cases", "volatility"]
    parking_model.stages.clear()
    monkeypatch.setattr(pipeline, "call_model", parking_model)
    payload(project.client.post(f"{project.design}/runs/{submitted['id']}/retry"))
    run_design_worker()
    assert parking_model.stages == ["boundaries", "walkthroughs", "review"]
    published = project.overview()
    assert published["revision"] and published["run"]["id"] == submitted["id"]
    assert project.analyze(upload)["id"] == submitted["id"]
    with TestClient(app, headers={"x-test-user": project.client.headers["x-test-user"]}) as reloaded:
        assert payload(reloaded.get(project.design)) == published


def test_f_competing_corrections_only_one_replaces_base(
    parking_project, parking_model, monkeypatch
):
    from galvanise.design_engine import pipeline

    project = parking_project
    base = project.publish()
    project.correct_in_chat()
    first_run = project.overview()["run"]
    assert first_run["base_revision_id"] == base["id"]
    first_ready, second_ready, allow_second_publish = Event(), Event(), Event()

    async def interleave(stage, context):
        if stage == "review":
            if first_ready.is_set():
                second_ready.set()
                assert allow_second_publish.wait(20)
            else:
                first_ready.set()
                assert second_ready.wait(20)
        return await parking_model(stage, context)

    monkeypatch.setattr(pipeline, "call_model", interleave)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run_design_worker)
        try:
            assert first_ready.wait(20), "First revision did not reach review"
            project.correct_in_chat()
            second_run = project.overview()["run"]
            assert second_run["id"] != first_run["id"]
            assert second_run["base_revision_id"] == base["id"]
            second = pool.submit(run_design_worker)
            assert second_ready.wait(20), "Second revision did not reach review"
            first.result(timeout=20)
            winner = project.overview()["revision"]
            assert winner["parent_revision_id"] == base["id"]
        finally:
            second_ready.set()
            allow_second_publish.set()
        second.result(timeout=20)
    final = project.overview()
    assert final["revision"] == winner
    assert (final["run"]["id"], final["run"]["status"]) == (second_run["id"], "stale")


def test_f_excerpt_requires_project_and_owner(parking_project, parking_model):
    project = parking_project
    revision = project.publish()
    ref = next(citations(revision["snapshot"]))
    original = project.chunk(ref)
    sibling = create_project(project.client)
    with TestClient(app) as outsider:
        authenticate(outsider, "outsider@example.test")
        outside = create_project(outsider)
        for client, design in (
            (outsider, project.design),
            (outsider, outside.design),
            (project.client, sibling.design),
        ):
            denied = client.get(f"{design}/chunks/{ref['chunk_id']}")
            assert denied.status_code == 404
            assert original["text"] not in denied.text


def test_g_schedules_persist_with_exact_inputs_and_revision(
    parking_project, parking_model
):
    project = parking_project
    revision = project.publish()
    url = f"{project.design}/plan"

    def plan(inputs):
        return payload(
            project.client.post(
                url, json={"revision_id": revision["id"], "planning_inputs": inputs}
            )
        )

    initial = plan({})["result"]
    assert initial["activities"] and initial["missing_inputs"] and not initial["runs"]
    component = revision["snapshot"]["components"][0]["id"]

    def activity(identifier, deliverable, days, predecessors):
        return {
            "id": identifier,
            "deliverable": deliverable,
            "related_ids": [component],
            "predecessors": predecessors,
            "skills": ["implementation"],
            "effort": {"likely": days},
            "estimate_source": "Synthetic team estimate",
            "estimate_confirmed": True,
        }

    def person(name, skill="implementation"):
        return {"id": name, "name": name, "skills": [skill], "availability": 1}

    inputs = {
        "start_date": "2026-11-26",  # Thursday. Even the shortest option crosses a weekend.
        "activities": [
            activity("A", "Publish pricing contract", 2, []),
            activity("B", "Implement gate adapter", 2, []),
            activity("I", "Integrate exit workflow", 1, ["A", "B"]),
        ],
        "rosters": [
            {"id": "one", "name": "One person", "people": [person("Sam")]},
            {
                "id": "two",
                "name": "Two people",
                "people": [person("Sam"), person("Jo")],
            },
            {
                "id": "unqualified",
                "name": "No implementation skill",
                "people": [person("Pat", "analysis")],
            },
        ],
    }
    saved = plan(inputs)
    assert saved["input"] == inputs and saved["revision_id"] == revision["id"]
    assert project.overview()["plan"] == saved
    runs = {r["roster_id"]: r for r in saved["result"]["runs"]}
    for roster, days, finish in (("one", 5, "2026-12-02"), ("two", 3, "2026-11-30")):
        run = runs[roster]
        assert run["status"] == "scheduled" and run["critical_path_days"] == 3
        assert (run["makespan_days"], run["finish_date"], run["total_cost"]) == (
            days,
            finish,
            None,
        )
        assigned = {a["activity_id"]: a for a in run["assignments"]}
        assert set(assigned) == {"A", "B", "I"}
        assert assigned["I"]["start_date"] > max(
            assigned[k]["finish_date"] for k in ("A", "B")
        )
        assert (assigned["A"]["person_id"] == assigned["B"]["person_id"]) == (
            roster == "one"
        )
    blocked = runs["unqualified"]
    assert blocked["status"] == "infeasible"
    assert any(
        b["activity_id"] in ("A", "B") and "implementation" in b["skills"]
        for b in blocked["blockers"]
    )


def test_selecting_different_upload_preserves_previous_revision(
    parking_project, parking_model
):
    project = parking_project
    previous = project.publish()
    selected = project.upload("fixed.py", FIXED_TARIFF_CODE)
    queued = project.analyze(selected, key="fixed-code-only")
    run_design_worker()
    view = project.overview()
    assert view["run"]["id"] == queued["id"] and view["run"]["status"] == "completed", (
        view["run"]
    )
    revised = view["revision"]
    assert revised["parent_revision_id"] == previous["id"]
    assert [s["path"] for s in revised["snapshot"]["manifest"]] == ["fixed.py"]
    assert all(v["status"] == "hypothesis" for v in revised["snapshot"]["volatilities"])
    assert {
        project.chunk(ref)["locator"]["path"] for ref in citations(revised["snapshot"])
    } == {"fixed.py"}
    assert (
        payload(project.client.get(f"{project.design}/revisions/{previous['id']}"))
        == previous
    )


def test_overlapping_selection_retains_grounded_ids_only(
    parking_project, parking_model, monkeypatch
):
    from galvanise.design_engine import pipeline

    project = parking_project
    kept = project.upload("parking.md", PARKING_TEXT)
    omitted = "An unrelated confidential note about archived visit counters."
    project.upload("omitted.md", omitted)
    payload(
        project.client.post(
            f"{project.design}/analyze", json={"idempotency_key": "both"}
        )
    )
    run_design_worker()
    base = project.overview()["revision"]
    assert base

    async def inspect(stage, context):
        assert omitted not in str(context) and "omitted.md" not in str(context)
        return await parking_model(stage, context)

    monkeypatch.setattr(pipeline, "call_model", inspect)
    project.analyze(kept, key="only-kept")
    run_design_worker()
    view = project.overview()
    assert view["run"]["status"] == "completed", view["run"]
    for field in (
        "actors",
        "implementation_findings",
        "components",
        "volatilities",
        "contracts",
        "dependencies",
        "walkthroughs",
        "change_probes",
    ):
        assert {r["id"] for r in view["revision"]["snapshot"][field]} == {
            r["id"] for r in base["snapshot"][field]
        }, field


@pytest.mark.parametrize(
    "answer",
    [
        "Every site uses the same hourly formula. North sets its rate to two credits and South to five.",
        "Each site chooses its own charging formula.",
        "We are unsure whether each site chooses the formula.",
    ],
)
def test_answer_is_bound_to_the_base_question_and_persisted(
    parking_project, parking_model, answer
):
    from parking_model import AMBIGUOUS, COMMON, FORMULA, PARKING_POLICY

    project = parking_project
    base = project.publish(text=PARKING_TEXT.replace(PARKING_POLICY, AMBIGUOUS))
    decision, gate = base["snapshot"]["volatilities"]
    question = base["snapshot"]["questions"][0]
    body = {
        "base_revision_id": base["id"],
        "question_id": question["id"],
        "decision_id": decision["id"],
        "answer": answer,
        "idempotency_key": "answer",
    }

    def submit(**changes):
        return project.client.post(f"{project.design}/revise", json=body | changes)

    assert submit(decision_id=gate["id"]).status_code == 422
    assert submit(question_id="missing").status_code == 422
    queued = payload(submit())
    assert payload(submit())["id"] == queued["id"]
    assert submit(answer="Different answer").status_code == 409
    run_design_worker()
    view = project.overview()
    assert view["run"]["status"] == "completed", view["run"]
    revised = view["revision"]
    current = revised["snapshot"]["volatilities"][0]
    assert (
        current["id"] == decision["id"] and revised["parent_revision_id"] == base["id"]
    )
    saved = current["answers"][0]
    assert (
        saved["question_id"] == question["id"]
        and saved["base_revision_id"] == base["id"]
    )
    assert project.chunk(saved["evidence"])["text"] == answer
    assert (
        current["explanation"]["owner_id"] != decision["explanation"]["owner_id"]
    ) == (answer == FORMULA)
    assert bool(current["explanation"]["uncertainty"]) == (
        answer not in (COMMON, FORMULA)
    )
    assert gate == revised["snapshot"]["volatilities"][1]
    assert payload(submit())["id"] == queued["id"]
    assert submit(idempotency_key="late").status_code == 409
    assert (
        payload(project.client.get(f"{project.design}/revisions/{base['id']}")) == base
    )
