"""Typed design invariants, deterministic diagnostics and versioned stage inputs.

AI output is a proposal. Diagnostics describe structural checks, never execution
or an architecture score. Historical records and human approvals are immutable
through generation; PATCH remains the only review path.
"""

import json

import networkx as nx
from fastapi import HTTPException
from galvanise.agents.design_schemas import (
    Component,
    CoreCase,
    CoreResult,
    DecompositionResult,
    UseCaseInput,
    Validation,
    ValidationResult,
    Volatility,
    VolatilityResult,
)
from galvanise.models import KnowledgeRecord, uid
from galvanise.services.knowledge import (
    bounded_context,
    evidence_ids,
    records_for,
    save_proposals,
    serialize,
)

KINDS = ("use_case", "core_use_case", "volatility", "boundary", "design_validation")
STAGES = {
    "core": "core_use_case",
    "volatility": "volatility",
    "decomposition": "boundary",
    "validation": "design_validation",
}
SCHEMAS = {
    "core_use_case": CoreCase,
    "volatility": Volatility,
    "boundary": Component,
    "design_validation": Validation,
}
RESULTS = {
    "core": CoreResult,
    "volatility": VolatilityResult,
    "decomposition": DecompositionResult,
    "validation": ValidationResult,
}
PRIOR = {
    "core": ("use_case",),
    "volatility": ("use_case", "core_use_case"),
    "decomposition": ("use_case", "core_use_case", "volatility"),
    "validation": ("use_case", "core_use_case", "volatility", "boundary"),
}
META = {
    "design_engine",
    "input_versions",
    "evidence_versions",
    "context_limits",
    "supersedes_id",
    "proposal_revision",
    "stale",
}
PROMPTS = {
    "core": "Discover business essence from original use cases, not similar wording. Preserve original variations by explicit use_case_ids. Explain mappings and rationale; list unresolved original IDs and uncertainty rather than silently omitting cases.",
    "volatility": "Independently analyze plausible reasons for change over time or across customers. A variation, entity, git churn, or optional feature is not automatically architectural volatility. Identify what changes, why plausible, stable aspects and concrete examples. Ground each hypothesis in reviewed core_use_case_ids and supplied evidence. Preserve uncertainty and focused questions.",
    "decomposition": "Decompose by encapsulating independent volatilities, not one service per use case or entity. Classify client, manager (workflow sequence), engine (business activity), resource_access, resource or utility. State responsibility, hidden change, stable contract and exclusions. Separate orchestration from business activity. Dependencies are existing component IDs or exact same-batch titles. Deployment is a separate decision; prefer modules/interfaces.",
    "validation": "Propose qualitative use-case collaborations and change-containment scenarios using reviewed components, known volatilities and core cases. List ordered steps, changed and unchanged components, rationale and assumptions. Distinguish hypotheses from evidence. Do not claim execution verification, measured savings, confidence scores or architecture scores.",
}


def is_design(record):
    return record.kind in ("use_case", "core_use_case", "design_validation") or (
        record.kind in ("volatility", "boundary")
        and record.payload.get("design_engine") is True
    )


def design_records(db, project_id):
    return [r for r in records_for(db, project_id) if is_design(r)]


def versions(records, stage):
    # Include rejected and pending history too: edits, rejections and new proposals
    # must not let an old report masquerade as validation of current inputs.
    return {r.id: r.version for r in records if is_design(r) and r.kind in PRIOR[stage]}


def evidence_references(payload, records):
    """Follow evidence links once each, retaining unknown IDs for validation."""
    by_id = {r.id: r for r in records}
    pending = list(payload.get("evidence_ids", []))
    result = set()
    while pending:
        rid = pending.pop()
        if rid in result:
            continue
        result.add(rid)
        target = by_id.get(rid)
        if target is not None:
            pending.extend(target.payload.get("evidence_ids", []))
    return result


def evidence_versions(payload, records):
    """Snapshot referenced versioned evidence separately from design inputs.

    Documents/messages have no optimistic versions and remain ownership-checked.
    """
    by_id = {r.id: r for r in records}
    return {
        rid: by_id[rid].version
        for rid in sorted(evidence_references(payload, records))
        if rid in by_id
    }


def evidence_stale(record, records):
    current = evidence_versions(record.payload, records)
    expected = record.payload.get("evidence_versions", {})
    by_id = {r.id: r for r in records}
    return expected != current or any(
        by_id[rid].status == "rejected" for rid in current
    )


def upstream_links(record):
    """Typed reasoning links; dependency cycles are traversed by stale()."""
    payload = record.payload
    if record.kind == "core_use_case":
        return [(rid, "use_case") for rid in payload.get("use_case_ids", [])]
    if record.kind == "volatility":
        return [(rid, "core_use_case") for rid in payload.get("core_use_case_ids", [])]
    if record.kind == "boundary":
        return [(rid, "volatility") for rid in payload.get("volatility_ids", [])] + [
            (rid, "boundary") for rid in payload.get("dependencies", [])
        ]
    linked = []
    if record.kind == "design_validation":
        for collaboration in payload.get("collaborations", []):
            linked.append((collaboration["core_use_case_id"], "core_use_case"))
            linked += [(rid, "boundary") for rid in collaboration["component_ids"]]
        for scenario in payload.get("scenarios", []):
            linked.append((scenario["volatility_id"], "volatility"))
            linked += [
                (rid, "boundary")
                for rid in scenario["changed_component_ids"]
                + scenario["unchanged_component_ids"]
            ]
    return linked


def stale(record, records):
    # Walk each reachable record once. A reviewed cycle stays visible as a
    # structural finding, without recursion or hiding a pending/stale member.
    by_id = {r.id: r for r in records}
    snapshots = {}
    pending, visited = [record], set()
    while pending:
        current = pending.pop()
        if current.id in visited:
            continue
        visited.add(current.id)
        if evidence_stale(current, records):
            return True
        stage = next((s for s, kind in STAGES.items() if kind == current.kind), None)
        if stage:
            if stage not in snapshots:
                snapshots[stage] = versions(records, stage)
            if current.payload.get("input_versions") != snapshots[stage]:
                return True
        for rid, kind in upstream_links(current):
            target = by_id.get(rid)
            if (
                target is None
                or not is_design(target)
                or target.kind != kind
                or (
                    target.status != "approved"
                    if kind != "use_case"
                    else target.status == "rejected"
                )
            ):
                return True
            pending.append(target)
    return False


def _refs(values, kind, by_id, field):
    for value in values:
        record = by_id.get(value)
        if (
            record is None
            or not is_design(record)
            or record.kind != kind
            or record.status == "rejected"
        ):
            raise ValueError(
                f"{field}: unknown, rejected, wrong-kind or cross-project {kind} reference: {value}"
            )
        if (
            kind != "use_case"
            and field != "dependencies"
            and record.status != "approved"
        ):
            raise ValueError(
                f"{field}: {kind} input must be reviewed and approved: {value}"
            )


def validate_payload(
    db,
    project_id,
    kind,
    title,
    description,
    payload,
    *,
    batch=None,
    references=None,
    allowed_evidence=None,
):
    """Validate a complete design payload before any database write."""
    by_id = (
        dict(references)
        if references is not None
        else {r.id: r for r in design_records(db, project_id)}
    )
    by_id.update(batch or {})
    clean = {k: v for k, v in payload.items() if k not in META}
    data = {"title": title, "description": description, **clean}
    model = UseCaseInput if kind == "use_case" else SCHEMAS[kind]
    parsed = model.model_validate(data).model_dump()
    evidence_records = (
        list(references.values())
        if references is not None
        else records_for(db, project_id)
    )
    if not evidence_references(parsed, evidence_records) <= (
        allowed_evidence
        if allowed_evidence is not None
        else evidence_ids(db, project_id)
    ):
        raise ValueError("Unknown, rejected or cross-project evidence id")
    if kind == "core_use_case":
        _refs(parsed["use_case_ids"], "use_case", by_id, "use_case_ids")
        _refs(
            parsed["unresolved_use_case_ids"],
            "use_case",
            by_id,
            "unresolved_use_case_ids",
        )
    elif kind == "volatility":
        _refs(parsed["core_use_case_ids"], "core_use_case", by_id, "core_use_case_ids")
    elif kind == "boundary":
        _refs(parsed["volatility_ids"], "volatility", by_id, "volatility_ids")
        _refs(parsed["dependencies"], "boundary", by_id, "dependencies")
    elif kind == "design_validation":
        for collaboration in parsed["collaborations"]:
            _refs(
                [collaboration["core_use_case_id"]],
                "core_use_case",
                by_id,
                "core_use_case_id",
            )
            _refs(collaboration["component_ids"], "boundary", by_id, "component_ids")
        for scenario in parsed["scenarios"]:
            _refs([scenario["volatility_id"]], "volatility", by_id, "volatility_id")
            _refs(
                scenario["changed_component_ids"] + scenario["unchanged_component_ids"],
                "boundary",
                by_id,
                "scenario components",
            )
            if set(scenario["changed_component_ids"]) & set(
                scenario["unchanged_component_ids"]
            ):
                raise ValueError(
                    "Scenario changed and unchanged components must be disjoint"
                )
    return parsed


def intake(db, project_id, body):
    data = body.model_dump()
    title, description = data.pop("title"), data.pop("description")
    validate_payload(db, project_id, "use_case", title, description, data)
    data["evidence_versions"] = evidence_versions(data, records_for(db, project_id))
    record = KnowledgeRecord(
        project_id=project_id,
        kind="use_case",
        title=title,
        description=description,
        payload=data,
        status="pending",
        evidence_status="human_confirmed",
    )
    db.add(record)
    db.commit()
    return record


def usable(record, records, by_id, valid_ids=None):
    """Reviewed, fresh inputs whose typed upstream links remain approved."""
    if (
        (valid_ids is not None and record.id not in valid_ids)
        or record.status != "approved"
        or stale(record, records)
    ):
        return False
    fields = {
        "core_use_case": ("use_case_ids",),
        "volatility": ("core_use_case_ids",),
        "boundary": ("volatility_ids",),
    }.get(record.kind, ())
    # Core discovery explicitly accepts unreviewed original cases; later stages
    # consume reviewed cores. Rejected original cases always invalidate them.
    for field in fields:
        for rid in record.payload.get(field, []):
            target = by_id.get(rid)
            if (
                target is None
                or target.status == "rejected"
                or (valid_ids is not None and target.id not in valid_ids)
            ):
                return False
            if record.kind != "core_use_case" and not usable(
                target, records, by_id, valid_ids
            ):
                return False
        if not record.payload.get(field):
            return False
    return True


def valid_record_ids(db, project_id, records):
    by_id = {r.id: r for r in records}
    allowed = evidence_ids(db, project_id)
    valid = set()
    for record in records:
        if not is_design(record):
            continue
        try:
            validate_payload(
                db,
                project_id,
                record.kind,
                record.title,
                record.description,
                record.payload,
                references=by_id,
                allowed_evidence=allowed,
            )
            valid.add(record.id)
        except ValueError:
            pass
    return valid


def prerequisites(db, project_id, stage):
    records = records_for(db, project_id)
    by_id = {r.id: r for r in records}
    valid_ids = valid_record_ids(db, project_id, records)
    required = {
        "core": ("use_case",),
        "volatility": ("core_use_case",),
        "decomposition": ("core_use_case", "volatility"),
        "validation": ("core_use_case", "volatility", "boundary"),
    }[stage]
    missing = [
        kind
        for kind in required
        if not any(
            r.kind == kind
            and (
                r.status != "rejected" and r.id in valid_ids and not stale(r, records)
                if stage == "core"
                else usable(r, records, by_id, valid_ids)
            )
            for r in records
        )
    ]
    if missing:
        raise HTTPException(
            422,
            "Stage requires "
            + ", ".join(missing)
            + (
                "; add original use cases first."
                if stage == "core"
                else "; approve current inputs and regenerate stale stages first."
            ),
        )
    return records


def context_for(db, project_id, records, stage):
    context = bounded_context(db, project_id)
    # Keep complete typed inputs where possible, explicitly mark per-record excerpts.
    entries = []
    by_id = {r.id: r for r in records}
    valid_ids = valid_record_ids(db, project_id, records)
    for r in records:
        if is_design(r) and r.kind in PRIOR[stage] and r.status != "rejected":
            value = serialize(r)
            value["reviewed_usable"] = usable(r, records, by_id, valid_ids)
            value["stale"] = stale(r, records)
            value.pop("history", None)
            value.pop("created_at", None)
            value.pop("updated_at", None)
            encoded = json.dumps(value["payload"], default=str)
            if len(encoded) > 10000:
                value["payload"] = {
                    "bounded_excerpt": encoded[:10000],
                    "truncated": True,
                }
            entries.append(value)
    entries.sort(
        key=lambda r: (
            not r["reviewed_usable"],
            r["status"] != "approved",
            r["kind"],
            r["id"],
        )
    )
    selected = entries[:100]
    context["design_inputs"] = selected
    context["stage"] = stage
    # Prioritize the typed inputs over generic duplicated knowledge.
    for key in ("knowledge", "stakeholder_answers", "documents", "messages"):
        original_size = len(context[key])
        while len(json.dumps(context, default=str)) > 90000 and context[key]:
            context[key].pop()
        context["context_limits"][f"{key}_omitted_for_budget"] = original_size - len(
            context[key]
        )
    while len(json.dumps(context, default=str)) > 90000 and selected:
        selected.pop()
    context["context_limits"]["design_records_omitted"] = len(entries) - len(selected)
    context["context_limits"]["design_payloads_truncated"] = sum(
        r["payload"].get("truncated") is True for r in selected
    )
    return context


def save_generated(db, project_id, stage, result, inputs, context_limits):
    # Revalidate even mocked/SDK output. No part of a bad batch is persisted.
    result = RESULTS[stage].model_validate(
        result.model_dump() if hasattr(result, "model_dump") else result
    )
    values = [r.model_dump() for r in result.records]
    kind = STAGES[stage]
    snapshot = versions(inputs, stage)
    existing = records_for(db, project_id)
    ids = [uid() for _ in values]
    batch = {}
    if stage == "decomposition":
        titles = [v["title"].casefold() for v in values]
        if len(titles) != len(set(titles)):
            raise ValueError("Component titles must be unique within a batch")
        # Compare in title space to make exact reruns (including cycles) idempotent.
        name_by_id = {r.id: r.title for r in existing if r.kind == "boundary"}

        def comparable(payload):
            p = {
                k: v
                for k, v in payload.items()
                if k not in ("supersedes_id", "proposal_revision")
            }
            p["dependencies"] = [
                name_by_id.get(d, d) for d in p.get("dependencies", [])
            ]
            return p

        for i, value in enumerate(values):
            payload = {
                k: v for k, v in value.items() if k not in ("title", "description")
            }
            payload.update(
                design_engine=True,
                input_versions=snapshot,
                evidence_versions=evidence_versions(payload, inputs),
                context_limits=context_limits,
            )
            duplicate = next(
                (
                    r
                    for r in reversed(existing)
                    if r.kind == kind
                    and r.status != "rejected"
                    and r.title == value["title"]
                    and r.description == value["description"]
                    and comparable(r.payload) == comparable(payload)
                ),
                None,
            )
            if duplicate:
                ids[i] = duplicate.id
        # A title-space match can depend on a revised peer. Propagate fresh IDs
        # until every reused record has exactly the resolved dependencies it had
        # before. This also handles cycles without mutating approved records.
        existing_by_id = {r.id: r for r in existing}
        while True:
            names = {v["title"]: ids[i] for i, v in enumerate(values)}
            revised = False
            for i, value in enumerate(values):
                previous = existing_by_id.get(ids[i])
                resolved = [names.get(d, d) for d in value["dependencies"]]
                if (
                    previous is not None
                    and previous.payload.get("dependencies") != resolved
                ):
                    ids[i] = uid()
                    revised = True
            if not revised:
                break
        names = {v["title"]: ids[i] for i, v in enumerate(values)}
        for i, value in enumerate(values):
            value["dependencies"] = [names.get(d, d) for d in value["dependencies"]]
            batch[ids[i]] = KnowledgeRecord(
                id=ids[i],
                project_id=project_id,
                kind="boundary",
                payload={"design_engine": True},
                title=value["title"],
                status="pending",
            )
    proposals = []
    references = {r.id: r for r in existing}
    allowed_evidence = evidence_ids(db, project_id)
    valid_ids = valid_record_ids(db, project_id, existing)
    for value in values:
        payload = {k: v for k, v in value.items() if k not in ("title", "description")}
        validate_payload(
            db,
            project_id,
            kind,
            value["title"],
            value["description"],
            payload,
            batch=batch,
            references=references,
            allowed_evidence=allowed_evidence,
        )
        upstream = []
        if stage == "volatility":
            upstream = value["core_use_case_ids"]
        elif stage == "decomposition":
            upstream = value["volatility_ids"]
        elif stage == "validation":
            upstream = [c["core_use_case_id"] for c in value["collaborations"]]
            upstream += [
                rid for c in value["collaborations"] for rid in c["component_ids"]
            ]
            upstream += [s["volatility_id"] for s in value["scenarios"]]
            upstream += [
                rid
                for s in value["scenarios"]
                for rid in s["changed_component_ids"] + s["unchanged_component_ids"]
            ]
        if any(
            not usable(references[rid], existing, references, valid_ids)
            for rid in upstream
        ):
            raise ValueError(
                "Generated links require current reviewed inputs; regenerate and review stale upstream artifacts first."
            )
        proposals.append(
            {
                "kind": kind,
                **value,
                "design_engine": True,
                "input_versions": snapshot,
                "evidence_versions": evidence_versions(value, inputs),
                "context_limits": context_limits,
            }
        )
    # Guard against evidence and design edits while the provider was running.
    evidence_payloads = [
        *proposals,
        *(r.payload for r in inputs if is_design(r) and r.kind in PRIOR[stage]),
    ]
    evidence_snapshot = [
        evidence_versions(value, inputs) for value in evidence_payloads
    ]
    db.expire_all()
    refreshed = records_for(db, project_id)
    if versions(refreshed, stage) != snapshot or any(
        previous != evidence_versions(value, refreshed)
        for value, previous in zip(evidence_payloads, evidence_snapshot, strict=True)
    ):
        raise HTTPException(
            409,
            "Design inputs or supporting evidence changed during generation; reload and retry.",
        )
    return save_proposals(db, project_id, proposals, record_ids=ids)


def view(db, project_id):
    records = records_for(db, project_id)
    by_id = {r.id: r for r in records}
    groups = {
        kind: [r for r in records if is_design(r) and r.kind == kind] for kind in KINDS
    }
    active = {
        kind: [r for r in rows if r.status != "rejected"]
        for kind, rows in groups.items()
    }
    findings = []
    valid_ids = set()
    allowed_evidence = evidence_ids(db, project_id)

    def finding(code, message, ids, severity="warning"):
        findings.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "record_ids": sorted(set(ids)),
            }
        )

    for r in records:
        if not is_design(r) or r.status == "rejected":
            continue
        try:
            validate_payload(
                db,
                project_id,
                r.kind,
                r.title,
                r.description,
                r.payload,
                references=by_id,
                allowed_evidence=allowed_evidence,
            )
            valid_ids.add(r.id)
        except ValueError as error:
            finding(
                "invalid_reference_or_payload", f"{r.title}: {error}", [r.id], "error"
            )
        if stale(r, records):
            finding(
                "stale_validation"
                if r.kind == "design_validation"
                else "stale_artifact",
                f"{r.title} predates changed design inputs; regenerate and review.",
                [r.id],
            )
        if any(
            v
            for v in r.payload.get("context_limits", {}).values()
            if isinstance(v, int)
        ):
            finding(
                "context_truncated",
                f"{r.title} was proposed with bounded context; review omitted inputs.",
                [r.id],
            )
    mapped = {
        rid
        for r in active["core_use_case"]
        for rid in r.payload.get("use_case_ids", [])
    }
    for r in active["use_case"]:
        if r.id not in mapped:
            finding(
                "uncovered_use_case",
                f"{r.title} has no core mapping; retain and resolve its variations.",
                [r.id],
            )
    for r in active["core_use_case"]:
        for rid in r.payload.get("unresolved_use_case_ids", []):
            finding(
                "unresolved_use_case",
                f"{r.title} leaves an original case unresolved.",
                [r.id, rid],
            )
    encapsulated = {
        rid for r in active["boundary"] for rid in r.payload.get("volatility_ids", [])
    }
    for r in active["volatility"]:
        if r.id not in encapsulated:
            finding(
                "unmapped_volatility",
                f"{r.title} has no encapsulating component.",
                [r.id],
            )
    graph = nx.DiGraph()
    component_ids = {r.id for r in active["boundary"]}
    graph.add_nodes_from(sorted(component_ids))
    for r in active["boundary"]:
        if not str(r.payload.get("stable_contract", "")).strip():
            finding(
                "missing_contract",
                f"{r.title} needs a stable contract.",
                [r.id],
                "error",
            )
        for dep in r.payload.get("dependencies", []):
            if dep not in component_ids:
                finding(
                    "unknown_dependency",
                    f"{r.title} depends on an unavailable component.",
                    [r.id, dep],
                    "error",
                )
            else:
                graph.add_edge(r.id, dep)
                if not usable(by_id[dep], records, by_id, valid_ids):
                    finding(
                        "unusable_dependency",
                        f"{r.title} depends on an unreviewed or stale component; review current dependency inputs before validation.",
                        [r.id, dep],
                        "error",
                    )
    # Strongly connected sets are linear-time and cannot explode like all cycles.
    for members in nx.strongly_connected_components(graph):
        if len(members) > 1 or any(graph.has_edge(rid, rid) for rid in members):
            finding(
                "dependency_cycle",
                "Component dependencies form a cycle; review responsibility direction.",
                list(members),
                "error",
            )
    fresh_validations = [
        r for r in active["design_validation"] if not stale(r, records)
    ]
    covered = {
        c["core_use_case_id"]
        for r in fresh_validations
        for c in r.payload.get("collaborations", [])
    }
    tested = {
        s["volatility_id"]
        for r in fresh_validations
        for s in r.payload.get("scenarios", [])
    }
    for r in active["core_use_case"]:
        if r.id not in covered:
            finding(
                "missing_collaboration",
                f"{r.title} has no current collaboration proposal.",
                [r.id],
            )
    for r in active["volatility"]:
        if r.id not in tested:
            finding(
                "missing_change_scenario",
                f"{r.title} has no current containment scenario.",
                [r.id],
            )
    for r in fresh_validations:
        for scenario in r.payload.get("scenarios", []):
            owners = {
                b.id
                for b in active["boundary"]
                if scenario["volatility_id"] in b.payload.get("volatility_ids", [])
            }
            changed = set(scenario["changed_component_ids"])
            if not owners or not owners & changed or changed - owners:
                finding(
                    "change_not_contained",
                    f"{scenario['title']}: proposed changes do not stay within the encapsulating components.",
                    [r.id, scenario["volatility_id"], *changed],
                )
    readiness = {
        name: any(usable(r, records, by_id, valid_ids) for r in groups[kind])
        for name, kind in [
            ("use_cases", "use_case"),
            ("core_use_cases", "core_use_case"),
            ("volatility", "volatility"),
            ("decomposition", "boundary"),
            ("validation", "design_validation"),
        ]
    }
    # A fresh report still needs reviewed current prerequisite inputs.
    readiness["validation"] &= all(
        readiness[name] for name in ("core_use_cases", "volatility", "decomposition")
    )

    def output(r):
        value = serialize(r)
        if is_design(r):
            value["payload"] = {**r.payload, "stale": stale(r, records)}
        return value

    names = [
        ("use_cases", "use_case"),
        ("core_use_cases", "core_use_case"),
        ("volatilities", "volatility"),
        ("components", "boundary"),
        ("validations", "design_validation"),
    ]
    limits = {
        f"{name}_omitted": max(0, len(groups[kind]) - 200) for name, kind in names
    }
    if any(limits.values()) or len(findings) > 500:
        finding(
            "results_truncated",
            "Overview lists are bounded to 200 artifacts per kind and 500 findings; use the records API for complete history.",
            [],
        )
    limits["findings_omitted"] = max(0, len(findings) - 500)
    return {
        **{name: [output(r) for r in groups[kind][-200:]] for name, kind in names},
        "findings": sorted(findings, key=lambda f: (f["code"], f["record_ids"]))[:500],
        "readiness": readiness,
        "context_limits": limits,
    }
