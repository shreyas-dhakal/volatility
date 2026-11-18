"""Resolve response-local handles to persistent application IDs before validating links."""

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid4, uuid5

COLLECTIONS = (
    "actors",
    "implementation_findings",
    "use_cases",
    "volatilities",
    "components",
    "contracts",
    "dependencies",
    "walkthroughs",
    "change_probes",
    "questions",
    "findings",
)


def normalized(text):
    return " ".join(text.split())


def persistent_id(kind, key):
    return str(uuid5(NAMESPACE_URL, f"galvanise/design/{kind}/{key}"))


def all_rows(snapshot):
    for kind in COLLECTIONS:
        for row in snapshot[kind]:
            yield kind, row
            if kind == "contracts":
                for operation in row["operations"]:
                    yield "operations", operation


def resolve(value, aliases):
    """Rewrite only reference fields. Source IDs, citation text and prose are immutable."""
    if isinstance(value, list):
        return [resolve(item, aliases) for item in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for field, item in value.items():
        if field == "id" or (field.endswith("_id") and field != "chunk_id"):
            out[field] = aliases.get(item, item)
        elif field == "owns" or field.endswith("_ids"):
            out[field] = [aliases.get(ref, ref) for ref in item]
        else:
            out[field] = resolve(item, aliases)
    return out


def bind_records(snapshot, changes):
    prior_kinds = {row["id"]: kind for kind, row in all_rows(snapshot)}
    aliases = {}
    seen_ids = set()
    operation_contracts = {
        op["id"]: contract["id"]
        for contract in snapshot["contracts"]
        for op in contract["operations"]
    }
    # Inventory alone is merged by normalized factual content. Equal labels never
    # establish identity between two proposals, contracts or operations.
    observations = {}

    def fact_key(kind, row):
        fields = (
            ("kind", "description", "name")
            if kind == "actors"
            else ("kind", "description")
        )
        return (kind, *(normalized(row[field]) for field in fields))

    for kind in ("actors", "implementation_findings"):
        observations.update((fact_key(kind, row), row["id"]) for row in snapshot[kind])

    def bind(kind, row):
        handle = row["id"]
        if handle in seen_ids:
            raise ValueError(f"Duplicate response ID {handle!r} in {kind}.")
        seen_ids.add(handle)
        inventory = kind in {"actors", "implementation_findings"}
        fact = fact_key(kind, row) if inventory else None
        if handle in prior_kinds:
            if prior_kinds[handle] != kind:
                raise ValueError(
                    f"{kind} handle {handle} conflicts with an existing ID."
                )
            if inventory and observations.get(fact) != handle:
                raise ValueError(
                    f"Use a new ID for an observation conflicting with {handle}."
                )
            target = handle
        else:
            target = observations.get(fact) or str(uuid4())
        aliases[handle] = target
        if inventory:
            observations[fact] = target
        return target

    for kind in COLLECTIONS:
        for row in changes.get(kind, []):
            identity = bind(kind, row)
            if kind == "contracts":
                for op in row["operations"]:
                    if (
                        op["id"] in operation_contracts
                        and operation_contracts[op["id"]] != identity
                    ):
                        raise ValueError(
                            f"Operation {op['id']} belongs to another contract."
                        )
                    bind("operations", op)
    return resolve(changes, aliases)


def upsert(snapshot, changes, catalog=None):
    candidate = deepcopy(snapshot)
    resolved = bind_records(catalog or snapshot, changes)
    for kind in COLLECTIONS:
        indexed = {row["id"]: row for row in candidate[kind]}
        for row in resolved.get(kind, []):
            previous = indexed.get(row["id"])
            if previous and kind in ("actors", "implementation_findings"):
                citations = previous["evidence"] + row["evidence"]
                row["evidence"] = list(
                    {(c["chunk_id"], c["excerpt"]): c for c in citations}.values()
                )
            if previous and kind == "contracts":
                operations = {op["id"]: op for op in previous["operations"]}
                operations.update((op["id"], op) for op in row["operations"])
                row["operations"] = list(operations.values())
            indexed[row["id"]] = row
        candidate[kind] = list(indexed.values())
    for retire in resolved.get("retire", []):
        found = False
        for kind in (field for field in COLLECTIONS if field in changes):
            rows = candidate[kind]
            remaining = [r for r in rows if r["id"] != retire["id"]]
            if len(remaining) != len(rows):
                candidate[kind] = remaining
                found = True
                break
        if not found and "contracts" in changes:
            for contract in candidate["contracts"]:
                remaining = [
                    op for op in contract["operations"] if op["id"] != retire["id"]
                ]
                if len(remaining) < len(contract["operations"]):
                    contract["operations"] = remaining
                    found = True
                    break
        if not found:
            raise ValueError(f"Cannot retire unknown or protected ID {retire['id']}.")
        message = f"Retired {retire['id']}. {retire['reason']}"
        candidate["findings"].append(
            {
                "id": persistent_id("retirement", retire["id"]),
                "code": "revision",
                "severity": "info",
                "message": message,
                "target_ids": [],
                "evidence": [],
            }
        )
    return candidate


def reference_ids(value):
    if isinstance(value, list):
        for item in value:
            yield from reference_ids(item)
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence":
                continue
            if key.endswith("_id") and item:
                yield item
            elif key.endswith("_ids") or key == "owns":
                yield from item
            else:
                yield from reference_ids(item)


def reuse_candidates(base, chunks):
    """Reuse identity only for proposals with provenance in the new selection.

    Start a fresh snapshot. Prior rows are suggestions to the provider, never
    carried forward automatically. Filter direct citations, then retain derived
    records only when their references still resolve back to supported facts.
    """
    text = {c["id"]: normalized(c["text"]) for c in chunks}
    filtered = {field: [] for field in COLLECTIONS}
    anchored = set()
    for field in COLLECTIONS:
        for row in base[field]:
            retained = [
                c
                for c in row["evidence"]
                if c["chunk_id"] in text
                and normalized(c["excerpt"]) in text[c["chunk_id"]]
            ]
            if retained or not row["evidence"]:
                filtered[field].append(row | {"evidence": retained})
            if retained:
                anchored.add(row["id"])
    references = {r["id"]: set(reference_ids(r)) for _, r in all_rows(filtered)}
    for contract in filtered["contracts"]:
        for operation in contract["operations"]:
            references[operation["id"]].add(contract["id"])
    reachable = anchored.copy()
    while True:
        next_ids = reachable | {
            key for key, deps in references.items() if deps & reachable
        }
        if next_ids == reachable:
            break
        reachable = next_ids
    while True:
        valid = {
            identity for identity in reachable if references[identity] <= reachable
        }
        if valid == reachable:
            break
        reachable = valid
    return {
        field: [row for row in rows if row["id"] in reachable]
        for field, rows in filtered.items()
    }


def with_candidates(snapshot, candidates, fields):
    if not candidates:
        return snapshot
    result = dict(snapshot)
    for field in fields:
        if field in COLLECTIONS:
            rows = {r["id"]: r for r in candidates[field]}
            rows.update((r["id"], r) for r in snapshot[field])
            result[field] = list(rows.values())
    return result
