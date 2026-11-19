"""Compare recorded observations in collection order, retaining missing coverage."""

import re
from datetime import datetime

MISSING = object()
VOLATILE = re.compile(r"(?:^id$|[_-]id$|Id$|uuid$|timestamp$|Timestamp$|[_-]at$|At$)")


def pointer(path):
    return "/" + "/".join(
        str(part).replace("~", "~0").replace("/", "~1") for part in path
    )


def field_rule(path, kind):
    field = path.rsplit("/", 1)[-1]
    return bool(
        path.startswith(("/initial/", "/steps/"))
        and VOLATILE.search(field)
        and (kind == "id") == field.lower().endswith(("id", "uuid"))
    )


def timestamp(value):
    if not isinstance(value, str) or len(value) < 19:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def compare(old, new, rules=(), mappings=()):
    policies = {rule["path"]: rule["kind"] for rule in rules}
    align = business_fields(mappings)
    forward, backward, unknown = {}, {}, []
    differences = []

    def visit(left, right, parts):
        path = pointer(parts)
        is_observer = parts in (
            ("initial",),
            ("initial_messages",),
            ("initial_jobs",),
        ) or (
            len(parts) == 3
            and parts[0] == "steps"
            and parts[2] in ("http", "database", "messages", "jobs", "drain")
        )
        if is_observer and (
            left is None or right is None or left is MISSING or right is MISSING
        ):
            unknown.append(path)
            return
        if left is MISSING or right is MISSING:
            differences.append(
                {
                    "path": path,
                    "legacy": None if left is MISSING else left,
                    "replacement": None if right is MISSING else right,
                    "missing": "legacy" if left is MISSING else "replacement",
                }
            )
            return
        rule = policies.get(path)
        if rule == "timestamp" and timestamp(left) and timestamp(right):
            return
        if rule == "id" and type(left) is type(right) and type(left) in (str, int):
            a, b = (type(left), left), (type(right), right)
            if forward.get(a, b) == b and backward.get(b, a) == a:
                forward[a], backward[b] = b, a
                return
        if isinstance(left, dict) and isinstance(right, dict):
            fields = {}
            if len(parts) == 3 and parts[0] == "initial":
                fields = align.get(parts[1], {})
            if len(parts) == 5 and parts[0] == "steps" and parts[2] == "database":
                fields = align.get(parts[3], {})
            pairs = [(key, fields.get(key, key), False) for key in left]
            keys = set(right) - {replacement for _, replacement, _ in pairs}
            pairs.extend((key, key, True) for key in keys)
            priority = (
                "initial",
                "initial_messages",
                "initial_jobs",
                "steps",
                "http",
                "count",
                "response",
                "database",
                "messages",
                "jobs",
            )
            for key, destination, extra in sorted(
                pairs,
                key=lambda item: (
                    priority.index(item[0]) if item[0] in priority else len(priority),
                    item[0],
                ),
            ):
                visit(
                    MISSING if extra else left.get(key, MISSING),
                    right.get(destination, MISSING),
                    (*parts, key),
                )
            return
        if isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                visit(
                    left[index] if index < len(left) else MISSING,
                    right[index] if index < len(right) else MISSING,
                    (*parts, index),
                )
            return
        if type(left) is not type(right) or left != right:
            differences.append({"path": path, "legacy": left, "replacement": right})

    visit(old, new, ())
    return {
        "status": "different" if differences else "unknown" if unknown else "match",
        "first": differences[0] if differences else None,
        "differences": differences[:100],
        "difference_count": len(differences),
        "unknown": unknown,
    }


def safe_mapping(legacy, replacement):
    parent, _, before = legacy.rpartition("/")
    other_parent, _, after = replacement.rpartition("/")
    protected = {"count", "requests", "destination", "status", "method", "payload"}
    return (
        parent == other_parent
        and bool(re.fullmatch(r"/database/[A-Za-z_][A-Za-z0-9_-]*", parent))
        and all(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name) and name not in protected
            for name in (before, after)
        )
        and before != after
    )


def business_fields(mappings):
    tables = {}
    for rule in mappings:
        _, _, table, before = rule["legacy"].split("/")
        after = rule["replacement"].rsplit("/", 1)[1]
        tables.setdefault(table, {})[before] = after
    return tables


def replacement_scenario(scenario, mappings):
    fields = business_fields(mappings)
    return {
        **scenario,
        "observe": [
            {
                **row,
                "fields": [
                    fields[row["target"]].get(field, field) for field in row["fields"]
                ],
            }
            if row["kind"] == "database" and row["target"] in fields
            else row
            for row in scenario["observe"]
        ],
    }


def rules_for(rules, name):
    return [rule for rule in rules if rule.get("scenario") == name]
