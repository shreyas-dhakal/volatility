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
        return (kind, *(normalized(row[field]).casefold() for field in fields))

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


def upsert(snapshot, changes):
    candidate = deepcopy(snapshot)
    resolved = bind_records(snapshot, changes)
    for kind in COLLECTIONS:
        indexed = {row["id"]: row for row in candidate[kind]}
        for row in resolved.get(kind, []):
            previous = indexed.get(row["id"])
            if previous and kind in ("actors", "implementation_findings"):
                citations = previous["evidence"] + row["evidence"]
                row["evidence"] = list(
                    {(c["chunk_id"], c["excerpt"]): c for c in citations}.values()
                )
            indexed[row["id"]] = row
        candidate[kind] = list(indexed.values())
    for retire in resolved.get("retire", []):
        found = False
        for kind in (
            "components",
            "contracts",
            "dependencies",
            "walkthroughs",
            "change_probes",
            "questions",
            "findings",
        ):
            rows = candidate[kind]
            remaining = [r for r in rows if r["id"] != retire["id"]]
            if len(remaining) != len(rows):
                candidate[kind] = remaining
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
