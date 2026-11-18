import pytest
from parking_model import (
    CORRECTION_TEXT,
    DUPLICATE_RECEIPT_TEXT,
    FIXED_TARIFF_CODE,
    PARKING_TEXT,
    ParkingModel,
)

from galvanise.design_engine import pipeline


def source(text=PARKING_TEXT, chunk_id="parking"):
    return {
        "id": chunk_id,
        "text": text,
        "locator": {"kind": "upload", "path": "parking.md"},
    }


async def run(chunks=None, **kwargs):
    options = {
        "chunks": [source()] if chunks is None else chunks,
        "manifest": [],
        "base": None,
        "correction": None,
        "start_stage": "inventory",
        "checkpoint": None,
        "save_checkpoint": lambda stage, value: None,
    }
    return await pipeline.generate(**(options | kwargs))


@pytest.mark.asyncio
async def test_parking_walkthrough_tracks_contracts_and_predictions(monkeypatch):
    monkeypatch.setattr(pipeline, "call_model", ParkingModel())
    result = await run()
    components = {r["name"]: r["id"] for r in result["components"]}
    assert result["walkthroughs"][0]["use_case_id"] == result["use_cases"][0]["id"]
    assert any(s["dependency_id"] for s in result["walkthroughs"][0]["steps"])
    assert result["change_probes"][0]["predicted_edit_ids"] == [components["Pricing"]]
    assert not any(f["code"] == "duplicate_knowledge" for f in result["findings"])
    assert all(v["status"] == "observed" for v in result["volatilities"])
    assert all(item["id"] != "gate" for item in result["components"])


@pytest.mark.asyncio
async def test_correction_keeps_gate_and_conflicting_current_evidence(monkeypatch):
    model = ParkingModel()
    monkeypatch.setattr(pipeline, "call_model", model)
    base = await run()
    model.stages.clear()
    correction = {
        "id": "change",
        "text": CORRECTION_TEXT,
        "locator": {"kind": "message", "message_id": "m1", "role": "user"},
    }
    revised = await run(
        chunks=[source(), correction],
        base=base,
        start_stage="volatility",
        correction={"chunk_id": "change", "text": CORRECTION_TEXT},
    )
    assert model.stages == ["volatility", "boundaries", "walkthroughs", "review"]
    assert revised["implementation_findings"] == base["implementation_findings"]
    gate = next(c for c in base["components"] if c["name"] == "Gate access")
    assert gate in revised["components"]
    tariff = next(v for v in revised["volatilities"] if v["status"] == "user_confirmed")
    assert any(e["chunk_id"] == "change" for e in tariff["evidence"])


@pytest.mark.asyncio
async def test_retry_skips_completed_stages(monkeypatch):
    model = ParkingModel()
    monkeypatch.setattr(pipeline, "call_model", model)
    saves = {}

    def save(stage, checkpoint):
        saves[stage] = checkpoint
        if stage == "boundaries":
            raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        await run(save_checkpoint=save)
    model.stages.clear()
    result = await run(checkpoint=saves["boundaries"])
    assert model.stages == ["walkthroughs", "review"]
    assert result["components"] and result["walkthroughs"]


@pytest.mark.asyncio
async def test_fixed_tariff_and_independent_receipt(monkeypatch):
    monkeypatch.setattr(pipeline, "call_model", ParkingModel())
    fixed = await run([source(FIXED_TARIFF_CODE)])
    assert all(v["status"] == "hypothesis" for v in fixed["volatilities"])
    assert any(f["code"] == "low_evidence" for f in fixed["findings"])
    duplicate = await run([source(DUPLICATE_RECEIPT_TEXT)])
    assert {"duplicate_knowledge", "poor_containment"} <= {
        f["code"] for f in duplicate["findings"]
    }
    probe = duplicate["change_probes"][0]
    assert (
        len(probe["predicted_edit_ids"]) == 2 and len(probe["predicted_owner_ids"]) == 1
    )


async def altered(monkeypatch, transform, **options):
    provider = ParkingModel()

    async def call(stage, context):
        response = await provider(stage, context)
        transform(stage, context, response)
        return response

    monkeypatch.setattr(pipeline, "call_model", call)
    return await run(**options)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    ["exact", "allowlist", "source", "crossing", "operation", "owner", "duplicate"],
)
async def test_invalid_output_gets_one_targeted_repair(monkeypatch, invalid):
    attempts = []
    stages = {
        "exact": "inventory",
        "allowlist": "inventory",
        "source": "volatility",
        "crossing": "walkthroughs",
        "operation": "boundaries",
        "owner": "boundaries",
        "duplicate": "boundaries",
    }

    def inject(stage, context, response):
        if stage != stages[invalid]:
            return
        attempts.append(context.get("repair"))
        if invalid == "exact":
            response["actors"][0]["evidence"][0]["excerpt"] = "north charges hourly"
        elif invalid == "allowlist":
            response["actors"][0]["evidence"][0]["chunk_id"] = "excluded-source"
        elif invalid == "source":
            response["volatilities"][0]["status"] = "user_confirmed"
        elif invalid == "crossing":
            response["walkthroughs"][0]["steps"][0].update(
                operation_id=None, dependency_id=None, coverage_gap="Undeclared."
            )
        elif invalid == "operation":
            response["dependencies"][0]["operation_id"] = "missing-operation"
        elif invalid == "owner":
            response["components"][0]["owns"] = response["components"][1]["owns"]
        else:
            response["components"][1]["id"] = response["components"][0]["id"]

    with pytest.raises(ValueError, match="after one repair"):
        await altered(monkeypatch, inject)
    first, second = attempts
    assert first is None and second["diagnostics"] and second["previous_response"]


@pytest.mark.asyncio
async def test_repair_can_publish_and_null_question_alternatives(monkeypatch):
    def modify(stage, context, response):
        if stage == "volatility":
            decision = response["volatilities"][0]
            response["questions"] = [
                {
                    "id": "q",
                    "evidence": [],
                    "question": "Who chooses a tariff?",
                    "target_ids": [decision["id"]],
                    "alternatives": None,
                    "decision_impact": "Determines whether sites select a tariff.",
                }
            ]
            if "repair" not in context:
                response["questions"][0]["target_ids"] = ["unknown"]

    result = await altered(monkeypatch, modify)
    assert len(result["questions"]) == 1
    assert result["questions"][0]["target_ids"] == [result["volatilities"][0]["id"]]


@pytest.mark.asyncio
async def test_missing_case_allowed_with_explicit_gap(monkeypatch):
    def disclose(stage, context, response):
        if stage == "walkthroughs":
            case = response["walkthroughs"].pop()["use_case_id"]
            response["findings"].append(
                {
                    "id": "gap",
                    "code": "coverage_gap",
                    "target_ids": [case],
                    "severity": "warning",
                    "evidence": [],
                    "message": "The recovery contract is unresolved.",
                }
            )

    result = await altered(monkeypatch, disclose)
    assert result["walkthroughs"] == []
    assert result["findings"][0]["target_ids"] == [result["use_cases"][0]["id"]]


@pytest.mark.asyncio
async def test_inventory_covers_every_chunk_merging_equal_facts_and_exact_whitespace(
    monkeypatch,
):
    from galvanise.design_engine import context as retrieval

    monkeypatch.setattr(retrieval, "BATCH_CHARS", 1000)
    chunks = [source(PARKING_TEXT + " " * 650, f"page-{i}") for i in range(4)]

    def normalize(stage, context, response):
        if stage == "inventory":
            for row in response["implementation_findings"]:
                row["evidence"][0]["excerpt"] = row["evidence"][0]["excerpt"].replace(
                    " ", "\n\t"
                )

    snapshot = await altered(monkeypatch, normalize, chunks=chunks)
    assert len(snapshot["implementation_findings"]) == 3
    for observation in snapshot["implementation_findings"]:
        assert {c["chunk_id"] for c in observation["evidence"]} == {
            c["id"] for c in chunks
        }


@pytest.mark.asyncio
async def test_no_name_join_and_reviewer_can_address_structural_findings(monkeypatch):
    def revise(stage, context, response):
        if stage == "boundaries":
            component = response["components"][2]
            response["components"].append(
                component
                | {"id": "extra", "responsibility": "Print archived receipts."}
            )
        elif stage == "review":
            finding = next(
                f
                for f in context["prior"]["findings"]
                if f["code"] == "overdecomposition"
            )
            response["retire"] = [
                {
                    "id": finding["target_ids"][0],
                    "reason": "No archived receipt workflow exists.",
                }
            ]

    snapshot = await altered(monkeypatch, revise)
    assert len([c for c in snapshot["components"] if c["name"] == "Receipt"]) == 1
    assert any(f["code"] == "revision" for f in snapshot["findings"])
    assert not any(f["code"] == "overdecomposition" for f in snapshot["findings"])


@pytest.mark.asyncio
async def test_no_measurements_in_change_probes(monkeypatch):
    def measure(stage, context, response):
        if stage == "walkthroughs":
            response["change_probes"][0]["leaks"] = [
                {
                    "component_id": response["change_probes"][0]["predicted_owner_ids"][
                        0
                    ],
                    "reason": "Our benchmarks measured a 50% improvement.",
                }
            ]

    with pytest.raises(ValueError, match="predictions"):
        await altered(monkeypatch, measure)


@pytest.mark.asyncio
async def test_incompatible_checkpoint_restarts(monkeypatch):
    model = ParkingModel()
    monkeypatch.setattr(pipeline, "call_model", model)
    saved = {}
    result = await run(
        save_checkpoint=lambda stage, checkpoint: saved.update({stage: checkpoint})
    )
    model.stages.clear()
    duplicate = await run(
        chunks=[source(DUPLICATE_RECEIPT_TEXT)], checkpoint=saved["review"]
    )
    assert model.stages[0] == "inventory"
    assert result["findings"] != duplicate["findings"]


@pytest.mark.asyncio
async def test_reanalysis_rebuilds_from_selected_sources_without_losing_retained_ids(
    monkeypatch,
):
    from copy import deepcopy

    monkeypatch.setattr(pipeline, "call_model", ParkingModel())
    initial = await run([source(chunk_id="keep"), source(chunk_id="excluded")])
    old = deepcopy(initial)
    retained = await run([source(chunk_id="keep")], base=initial)
    assert [r["id"] for r in retained["components"]] == [
        r["id"] for r in old["components"]
    ]
    assert {
        c["chunk_id"]
        for r in retained["implementation_findings"]
        for c in r["evidence"]
    } == {"keep"}
    fixed = await run([source(FIXED_TARIFF_CODE, "fixed-code")], base=retained)
    assert all(v["status"] == "hypothesis" for v in fixed["volatilities"])
    assert {
        c["chunk_id"] for r in fixed["implementation_findings"] for c in r["evidence"]
    } == {"fixed-code"}
    assert initial == old


@pytest.mark.asyncio
async def test_correction_retires_superseded_goal_and_decision(monkeypatch):
    monkeypatch.setattr(pipeline, "call_model", ParkingModel())
    base = await run()
    old_case = base["use_cases"][0]["id"]
    old_price = base["volatilities"][0]["id"]
    note = {
        "id": "note",
        "text": CORRECTION_TEXT,
        "locator": {"kind": "message", "message_id": "m", "role": "user"},
    }

    def replace(stage, context, response):
        if stage == "use_cases":
            response["use_cases"][0].update(
                id="new-goal", outcome="Exit under a common tariff."
            )
            response["retire"] = [
                {"id": old_case, "reason": "Operator replaced the prior goal."}
            ]
        if stage == "volatility":
            response["volatilities"][0]["id"] = "shared-rule"
            response["retire"] = [
                {"id": old_price, "reason": "Operator specified a shared tariff."}
            ]
        if stage == "walkthroughs":
            response["retire"] = [
                {
                    "id": base["walkthroughs"][0]["id"],
                    "reason": "Trace the replacement goal.",
                },
                {
                    "id": base["change_probes"][0]["id"],
                    "reason": "Probe the shared rule.",
                },
            ]

    result = await altered(
        monkeypatch,
        replace,
        chunks=[source(), note],
        base=base,
        start_stage="use_cases",
        correction={"chunk_id": "note", "text": CORRECTION_TEXT},
    )
    assert old_case not in {r["id"] for r in result["use_cases"]}
    assert old_price not in {r["id"] for r in result["volatilities"]}
    assert result["walkthroughs"][0]["use_case_id"] == result["use_cases"][0]["id"]


@pytest.mark.asyncio
async def test_stage_cannot_cite_supplied_project_chunks_outside_call(monkeypatch):
    from galvanise.design_engine import context as retrieval

    material = [source(), source("An excluded original excerpt.", "other")]
    monkeypatch.setattr(retrieval, "RETRIEVAL_CHARS", len(PARKING_TEXT))

    def cite_excluded(stage, context, response):
        if stage == "volatility":
            assert "other" not in [c["id"] for c in context["chunks"]]
            response["volatilities"][0]["evidence"] = [
                {"chunk_id": "other", "excerpt": "An excluded original excerpt."}
            ]

    with pytest.raises(ValueError, match="after one repair"):
        await altered(monkeypatch, cite_excluded, chunks=material)


@pytest.mark.asyncio
async def test_stage_rejects_unexplained_review_changes(monkeypatch):
    def material_change(stage, context, response):
        if stage == "review":
            old = context["prior"]["components"][0]
            response["components"] = [old | {"responsibility": "Retain audit records."}]

    with pytest.raises(ValueError, match="revision finding"):
        await altered(monkeypatch, material_change)


@pytest.mark.asyncio
async def test_model_uses_design_override_and_structured_stage_output(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from galvanise.agents import client
    from galvanise.config import settings
    from galvanise.design_engine import model
    from galvanise.design_engine.schemas import Inventory

    monkeypatch.setattr(settings, "openai_api_key", "local-test")
    monkeypatch.setattr(settings, "openai_model", "")
    monkeypatch.setattr(settings, "design_model", "design-test")
    parse = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            output_parsed=Inventory(actors=[], implementation_findings=[]),
        )
    )
    connection = AsyncMock()
    connection.__aenter__.return_value = SimpleNamespace(
        responses=SimpleNamespace(parse=parse)
    )
    monkeypatch.setattr(client, "AsyncOpenAI", lambda **_: connection)
    output = await model.call_model("inventory", {"chunks": []})
    assert output == {"actors": [], "implementation_findings": []}
    request = parse.await_args.kwargs
    assert request["model"] == "design-test" and request["text_format"] is Inventory


def test_call_local_handles_round_trip_without_changing_evidence_text():
    from galvanise.design_engine.model import reference_aliases, translate

    source_id, owner_id, operation_id = "source-uuid", "contract-uuid", "operation-uuid"
    context = {
        "chunks": [{"id": source_id, "text": "contract-uuid appears in the source"}],
        "prior": {
            "contracts": [{"id": owner_id, "operations": [{"id": operation_id}]}]
        },
    }
    aliases = reference_aliases(context)
    encoded = translate(context, aliases)
    assert encoded["chunks"] == [
        {"id": "source_1", "text": "contract-uuid appears in the source"}
    ]
    result = {
        "operation_id": "op_1_1",
        "target_ids": ["contracts_1"],
        "evidence": [{"chunk_id": "source_1", "excerpt": "source_1"}],
    }
    decoded = translate(result, {name: identity for identity, name in aliases.items()})
    assert decoded == {
        "operation_id": operation_id,
        "target_ids": [owner_id],
        "evidence": [{"chunk_id": source_id, "excerpt": "source_1"}],
    }


@pytest.mark.asyncio
async def test_exception_flow_resolves_when_source_wraps_a_line(monkeypatch):
    def wrapped(stage, context, result):
        if stage == "walkthroughs":
            for step in result["walkthroughs"][0]["steps"]:
                if step["path"] != "main":
                    step["path"] = step["path"].replace(" ", "\n", 1)

    result = await altered(monkeypatch, wrapped)
    assert any("\n" in step["path"] for step in result["walkthroughs"][0]["steps"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy,approach",
    [
        (
            "Every site uses the same hourly formula. North sets its rate to two credits and South to five.",
            "Configure the site rate",
        ),
        (
            "Each site chooses its own charging formula.",
            "Encapsulate the formula in Pricing",
        ),
        (
            "North charges two credits and South charges five credits.",
            "Configure the site rate",
        ),
    ],
)
async def test_boundary_explains_the_evidenced_variation(monkeypatch, policy, approach):
    from parking_model import AMBIGUOUS, PARKING_POLICY

    monkeypatch.setattr(pipeline, "call_model", ParkingModel())
    snapshot = await run([source(PARKING_TEXT.replace(PARKING_POLICY, policy))])
    decision = snapshot["volatilities"][0]
    why = decision["explanation"]
    assert why["approach"] == approach
    assert why["evidence"] == [{"chunk_id": "parking", "excerpt": policy}]
    assert why["owner_id"] == next(
        c["id"] for c in snapshot["components"] if decision["id"] in c["owns"]
    )
    assert [a["hypothetical"] for a in decision["alternatives"]] == [
        "hourly" not in policy,
        True,
    ]
    assert bool(why["uncertainty"]) == (policy == AMBIGUOUS)
    if why["uncertainty"]:
        assert snapshot["questions"][0]["target_ids"] == [decision["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["missing", "owner", "decision", "citation", "duplicate"]
)
async def test_invalid_boundary_explanation_cannot_publish(monkeypatch, fault):
    def damage(stage, context, response):
        if stage != "boundaries":
            return
        rows = response["explanations"]
        if fault == "missing":
            rows.pop()
        elif fault == "owner":
            rows[0]["owner_id"] = rows[1]["owner_id"]
        elif fault == "decision":
            rows[0]["volatility_id"] = "unknown"
        elif fault == "citation":
            rows[0]["evidence"][0]["excerpt"] = "Fabricated source."
        else:
            rows.append(rows[0])

    with pytest.raises(ValueError, match="boundaries failed validation"):
        await altered(monkeypatch, damage)


@pytest.mark.asyncio
async def test_reanalysis_preserves_answers_only_with_their_selected_source(
    monkeypatch,
):
    from parking_model import AMBIGUOUS, FORMULA, PARKING_POLICY, QUESTION

    monkeypatch.setattr(pipeline, "call_model", ParkingModel())
    brief = source(PARKING_TEXT.replace(PARKING_POLICY, AMBIGUOUS))
    base = await run([brief])
    decision = base["volatilities"][0]["id"]
    note = {
        "id": "answer",
        "text": FORMULA,
        "locator": {"kind": "message", "message_id": "msg", "role": "user"},
    }
    revised = await run(
        [brief, note],
        base=base,
        start_stage="volatility",
        correction={
            "chunk_id": "answer",
            "text": FORMULA,
            "decision_id": decision,
            "question_id": base["questions"][0]["id"],
            "base_revision_id": "original",
            "question": QUESTION,
        },
    )
    included = await run([brief, note], base=revised)
    excluded = await run([brief], base=revised)
    assert included["volatilities"][0]["id"] == decision
    assert (
        included["volatilities"][0]["answers"] == revised["volatilities"][0]["answers"]
    )
    assert not excluded["volatilities"][0]["answers"]


@pytest.mark.asyncio
async def test_receipt_cannot_be_an_unchanged_consumer_and_a_rule_leak(monkeypatch):
    def contradict(stage, context, response):
        if stage == "walkthroughs":
            probe = response["change_probes"][0]
            probe["leaks"] = [
                probe["consumers"][0]
                | {"reason": "Receipt duplicates the calculation."}
            ]

    with pytest.raises(ValueError, match="unchanged consumer"):
        await altered(monkeypatch, contradict)


@pytest.mark.asyncio
async def test_historical_snapshot_without_explanations_can_start_a_revision(
    monkeypatch,
):
    monkeypatch.setattr(pipeline, "call_model", ParkingModel())
    historical = await run()
    for decision in historical["volatilities"]:
        del decision["explanation"]
        del decision["answers"]
    for probe in historical["change_probes"]:
        del probe["consumers"]
    revised = await run(base=historical, start_stage="boundaries")
    assert all(d["explanation"] for d in revised["volatilities"])
    assert all("explanation" not in d for d in historical["volatilities"])


@pytest.mark.asyncio
async def test_unassigned_decision_keeps_its_ownership_gap(monkeypatch):
    def unassign(stage, context, response):
        if stage == "boundaries":
            decision = response["explanations"].pop(0)["volatility_id"]
            for component in response["components"]:
                component["owns"] = [v for v in component["owns"] if v != decision]
            response["findings"].append(
                {
                    "id": "gap",
                    "code": "ownership_gap",
                    "evidence": [],
                    "severity": "warning",
                    "target_ids": [decision],
                    "message": "The brief leaves charge ownership open.",
                }
            )
        if stage == "walkthroughs":
            response["change_probes"][0]["predicted_owner_ids"] = []

    snapshot = await altered(monkeypatch, unassign)
    decision = snapshot["volatilities"][0]
    assert decision["explanation"] is None
    assert any(
        f["code"] == "ownership_gap" and f["target_ids"] == [decision["id"]]
        for f in snapshot["findings"]
    )
