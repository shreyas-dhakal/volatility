"""Materialize immutable evidence from project-owned, already extracted text."""

import bisect
import hashlib
import json
import re
from pathlib import PurePosixPath

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from galvanise.models import (
    ConnectedSource,
    Conversation,
    DesignChunk,
    DesignSource,
    IngestionJob,
    KnowledgeRecord,
    Message,
    SourceDocument,
    TechnicalGraph,
    uid,
)
from galvanise.services.ingestion import TEXT_EXTENSIONS, redact


def insert_once(db, model, values, keys):
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    return db.execute(
        insert(model).values(**values).on_conflict_do_nothing(index_elements=keys)
    )


def scoped(db, model, project_id):
    return select(model).where(model.project_id == project_id)


def user_message(db, project_id, message_id):
    message = db.scalar(
        scoped(db, Message, project_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.id == message_id,
            Message.role == "user",
            Conversation.project_id == project_id,
        )
    )
    if message is None:
        raise HTTPException(404, "User message not found")
    return message


def validate_selection(db, project_id, ids):
    if not ids:
        return
    docs = db.scalars(
        select(SourceDocument.id).where(
            SourceDocument.project_id == project_id, SourceDocument.id.in_(ids)
        )
    )
    jobs = db.scalars(
        select(IngestionJob.id).where(
            IngestionJob.project_id == project_id,
            IngestionJob.id.in_(ids),
            IngestionJob.kind == "document",
        )
    )
    if set(ids) - set(docs) - set(jobs):
        raise HTTPException(404, "Selected upload not found")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def split_section(text):
    """Use line/paragraph/declaration breaks and retain offsets even for long lines."""
    lines = [0] + [m.end() for m in re.finditer("\n", text)]
    boundaries = [
        m.start()
        for m in re.finditer(
            r"(?m)^(?:[ \t]*(?:class |(?:async )?def |(?:export )?function |func |#)|(?<=\n)\n)",
            text,
        )
    ]
    start = 0
    while start < len(text):
        end = min(len(text), start + 4800)  # approximate 1,200 tokens
        if end < len(text):
            for breaks in (boundaries, lines):
                i = bisect.bisect_right(breaks, end) - 1
                if i >= 0 and breaks[i] >= start + 3200:
                    end = breaks[i]
                    break
        if text[start:end].strip():
            yield (
                text[start:end],
                bisect.bisect_right(lines, start),
                bisect.bisect_right(lines, end - 1),
            )
        if end == len(text):
            break
        # Keep about 150 tokens of context. Snap to a nearby full line if possible.
        target = end - 600
        candidate = lines[bisect.bisect_right(lines, target) - 1]
        start = candidate if candidate >= target - 160 else target


def store(
    db,
    project_id,
    origin,
    locator,
    sections=(),
    *,
    status="analyzed",
    detail="",
    document_id=None,
    message_id=None,
):
    sections = list(sections)
    if status == "analyzed" and not any(text.strip() for _, text in sections):
        status, detail = "unreadable", "No extractable text"
    fingerprint = digest(
        json.dumps([locator, sections, status, detail], sort_keys=True)
    )
    values = dict(
        id=uid(),
        project_id=project_id,
        origin=origin,
        content_hash=fingerprint,
        locator_json=locator,
        extraction_status=status,
        detail=detail,
        document_id=document_id,
        message_id=message_id,
    )
    keys = ["project_id", "origin", "content_hash"]
    result = insert_once(db, DesignSource, values, keys)
    if result.rowcount == 0:
        return db.scalar(
            select(DesignSource.id).where(
                DesignSource.project_id == project_id,
                DesignSource.origin == origin,
                DesignSource.content_hash == fingerprint,
            )
        )
    ordinal = 0
    for section, value in sections:
        for part, first, last in split_section(value):
            db.add(
                DesignChunk(
                    source_id=values["id"],
                    ordinal=ordinal,
                    text=part,
                    content_hash=digest(part),
                    locator_json={
                        **locator,
                        **section,
                        "line_start": first,
                        "line_end": last,
                    },
                )
            )
            ordinal += 1
    return values["id"]


def store_document(db, doc):
    meta = doc.metadata_json
    suffix = PurePosixPath(doc.name).suffix.lower()
    kind = (
        "code"
        if suffix in TEXT_EXTENSIONS - {".txt", ".md", ".rst", ".csv"}
        else "document"
    )
    locator = {"kind": kind, "path": doc.name}
    if doc.source_id:
        locator["repository_id"] = doc.source_id
    if meta.get("archive"):
        locator["archive"] = meta["archive"]
    status = meta.get("extraction_status", "analyzed")
    detail = ""
    sections = [({"section": doc.name}, doc.content)]
    if meta.get("page_lengths"):
        sections = []
        offset = 0
        for i, length in enumerate(meta["page_lengths"], 1):
            sections.append(({"page": i}, doc.content[offset : offset + length]))
            offset += length + 1
        if status == "analyzed" and not all(page.strip() for _, page in sections):
            status, detail = (
                "partially analyzed",
                "Some PDF pages have no extracted text",
            )
    origin = json.dumps(locator, sort_keys=True)
    return store(
        db,
        doc.project_id,
        origin,
        locator,
        sections,
        status=status,
        detail=detail,
        document_id=doc.id,
    )


def store_message(db, project_id, message_id):
    msg = user_message(db, project_id, message_id)
    return store(
        db,
        project_id,
        "message/" + msg.id,
        {"kind": "message", "message_id": msg.id, "role": "user"},
        [({}, redact(msg.content))],
        message_id=msg.id,
    )


def collect(db, project_id, selection):
    docs = scoped(db, SourceDocument, project_id)
    jobs = scoped(db, IngestionJob, project_id).where(IngestionJob.kind == "document")
    if selection is not None:
        jobs = jobs.where(IngestionJob.id.in_(selection))
    selected_jobs = list(
        db.scalars(jobs.order_by(IngestionJob.created_at, IngestionJob.id))
    )
    if selection is not None:
        ids = set(selection)
        for job in selected_jobs:
            ids.update(job.payload.get("document_ids", []))
        docs = docs.where(SourceDocument.id.in_(ids))
    source_ids = []
    indexed_paths = set()
    for doc in db.scalars(docs.order_by(SourceDocument.created_at, SourceDocument.id)):
        source_ids.append(store_document(db, doc))
        indexed_paths.add((doc.source_id, doc.name))
    for job in selected_jobs:
        if job.status == "completed":
            continue
        path = job.payload.get("name", job.id)
        source_ids.append(
            store(
                db,
                project_id,
                "upload/" + job.id,
                {"kind": "document", "path": path, "upload_id": job.id},
                status="unreadable",
                detail=job.error or f"Extraction is {job.status}",
            )
        )
    if selection is None:
        for repo in db.scalars(
            scoped(db, ConnectedSource, project_id).order_by(ConnectedSource.id)
        ):
            info = repo.metadata_json
            skipped = {item["path"]: item for item in info.get("skipped", [])}
            # Older repositories have a file index but no per-file exclusion metadata.
            for graph in db.scalars(
                scoped(db, TechnicalGraph, project_id).where(
                    TechnicalGraph.source_id == repo.id
                )
            ):
                for node in graph.nodes_json:
                    path = node.get("file_path")
                    if path and (repo.id, path) not in indexed_paths:
                        skipped.setdefault(
                            path,
                            {
                                "status": "unsupported",
                                "detail": "No text in repository index",
                            },
                        )
            if (
                repo.status != "ready"
                or not any(r == repo.id for r, _ in indexed_paths)
                and not skipped
            ):
                skipped[repo.name] = {
                    "status": "unreadable",
                    "detail": f"Repository {repo.status}; no indexed text",
                }
            for path, item in skipped.items():
                source_ids.append(
                    store(
                        db,
                        project_id,
                        f"repository/{repo.id}/{path}",
                        {"kind": "repository", "repository_id": repo.id, "path": path},
                        status=item["status"],
                        detail=item["detail"],
                    )
                )
    for req in db.scalars(
        scoped(db, KnowledgeRecord, project_id)
        .where(
            KnowledgeRecord.kind == "requirement", KnowledgeRecord.status != "rejected"
        )
        .order_by(KnowledgeRecord.id)
    ):
        source_ids.append(
            store(
                db,
                project_id,
                "requirement/" + req.id,
                {"kind": "requirement", "record_id": req.id, "section": req.title},
                [({}, redact(req.title + "\n" + req.description))],
            )
        )
    return list(dict.fromkeys(source_ids))


def evidence(db, project_id, source_ids):
    sources = {
        s.id: s
        for s in db.scalars(
            scoped(db, DesignSource, project_id).where(DesignSource.id.in_(source_ids))
        )
    }
    if set(sources) != set(source_ids):
        raise ValueError("A saved source does not belong to this project")
    grouped = {sid: [] for sid in source_ids}
    for c in db.scalars(
        select(DesignChunk)
        .where(DesignChunk.source_id.in_(source_ids))
        .order_by(DesignChunk.source_id, DesignChunk.ordinal)
    ):
        grouped[c.source_id].append(
            {"id": c.id, "text": c.text, "locator": c.locator_json}
        )
    manifest = []
    chunks = []
    for sid in source_ids:
        source = sources[sid]
        chunks.extend(grouped[sid])
        manifest.append(
            {
                "id": sid,
                "source_id": sid,
                **source.locator_json,
                "locator": source.locator_json,
                "status": source.extraction_status,
                "detail": source.detail,
                "chunk_count": len(grouped[sid]),
            }
        )
    return chunks, manifest
