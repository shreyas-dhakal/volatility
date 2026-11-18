import base64
import io
import re
import zipfile
from pathlib import PurePosixPath

from fastapi import HTTPException
from sqlalchemy import select, update

from galvanise.clerk_identity import resolve_user
from galvanise.config import settings
from galvanise.database import SessionLocal
from galvanise.graph.repository import GraphBuildError, build_repository_graph
from galvanise.integrations.github import EmptyRepository, account_token, api
from galvanise.models import (
    ConnectedSource,
    IngestionJob,
    SourceDocument,
    TechnicalGraph,
    User,
    now,
)
from galvanise.security import decrypt

MAX_TEXT = 300_000
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".rst",
    ".csv",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".xml",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".cs",
    ".rb",
    ".php",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".sql",
    ".kt",
    ".kts",
    ".swift",
    ".sh",
    ".html",
    ".css",
    ".vue",
    ".scala",
    ".dart",
    ".ex",
    ".exs",
}
ALLOWED = TEXT_EXTENSIONS | {".pdf", ".docx", ".zip"}


def relative_path(name):
    path = PurePosixPath(name.replace("\\", "/"))
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.name
        or ":" in path.parts[0]
    ):
        return path.name or "document"
    return str(path)


def excluded_path(path):
    return (
        any(
            p in ("node_modules", ".git", "vendor", "dist", "build", ".venv")
            for p in PurePosixPath(path).parts
        )
        or PurePosixPath(path).name.startswith(".env")
        or any(x in path.lower() for x in ("credentials", "id_rsa", ".pem", ".key"))
    )


def redact(text):
    text = re.sub(
        r"(?im)((?:password|passwd|api[_-]?key|access[_-]?token|secret|authorization)\s*[:=]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b",
        "[REDACTED]",
        text,
    )
    return re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
        lambda match: "[REDACTED PRIVATE KEY]" + re.sub(r"[^\r\n\f]", "", match[0]),
        text,
        flags=re.S,
    )


def extract(data, name):
    if len(data) > settings.max_upload_bytes:
        raise ValueError("File exceeds upload limit")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("Binary data in text file")
    elif suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > 200:
            raise ValueError("PDF encrypted or exceeds 200 pages")
        chunks = []
        total = 0
        for page in reader.pages:
            # Reject compressed page streams before text extraction allocates them.
            contents = page.get("/Contents")
            if contents is not None:
                objs = contents if isinstance(contents, list) else [contents]
                if (
                    sum(len(getattr(obj.get_object(), "_data", b"")) for obj in objs)
                    > 2_000_000
                ):
                    raise ValueError("PDF page too complex")
            value = page.extract_text() or ""
            total += len(value)
            if total > MAX_TEXT:
                raise ValueError("Extracted text exceeds limit")
            chunks.append(value.replace("\f", "\n"))
        text = "\f".join(chunks)
    elif suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if (
                len(archive.infolist()) > 1000
                or sum(i.file_size for i in archive.infolist()) > 20_000_000
            ):
                raise ValueError("DOCX expanded size exceeds limit")
        from docx import Document

        doc = Document(io.BytesIO(data))
        text = "\n".join(
            [p.text for p in doc.paragraphs]
            + [
                cell.text
                for table in doc.tables
                for row in table.rows
                for cell in row.cells
            ]
        )
    else:
        raise ValueError("Unsupported document format")
    if len(text) > MAX_TEXT:
        raise ValueError("Extracted text exceeds limit")
    if not text.strip():
        raise ValueError("Document has no extractable text; scanned PDFs need OCR")
    return redact(text)


def extract_project(data, name):
    """Read archive members in memory inside the bounded extraction subprocess."""
    if PurePosixPath(name).suffix.lower() != ".zip":
        return [{"path": name, "text": extract(data, name), "status": "analyzed"}]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        if len(files) > 1000 or sum(i.file_size for i in files) > 20_000_000:
            raise ValueError("Project archive exceeds extraction limits")
        results = []
        for item in files:
            path = relative_path(item.filename)
            member = {"path": path, "text": "", "status": "unsupported"}
            suffix = PurePosixPath(path).suffix.lower()
            if (
                path == item.filename
                and not excluded_path(path)
                and suffix in ALLOWED - {".zip"}
            ):
                try:
                    member["text"] = extract(archive.read(item), path)
                    member["status"] = "analyzed"
                except Exception:
                    member["status"] = "unreadable"
            results.append(member)
        if not results:
            raise ValueError("Empty archive")
        return results


def _extract_child(connection, data, name, project):
    try:
        import resource
        import sys

        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        if sys.platform.startswith("linux"):
            resource.setrlimit(
                resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024)
            )
        connection.send(
            ("ok", extract_project(data, name) if project else extract(data, name))
        )
    except BaseException:
        connection.send(
            ("error", "Document cannot be extracted within supported limits")
        )
    finally:
        connection.close()


def extract_bounded(data, name, *, project=False):
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_extract_child, args=(sender, data, name, project), daemon=True
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(20):
            raise ValueError("Document extraction timed out")
        try:
            status, text = receiver.recv()
        except EOFError:
            raise ValueError("Document extraction resource limit reached")
        if status != "ok":
            raise ValueError(text)
        return text
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)


def ingest_repository(db, job):
    payload = job.payload
    owner = db.get(User, payload["user_id"])
    if not owner or not owner.clerk_user_id:
        raise ValueError("GitHub connection unavailable")
    token = account_token(resolve_user(db, owner.clerk_user_id))
    repo = payload["full_name"]
    info = api(token, "/repos/" + repo)
    if (
        payload.get("repository_id") is not None
        and info["id"] != payload["repository_id"]
    ):
        raise ValueError("Repository identity changed")
    if info.get("private") and (not token or not payload.get("repository_id")):
        raise ValueError("Select the private repository again to authorize this import")
    source = db.get(ConnectedSource, payload["source_id"])
    try:
        tree = api(
            token,
            f"/repos/{repo}/git/trees/{info['default_branch']}",
            {"recursive": "1"},
        )
    except EmptyRepository:
        tree = {"tree": []}
    if tree.get("truncated"):
        raise ValueError(
            "Repository tree is too large; import a focused Graphify export"
        )
    if not tree["tree"]:
        source.status = "empty"
        source.metadata_json = {
            "full_name": repo,
            "file_count": 0,
            "indexed_text_files": 0,
        }
        return
    entries = [e for e in tree.get("tree", []) if e.get("type") == "blob"]
    if len(entries) > 3000:
        raise ValueError("Repository exceeds 3000 files")
    nodes = []
    total = 0
    indexed = 0
    skipped = []
    for entry in entries:
        path = entry["path"]
        if excluded_path(path):
            skipped.append(
                {
                    "path": path,
                    "status": "unsupported",
                    "detail": "Excluded from repository ingestion",
                }
            )
            continue
        nodes.append(
            {
                "id": path,
                "label": PurePosixPath(path).name,
                "type": "file",
                "file_path": path,
                "source_id": source.id,
                "metadata": {"sha": entry["sha"], "repository": repo},
            }
        )
        if (
            PurePosixPath(path).suffix.lower() not in TEXT_EXTENSIONS
            or entry.get("size", 0) > 100_000
            or indexed >= 300
        ):
            status = (
                "unsupported"
                if PurePosixPath(path).suffix.lower() not in TEXT_EXTENSIONS
                else "partially analyzed"
            )
            skipped.append(
                {
                    "path": path,
                    "status": status,
                    "detail": "File type or repository indexing limit",
                }
            )
            continue
        total += entry.get("size", 0)
        if total > 3_000_000:
            skipped.append(
                {
                    "path": path,
                    "status": "partially analyzed",
                    "detail": "Repository byte limit",
                }
            )
            continue
        blob = api(token, f"/repos/{repo}/git/blobs/{entry['sha']}")
        raw = base64.b64decode(blob.get("content", ""))
        if len(raw) > 100_000:
            skipped.append(
                {
                    "path": path,
                    "status": "partially analyzed",
                    "detail": "File byte limit",
                }
            )
            continue
        try:
            content = redact(raw.decode("utf-8"))
            if "\x00" in content:
                raise ValueError("Binary content")
        except ValueError:
            skipped.append(
                {
                    "path": path,
                    "status": "unreadable",
                    "detail": "File is not UTF-8 text",
                }
            )
            continue
        db.add(
            SourceDocument(
                project_id=job.project_id,
                source_id=source.id,
                name=path,
                content=content,
                media_type="text/plain",
                metadata_json={"sha": entry["sha"], "untrusted": True},
            )
        )
        indexed += 1
    db.add(
        TechnicalGraph(
            project_id=job.project_id,
            source_id=source.id,
            name=repo + " file index",
            nodes_json=nodes,
            edges_json=[],
            metadata_json={
                "provenance": "GitHub tree API",
                "dependencies_inferred": False,
                "indexed_text_files": indexed,
            },
        )
    )
    source.status = "ready"
    source.metadata_json = {
        "full_name": repo,
        "indexed_text_files": indexed,
        "file_count": len(nodes),
        "tree_sha": tree.get("sha"),
        "skipped": skipped,
        "dependencies_inferred": False,
    }
    db.add(
        IngestionJob(
            project_id=job.project_id, kind="graphify", payload={"source_id": source.id}
        )
    )


def recover_jobs():
    with SessionLocal() as db:
        db.execute(
            update(IngestionJob)
            .where(IngestionJob.status == "running")
            .values(status="queued")
        )
        db.commit()


def process_next_job():
    with SessionLocal() as db:
        job = db.scalar(
            select(IngestionJob)
            .where(IngestionJob.status == "queued")
            .order_by(IngestionJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        job_id = job.id
        job.status = "running"
        db.commit()
        try:
            if job.kind == "document":
                data = base64.b64decode(decrypt(job.payload["content_ciphertext"]))
                entries = extract_bounded(data, job.payload["name"], project=True)
                document_ids = []
                for entry in entries:
                    path, content = entry["path"], entry["text"]
                    metadata = {
                        "untrusted": True,
                        "redacted": True,
                        "upload_id": job.id,
                        "extraction_status": entry["status"],
                    }
                    if job.payload["name"].lower().endswith(".zip"):
                        metadata["archive"] = job.payload["name"]
                    if path.lower().endswith(".pdf"):
                        pages = content.split("\f")
                        metadata["page_lengths"] = [len(page) for page in pages]
                        content = "\n".join(pages)
                    doc = SourceDocument(
                        project_id=job.project_id,
                        name=path,
                        content=content,
                        media_type=job.payload["media_type"],
                        metadata_json=metadata,
                    )
                    db.add(doc)
                    db.flush()
                    document_ids.append(doc.id)
                job.payload = {**job.payload, "document_ids": document_ids}
                if job.payload["name"].lower().endswith(".zip"):
                    db.add(
                        IngestionJob(
                            project_id=job.project_id,
                            kind="graphify",
                            payload={"upload_id": job.id, "name": job.payload["name"]},
                        )
                    )
            elif job.kind in ("github", "graphify"):
                if job.kind == "graphify":
                    build_repository_graph(db, job)
                else:
                    ingest_repository(db, job)
                # Deleting the import revokes its job. Lock the job before
                # flushing staged files so deletion and publication serialize.
                with db.no_autoflush:
                    active = db.scalar(
                        select(IngestionJob.id)
                        .where(IngestionJob.id == job_id)
                        .with_for_update()
                    )
                if active is None:
                    db.rollback()
                    return True
            else:
                raise ValueError("Unsupported job kind")
            job.status = "completed"
            job.error = None
        except Exception as error:
            db.rollback()
            job = db.get(IngestionJob, job_id, with_for_update=True)
            if job is None:
                return True
            job.status = "failed"
            job.error = "Ingestion failed. Check file format, extraction limits, or GitHub connection."
            if isinstance(error, (ValueError, UnicodeDecodeError, zipfile.BadZipFile)):
                job.error = "Document or repository does not satisfy ingestion limits or format requirements."
            if job.kind == "github" and isinstance(error, HTTPException):
                job.error = error.detail
            if job.kind == "graphify":
                job.error = (
                    str(error)
                    if isinstance(error, GraphBuildError)
                    else "Graphify could not build this code map."
                )
            elif job.payload.get("source_id"):
                source = db.get(ConnectedSource, job.payload["source_id"])
                if source:
                    source.status = "failed"
        job.payload = {
            k: v for k, v in job.payload.items() if k != "content_ciphertext"
        }
        job.updated_at = now()
        db.commit()
        return True


def run_worker(stop):
    import threading
    from galvanise.design_engine.worker import consume

    recover_jobs()
    # Both consumers use the existing worker lifecycle. Lengthy model calls must
    # leave the document queue available for uploads and repository indexing.
    threading.Thread(target=consume, args=(stop,), daemon=True).start()
    while not stop.is_set():
        try:
            if not process_next_job():
                stop.wait(1)
        except Exception:
            stop.wait(2)
