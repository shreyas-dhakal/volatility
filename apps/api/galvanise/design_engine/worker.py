"""Claim durable runs with a renewable lease and fence every write by claim token."""

import asyncio
import re
from contextlib import suppress
from datetime import timedelta

from fastapi import HTTPException
from httpx import HTTPError, HTTPStatusError
from openai import APIError, APIStatusError
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from galvanise.database import SessionLocal
from galvanise.design_engine.service import head_id, in_project
from galvanise.design_engine.sources import evidence, initial_sources, store_message
from galvanise.models import (
    DesignHead,
    DesignRevision,
    DesignRun,
    IngestionJob,
    now,
    uid,
)
from galvanise.services.ingestion import redact

LEASE = timedelta(minutes=3)
STAGES = (
    "inventory",
    "use_cases",
    "volatility",
    "boundaries",
    "walkthroughs",
    "review",
)


class LostClaim(Exception):
    pass


class StaleHead(Exception):
    pass


def available():
    # Uploads submitted immediately before "Design system" may still be parsing.
    # Wait in the queue without occupying a worker or freezing incomplete inputs.
    extracting = (
        select(IngestionJob.id)
        .where(
            IngestionJob.project_id == DesignRun.project_id,
            IngestionJob.created_at <= DesignRun.created_at,
            IngestionJob.status.in_(("queued", "running")),
        )
        .exists()
    )
    return or_(
        and_(
            DesignRun.status == "queued",
            or_(DesignRun.operation != "analyze", ~extracting),
        ),
        and_(DesignRun.status == "running", DesignRun.lease_until <= now()),
    )


def claim():
    with SessionLocal() as db:
        run_id = db.scalar(
            select(DesignRun.id)
            .where(available())
            .order_by(DesignRun.created_at, DesignRun.id)
            .limit(1)
        )
        if run_id is None:
            return None
        token = uid()
        acquired = db.execute(
            update(DesignRun)
            .where(DesignRun.id == run_id, available())
            .values(status="running", claim_token=token, lease_until=now() + LEASE)
        )
        db.commit()
        return (run_id, token) if acquired.rowcount == 1 else None


def fenced(db, run_id, token, **values):
    updated = db.execute(
        update(DesignRun)
        .where(
            DesignRun.id == run_id,
            DesignRun.status == "running",
            DesignRun.claim_token == token,
        )
        .values(**values)
    )
    if updated.rowcount != 1:
        raise LostClaim()


def prepare(run_id, token):
    with SessionLocal() as db:
        fenced(db, run_id, token, lease_until=now() + LEASE)
        run = db.get(DesignRun, run_id)
        if head_id(db, run.project_id) != run.base_revision_id:
            raise StaleHead()
        parent = (
            in_project(db, DesignRevision, run.project_id, run.base_revision_id)
            if run.base_revision_id
            else None
        )
        if run.source_ids is None:
            if run.operation == "revise":
                correction_id = store_message(
                    db, run.project_id, run.request_json["correction_message_id"]
                )
                ids = list(dict.fromkeys([*parent.source_ids, correction_id]))
            else:
                ids = initial_sources(db, run.project_id, run.request_json)
            run.source_ids = ids
        db.flush()
        chunks, manifest = evidence(db, run.project_id, run.source_ids)
        correction = None
        if run.operation == "revise":
            message_id = run.request_json["correction_message_id"]
            matches = [
                c for c in chunks if c["locator"].get("message_id") == message_id
            ]
            if not matches:
                raise ValueError("Correction has no extractable text")
            correction = {"chunk_id": matches[0]["id"], "text": matches[0]["text"]}
            if "question_id" in run.request_json:
                question = next(
                    q
                    for q in parent.snapshot_json["questions"]
                    if q["id"] == run.request_json["question_id"]
                )
                correction.update(
                    question_id=question["id"],
                    question=question["question"],
                    decision_id=run.request_json["decision_id"],
                    base_revision_id=parent.id,
                )
        arguments = {
            "chunks": chunks,
            "manifest": manifest,
            # A new selection may explicitly exclude an earlier source. Its
            # prior observations and quotations must not enter model context.
            "base": parent.snapshot_json
            if parent and set(parent.source_ids).issubset(run.source_ids)
            else None,
            "correction": correction,
            "start_stage": run.start_stage,
            "checkpoint": run.checkpoint_json,
        }
        if (
            parent
            and not arguments["base"]
            and set(parent.source_ids).intersection(run.source_ids)
        ):
            from .records import identity_hints

            hints = identity_hints(parent.snapshot_json, chunks)
            if hints:
                arguments["prior_ids"] = hints
        db.commit()
        return arguments


def save(run_id, token, stage, checkpoint):
    next_stage = STAGES[min(STAGES.index(stage) + 1, len(STAGES) - 1)]
    with SessionLocal() as db:
        fenced(
            db,
            run_id,
            token,
            stage=next_stage,
            checkpoint_json=checkpoint,
            lease_until=now() + LEASE,
        )
        db.commit()


def revision_diff(before, after, reason):
    result = {"added": [], "changed": [], "removed": []}
    explanations = {}
    for finding in after.get("findings", []):
        if finding.get("code") == "revision":
            for target in finding.get("target_ids", []):
                explanations[target] = finding["message"]
            retired = re.match(r"Retired ([^.]+)\. (.+)", finding.get("message", ""))
            if retired:
                explanations[retired[1]] = retired[2]
    for collection in sorted(set(after) | set(before)):
        if collection == "manifest":
            continue
        old_rows, new_rows = before.get(collection, []), after.get(collection, [])
        if not isinstance(old_rows, list) or not isinstance(new_rows, list):
            continue
        old = {
            row["id"]: row for row in old_rows if isinstance(row, dict) and "id" in row
        }
        new = {
            row["id"]: row for row in new_rows if isinstance(row, dict) and "id" in row
        }
        for key in sorted(old.keys() | new.keys()):
            if key not in new:
                kind, detail = "removed", "Removed from the revised proposal"
            elif key not in old:
                kind, detail = "added", "Introduced by the analysis"
            elif old[key] != new[key]:
                fields = sorted(
                    k
                    for k in old[key].keys() | new[key].keys()
                    if old[key].get(k) != new[key].get(k)
                )
                kind, detail = "changed", "Updated " + ", ".join(fields)
            else:
                continue
            result[kind].append(
                {
                    "collection": collection,
                    "id": key,
                    "reason": f"{detail}. {explanations.get(key, reason)}",
                }
            )
    return result


def publish(run_id, token, snapshot, arguments):
    with SessionLocal() as db:
        fenced(db, run_id, token, lease_until=now() + LEASE)
        run = db.get(DesignRun, run_id)
        reason = "Generated from the selected project evidence."
        if arguments["correction"]:
            reason = f"User correction: {arguments['correction']['text'][:300]}"
        previous = (
            in_project(
                db, DesignRevision, run.project_id, run.base_revision_id
            ).snapshot_json
            if run.base_revision_id
            else {}
        )
        revision = DesignRevision(
            project_id=run.project_id,
            parent_revision_id=run.base_revision_id,
            snapshot_json=snapshot,
            diff_json=revision_diff(previous, snapshot, reason),
            source_ids=run.source_ids,
        )
        db.add(revision)
        db.flush()
        changed = db.execute(
            update(DesignHead)
            .where(
                DesignHead.project_id == run.project_id,
                DesignHead.current_revision_id == run.base_revision_id,
            )
            .values(current_revision_id=revision.id)
        )
        if changed.rowcount != 1:
            raise StaleHead()  # rolls back the candidate revision too
        run.status, run.revision_id, run.stage = "completed", revision.id, "review"
        run.claim_token = run.lease_until = run.error = None
        db.commit()


def failure_message(exc):
    # Provider errors may quote response bodies, and DB errors may contain a
    # complete snapshot as bound parameters. Keep only safe operational detail.
    name = type(exc).__name__
    if isinstance(exc, (APIStatusError, HTTPStatusError)):
        return f"{name}: Model service returned HTTP {exc.response.status_code}."
    if isinstance(exc, (APIError, HTTPError)):
        return f"{name}: Model service request failed."
    if isinstance(exc, SQLAlchemyError):
        return f"{name}: Design persistence failed."
    if isinstance(exc, HTTPException):
        return f"{name}: Request failed (HTTP {exc.status_code})."
    if isinstance(exc, ValueError):
        return redact(f"{name}: {exc}")[:16000]
    return f"{name}: Design generation failed."


def record_failure(run_id, token, status, message):
    with SessionLocal() as db:
        fenced(
            db,
            run_id,
            token,
            lease_until=None,
            claim_token=None,
            status=status,
            error=message,
        )
        run = db.get(DesignRun, run_id)
        run.diagnostics = [
            *run.diagnostics,
            {
                "stage": run.stage,
                "status": status,
                "error": message,
                "at": now().isoformat(),
            },
        ]
        db.commit()


async def heartbeat(run_id, token):
    while True:
        await asyncio.sleep(LEASE.total_seconds() / 3)
        with SessionLocal() as db:
            fenced(db, run_id, token, lease_until=now() + LEASE)
            db.commit()


async def generate(**arguments):
    from galvanise.design_engine.pipeline import generate

    return await generate(**arguments)


async def execute(run_id, token):
    pulse = asyncio.create_task(heartbeat(run_id, token))
    try:
        arguments = prepare(run_id, token)
        if not arguments["chunks"]:
            raise ValueError("No readable evidence in the selected sources")
        snapshot = await generate(
            **arguments,
            save_checkpoint=lambda stage, data: save(run_id, token, stage, data),
        )
        publish(run_id, token, snapshot, arguments)
    except LostClaim:
        pass
    except StaleHead:
        with suppress(LostClaim):
            record_failure(
                run_id,
                token,
                "stale",
                "A newer revision was published. Retry against the current revision.",
            )
    except Exception as exc:  # noqa: BLE001 - persist failures at the job boundary
        with suppress(LostClaim):
            record_failure(
                run_id,
                token,
                "failed",
                failure_message(exc),
            )
    finally:
        pulse.cancel()
        with suppress(asyncio.CancelledError, LostClaim):
            await pulse


def process_next_run():
    claimed = claim()
    if claimed:
        asyncio.run(execute(*claimed))
    return bool(claimed)


def consume(stop):
    while not stop.is_set():
        try:
            if not process_next_run():
                stop.wait(1)
        except Exception:  # noqa: BLE001 - keep the durable consumer alive
            # A database outage or process restart releases the run by lease expiry.
            stop.wait(2)
