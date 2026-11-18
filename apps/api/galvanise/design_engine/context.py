"""Stage-specific source retrieval and typed inputs for structured reasoning."""

import re
from collections import Counter
from math import log
from typing import Any

from pydantic import create_model

from .records import COLLECTIONS
from .schemas import Model, Snapshot, Text


class Chunk(Model):
    id: Text
    text: str
    locator: dict[str, Any]


class Correction(Model):
    chunk_id: Text
    text: Text


class StageInput(Model):
    chunks: list[Chunk]
    correction: Correction | None


PRIOR = {
    "inventory": ("actors", "implementation_findings"),
    "use_cases": ("actors", "implementation_findings", "use_cases"),
    "volatility": (
        "actors",
        "use_cases",
        "implementation_findings",
        "volatilities",
        "questions",
    ),
    "boundaries": COLLECTIONS[:7] + ("questions", "findings"),
    "walkthroughs": COLLECTIONS,
    "review": COLLECTIONS,
}


def input_type(stage, fields):
    prior = create_model(
        stage.title() + "Records",
        __base__=Model,
        **{field: (Snapshot.model_fields[field].annotation, ...) for field in fields},
    )
    return create_model(
        stage.title() + "Input", __base__=StageInput, prior=(prior, ...)
    )


INPUT_TYPES = {stage: input_type(stage, fields) for stage, fields in PRIOR.items()}
BATCH_CHARS = 28_000
RETRIEVAL_CHARS = 42_000
OBSERVATION_CHARS = 24_000


def inventory_batches(chunks):
    batch = []
    size = 0
    for chunk in chunks:
        # Normally ingestion splits at semantic boundaries. The fallback also
        # lets a single oversized chunk keep its original ID and verifiable text.
        for start in range(0, len(chunk["text"]), BATCH_CHARS):
            part = chunk | {"text": chunk["text"][start : start + BATCH_CHARS]}
            if batch and size + len(part["text"]) > BATCH_CHARS:
                yield batch
                batch, size = [], 0
            batch.append(part)
            size += len(part["text"])
    if batch:
        yield batch


def terms(text):
    return set(re.findall(r"[^\W_]{3,}", text.casefold()))


VOCABULARY = {
    "inventory": "current implementation actor resource observes workflow",
    "use_cases": "actor trigger workflow goal outcome except fails",
    "volatility": "changes policy differences customer installation alternatives vendors assumptions",
    "boundaries": "ownership responsibility rule contract access failure policy driver",
    "walkthroughs": "exception outcome failure contract decision alternative change",
    "review": "exception contradiction failure duplicated decision leak uncertainty",
}


def relevant_chunks(stage, chunks, snapshot, correction):
    query = terms(VOCABULARY[stage] + " " + (correction["text"] if correction else ""))
    grounded = set()
    for field in PRIOR[stage]:
        if field == "implementation_findings":
            continue
        for row in snapshot[field]:
            for value in row.values():
                if isinstance(value, str):
                    query.update(terms(value))
            grounded.update(cite["chunk_id"] for cite in row["evidence"])
    tokens = [terms(c["text"]) for c in chunks]
    frequency = Counter(t for words in tokens for t in words)
    weights = {t: log(1 + len(chunks) / (1 + frequency[t])) for t in query}
    correction_id = correction["chunk_id"] if correction else None
    ranked = sorted(
        range(len(chunks)),
        key=lambda index: (
            chunks[index]["id"] == correction_id,
            sum(weights[t] for t in tokens[index] & query)
            + (1 if chunks[index]["id"] in grounded else 0),
            -index,
        ),
        reverse=True,
    )
    selected = []
    remaining = RETRIEVAL_CHARS
    for index in ranked:
        c = chunks[index]
        if len(c["text"]) > remaining:
            if not selected:
                selected.append(c | {"text": c["text"][:remaining]})
                break
            continue
        selected.append(c)
        remaining -= len(c["text"])
    return selected


def context_for(stage, snapshot, chunks, correction):
    prior = {field: snapshot[field] for field in PRIOR[stage]}
    # Keep inventory summaries bounded even when the project spans thousands of chunks.
    # The original observations remain in the snapshot with all their provenance.
    if "implementation_findings" in prior:
        selected_ids = {c["id"] for c in chunks}
        ranked = sorted(
            prior["implementation_findings"],
            key=lambda r: not any(c["chunk_id"] in selected_ids for c in r["evidence"]),
        )
        prior["implementation_findings"] = []
        remaining = OBSERVATION_CHARS
        for row in ranked:
            size = len(str(row))
            if size <= remaining:
                prior["implementation_findings"].append(row)
                remaining -= size
    return (
        INPUT_TYPES[stage]
        .model_validate({"prior": prior, "chunks": chunks, "correction": correction})
        .model_dump()
    )
