"""Find candidate writes and reverse references in the saved design's source snapshot."""

import hashlib
import re
from collections import defaultdict, deque

from sqlalchemy import select

from galvanise.design_engine.sources import evidence
from galvanise.models import TechnicalGraph

EFFECTS = {
    "database": re.compile(
        r"\b(?:insert\s+into|update\s+[\"\w.]+\s+set|delete\s+from|merge\s+into|"
        r"\.(?:insert|update|delete|save|saveAll|create|upsert|flush|add|bulk_create)\s*\()",
        re.IGNORECASE,
    ),
    "http": re.compile(
        r"(?:\b(?:fetch|urlopen)\s*\(|\b(?:axios|requests|httpx|http|client|session)"
        r"\.(?:get|post|put|patch|delete|request)\s*\(|https?://)",
        re.IGNORECASE,
    ),
    "messages": re.compile(
        r"\b(?:publish|produce|send_message|sendMessage|enqueue|xadd|lpush|rpush|sendToQueue)\s*\(",
        re.IGNORECASE,
    ),
    "jobs": re.compile(
        r"\b(?:delay|apply_async|add_job|create_task|schedule|perform_async|BackgroundTasks|"
        r"@?cron|celery|sidekiq|background_job)\b",
        re.IGNORECASE,
    ),
}
SCHEDULING = re.compile(
    r"\b(?:cron|scheduler|schedule|trigger|before each row|after each row)\b",
    re.IGNORECASE,
)
TRANSACTION = re.compile(
    r"\b(?:transaction|commit|rollback|atomic|begin|autocommit|savepoint)\b",
    re.IGNORECASE,
)
TOKEN = re.compile(r"[a-zA-Z_][\w-]{1,80}")
COMMON = {
    "the",
    "and",
    "for",
    "from",
    "with",
    "when",
    "use",
    "then",
    "this",
    "that",
    "insert",
    "update",
    "send",
    "create",
    "save",
    "publish",
    "post",
    "into",
    "json",
}
TABLE = re.compile(
    r"\b(?:insert\s+into|update|delete\s+from|merge\s+into)\s+([\w.\"\x60]+)(\s*\([^)]*\)|\s+set\s+[^;]+)?",
    re.IGNORECASE,
)


def terms(value):
    split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return (
        set(TOKEN.findall(value.casefold()))
        | set(TOKEN.findall(split.replace("_", " ").casefold()))
    ) - COMMON


def write_targets(kind, line):
    if kind != "database" or not (match := TABLE.search(line)):
        return [(line.strip()[:180], None, None)]
    table = match[1].strip('`"')
    raw = (match[2] or "").strip()
    if raw.startswith("("):
        fields = [value.strip(' `"') for value in raw[1:-1].split(",")]
    else:
        fields = re.findall(
            r'([\w]+)["`]?\s*=', re.split(r"\bWHERE\b", raw, flags=re.IGNORECASE)[0]
        )
    return [
        (table, table, None),
        *[
            (table + "." + field, table, field)
            for field in fields
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field)
        ][:10],
    ]


def reference(chunk, line):
    return {"chunk_id": chunk["id"], "excerpt": line.strip()[:400]}


def location(chunk, offset):
    where = chunk["locator"]
    return {
        "path": where.get("path") or where.get("section") or where.get("kind"),
        "line": where.get("line_start", 1) + offset,
        "repository_id": where.get("repository_id"),
        "source_id": chunk.get("source_id"),
    }


def transaction_terms(citations):
    return sorted(
        {
            word.casefold()
            for citation in citations
            for word in TRANSACTION.findall(citation["excerpt"])
        }
    )


def effects(line):
    return [name for name, pattern in EFFECTS.items() if pattern.search(line)]


def graph_files(db, revision, query, chunks):
    paths = {
        (c["locator"].get("repository_id"), c["locator"].get("path")) for c in chunks
    }
    paths_by_name = defaultdict(set)
    for key in paths:
        paths_by_name[key[1]].add(key)
    result, callers = set(), {}
    snapshot_trees = {
        c["locator"].get("git_tree") for c in chunks if c["locator"].get("git_tree")
    }
    for graph in db.scalars(
        select(TechnicalGraph)
        .where(TechnicalGraph.project_id == revision.project_id)
        .order_by(TechnicalGraph.created_at.desc())
        .limit(15)
    ):
        if not graph.edges_json or (
            graph.source_id
            and graph.metadata_json.get("tree_sha")
            and snapshot_trees
            and graph.metadata_json["tree_sha"] not in snapshot_trees
        ):
            continue

        def locations(node, repo_id=graph.source_id):
            return {
                key
                for key in paths_by_name[node["file_path"]]
                if not repo_id or key[0] == repo_id
            }

        nodes = {node["id"]: node for node in graph.nodes_json}
        outgoing, incoming = defaultdict(list), defaultdict(list)
        for edge in graph.edges_json:
            if edge["type"] in ("calls", "call", "invokes"):
                outgoing[edge["source"]].append(edge["target"])
                incoming[edge["target"]].append(edge["source"])

        def walk(roots, links):
            seen = set(roots)
            queue = deque((node, 0) for node in roots)
            while queue and len(seen) < 100:
                node, depth = queue.popleft()
                if depth < 4:
                    for neighbor in links[node][:25]:
                        if neighbor not in seen:
                            seen.add(neighbor)
                            queue.append((neighbor, depth + 1))
            return seen

        roots = [
            key
            for key, node in nodes.items()
            if query & terms(node["label"]) and locations(node)
        ][:10]
        reached = walk(roots, outgoing)
        for key in reached:
            result |= locations(nodes[key])
        for key in walk(reached, incoming) - set(roots):
            node = nodes[key]
            for path in locations(node):
                callers[path] = graph.id
    return result, callers


def discover(db, revision, operation, query="", selected=(), previous=()):
    chunks, manifest = evidence(
        db, revision.project_id, revision.source_ids, include_provenance=True
    )
    search = terms(query or operation["name"])
    forward_paths, caller_paths = graph_files(db, revision, search, chunks)
    anchored = set(forward_paths)
    for chunk in chunks:
        loc = location(chunk, 0)
        if search & terms(loc["path"] or "") or any(
            cite["chunk_id"] == chunk["id"] for cite in operation["evidence"]
        ):
            anchored.add((loc["repository_id"], loc["path"]))
    candidates, seen = [], set()
    for chunk in chunks:
        if chunk["locator"].get("kind") != "code":
            continue
        loc = location(chunk, 0)
        lines = chunk["text"].splitlines()
        for offset, line in enumerate(lines):
            if not line.strip():
                continue
            key = (loc["repository_id"], loc["path"])
            found = effects(line)
            overlaps = search & terms(line)
            if not found or (key not in anchored and not overlaps):
                continue
            cite = reference(chunk, line)
            transactions = [
                reference(chunk, item)
                for item in lines[max(0, offset - 7) : offset + 8]
                if TRANSACTION.search(item)
            ][:4]
            for kind in found:
                for target, table, field in write_targets(kind, line):
                    marker = (key, loc["line"] + offset, kind, cite["excerpt"], target)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    candidates.append(
                        {
                            "id": hashlib.sha256(repr(marker).encode()).hexdigest()[
                                :24
                            ],
                            "kind": kind,
                            "target": target,
                            "table": table,
                            "field": field,
                            "location": location(chunk, offset),
                            "evidence": [cite],
                            "basis": "source",
                            "transaction_evidence": transactions,
                            "transaction_markers": transaction_terms(transactions),
                            "match": len(overlaps) + (3 if key in anchored else 0),
                        }
                    )
    candidates.sort(key=lambda item: -item["match"])
    candidates = [
        {k: v for k, v in item.items() if k != "match"} for item in candidates[:120]
    ]
    by_id = {item["id"]: item for item in [*previous, *candidates]}
    selection = [by_id[key] for key in selected if key in by_id]
    reverse_terms = set(terms(query)) or search
    for item in selection:
        reverse_terms |= terms(item["target"])
    selected_boundaries = {
        tuple(item["transaction_markers"])
        for item in selection
        if item.get("transaction_markers")
    }
    reverse, model_chunks = [], []
    selected_chunks = {
        ref["chunk_id"] for item in selection for ref in item["evidence"]
    }
    direct_chunks = {ref["chunk_id"] for ref in operation["evidence"]}
    for chunk in chunks:
        loc = location(chunk, 0)
        key = (loc["repository_id"], loc["path"])
        path = loc["path"] or ""
        rank = min(4, len(reverse_terms & terms(chunk["text"])))
        if re.search(r"test|spec|schema|migration|trace|fixture", path, re.IGNORECASE):
            rank += 2
        if chunk["id"] in selected_chunks | direct_chunks:
            rank += 20
        if rank:
            model_chunks.append((rank, chunk))
        if not reverse_terms and key not in caller_paths:
            continue
        lines = chunk["text"].splitlines()
        for offset, line in enumerate(lines):
            near = lines[max(0, offset - 7) : offset + 8]
            matched = reverse_terms & terms(line)
            if SCHEDULING.search(line):
                matched |= reverse_terms & terms(" ".join(near))
            graph_match = key in caller_paths and bool(re.search(r"\w+\s*\(", line))
            if not matched and not graph_match:
                continue
            matches = effects(line)
            kind = (
                "scheduler / trigger"
                if SCHEDULING.search(line)
                else ("other writer" if matches else "possible caller")
            )
            citations = [reference(chunk, line)]
            if any(citations[0] in item["evidence"] for item in selection):
                continue
            rank = (
                len(matched)
                + (4 if SCHEDULING.search(line) else 0)
                + (2 if matches else 0)
            )
            transaction_citations = [
                reference(chunk, item) for item in near if TRANSACTION.search(item)
            ][:3]
            markers = transaction_terms(transaction_citations)
            reverse.append(
                (
                    rank,
                    {
                        "kind": kind,
                        "location": location(chunk, offset),
                        "evidence": citations,
                        "basis": "unverified" if not matched else "source",
                        "graph_id": caller_paths.get(key),
                        "transaction_evidence": transaction_citations,
                        "transaction_markers": markers,
                        "different_transaction_markers": bool(
                            markers
                            and selected_boundaries
                            and tuple(markers) not in selected_boundaries
                        ),
                    },
                )
            )
    reverse.sort(key=lambda row: -row[0])
    unique = {}
    for _, item in reverse:
        loc = item["location"]
        unique.setdefault(
            (loc["repository_id"], loc["path"], loc["line"], item["kind"]), item
        )
        if len(unique) >= 80:
            break
    model_chunks.sort(key=lambda pair: -pair[0])
    return {
        "writes": list(by_id.values()),
        "reverse": list(unique.values()),
        "manifest": manifest,
        "chunks": [chunk for _, chunk in model_chunks[:22]],
    }
