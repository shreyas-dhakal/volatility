"""Design workflow tests use real persistence/routes and mock only the AI provider."""

import os

os.environ.update(
    DATABASE_URL="sqlite://",
    APP_ENV="test",
    SOURCE_TOKEN_ENCRYPTION_KEY="test-source-token-encryption-key",
    AUTO_CREATE_TABLES="true",
)
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from galvanise.database import Base, SessionLocal, engine
from galvanise.main import app
from galvanise.models import KnowledgeRecord, SourceDocument
from auth_helpers import authenticate_as, sign_out_test_user
from sqlalchemy import select


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        authenticate_as(c, "design@example.com", "Architect")
        yield c


def project(c):
    return c.post(
        "/api/projects", json={"name": "Purchasing", "system_type": "new"}
    ).json()["id"]


def intake(c, pid, **changes):
    body = {
        "title": "Place order",
        "description": "Buy supplies",
        "actor": "Buyer",
        "trigger": "Stock low",
        "preconditions": ["Buyer authorized"],
        "steps": ["Select supplies", "Submit order"],
        "outcome": "Order accepted",
        "variations": ["Rush order", "Supplier unavailable"],
        "evidence_ids": [],
    }
    return c.post(f"/api/projects/{pid}/design/use-cases", json={**body, **changes})


def approve(c, pid, r):
    response = c.patch(
        f"/api/projects/{pid}/records/{r['id']}",
        json={"expected_version": r["version"], "status": "approved"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def generate(c, pid, stage):
    return c.post(f"/api/projects/{pid}/design/generate", json={"stage": stage})


def provider(monkeypatch, records):
    import galvanise.routes.design as routes

    async def parse(**kwargs):
        return SimpleNamespace(
            status="completed",
            output_parsed=kwargs["text_format"].model_validate({"records": records}),
        )

    fake = SimpleNamespace(
        responses=SimpleNamespace(parse=AsyncMock(side_effect=parse)), close=AsyncMock()
    )
    monkeypatch.setattr(routes, "configured_client", lambda: fake)
    return fake


def core(uid, **changes):
    return dict(
        title="Acquire supplies",
        description="Business outcome independent of ordering channel",
        use_case_ids=[uid],
        rationale="Rush and normal orders share the acquisition outcome",
        unresolved_use_case_ids=[],
        evidence_ids=[],
        uncertainty="Confirm cancellations",
        open_questions=["Are cancellations included?"],
        **changes,
    )


def volatility(cid):
    return {
        "title": "Supplier protocol",
        "description": "Protocol can change independently of acquisition",
        "core_use_case_ids": [cid],
        "axis": "over_time",
        "what_changes": "Supplier request protocol",
        "why_plausible": "Supplier migration is planned",
        "stable_aspects": ["Acquisition outcome"],
        "examples": ["REST to messages"],
        "evidence_ids": [],
        "uncertainty": "Migration date unknown",
        "open_questions": ["When will supplier migrate?"],
    }


def component(vid, title="Supplier access", dependencies=None):
    return {
        "title": title,
        "description": "Encapsulate protocol",
        "component_role": "resource_access",
        "volatility_ids": [vid],
        "responsibility": "Translate purchase requests",
        "hidden_change": "Supplier protocol",
        "stable_contract": "submit(PurchaseRequest) -> OrderReceipt",
        "excluded_responsibilities": ["Approval orchestration"],
        "dependencies": dependencies or [],
        "evidence_ids": [],
        "uncertainty": "Error semantics need agreement",
        "open_questions": [],
    }


def validation(cid, vid, bid):
    return {
        "title": "Acquisition review",
        "description": "Qualitative proposed collaboration and change scenario",
        "collaborations": [
            {
                "core_use_case_id": cid,
                "component_ids": [bid],
                "steps": ["Submit through stable contract"],
            }
        ],
        "scenarios": [
            {
                "title": "Supplier moves to messages",
                "volatility_id": vid,
                "changed_component_ids": [bid],
                "unchanged_component_ids": [],
                "rationale": "Only protocol translation changes",
            }
        ],
        "assumptions": ["No execution verified"],
        "evidence_ids": [],
    }


def stages(c, pid, monkeypatch):
    u = approve(c, pid, intake(c, pid).json())
    provider(monkeypatch, [core(u["id"])])
    response = generate(c, pid, "core")
    assert response.status_code == 200, response.text
    co = approve(c, pid, response.json()["records"][0])
    provider(monkeypatch, [volatility(co["id"])])
    response = generate(c, pid, "volatility")
    assert response.status_code == 200, response.text
    v = approve(c, pid, response.json()["records"][0])
    provider(monkeypatch, [component(v["id"])])
    response = generate(c, pid, "decomposition")
    assert response.status_code == 200, response.text
    b = approve(c, pid, response.json()["records"][0])
    return u, co, v, b


def test_manual_intake_validation_evidence_and_owner_isolation(client):
    pid = project(client)
    response = intake(client, pid)
    assert response.status_code == 200, response.text
    r = response.json()
    assert (r["kind"], r["status"], r["evidence_status"], r["version"]) == (
        "use_case",
        "pending",
        "human_confirmed",
        1,
    )
    assert r["payload"]["variations"] == ["Rush order", "Supplier unavailable"]
    for changes in [
        {"title": " "},
        {"steps": []},
        {"steps": [" "]},
        {"outcome": ""},
        {"evidence_ids": ["outside"]},
        {"actor": "a" * 10001},
    ]:
        assert intake(client, pid, **changes).status_code == 422
    other = project(client)
    with SessionLocal() as db:
        d = SourceDocument(project_id=other, name="Outside", content="Private")
        db.add(d)
        db.commit()
        did = d.id
    assert intake(client, pid, evidence_ids=[did]).status_code == 422
    sign_out_test_user(client)
    assert client.get(f"/api/projects/{pid}/design").status_code == 401
    authenticate_as(client, "outside@example.com", "Outside")
    for method, path, body in [
        ("get", "", None),
        ("post", "/use-cases", {}),
        ("post", "/generate", {"stage": "core"}),
    ]:
        response = getattr(client, method)(
            f"/api/projects/{pid}/design{path}",
            **({"json": body} if body is not None else {}),
        )
        assert response.status_code in (404, 422)
    assert client.get(f"/api/projects/{pid}/design").status_code == 404


def test_prerequisites_config_and_pending_inputs(client, monkeypatch):
    from galvanise.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "")
    pid = project(client)
    for stage in ["core", "volatility", "decomposition", "validation"]:
        response = generate(client, pid, stage)
        assert response.status_code == 422, response.text
        assert "require" in response.text.lower()
    u = intake(client, pid).json()
    assert generate(client, pid, "core").status_code == 503
    fake = provider(monkeypatch, [core(u["id"])])
    response = generate(client, pid, "core")
    assert response.status_code == 200, response.text
    assert generate(client, pid, "volatility").status_code == 422
    co = approve(client, pid, response.json()["records"][0])
    provider(monkeypatch, [volatility(co["id"])])
    assert generate(client, pid, "volatility").status_code == 200
    sent = json.loads(fake.responses.parse.call_args.kwargs["input"])
    assert u["id"] in str(sent) and "Rush order" in str(sent)
    assert "untrusted" in fake.responses.parse.call_args.kwargs["instructions"]
    fake.close.assert_awaited_once()


@pytest.mark.parametrize("bad_link", ["missing", "wrong_kind", "cross_project"])
def test_generated_references_are_typed_owned_and_atomic(client, monkeypatch, bad_link):
    pid = project(client)
    u = intake(client, pid).json()
    foreign = intake(client, project(client)).json()
    with SessionLocal() as db:
        d = SourceDocument(project_id=pid, name="Evidence", content="Notes")
        db.add(d)
        db.commit()
        did = d.id
    link = {"missing": "invented", "wrong_kind": did, "cross_project": foreign["id"]}[
        bad_link
    ]
    provider(monkeypatch, [core(u["id"]), {**core(link), "title": "Invalid"}])
    response = generate(client, pid, "core")
    assert response.status_code == 422, response.text
    assert client.get(f"/api/projects/{pid}/design").json()["core_use_cases"] == []


def test_generation_preserves_approved_and_tracks_versions_and_variations(
    client, monkeypatch
):
    pid = project(client)
    u, co, _v, _b = stages(client, pid, monkeypatch)
    provider(monkeypatch, [core(u["id"])])
    response = generate(client, pid, "core")
    assert response.json()["records"][0]["id"] == co["id"]
    provider(monkeypatch, [{**core(u["id"]), "description": "A revised hypothesis"}])
    revised = generate(client, pid, "core").json()["records"][0]
    assert revised["id"] != co["id"] and revised["status"] == "pending"
    assert revised["payload"]["supersedes_id"] == co["id"]
    records = client.get(f"/api/projects/{pid}/records").json()
    original = next(r for r in records if r["id"] == co["id"])
    assert original == co
    assert (
        next(r for r in records if r["id"] == u["id"])["payload"]["variations"]
        == u["payload"]["variations"]
    )


def test_complete_journey_and_stale_validation_after_upstream_review(
    client, monkeypatch
):
    pid = project(client)
    u, co, v, b = stages(client, pid, monkeypatch)
    provider(monkeypatch, [validation(co["id"], v["id"], b["id"])])
    response = generate(client, pid, "validation")
    assert response.status_code == 200, response.text
    val = approve(client, pid, response.json()["records"][0])
    assert b["id"] in val["payload"]["input_versions"]
    view = client.get(f"/api/projects/{pid}/design").json()
    assert all(view["readiness"].values()), view
    assert view["validations"][0]["payload"]["stale"] is False
    patch = client.patch(
        f"/api/projects/{pid}/records/{u['id']}",
        json={"expected_version": u["version"], "status": "rejected"},
    )
    assert patch.status_code == 200, patch.text
    view = client.get(f"/api/projects/{pid}/design").json()
    assert not view["readiness"]["validation"]
    assert any(f["code"] == "stale_validation" for f in view["findings"])
    assert view["validations"][0]["payload"]["stale"] is True
    assert (
        client.patch(
            f"/api/projects/{pid}/records/{u['id']}",
            json={"expected_version": u["version"], "status": "approved"},
        ).status_code
        == 409
    )


def test_patch_rejects_invalid_design_payload_without_mutation(client, monkeypatch):
    pid = project(client)
    _u, co, _v, b = stages(client, pid, monkeypatch)
    for payload in [
        {**b["payload"], "volatility_ids": [co["id"]]},
        {**b["payload"], "dependencies": ["invented"]},
        {**b["payload"], "stable_contract": " "},
        {**b["payload"], "component_role": "service"},
    ]:
        response = client.patch(
            f"/api/projects/{pid}/records/{b['id']}",
            json={"expected_version": b["version"], "payload": payload},
        )
        assert response.status_code == 422, response.text
    assert (
        next(
            r
            for r in client.get(f"/api/projects/{pid}/records").json()
            if r["id"] == b["id"]
        )
        == b
    )


def test_decomposition_resolves_batch_dependencies_and_rejects_invalid_contract(
    client, monkeypatch
):
    pid = project(client)
    _u, _co, v, _b = stages(client, pid, monkeypatch)
    provider(
        monkeypatch,
        [
            component(v["id"], "Workflow", ["Policy"]),
            {**component(v["id"], "Policy", ["Workflow"]), "component_role": "engine"},
        ],
    )
    response = generate(client, pid, "decomposition")
    assert response.status_code == 200, response.text
    rows = response.json()["records"]
    by_title = {r["title"]: r for r in rows}
    assert by_title["Workflow"]["payload"]["dependencies"] == [by_title["Policy"]["id"]]
    assert by_title["Policy"]["payload"]["dependencies"] == [by_title["Workflow"]["id"]]
    view = client.get(f"/api/projects/{pid}/design").json()
    assert any(f["code"] == "dependency_cycle" for f in view["findings"])
    provider(monkeypatch, [{**component(v["id"], "Broken"), "stable_contract": ""}])
    assert generate(client, pid, "decomposition").status_code == 422
    assert len(client.get(f"/api/projects/{pid}/design").json()["components"]) == 3


def test_failed_provider_saves_nothing_and_closes(client, monkeypatch):
    pid = project(client)
    intake(client, pid)
    fake = provider(monkeypatch, [])
    fake.responses.parse.side_effect = RuntimeError("provider-secret")
    response = generate(client, pid, "core")
    assert response.status_code == 502 and "provider-secret" not in response.text
    fake.close.assert_awaited_once()
    assert client.get(f"/api/projects/{pid}/design").json()["core_use_cases"] == []


def test_deterministic_coverage_contracts_dependencies_and_containment(
    client, monkeypatch
):
    pid = project(client)
    _u, _co, _v, _b = stages(client, pid, monkeypatch)
    unlinked = intake(client, pid, title="Cancel order").json()
    # Historical/malformed stored artifacts must be diagnosed even if they predate
    # strict write checks. Keep their original records visible for remediation.
    with SessionLocal() as db:
        broken = KnowledgeRecord(
            project_id=pid,
            kind="boundary",
            title="Legacy boundary",
            status="approved",
            payload={
                "design_engine": True,
                "volatility_ids": [],
                "dependencies": ["unknown"],
                "stable_contract": "",
            },
        )
        db.add(broken)
        db.commit()
        broken_id = broken.id
    view = client.get(f"/api/projects/{pid}/design").json()
    codes = {f["code"] for f in view["findings"]}
    assert {
        "uncovered_use_case",
        "missing_contract",
        "unknown_dependency",
        "missing_collaboration",
        "missing_change_scenario",
        "invalid_reference_or_payload",
    } <= codes
    assert any(
        unlinked["id"] in f["record_ids"]
        for f in view["findings"]
        if f["code"] == "uncovered_use_case"
    )
    assert any(
        broken_id in f["record_ids"]
        for f in view["findings"]
        if f["code"] == "missing_contract"
    )


def test_invalid_stored_artifacts_are_not_ready(client):
    pid = project(client)
    with SessionLocal() as db:
        db.add(
            KnowledgeRecord(
                project_id=pid,
                kind="use_case",
                title="Incomplete imported case",
                status="approved",
                payload={},
            )
        )
        db.commit()
    view = client.get(f"/api/projects/{pid}/design").json()
    assert view["readiness"]["use_cases"] is False
    assert generate(client, pid, "core").status_code == 422


def test_validation_references_and_disjoint_scenarios_checked_before_save(
    client, monkeypatch
):
    pid = project(client)
    u, co, v, b = stages(client, pid, monkeypatch)
    valid = validation(co["id"], v["id"], b["id"])
    invalids = [
        {
            **valid,
            "collaborations": [
                {
                    "core_use_case_id": u["id"],
                    "component_ids": [b["id"]],
                    "steps": ["Try"],
                }
            ],
        },
        {**valid, "scenarios": [{**valid["scenarios"][0], "volatility_id": co["id"]}]},
        {
            **valid,
            "scenarios": [
                {**valid["scenarios"][0], "unchanged_component_ids": [b["id"]]}
            ],
        },
        {
            **valid,
            "scenarios": [
                {**valid["scenarios"][0], "changed_component_ids": [v["id"]]}
            ],
        },
    ]
    for invalid in invalids:
        provider(monkeypatch, [valid, {**invalid, "title": "Invalid scenario"}])
        assert generate(client, pid, "validation").status_code == 422
        assert client.get(f"/api/projects/{pid}/design").json()["validations"] == []


def test_incomplete_and_empty_output_never_create_fake_artifacts(client, monkeypatch):
    pid = project(client)
    u = intake(client, pid).json()
    fake = provider(monkeypatch, [core(u["id"])])
    fake.responses.parse.side_effect = None
    for response in [
        SimpleNamespace(status="incomplete", output_parsed=None),
        SimpleNamespace(status="completed", output_parsed=None),
    ]:
        fake.responses.parse.return_value = response
        assert generate(client, pid, "core").status_code == 422
    provider(monkeypatch, [])
    assert generate(client, pid, "core").status_code == 422
    assert client.get(f"/api/projects/{pid}/design").json()["core_use_cases"] == []


def test_server_owned_provenance_cannot_be_forged_or_removed(client, monkeypatch):
    pid = project(client)
    _u, _co, _v, b = stages(client, pid, monkeypatch)
    for payload in [
        {**b["payload"], "design_engine": False},
        {**b["payload"], "input_versions": {}},
        {k: v for k, v in b["payload"].items() if k != "input_versions"},
    ]:
        assert (
            client.patch(
                f"/api/projects/{pid}/records/{b['id']}",
                json={"expected_version": b["version"], "payload": payload},
            ).status_code
            == 422
        )


def test_generation_detects_inputs_changed_during_provider_call(client, monkeypatch):
    from galvanise.agents.design_schemas import CoreResult

    pid = project(client)
    u = intake(client, pid).json()
    fake = provider(monkeypatch, [core(u["id"])])

    async def change_inputs(**kwargs):
        with SessionLocal() as db:
            row = db.get(KnowledgeRecord, u["id"])
            row.version += 1
            row.description = "Changed during request"
            db.commit()
        return SimpleNamespace(
            status="completed",
            output_parsed=CoreResult.model_validate({"records": [core(u["id"])]}),
        )

    fake.responses.parse.side_effect = change_inputs
    response = generate(client, pid, "core")
    assert response.status_code == 409, response.text
    assert client.get(f"/api/projects/{pid}/design").json()["core_use_cases"] == []


def test_context_is_bounded_and_truncation_visible(client, monkeypatch):
    pid = project(client)
    with SessionLocal() as db:
        for i in range(110):
            db.add(
                KnowledgeRecord(
                    project_id=pid,
                    kind="use_case",
                    title=f"Case {i}",
                    status="approved",
                    description="Original",
                    payload={
                        "actor": "Buyer",
                        "trigger": "Stock low",
                        "preconditions": [],
                        "steps": ["Order supplies"],
                        "outcome": "Accepted",
                        "variations": ["v" * 6000] * 10,
                        "evidence_ids": [],
                    },
                )
            )
        db.commit()
        uid = db.scalar(
            select(KnowledgeRecord.id).where(KnowledgeRecord.project_id == pid)
        )
    fake = provider(monkeypatch, [core(uid)])
    response = generate(client, pid, "core")
    assert response.status_code == 200, response.text
    text = fake.responses.parse.call_args.kwargs["input"]
    context = json.loads(text)
    assert len(text) < 110000
    assert context["context_limits"]["design_records_omitted"] > 0
    assert context["context_limits"]["design_payloads_truncated"] > 0
    assert (
        response.json()["records"][0]["payload"]["context_limits"][
            "design_records_omitted"
        ]
        > 0
    )
    assert any(
        f["code"] == "context_truncated"
        for f in client.get(f"/api/projects/{pid}/design").json()["findings"]
    )


def test_same_batch_component_cycle_rerun_preserves_approved_records(
    client, monkeypatch
):
    pid = project(client)
    _u, _co, v, _b = stages(client, pid, monkeypatch)
    proposals = [
        component(v["id"], "Workflow", ["Policy"]),
        component(v["id"], "Policy", ["Workflow"]),
    ]
    provider(monkeypatch, proposals)
    first = generate(client, pid, "decomposition").json()["records"]
    approved = [approve(client, pid, r) for r in first]
    provider(monkeypatch, proposals)
    again = generate(client, pid, "decomposition")
    assert again.status_code == 200, again.text
    assert again.json()["records"] == approved


def test_generation_cannot_link_unreviewed_stage_inputs(client, monkeypatch):
    pid = project(client)
    u, _co, _v, _b = stages(client, pid, monkeypatch)
    provider(monkeypatch, [{**core(u["id"]), "title": "Unreviewed core"}])
    pending = generate(client, pid, "core").json()["records"][0]
    provider(monkeypatch, [volatility(pending["id"])])
    response = generate(client, pid, "volatility")
    assert response.status_code == 422, response.text
    # Restore a fresh reviewed chain, then introduce a pending peer component.
    approve(client, pid, pending)
    provider(monkeypatch, [volatility(pending["id"])])
    fresh_v = approve(
        client, pid, generate(client, pid, "volatility").json()["records"][0]
    )
    provider(
        monkeypatch,
        [component(fresh_v["id"], "Reviewed"), component(fresh_v["id"], "Pending")],
    )
    peers = generate(client, pid, "decomposition").json()["records"]
    reviewed = approve(client, pid, peers[0])
    unreviewed = peers[1]
    provider(monkeypatch, [validation(pending["id"], fresh_v["id"], unreviewed["id"])])
    response = generate(client, pid, "validation")
    assert response.status_code == 422, response.text
    provider(monkeypatch, [validation(pending["id"], fresh_v["id"], reviewed["id"])])
    assert generate(client, pid, "validation").status_code == 200


def test_review_cannot_promote_legacy_payload_into_design_without_validation(client):
    pid = project(client)
    with SessionLocal() as db:
        r = KnowledgeRecord(
            project_id=pid,
            kind="boundary",
            title="Legacy architecture boundary",
            payload={"responsibility": "Legacy"},
        )
        db.add(r)
        db.commit()
        rid = r.id
    response = client.patch(
        f"/api/projects/{pid}/records/{rid}",
        json={
            "expected_version": 1,
            "payload": {"design_engine": True, "dependencies": ["other-project"]},
        },
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "change",
    [{"title": "Edited outcome"}, {"status": "rejected"}, {"status": "pending"}],
)
def test_component_reviews_invalidate_historical_validation(
    client, monkeypatch, change
):
    pid = project(client)
    _u, co, v, b = stages(client, pid, monkeypatch)
    provider(monkeypatch, [validation(co["id"], v["id"], b["id"])])
    val = approve(client, pid, generate(client, pid, "validation").json()["records"][0])
    response = client.patch(
        f"/api/projects/{pid}/records/{b['id']}",
        json={"expected_version": b["version"], **change},
    )
    assert response.status_code == 200, response.text
    view = client.get(f"/api/projects/{pid}/design").json()
    assert view["readiness"]["validation"] is False
    assert (
        next(r for r in view["validations"] if r["id"] == val["id"])["payload"]["stale"]
        is True
    )


def test_list_bounds_report_omissions(client):
    pid = project(client)
    with SessionLocal() as db:
        for i in range(205):
            db.add(
                KnowledgeRecord(
                    project_id=pid,
                    kind="use_case",
                    title=f"Case {i}",
                    payload={
                        "steps": ["Submit"],
                        "outcome": "Accepted",
                        "evidence_ids": [],
                    },
                )
            )
        db.commit()
    view = client.get(f"/api/projects/{pid}/design").json()
    assert len(view["use_cases"]) == 200
    assert view["context_limits"]["use_cases_omitted"] == 5
    assert any(f["code"] == "results_truncated" for f in view["findings"])


def test_containment_findings_and_unmapped_volatility_are_deterministic(
    client, monkeypatch
):
    pid = project(client)
    _u, co, v, _b = stages(client, pid, monkeypatch)
    provider(monkeypatch, [{**volatility(co["id"]), "title": "Approval policy"}])
    v2 = approve(client, pid, generate(client, pid, "volatility").json()["records"][0])
    provider(
        monkeypatch,
        [
            component(v["id"], "Protocol"),
            {**component(v2["id"], "Approval"), "component_role": "engine"},
        ],
    )
    components = [
        approve(client, pid, r)
        for r in generate(client, pid, "decomposition").json()["records"]
    ]
    # Valid references, but a change is proposed in a component that doesn't hide it.
    provider(monkeypatch, [validation(co["id"], v["id"], components[1]["id"])])
    response = generate(client, pid, "validation")
    assert response.status_code == 200, response.text
    first = client.get(f"/api/projects/{pid}/design").json()["findings"]
    second = client.get(f"/api/projects/{pid}/design").json()["findings"]
    assert first == second
    assert any(f["code"] == "change_not_contained" for f in first)
    assert any(
        f["code"] == "missing_change_scenario" and v2["id"] in f["record_ids"]
        for f in first
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("axis", "git_churn"),
        ("why_plausible", " "),
        ("what_changes", ""),
        ("stable_aspects", []),
        ("examples", []),
    ],
)
def test_volatility_requires_independent_explicit_reasoning(
    client, monkeypatch, field, value
):
    pid = project(client)
    u = approve(client, pid, intake(client, pid).json())
    provider(monkeypatch, [core(u["id"])])
    co = approve(client, pid, generate(client, pid, "core").json()["records"][0])
    provider(monkeypatch, [{**volatility(co["id"]), field: value}])
    response = generate(client, pid, "volatility")
    assert response.status_code == 422, response.text
    assert client.get(f"/api/projects/{pid}/design").json()["volatilities"] == []


def test_generated_links_cannot_use_stale_approved_inputs(client, monkeypatch):
    pid = project(client)
    u, _co, v, _b = stages(client, pid, monkeypatch)
    provider(monkeypatch, [{**core(u["id"]), "title": "Additional core"}])
    extra = approve(client, pid, generate(client, pid, "core").json()["records"][0])
    # Old volatility remains approved, but its input snapshot is now stale.
    provider(monkeypatch, [{**volatility(extra["id"]), "title": "Current volatility"}])
    current = approve(
        client, pid, generate(client, pid, "volatility").json()["records"][0]
    )
    provider(monkeypatch, [component(v["id"], "Uses stale hypothesis")])
    response = generate(client, pid, "decomposition")
    assert response.status_code == 422, response.text
    provider(monkeypatch, [component(current["id"], "Uses current hypothesis")])
    assert generate(client, pid, "decomposition").status_code == 200


def test_review_round_trip_does_not_persist_computed_staleness(client, monkeypatch):
    pid = project(client)
    _u, _co, _v, b = stages(client, pid, monkeypatch)
    visible = client.get(f"/api/projects/{pid}/design").json()["components"][0]
    assert visible["payload"]["stale"] is False
    response = client.patch(
        f"/api/projects/{pid}/records/{b['id']}",
        json={"expected_version": b["version"], "payload": visible["payload"]},
    )
    assert response.status_code == 200, response.text
    assert "stale" not in response.json()["payload"]


def test_changed_dependency_batch_allocates_new_records_atomically(client, monkeypatch):
    pid = project(client)
    _u, _co, v, _b = stages(client, pid, monkeypatch)
    provider(
        monkeypatch,
        [component(v["id"], "Workflow", ["Policy"]), component(v["id"], "Policy")],
    )
    first = [
        approve(client, pid, r)
        for r in generate(client, pid, "decomposition").json()["records"]
    ]
    # Workflow text remains unchanged, but its same-batch dependency is revised.
    provider(
        monkeypatch,
        [
            component(v["id"], "Workflow", ["Policy"]),
            {**component(v["id"], "Policy"), "description": "Policy revised"},
        ],
    )
    response = generate(client, pid, "decomposition")
    assert response.status_code == 200, response.text
    second = response.json()["records"]
    assert second[0]["id"] != first[0]["id"]
    assert second[0]["payload"]["dependencies"] == [second[1]["id"]]
    assert second[1]["id"] != first[1]["id"]
    stored = {r["id"]: r for r in client.get(f"/api/projects/{pid}/records").json()}
    assert stored[first[0]["id"]] == first[0]
    assert stored[first[1]["id"]] == first[1]


def test_migrated_schema_preserves_design_discriminators(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from galvanise.config import settings
    from galvanise.models import CoreUseCase, DesignValidation, Project, UseCase, User
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    command.upgrade(config, "head")
    migrated = create_engine(database_url)
    with migrated.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []
    with Session(migrated) as db:
        user = User(email="migration@example.com", name="Migrated")
        db.add(user)
        db.flush()
        p = Project(user_id=user.id, name="Existing schema")
        db.add(p)
        db.flush()
        for kind in ("decision", "use_case", "core_use_case", "design_validation"):
            db.add(KnowledgeRecord(project_id=p.id, kind=kind, title=kind, payload={}))
        db.commit()
        db.expire_all()
        rows = list(db.scalars(select(KnowledgeRecord)))
        assert {type(row) for row in rows if row.kind != "decision"} == {
            UseCase,
            CoreUseCase,
            DesignValidation,
        }
        assert len(rows) == 4
    migrated.dispose()


def test_reviewed_validation_with_stale_component_link_is_not_ready(
    client, monkeypatch
):
    pid = project(client)
    u, _co, _v, old_component = stages(client, pid, monkeypatch)
    provider(monkeypatch, [{**core(u["id"]), "title": "Another business outcome"}])
    new_core = approve(client, pid, generate(client, pid, "core").json()["records"][0])
    provider(monkeypatch, [{**volatility(new_core["id"]), "title": "Current protocol"}])
    new_volatility = approve(
        client, pid, generate(client, pid, "volatility").json()["records"][0]
    )
    provider(monkeypatch, [component(new_volatility["id"], "Current component")])
    current = approve(
        client, pid, generate(client, pid, "decomposition").json()["records"][0]
    )
    provider(
        monkeypatch, [validation(new_core["id"], new_volatility["id"], current["id"])]
    )
    report = approve(
        client, pid, generate(client, pid, "validation").json()["records"][0]
    )
    assert client.get(f"/api/projects/{pid}/design").json()["readiness"]["validation"]
    payload = report["payload"]
    payload["collaborations"][0]["component_ids"] = [old_component["id"]]
    response = client.patch(
        f"/api/projects/{pid}/records/{report['id']}",
        json={"expected_version": report["version"], "payload": payload},
    )
    assert response.status_code == 200, response.text
    assert not client.get(f"/api/projects/{pid}/design").json()["readiness"][
        "validation"
    ]


@pytest.mark.parametrize("change", ["add", "delete"])
def test_added_or_deleted_inputs_stale_validation(client, monkeypatch, change):
    pid = project(client)
    _u, co, v, b = stages(client, pid, monkeypatch)
    provider(monkeypatch, [validation(co["id"], v["id"], b["id"])])
    report = approve(
        client, pid, generate(client, pid, "validation").json()["records"][0]
    )
    if change == "add":
        assert intake(client, pid, title="Cancel supply order").status_code == 200
    else:
        with SessionLocal() as db:
            db.delete(db.get(KnowledgeRecord, b["id"]))
            db.commit()
    view = client.get(f"/api/projects/{pid}/design").json()
    assert not view["readiness"]["validation"]
    assert next(r for r in view["validations"] if r["id"] == report["id"])["payload"][
        "stale"
    ]
    assert any(
        f["code"] == "stale_validation" and report["id"] in f["record_ids"]
        for f in view["findings"]
    )


@pytest.mark.parametrize("reference", ["cross_project", "rejected"])
def test_review_rejects_cross_project_or_rejected_typed_links(
    client, monkeypatch, reference
):
    pid = project(client)
    _u, _co, v, b = stages(client, pid, monkeypatch)
    if reference == "cross_project":
        other = project(client)
        with SessionLocal() as db:
            outside = KnowledgeRecord(
                project_id=other,
                kind="volatility",
                title="Private",
                status="approved",
                payload={"design_engine": True},
            )
            db.add(outside)
            db.commit()
            target = outside.id
    else:
        assert (
            client.patch(
                f"/api/projects/{pid}/records/{v['id']}",
                json={"expected_version": v["version"], "status": "rejected"},
            ).status_code
            == 200
        )
        target = v["id"]
    response = client.patch(
        f"/api/projects/{pid}/records/{b['id']}",
        json={
            "expected_version": b["version"],
            "payload": {**b["payload"], "volatility_ids": [target]},
        },
    )
    assert response.status_code == 422, response.text
    assert (
        next(
            r
            for r in client.get(f"/api/projects/{pid}/records").json()
            if r["id"] == b["id"]
        )
        == b
    )


def supporting_evidence(pid):
    with SessionLocal() as db:
        row = KnowledgeRecord(
            project_id=pid,
            kind="evidence",
            title="Supplier commitment",
            description="Protocol migration confirmed",
            status="approved",
            evidence_status="human_confirmed",
            payload={},
        )
        db.add(row)
        db.commit()
        return row.id


@pytest.mark.parametrize(
    "change", [{"description": "Supplier withdrew commitment"}, {"status": "rejected"}]
)
@pytest.mark.parametrize("link_stage", ["use_case", "validation"])
def test_review_evidence_changes_propagate_freshness(
    client, monkeypatch, change, link_stage
):
    pid = project(client)
    eid = supporting_evidence(pid)
    if link_stage == "use_case":
        u = approve(client, pid, intake(client, pid, evidence_ids=[eid]).json())
        provider(monkeypatch, [core(u["id"])])
        co = approve(client, pid, generate(client, pid, "core").json()["records"][0])
        provider(monkeypatch, [volatility(co["id"])])
        v = approve(
            client, pid, generate(client, pid, "volatility").json()["records"][0]
        )
        provider(monkeypatch, [component(v["id"])])
        b = approve(
            client, pid, generate(client, pid, "decomposition").json()["records"][0]
        )
    else:
        u, co, v, b = stages(client, pid, monkeypatch)
    proposal = validation(co["id"], v["id"], b["id"])
    if link_stage == "validation":
        proposal["evidence_ids"] = [eid]
    provider(monkeypatch, [proposal])
    report = approve(
        client, pid, generate(client, pid, "validation").json()["records"][0]
    )
    before = client.get(f"/api/projects/{pid}/design").json()
    assert before["readiness"]["validation"]
    response = client.patch(
        f"/api/projects/{pid}/records/{eid}", json={"expected_version": 1, **change}
    )
    assert response.status_code == 200, response.text
    after = client.get(f"/api/projects/{pid}/design").json()
    assert not after["readiness"]["validation"]
    assert next(r for r in after["validations"] if r["id"] == report["id"])["payload"][
        "stale"
    ]
    assert any(f["code"] == "stale_validation" for f in after["findings"])
    if link_stage == "validation":
        assert report["payload"]["evidence_versions"] == {eid: 1}
        assert eid not in report["payload"]["input_versions"]
    else:
        assert not after["readiness"]["core_use_cases"]
        assert generate(client, pid, "core").status_code == 422


def test_rejected_evidence_is_blocked_on_intake_generation_and_review(
    client, monkeypatch
):
    pid = project(client)
    _u, co, v, b = stages(client, pid, monkeypatch)
    eid = supporting_evidence(pid)
    assert (
        client.patch(
            f"/api/projects/{pid}/records/{eid}",
            json={"expected_version": 1, "status": "rejected"},
        ).status_code
        == 200
    )
    assert intake(client, pid, evidence_ids=[eid]).status_code == 422
    provider(
        monkeypatch, [{**validation(co["id"], v["id"], b["id"]), "evidence_ids": [eid]}]
    )
    assert generate(client, pid, "validation").status_code == 422
    assert (
        client.patch(
            f"/api/projects/{pid}/records/{b['id']}",
            json={
                "expected_version": b["version"],
                "payload": {**b["payload"], "evidence_ids": [eid]},
            },
        ).status_code
        == 422
    )
    assert client.get(f"/api/projects/{pid}/design").json()["validations"] == []


def test_evidence_snapshots_are_managed_and_refresh_on_human_payload_edit(
    client, monkeypatch
):
    pid = project(client)
    _u, co, v, b = stages(client, pid, monkeypatch)
    eid = supporting_evidence(pid)
    provider(
        monkeypatch, [{**validation(co["id"], v["id"], b["id"]), "evidence_ids": [eid]}]
    )
    report = approve(
        client, pid, generate(client, pid, "validation").json()["records"][0]
    )
    assert report["payload"].get("evidence_versions") == {eid: 1}
    assert (
        client.patch(
            f"/api/projects/{pid}/records/{report['id']}",
            json={
                "expected_version": report["version"],
                "payload": {**report["payload"], "evidence_versions": {eid: 999}},
            },
        ).status_code
        == 422
    )
    client.patch(
        f"/api/projects/{pid}/records/{eid}",
        json={"expected_version": 1, "description": "Confirmed updated commitment"},
    )
    refreshed = client.patch(
        f"/api/projects/{pid}/records/{report['id']}",
        json={
            "expected_version": report["version"],
            "payload": report["payload"],
            "status": "pending",
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["payload"]["evidence_versions"] == {eid: 2}
    assert refreshed.json()["history"][-1]["payload"]["evidence_versions"] == {eid: 1}
    approve(client, pid, refreshed.json())
    assert client.get(f"/api/projects/{pid}/design").json()["readiness"]["validation"]


@pytest.mark.parametrize("cyclic", [False, True])
def test_unreviewed_dependency_blocks_validation_until_reviewed(
    client, monkeypatch, cyclic
):
    pid = project(client)
    _u, co, v, original = stages(client, pid, monkeypatch)
    assert (
        client.patch(
            f"/api/projects/{pid}/records/{original['id']}",
            json={"expected_version": original["version"], "status": "rejected"},
        ).status_code
        == 200
    )
    provider(
        monkeypatch,
        [
            component(v["id"], "Workflow", ["Supplier"]),
            component(v["id"], "Supplier", ["Workflow"] if cyclic else []),
        ],
    )
    pair = generate(client, pid, "decomposition").json()["records"]
    workflow = approve(client, pid, pair[0])
    provider(monkeypatch, [validation(co["id"], v["id"], workflow["id"])])
    response = generate(client, pid, "validation")
    assert response.status_code == 422, response.text
    view = client.get(f"/api/projects/{pid}/design").json()
    assert not view["readiness"]["decomposition"]
    assert not view["readiness"]["validation"]
    assert next(r for r in view["components"] if r["id"] == workflow["id"])["payload"][
        "stale"
    ]
    assert any(f["code"] == "unusable_dependency" for f in view["findings"])
    approve(client, pid, pair[1])
    provider(monkeypatch, [validation(co["id"], v["id"], workflow["id"])])
    response = generate(client, pid, "validation")
    assert response.status_code == 200, response.text
    approve(client, pid, response.json()["records"][0])
    assert client.get(f"/api/projects/{pid}/design").json()["readiness"]["validation"]
    if cyclic:
        assert any(
            f["code"] == "dependency_cycle"
            for f in client.get(f"/api/projects/{pid}/design").json()["findings"]
        )


def test_dependency_evidence_freshness_propagates_through_approved_cycle(
    client, monkeypatch
):
    pid = project(client)
    _u, co, v, _b = stages(client, pid, monkeypatch)
    eid = supporting_evidence(pid)
    provider(
        monkeypatch,
        [
            component(v["id"], "Workflow", ["Supplier"]),
            {**component(v["id"], "Supplier", ["Workflow"]), "evidence_ids": [eid]},
        ],
    )
    pair = [
        approve(client, pid, r)
        for r in generate(client, pid, "decomposition").json()["records"]
    ]
    provider(monkeypatch, [validation(co["id"], v["id"], pair[0]["id"])])
    report = approve(
        client, pid, generate(client, pid, "validation").json()["records"][0]
    )
    assert client.get(f"/api/projects/{pid}/design").json()["readiness"]["validation"]
    client.patch(
        f"/api/projects/{pid}/records/{eid}",
        json={"expected_version": 1, "description": "Protocol promise changed"},
    )
    view = client.get(f"/api/projects/{pid}/design").json()
    assert not view["readiness"]["validation"]
    assert next(r for r in view["validations"] if r["id"] == report["id"])["payload"][
        "stale"
    ]
    assert all(
        next(r for r in view["components"] if r["id"] == b["id"])["payload"]["stale"]
        for b in pair
    )


def test_initial_context_limits_count_source_and_record_excerpts(client):
    from galvanise.models import Conversation, Message
    from galvanise.services.knowledge import bounded_context

    pid = project(client)
    with SessionLocal() as db:
        conversation = Conversation(project_id=pid, title="Discovery")
        db.add(conversation)
        db.flush()
        for i in range(13):
            db.add(
                SourceDocument(project_id=pid, name=f"Source {i}", content="d" * 5001)
            )
        for i in range(17):
            db.add(
                Message(
                    project_id=pid,
                    conversation_id=conversation.id,
                    role="user",
                    content="m" * 2001,
                )
            )
        for i in range(61):
            db.add(
                KnowledgeRecord(
                    project_id=pid,
                    kind="evidence",
                    title="t" * 301,
                    description="r" * 2001,
                    payload={"text": "p" * 2600},
                )
            )
        db.commit()
        context = bounded_context(db, pid)
    limits = context["context_limits"]
    assert limits["documents_omitted"] == 1
    assert limits["messages_omitted"] == 1
    assert limits["document_texts_truncated"] == 12
    assert limits["document_characters_omitted"] == 12
    assert limits["message_texts_truncated"] == 16
    assert limits["message_characters_omitted"] == 16
    assert limits["knowledge_records_omitted"] == 1
    assert limits["knowledge_titles_truncated"] == 60
    assert limits["knowledge_descriptions_truncated"] == 60
    assert limits["knowledge_payloads_truncated"] == 60
    assert all(len(d["untrusted_text"]) == 5000 for d in context["documents"])
    assert all(len(m["untrusted_text"]) == 2000 for m in context["messages"])


def test_answer_excerpts_count_only_selected_answers_and_rejected_records_are_excluded(
    client,
):
    from galvanise.services.knowledge import bounded_context

    pid = project(client)
    with SessionLocal() as db:
        for i in range(21):
            db.add(
                KnowledgeRecord(
                    project_id=pid,
                    kind="answer",
                    title="a" * 301,
                    description="a" * 2001,
                    payload={"answer": "a" * 2600},
                )
            )
        db.add(
            KnowledgeRecord(
                project_id=pid,
                kind="answer",
                title="Rejected",
                status="rejected",
                payload={},
            )
        )
        db.commit()
        context = bounded_context(db, pid)
    limits = context["context_limits"]
    assert limits["answer_records_omitted"] == 1
    assert limits["answer_titles_truncated"] == 20
    assert limits["answer_descriptions_truncated"] == 20
    assert limits["answer_payloads_truncated"] == 20
    assert limits["knowledge_records_omitted"] == 0
    assert len(context["stakeholder_answers"]) == 20


def test_source_excerpts_persist_and_raise_design_findings(client, monkeypatch):
    from galvanise.models import Conversation, Message

    pid = project(client)
    u = intake(client, pid).json()
    with SessionLocal() as db:
        conversation = Conversation(project_id=pid, title="Interview")
        db.add(conversation)
        db.flush()
        for i in range(13):
            db.add(
                SourceDocument(project_id=pid, name=f"Source {i}", content="d" * 5001)
            )
        for i in range(17):
            db.add(
                Message(
                    project_id=pid,
                    conversation_id=conversation.id,
                    role="user",
                    content="m" * 2001,
                )
            )
        db.commit()
    fake = provider(monkeypatch, [core(u["id"])])
    response = generate(client, pid, "core")
    assert response.status_code == 200, response.text
    record = response.json()["records"][0]
    limits = record["payload"]["context_limits"]
    assert limits["documents_omitted"] == 1 and limits["document_texts_truncated"] == 12
    assert limits["messages_omitted"] == 1 and limits["message_texts_truncated"] == 16
    sent = json.loads(fake.responses.parse.call_args.kwargs["input"])
    assert sent["context_limits"] == limits
    assert any(
        f["code"] == "context_truncated" and record["id"] in f["record_ids"]
        for f in client.get(f"/api/projects/{pid}/design").json()["findings"]
    )


def test_nested_evidence_versions_and_rejections_are_checked(client, monkeypatch):
    pid = project(client)
    _u, co, v, b = stages(client, pid, monkeypatch)
    outer = supporting_evidence(pid)
    inner = supporting_evidence(pid)
    with SessionLocal() as db:
        db.get(KnowledgeRecord, outer).payload = {"evidence_ids": [inner]}
        db.commit()
    proposal = {**validation(co["id"], v["id"], b["id"]), "evidence_ids": [outer]}
    provider(monkeypatch, [proposal])
    report = approve(
        client, pid, generate(client, pid, "validation").json()["records"][0]
    )
    assert report["payload"]["evidence_versions"] == {outer: 1, inner: 1}
    client.patch(
        f"/api/projects/{pid}/records/{inner}",
        json={"expected_version": 1, "status": "rejected"},
    )
    assert not client.get(f"/api/projects/{pid}/design").json()["readiness"][
        "validation"
    ]
    provider(monkeypatch, [proposal])
    response = generate(client, pid, "validation")
    assert response.status_code == 422, response.text


def test_evidence_changes_while_provider_runs_save_nothing(client, monkeypatch):
    from galvanise.agents.design_schemas import ValidationResult

    pid = project(client)
    _u, co, v, b = stages(client, pid, monkeypatch)
    eid = supporting_evidence(pid)
    proposal = {**validation(co["id"], v["id"], b["id"]), "evidence_ids": [eid]}
    fake = provider(monkeypatch, [proposal])

    async def change_evidence(**kwargs):
        with SessionLocal() as db:
            row = db.get(KnowledgeRecord, eid)
            row.description = "Changed while model runs"
            row.version += 1
            db.commit()
        return SimpleNamespace(
            status="completed",
            output_parsed=ValidationResult.model_validate({"records": [proposal]}),
        )

    fake.responses.parse.side_effect = change_evidence
    response = generate(client, pid, "validation")
    assert response.status_code == 409, response.text
    assert client.get(f"/api/projects/{pid}/design").json()["validations"] == []
