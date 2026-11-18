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
