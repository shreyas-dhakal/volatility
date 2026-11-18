"""Project-authorized entry points shared by HTTP and chat."""

import re
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select, update

from galvanise.dependencies import require_project
from galvanise.design_engine.records import persistent_id
from galvanise.design_engine.sources import (
    insert_once,
    scoped,
    user_message,
    validate_selection,
)
from galvanise.models import (
    Conversation,
    DesignChunk,
    DesignHead,
    DesignPlan,
    DesignRevision,
    DesignRun,
    DesignSource,
    Message,
)


def in_project(db, model, project_id, object_id):
    value = db.scalar(scoped(db, model, project_id).where(model.id == object_id))
    if value is None:
        raise HTTPException(404, "Design record not found")
    return value


def run_view(run):
    return {
        key: getattr(run, key)
        for key in (
            "id",
            "status",
            "operation",
            "stage",
            "error",
            "base_revision_id",
            "revision_id",
            "diagnostics",
            "created_at",
            "updated_at",
        )
    }


def revision_view(row):
    return {
        "id": row.id,
        "parent_revision_id": row.parent_revision_id,
        "snapshot": row.snapshot_json,
        "diff": row.diff_json,
        "created_at": row.created_at,
    }


def plan_view(row):
    return {
        "id": row.id,
        "revision_id": row.revision_id,
        "input": row.input_json,
        "result": row.result_json,
    }


def head_id(db, project_id):
    return db.scalar(
        select(DesignHead.current_revision_id).where(
            DesignHead.project_id == project_id
        )
    )


def current_revision(db, project_id, user):
    require_project(project_id, db, user)
    row = db.scalar(
        scoped(db, DesignRevision, project_id)
        .join(DesignHead, DesignHead.current_revision_id == DesignRevision.id)
        .where(DesignHead.project_id == project_id)
    )
    return revision_view(row) if row else None


def overview(db, project_id, user):
    revision = current_revision(db, project_id, user)
    run = db.scalar(
        scoped(db, DesignRun, project_id)
        .order_by(DesignRun.created_at.desc(), DesignRun.id.desc())
        .limit(1)
    )
    plan = None
    if revision:
        plan = db.scalar(
            scoped(db, DesignPlan, project_id)
            .where(DesignPlan.revision_id == revision["id"])
            .order_by(DesignPlan.created_at.desc(), DesignPlan.id.desc())
            .limit(1)
        )
    return {
        "revision": revision,
        "run": run_view(run) if run else None,
        "plan": plan_view(plan) if plan else None,
    }


def get_revision(db, project_id, user, revision_id):
    require_project(project_id, db, user)
    return revision_view(in_project(db, DesignRevision, project_id, revision_id))


def get_chunk(db, project_id, user, chunk_id):
    require_project(project_id, db, user)
    row = db.scalar(
        select(DesignChunk)
        .join(DesignSource)
        .where(DesignSource.project_id == project_id, DesignChunk.id == chunk_id)
    )
    if row is None:
        raise HTTPException(404, "Evidence chunk not found")
    return {"id": row.id, "locator": row.locator_json, "text": row.text}


def correction_stage(text):
    text = text.lower()
    if re.search(
        r"\b(goal|objective|purpose|use[ -]?case|business outcome|actor|main flow|trigger)s?\b",
        text,
    ):
        return "use_cases"
    # If both a policy and its contract change, recompute volatility first.
    if re.search(
        r"\b(tariff|polic(?:y|ies)|varies|variation|assumption|pricing rule|vendor)s?\b",
        text,
    ):
        return "volatility"
    if re.search(
        r"\b(contract|interface|operation|caller|callee|boundary|boundaries|input|output|failure mode|component)s?\b",
        text,
    ):
        return "boundaries"
    return "volatility"


def enqueue(db, project_id, operation, key, request, stage):
    if not isinstance(key, str) or not key.strip() or len(key) > 256:
        raise HTTPException(422, "Provide an idempotency key of 1 to 256 characters")
    request_lookup = scoped(db, DesignRun, project_id).where(
        DesignRun.idempotency_key == key
    )

    def existing(row):
        if row.operation != operation or row.request_json != request:
            raise HTTPException(409, "Idempotency key belongs to a different request")
        return run_view(row)

    previous = db.scalar(request_lookup)
    if previous:
        return existing(previous)
    # The singleton row exists even before the first publication. A conditional
    # UPDATE from NULL can therefore elect exactly one initial revision.
    insert_once(db, DesignHead, {"project_id": project_id}, ["project_id"])
    base = head_id(db, project_id)
    if operation == "revise" and base != request["base_revision_id"]:
        # Another process may have accepted this same request in the meantime.
        previous = db.scalar(request_lookup)
        if previous:
            return existing(previous)
        raise HTTPException(409, "Base revision changed; use the current revision")
    insert_once(
        db,
        DesignRun,
        {
            "project_id": project_id,
            "base_revision_id": base,
            "idempotency_key": key,
            "operation": operation,
            "request_json": request,
            "status": "queued",
            "stage": stage,
            "start_stage": stage,
        },
        ["project_id", "idempotency_key"],
    )
    row = db.scalar(request_lookup)
    result = existing(row)
    db.commit()
    return result


def analyze_design(
    db,
    project_id,
    user,
    *,
    idempotency_key,
    selected_upload_ids=None,
    request_message_id=None,
):
    require_project(project_id, db, user)
    selected = None if selected_upload_ids is None else sorted(set(selected_upload_ids))
    validate_selection(db, project_id, selected)
    if request_message_id is not None:
        user_message(db, project_id, request_message_id)
    return enqueue(
        db,
        project_id,
        "analyze",
        idempotency_key,
        {"selected_upload_ids": selected, "request_message_id": request_message_id},
        "inventory",
    )


def answer_question(
    db,
    project_id,
    user,
    *,
    base_revision_id,
    question_id,
    decision_id,
    answer,
    idempotency_key,
):
    require_project(project_id, db, user)
    answer = answer.strip()
    if not answer:
        raise HTTPException(422, "Enter an answer")
    # Both inserts and enqueue share a transaction. A lost HTTP response or two
    # simultaneous submissions with the same key create one message and one run.
    conversation_id = persistent_id("decision-conversation", project_id)
    message_id = persistent_id("decision-answer", project_id + "/" + idempotency_key)
    insert_once(
        db,
        Conversation,
        {"id": conversation_id, "project_id": project_id, "title": "Design decisions"},
        ["id"],
    )
    insert_once(
        db,
        Message,
        {
            "id": message_id,
            "conversation_id": conversation_id,
            "project_id": project_id,
            "role": "user",
            "content": answer,
        },
        ["id"],
    )
    if user_message(db, project_id, message_id).content != answer:
        raise HTTPException(409, "Idempotency key belongs to a different answer")
    return revise_design(
        db,
        project_id,
        user,
        base_revision_id=base_revision_id,
        correction_message_id=message_id,
        idempotency_key=idempotency_key,
        question_id=question_id,
        decision_id=decision_id,
    )


def revise_design(
    db,
    project_id,
    user,
    *,
    base_revision_id,
    correction_message_id,
    idempotency_key,
    question_id=None,
    decision_id=None,
):
    require_project(project_id, db, user)
    revision = in_project(db, DesignRevision, project_id, base_revision_id)
    target = {}
    if question_id is not None:
        snapshot = revision.snapshot_json
        question = next(
            (q for q in snapshot["questions"] if q["id"] == question_id), None
        )
        if (
            not question
            or decision_id not in question["target_ids"]
            or not any(v["id"] == decision_id for v in snapshot["volatilities"])
        ):
            raise HTTPException(
                422,
                "This question does not target the decision in the selected revision",
            )
        target = {"question_id": question_id, "decision_id": decision_id}
    message = user_message(db, project_id, correction_message_id)
    return enqueue(
        db,
        project_id,
        "revise",
        idempotency_key,
        {
            "base_revision_id": base_revision_id,
            "correction_message_id": message.id,
            **target,
        },
        "volatility" if target else correction_stage(message.content),
    )


def retry(db, project_id, user, run_id):
    require_project(project_id, db, user)
    run = in_project(db, DesignRun, project_id, run_id)
    if run.status in {"running", "queued", "completed"}:
        return run_view(run)
    current = head_id(db, project_id)
    if current != run.base_revision_id:
        # A stale run and its checkpoints belong to the original baseline.
        # Record the rerun as a new request and keep that history intact.
        key = f"retry/{run.id}/{current}"
        if run.operation == "revise":
            return revise_design(
                db,
                project_id,
                user,
                base_revision_id=current,
                **{
                    k: v for k, v in run.request_json.items() if k != "base_revision_id"
                },
                idempotency_key=key,
            )
        return analyze_design(
            db, project_id, user, **run.request_json, idempotency_key=key
        )
    db.execute(
        update(DesignRun)
        .where(DesignRun.id == run.id, DesignRun.status == "failed")
        .values(status="queued", error=None)
    )
    db.commit()
    db.refresh(run)
    return run_view(run)


def calculate_plan(snapshot, planning_inputs):
    from galvanise.design_engine.planning import plan

    return plan(snapshot, planning_inputs)


def plan_project(db, project_id, user, *, revision_id, planning_inputs):
    require_project(project_id, db, user)
    revision = in_project(db, DesignRevision, project_id, revision_id)
    try:
        result = calculate_plan(
            deepcopy(revision.snapshot_json), deepcopy(planning_inputs)
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = DesignPlan(
        project_id=project_id,
        revision_id=revision_id,
        input_json=planning_inputs,
        result_json=result,
    )
    db.add(row)
    db.commit()
    return plan_view(row)
