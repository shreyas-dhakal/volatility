"""Authenticated workflow migration actions and artifacts for a saved revision."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from galvanise.database import get_db
from galvanise.dependencies import get_current_user, require_project
from galvanise.migration import agent, runner
from galvanise.migration.compare import compare, field_rule, rules_for, safe_mapping
from galvanise.migration.evidence import discover
from galvanise.migration.schemas import AcceptPatch, Approval, Enqueue, Selection, Suite
from galvanise.models import (
    DesignRevision,
    User,
    WorkflowAcceptedPatch,
    WorkflowBaseline,
    WorkflowMigration,
    WorkflowMigrationJob,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/workflow-migrations/{revision_id}/{operation_id}",
    tags=["workflow-migration"],
)
Database = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def resolve(db, user, project_id, revision_id, operation_id):
    project = require_project(project_id, db, user)
    revision = db.get(DesignRevision, revision_id)
    if (
        project.system_type != "existing"
        or not revision
        or revision.project_id != project.id
    ):
        raise HTTPException(404, "Saved legacy workflow not found.")
    snapshot = revision.snapshot_json
    use_case = next(
        (
            x
            for x in snapshot.get("use_cases", [])
            if x["id"] == operation_id
            and x.get("basis") == "observed"
            and x.get("evidence")
        ),
        None,
    )
    finding = next(
        (
            x
            for x in snapshot.get("implementation_findings", [])
            if x["id"] == operation_id
            and x.get("kind") in ("workflow", "implementation")
            and x.get("evidence")
        ),
        None,
    )
    if use_case:
        operation = {
            **use_case,
            "walkthroughs": [
                x
                for x in snapshot.get("walkthroughs", [])
                if x["use_case_id"] == operation_id
            ],
        }
    elif finding:
        operation = {**finding, "name": finding["title"]}
    else:
        raise HTTPException(404, "Saved legacy workflow not found.")
    migration = db.scalar(
        select(WorkflowMigration).where(
            WorkflowMigration.project_id == project_id,
            WorkflowMigration.revision_id == revision.id,
            WorkflowMigration.operation_id == operation_id,
        )
    )
    return revision, operation, migration


def commit(db):
    try:
        db.commit()
    except (IntegrityError, StaleDataError) as exc:
        db.rollback()
        raise HTTPException(
            409, "The migration changed in another session. Reload it and retry."
        ) from exc


def baseline_for(db, migration):
    if migration:
        return db.scalar(
            select(WorkflowBaseline).where(
                WorkflowBaseline.migration_id == migration.id
            )
        )
    return None


def serialize(job):
    return {
        "id": job.id,
        "action": job.action,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "error": job.error,
        "target": (job.input_json.get("replacement") or {}).get("target"),
        "result_available": job.result_json is not None,
    }


def job_for(db, migration, job_id):
    job = db.get(WorkflowMigrationJob, job_id)
    if (
        not migration
        or not job
        or job.migration_id != migration.id
        or job.project_id != migration.project_id
    ):
        raise HTTPException(404, "Migration job not found.")
    return job


@router.get("")
def overview(
    project_id: str,
    revision_id: str,
    operation_id: str,
    db: Database,
    user: CurrentUser,
):
    _, op, migration = resolve(db, user, project_id, revision_id, operation_id)
    baseline = baseline_for(db, migration)
    jobs, accepted = [], []
    if migration:
        jobs = list(
            db.scalars(
                select(WorkflowMigrationJob)
                .where(WorkflowMigrationJob.migration_id == migration.id)
                .order_by(WorkflowMigrationJob.created_at.desc())
                .limit(30)
            )
        )
        accepted = list(
            db.scalars(
                select(WorkflowAcceptedPatch)
                .where(WorkflowAcceptedPatch.migration_id == migration.id)
                .order_by(WorkflowAcceptedPatch.created_at.desc())
            )
        )
    gaps = []
    try:
        config = runner.operator_config(project_id)
    except runner.SetupGap as exc:
        config = {}
        gaps.append(str(exc))
    if not config.get("legacy"):
        gaps.append(
            "Register the project legacy Git ref and replay adapter with the API operator."
        )
    if not migration or not migration.selection_json.get("writes"):
        gaps.append("Find and select at least one source-backed write.")
    if not migration or not migration.scenarios_json:
        gaps.append("Generate or enter behavior scenarios before running legacy.")
    return {
        "workflow": op["name"],
        "selection": (
            {
                k: v
                for k, v in migration.selection_json.items()
                if k not in ("chunks", "manifest")
            }
            if migration
            else {}
        ),
        "scenarios": migration.scenarios_json if migration else [],
        "baseline": (
            {
                "id": baseline.id,
                "source_commit": baseline.artifact_json["source_commit"],
            }
            if baseline
            else None
        ),
        "jobs": [serialize(job) for job in jobs],
        "targets": [
            {
                "name": name,
                "draft_pr_configured": bool(
                    value.get("github_remote") and value.get("github_base")
                ),
            }
            for name, value in config.get("targets", {}).items()
            if isinstance(value, dict)
        ],
        "accepted": [
            {"job_id": item.job_id, "reason": item.reason} for item in accepted
        ],
        "setup": gaps,
    }


@router.get("/sources")
def sources(
    project_id: str,
    revision_id: str,
    operation_id: str,
    db: Database,
    user: CurrentUser,
    query: Annotated[str, Query(max_length=160)] = "",
):
    revision, operation, migration = resolve(
        db, user, project_id, revision_id, operation_id
    )
    selection = migration.selection_json if migration else {}
    previous = selection.get("writes", [])
    found = discover(
        db, revision, operation, query, [x["id"] for x in previous], previous
    )
    return {"writes": found["writes"], "reverse": found["reverse"]}


@router.put("/selection")
def save_selection(
    project_id: str,
    revision_id: str,
    operation_id: str,
    body: Selection,
    db: Database,
    user: CurrentUser,
):
    revision, operation, migration = resolve(
        db, user, project_id, revision_id, operation_id
    )
    if baseline_for(db, migration):
        raise HTTPException(409, "The accepted baseline locks its source selection.")
    previous = migration.selection_json.get("writes", []) if migration else []
    found = discover(db, revision, operation, body.query, body.selected, previous)
    writes = [x for x in found["writes"] if x["id"] in body.selected]
    if {x["id"] for x in writes} != set(body.selected):
        raise HTTPException(
            422, "Some selected writes are outside these search results."
        )
    if not migration:
        migration = WorkflowMigration(
            project_id=project_id, revision_id=revision.id, operation_id=operation_id
        )
        db.add(migration)
    migration.selection_json = {**found, "query": body.query, "writes": writes}
    commit(db)
    return {"selected": [w["id"] for w in writes], "reverse": found["reverse"]}


@router.put("/scenarios")
def save_scenarios(
    project_id: str,
    revision_id: str,
    operation_id: str,
    body: Suite,
    db: Database,
    user: CurrentUser,
):
    _, _, migration = resolve(db, user, project_id, revision_id, operation_id)
    if not migration or baseline_for(db, migration):
        raise HTTPException(
            409, "Select writes first. An accepted baseline locks its scenarios."
        )
    allowed = {x["id"] for x in migration.selection_json["chunks"]}
    if any(set(x.evidence_ids) - allowed for x in body.scenarios):
        raise HTTPException(
            422, "Scenario citations must refer to the selected workflow evidence."
        )
    migration.scenarios_json = body.model_dump()["scenarios"]
    commit(db)
    return {"scenarios": migration.scenarios_json}


@router.post("/jobs", status_code=202)
def enqueue(
    project_id: str,
    revision_id: str,
    operation_id: str,
    body: Enqueue,
    db: Database,
    user: CurrentUser,
):
    _, operation, migration = resolve(db, user, project_id, revision_id, operation_id)
    if not migration:
        raise HTTPException(409, "Select and save the legacy writes first.")
    old = db.scalar(
        select(WorkflowMigrationJob).where(
            WorkflowMigrationJob.migration_id == migration.id,
            WorkflowMigrationJob.request_id == body.request_id,
        )
    )
    if old:
        if old.input_json["request"] != body.model_dump():
            raise HTTPException(
                409, "The request ID was already used for another action."
            )
        return serialize(old)
    baseline = baseline_for(db, migration)
    action = body.action
    prior = None
    if action in ("generate", "baseline") and baseline:
        raise HTTPException(409, "This workflow already has an immutable baseline.")
    if action == "baseline" and not migration.scenarios_json:
        raise HTTPException(409, "Save behavior scenarios before running the baseline.")
    if action in ("compare", "generate_patch", "repair", "draft_pr"):
        if not baseline or not body.replacement:
            raise HTTPException(
                409, "Approve the baseline and choose a replacement target first."
            )
        changes = body.replacement.intentional_changes
        if len({(item.scenario, item.path) for item in changes}) != len(changes) or any(
            not item.reason.strip() or not item.path.startswith("/") for item in changes
        ):
            raise HTTPException(
                422,
                "Use one reasoned intentional change per scenario and observed field path.",
            )
        mappings = body.replacement.mappings
        if any(not safe_mapping(x.legacy, x.replacement) for x in mappings) or any(
            len({getattr(x, key) for x in mappings}) != len(mappings)
            for key in ("legacy", "replacement")
        ):
            raise HTTPException(
                422,
                "Map unique old and new business fields using /database/table/field paths in the same table.",
            )
        if body.prior_job_id:
            record = job_for(db, migration, body.prior_job_id)
            prior = record.result_json
            if (
                not prior
                or record.action not in ("compare", "generate_patch", "repair")
                or (prior["target"] != body.replacement.target)
            ):
                raise HTTPException(
                    409, "Use a previous comparison for the same target."
                )
        if action == "repair" and (
            not body.repair.strip()
            or not prior
            or not any(
                row["name"] == body.scenario and row["status"] == "different"
                for row in prior["comparisons"]
            )
        ):
            raise HTTPException(
                422, "Choose a failing scenario and give a focused repair instruction."
            )
        if action == "draft_pr":
            accepted = db.scalar(
                select(WorkflowAcceptedPatch).where(
                    WorkflowAcceptedPatch.migration_id == migration.id,
                    WorkflowAcceptedPatch.job_id == body.prior_job_id,
                )
            )
            if not prior or not prior.get("patch") or not accepted:
                raise HTTPException(
                    409,
                    "Accept a compared patch before requesting a draft pull request.",
                )
            try:
                adapter = runner.get_variant(
                    project_id, "target", body.replacement.target
                )
                agent.github_ready(adapter)
            except runner.SetupGap as exc:
                raise HTTPException(409, str(exc)) from exc
    job = WorkflowMigrationJob(
        project_id=project_id,
        migration_id=migration.id,
        request_id=body.request_id,
        action=action,
        status="queued",
        input_json={
            **body.model_dump(),
            "request": body.model_dump(),
            "project_id": project_id,
            "version": migration.state_version,
            "operation": operation,
            "prior": prior,
            "scenarios": migration.scenarios_json,
            "selection": migration.selection_json,
            "baseline": baseline.artifact_json if baseline else None,
        },
    )
    db.add(job)
    commit(db)
    return serialize(job)


@router.get("/jobs/{job_id}")
def result(
    project_id: str,
    revision_id: str,
    operation_id: str,
    job_id: str,
    db: Database,
    user: CurrentUser,
):
    _, _, migration = resolve(db, user, project_id, revision_id, operation_id)
    job = job_for(db, migration, job_id)
    return {**serialize(job), "result": job.result_json}


@router.post("/baseline")
def approve(
    project_id: str,
    revision_id: str,
    operation_id: str,
    body: Approval,
    db: Database,
    user: CurrentUser,
):
    revision, operation, migration = resolve(
        db, user, project_id, revision_id, operation_id
    )
    capture = job_for(db, migration, body.capture_id)
    if baseline_for(db, migration):
        raise HTTPException(409, "An approved baseline already exists.")
    if (
        capture.action != "baseline"
        or capture.status != "completed"
        or not capture.result_json
    ):
        raise HTTPException(
            422, "Choose a legacy capture with two completed runs per scenario."
        )
    if migration.state_version != capture.input_json["version"]:
        raise HTTPException(
            409, "The draft changed after capture. Run the legacy baseline again."
        )
    result = capture.result_json
    rules = body.model_dump()["rules"]
    if len({(r["scenario"], r["path"]) for r in rules}) != len(rules) or any(
        not field_rule(r["path"], r["kind"]) or not r["reason"].strip() for r in rules
    ):
        raise HTTPException(
            422,
            "Rules must name unique concrete ID or timestamp fields and give a reason.",
        )
    observed = {
        (row["name"], d["path"])
        for row in result["captures"]
        if "stability" in row
        for d in row["stability"]["differences"]
    }
    if any((rule["scenario"], rule["path"]) not in observed for rule in rules):
        raise HTTPException(
            422, "Only fields with observed instability can receive comparison rules."
        )
    for row in result["captures"]:
        if (
            "gap" in row
            or compare(row["first"], row["second"], rules_for(rules, row["name"]))[
                "status"
            ]
            == "different"
        ):
            raise HTTPException(
                422,
                f"Legacy scenario {row['name']!r} has unresolved setup or instability.",
            )
    artifact = {
        "format": "galvanise-workflow-replay/v1",
        "project_id": project_id,
        "revision_id": revision.id,
        "operation_id": operation_id,
        "operation": operation["name"],
        "scenarios": capture.input_json["scenarios"],
        "rules": rules,
        "sources": capture.input_json["selection"]["writes"],
        "callers": capture.input_json["selection"]["reverse"],
        "replay_command": "cd apps/api && uv run python -m galvanise.migration.replay workflow-replay.json",
        **result,
    }
    row = WorkflowBaseline(
        project_id=project_id,
        migration_id=migration.id,
        capture_id=capture.id,
        approved_by=user.id,
        artifact_json=artifact,
    )
    # Advance the draft version in the same transaction so stale mutations fail.
    migration.state_version += 1
    db.add(row)
    commit(db)
    return {"id": row.id, "source_commit": result["source_commit"]}


@router.get("/baseline/export")
def export(
    project_id: str,
    revision_id: str,
    operation_id: str,
    db: Database,
    user: CurrentUser,
):
    _, _, migration = resolve(db, user, project_id, revision_id, operation_id)
    baseline = baseline_for(db, migration)
    if not baseline:
        raise HTTPException(404, "Approve a legacy baseline before export.")
    return baseline.artifact_json


@router.post("/accept-patch")
def accept(
    project_id: str,
    revision_id: str,
    operation_id: str,
    body: AcceptPatch,
    db: Database,
    user: CurrentUser,
):
    _, _, migration = resolve(db, user, project_id, revision_id, operation_id)
    job = job_for(db, migration, body.job_id)
    result = job.result_json or {}
    rows = result.get("comparisons", [])
    if (
        not result.get("patch")
        or not rows
        or any(r["status"] == "not_run" for r in rows)
    ):
        raise HTTPException(
            422, "Run every replacement scenario before accepting a patch."
        )
    if any(row.get("unknown") for row in rows):
        raise HTTPException(422, "Complete missing observers before accepting a patch.")
    intended = {
        (change["scenario"], change["path"])
        for change in result.get("intentional_changes", [])
    }
    observed = {
        (row["name"], diff["path"]) for row in rows for diff in row["differences"]
    }
    if intended != observed or any(
        row["difference_count"] > len(row["differences"]) for row in rows
    ):
        raise HTTPException(
            422,
            "Resolve observed differences or record a reason for each intentional change.",
        )
    accepted = WorkflowAcceptedPatch(
        project_id=project_id,
        migration_id=migration.id,
        job_id=job.id,
        approved_by=user.id,
        reason=body.reason,
    )
    db.add(accepted)
    commit(db)
    return {"id": accepted.id}


@router.get("/jobs/{job_id}/replay")
def replay_bundle(
    project_id: str,
    revision_id: str,
    operation_id: str,
    job_id: str,
    db: Database,
    user: CurrentUser,
):
    _, _, migration = resolve(db, user, project_id, revision_id, operation_id)
    job = job_for(db, migration, job_id)
    baseline = baseline_for(db, migration)
    result = job.result_json or {}
    if not baseline or not result.get("target_commit"):
        raise HTTPException(404, "No replacement replay is available for this job.")
    return {
        **baseline.artifact_json,
        "replacement": {
            key: result[key]
            for key in (
                "target",
                "target_commit",
                "target_adapter",
                "mappings",
                "patch",
                "intentional_changes",
            )
        }
        | {
            "reproductions": [
                {
                    "name": row["name"],
                    "scenario": row["reproduce"],
                    "legacy": row["reduced_legacy"],
                }
                for row in result["comparisons"]
                if row.get("reduced_legacy") is not None
            ]
        },
    }


@router.get("/pr-readiness")
def pr_readiness(
    project_id: str,
    revision_id: str,
    operation_id: str,
    db: Database,
    user: CurrentUser,
    target: Annotated[str, Query(max_length=100)],
):
    resolve(db, user, project_id, revision_id, operation_id)
    try:
        adapter = runner.get_variant(project_id, "target", target)
        agent.github_ready(adapter)
    except runner.SetupGap as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ready": True}
