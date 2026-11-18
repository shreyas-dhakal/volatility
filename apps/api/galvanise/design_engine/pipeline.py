"""Versioned design reasoning. Persistence owns the transaction and publication."""

import hashlib
import json
from copy import deepcopy

from .context import Chunk, Correction, context_for, inventory_batches, relevant_chunks
from .model import call_model
from .prompts import STAGES
from .records import COLLECTIONS, reuse_candidates, upsert, with_candidates
from .schemas import Snapshot
from .validation import (
    check_evidence,
    check_links,
    review_checks,
    review_reasons,
    user_message,
)


def signature(chunks, manifest, base, correction, start_stage):
    data = [1, chunks, manifest, base, correction, start_stage]
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def remove_previous_checks(snapshot):
    generated = {f["id"] for f in review_checks(snapshot)}
    snapshot["findings"] = [f for f in snapshot["findings"] if f["id"] not in generated]


def check_final(candidate, chunks, correction):
    check_evidence({field: candidate[field] for field in COLLECTIONS}, chunks)
    if correction:
        cited = any(
            c["chunk_id"] == correction["chunk_id"]
            for field in COLLECTIONS
            for row in candidate[field]
            for c in row["evidence"]
        )
        if not cited:
            raise ValueError(
                "Cite the correction message in the affected record or explain its impact in a finding."
            )
    Snapshot.model_validate(candidate)


async def run_call(stage, snapshot, context, all_chunks, correction, catalog):
    schema, _ = STAGES[stage]
    diagnostics = []
    request = context
    for _ in range(2):
        raw = None
        try:
            raw = await call_model(stage, request)
            changes = schema.model_validate(raw).model_dump()
            check_evidence(changes, context["chunks"])
            candidate = upsert(snapshot, changes, catalog)
            if stage == "review":
                review_reasons(snapshot, candidate)
                previous_checks = {f["id"] for f in review_checks(snapshot)}
                candidate["findings"] = [
                    f for f in candidate["findings"] if f["id"] not in previous_checks
                ]
                candidate["findings"].extend(review_checks(candidate))
                check_final(candidate, all_chunks, correction)
            check_links(candidate, stage)
            return candidate
        except ValueError as exc:
            diagnostics.append(str(exc))
            request = {
                **context,
                "repair": {
                    "instruction": "Return a corrected response for this stage only. Resolve these validation errors.",
                    "diagnostics": str(exc),
                    "previous_response": raw,
                },
            }
    raise ValueError(
        f"{stage} failed validation after one repair. " + " | ".join(diagnostics)
    )


async def generate(
    *, chunks, manifest, base, correction, start_stage, checkpoint, save_checkpoint
):
    """Return a new validated snapshot, resuming only a checkpoint from the same inputs."""
    if start_stage not in {"inventory", "use_cases", "volatility", "boundaries"}:
        raise ValueError(f"Unknown starting stage {start_stage!r}.")
    if base is None and start_stage != "inventory":
        raise ValueError("A partial run requires a base revision.")
    chunks = [Chunk.model_validate(c).model_dump() for c in chunks]
    if len({c["id"] for c in chunks}) != len(chunks):
        raise ValueError("Duplicate input chunk IDs.")
    if correction:
        correction = Correction.model_validate(correction).model_dump()
        if not any(
            c["id"] == correction["chunk_id"]
            and user_message(c)
            and correction["text"] in c["text"]
            for c in chunks
        ):
            raise ValueError(
                "The correction must reference text from an authorized user message."
            )
    fingerprint = signature(chunks, manifest, base, correction, start_stage)
    fresh = start_stage == "inventory" and not correction
    base = Snapshot.model_validate(base).model_dump() if base is not None else None
    candidates = reuse_candidates(base, chunks) if base and fresh else None
    order = list(STAGES)
    start = order.index(start_stage)
    if (
        checkpoint
        and checkpoint.get("signature") == fingerprint
        and checkpoint.get("completed_stage") in order[start:]
    ):
        snapshot = Snapshot.model_validate(checkpoint["snapshot"]).model_dump()
        completed = checkpoint["completed_stage"]
        check_links(snapshot, completed)
        start = order.index(completed) + 1
    else:
        snapshot = (
            base if base is not None and not fresh else {f: [] for f in COLLECTIONS}
        )
        snapshot["manifest"] = deepcopy(manifest)
        snapshot["analysis_type"] = "design_analysis"
        if base and not fresh:
            remove_previous_checks(snapshot)

    for stage in order[start:]:
        if stage == "review":
            snapshot["findings"].extend(review_checks(snapshot))
        if stage == "inventory":
            batches = inventory_batches(chunks)
        else:
            batches = [relevant_chunks(stage, chunks, snapshot, correction)]
        for batch in batches:
            identities = None if stage == "review" else candidates
            catalog = with_candidates(
                snapshot, identities, STAGES[stage][0].model_fields
            )
            context = context_for(stage, catalog, batch, correction)
            if identities:
                context["reanalyze"] = (
                    "Return this stage's complete output from selected evidence. Prior IDs are for matching meaning only."
                )
            snapshot = await run_call(
                stage, snapshot, context, chunks, correction, catalog
            )
        save_checkpoint(
            stage,
            {
                "completed_stage": stage,
                "signature": fingerprint,
                "snapshot": deepcopy(snapshot),
            },
        )
    check_final(snapshot, chunks, correction)
    return Snapshot.model_validate(snapshot).model_dump()
