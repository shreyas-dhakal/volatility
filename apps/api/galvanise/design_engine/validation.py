from collections import defaultdict

import networkx as nx

from .prompts import STAGES
from .records import all_rows, normalized, persistent_id


def user_message(chunk):
    locator = chunk.get("locator", {})
    return (
        isinstance(locator, dict)
        and (locator.get("kind") or locator.get("source_type"))
        in {"message", "chat", "chat_message"}
        and locator.get("role") == "user"
        and bool(locator.get("message_id"))
    )


def check_evidence(changes, chunks):
    """Validate only the text actually supplied to this call (including partial chunks)."""
    allowed = defaultdict(list)
    for chunk in chunks:
        allowed[chunk["id"]].append(normalized(chunk["text"]))
    users = {chunk["id"] for chunk in chunks if user_message(chunk)}
    for kind, rows in changes.items():
        if kind == "retire":
            continue
        for row in rows:
            citations = row["evidence"]
            for citation in citations:
                source = citation["chunk_id"]
                text = normalized(citation["excerpt"])
                if not text or not any(text in excerpt for excerpt in allowed[source]):
                    raise ValueError(
                        f"{kind}/{row['id']} has an unknown chunk or inexact excerpt: {source}."
                    )
            if row.get("status") == "user_confirmed" and not any(
                c["chunk_id"] in users for c in citations
            ):
                raise ValueError(
                    f"Decision {row['id']} requires an actual user-message citation."
                )
            if not citations and (
                kind == "actors"
                or row.get("basis") in {"observed", "stated_requirement"}
                or row.get("status") in {"observed", "disputed"}
            ):
                raise ValueError(f"{kind}/{row['id']} requires source evidence.")


def check_links(snapshot, stage):
    ids = {}
    for kind, row in all_rows(snapshot):
        if row["id"] in ids:
            raise ValueError(f"Duplicate persistent ID {row['id']}.")
        ids[row["id"]] = kind

    def ref(identity, kind, subject):
        if ids.get(identity) != kind:
            raise ValueError(f"{subject} references unknown {kind} ID {identity}.")

    def targets(row):
        for target in row["target_ids"]:
            if target not in ids:
                raise ValueError(f"{row['id']} references unknown target {target}.")

    def done(name):
        order = list(STAGES)
        return order.index(stage) >= order.index(name)

    cases = {r["id"]: r for r in snapshot["use_cases"]}
    for case in cases.values():
        ref(case["actor_id"], "actors", case["id"])
    if not done("volatility"):
        return
    for decision in snapshot["volatilities"]:
        for case in decision["use_case_ids"]:
            ref(case, "use_cases", decision["id"])
    for question in snapshot["questions"]:
        targets(question)
    if len(snapshot["questions"]) > 3:
        raise ValueError("Select at most three design-changing questions.")
    if not done("boundaries"):
        return

    owners = defaultdict(list)
    for component in snapshot["components"]:
        if not (
            component["owns"] or component["use_case_ids"] or component["rationale_ids"]
        ):
            raise ValueError(
                f"Component {component['id']} needs a rationale linked to a decision, use case or resource."
            )
        for target in component["rationale_ids"]:
            if ids.get(target) not in {
                "volatilities",
                "use_cases",
                "actors",
                "implementation_findings",
            }:
                raise ValueError(
                    f"Component {component['id']} has an unresolved rationale link {target}."
                )
        for decision in component["owns"]:
            ref(decision, "volatilities", component["id"])
            owners[decision].append(component["id"])
        for case in component["use_case_ids"]:
            ref(case, "use_cases", component["id"])
    gaps = {
        target
        for f in snapshot["findings"]
        if f["code"] == "ownership_gap"
        for target in f["target_ids"]
    }
    for decision in snapshot["volatilities"]:
        primary = owners[decision["id"]]
        if len(primary) > 1 or (not primary and decision["id"] not in gaps):
            raise ValueError(
                f"Decision {decision['id']} needs one primary owner or an explicit ownership_gap."
            )
    operation_owner = {}
    for contract in snapshot["contracts"]:
        ref(contract["owner_id"], "components", contract["id"])
        for operation in contract["operations"]:
            operation_owner[operation["id"]] = contract["owner_id"]
    dependencies = {d["id"]: d for d in snapshot["dependencies"]}
    for dep in dependencies.values():
        for field in ("caller_id", "callee_id"):
            ref(dep[field], "components", dep["id"])
        if (
            dep["caller_id"] == dep["callee_id"]
            or operation_owner.get(dep["operation_id"]) != dep["callee_id"]
        ):
            raise ValueError(
                f"Dependency {dep['id']} must call an operation owned by a different callee."
            )
    for finding in snapshot["findings"]:
        targets(finding)
    if not done("walkthroughs"):
        return

    covered = set()
    for walk in snapshot["walkthroughs"]:
        case_id = walk["use_case_id"]
        ref(case_id, "use_cases", walk["id"])
        if case_id in covered:
            raise ValueError(f"Multiple walkthroughs for use case {case_id}.")
        covered.add(case_id)
        paths = {"main", *(normalized(path) for path in cases[case_id]["exceptions"])}
        seen_paths = set()
        for step in walk["steps"]:
            seen_paths.add(normalized(step["path"]))
            for field in ("caller_id", "callee_id"):
                ref(step[field], "components", walk["id"])
            operation = step["operation_id"]
            dependency = step["dependency_id"]
            if operation and operation_owner.get(operation) != step["callee_id"]:
                raise ValueError(
                    f"Walkthrough {walk['id']} calls an operation absent from the callee's contract."
                )
            if dependency:
                dep = dependencies.get(dependency)
                if not dep or any(
                    dep[f] != step[f]
                    for f in ("caller_id", "callee_id", "operation_id")
                ):
                    raise ValueError(
                        f"Walkthrough {walk['id']} references a mismatched dependency."
                    )
            if step["caller_id"] != step["callee_id"] and not (
                dependency and operation
            ):
                raise ValueError(
                    f"Walkthrough {walk['id']} crossing needs an operation and dependency."
                )
        if seen_paths != paths:
            raise ValueError(
                f"Walkthrough {walk['id']} must cover main and exception paths {sorted(paths)}."
            )
    explained = {
        target
        for f in snapshot["findings"]
        if f["code"] == "coverage_gap"
        for target in f["target_ids"]
    }
    missing = set(cases) - covered - explained
    if missing:
        raise ValueError(
            f"Missing walkthrough or coverage_gap for use cases {sorted(missing)}."
        )
    for probe in snapshot["change_probes"]:
        decision = probe["volatility_id"]
        ref(decision, "volatilities", probe["id"])
        if set(probe["predicted_owner_ids"]) != set(owners[decision]):
            raise ValueError(
                f"Probe {probe['id']} predicted owners disagree with ownership of {decision}."
            )
        for component in probe["predicted_edit_ids"] + [
            leak["component_id"] for leak in probe["leaks"]
        ]:
            ref(component, "components", probe["id"])


def review_reasons(before, after):
    previous = {row["id"]: row for _, row in all_rows(before)}
    changed = {
        row["id"]
        for kind, row in all_rows(after)
        if kind
        in {"components", "contracts", "dependencies", "walkthroughs", "change_probes"}
        and row != previous.get(row["id"])
    }
    explained = {
        target
        for f in after["findings"]
        if f["code"] == "revision" and f != previous.get(f["id"])
        for target in f["target_ids"]
    }
    if changed - explained:
        raise ValueError(
            f"Explain each material review change in a revision finding targeting its ID: {sorted(changed - explained)}."
        )


def review_checks(snapshot):
    """Independent structural review supplements the qualitative model review."""
    findings = []

    def report(code, message, targets):
        targets = sorted(set(targets))
        identity = persistent_id("check", code + "/" + "/".join(targets))
        findings.append(
            {
                "id": identity,
                "code": code,
                "message": message,
                "severity": "warning",
                "target_ids": targets,
                "evidence": [],
            }
        )

    graph = nx.DiGraph()
    graph.add_edges_from(
        (d["caller_id"], d["callee_id"]) for d in snapshot["dependencies"]
    )
    for cycle in nx.strongly_connected_components(graph):
        if len(cycle) > 1:
            report(
                "dependency_cycle",
                "These components depend on each other in a cycle.",
                cycle,
            )
    traced = {
        step[side]
        for walk in snapshot["walkthroughs"]
        for step in walk["steps"]
        for side in ("caller_id", "callee_id")
    }
    for component in snapshot["components"]:
        if (
            not component["owns"]
            and component["id"] not in traced
            and component["id"] not in graph
        ):
            report(
                "overdecomposition",
                "This component has no owned decision, traced step or dependency.",
                [component["id"]],
            )
    for decision in snapshot["volatilities"]:
        if not decision["evidence"] or decision["status"] == "hypothesis":
            report(
                "low_evidence",
                "The rationale for this decision still needs confirmation.",
                [decision["id"]],
            )
    if not snapshot["use_cases"]:
        report(
            "low_evidence",
            "The supplied material did not establish a core use case.",
            [],
        )
    exercised = {probe["volatility_id"] for probe in snapshot["change_probes"]}
    for decision in snapshot["volatilities"]:
        if decision["id"] not in exercised:
            report(
                "coverage_gap", "No change probe tests this decision.", [decision["id"]]
            )
    for walk in snapshot["walkthroughs"]:
        gaps = [s["coverage_gap"] for s in walk["steps"] if s["coverage_gap"]]
        if gaps:
            report("coverage_gap", " ".join(dict.fromkeys(gaps)), [walk["id"]])
    for probe in snapshot["change_probes"]:
        outside = set(probe["predicted_edit_ids"]) - set(probe["predicted_owner_ids"])
        outside.update(leak["component_id"] for leak in probe["leaks"])
        if outside:
            report(
                "poor_containment",
                "The predicted change reaches components outside its primary owner.",
                [probe["id"], *outside],
            )
    return findings
