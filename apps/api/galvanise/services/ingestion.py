import base64
import io
import re
import zipfile
from pathlib import PurePosixPath

from sqlalchemy import select, update

from galvanise.config import settings
from galvanise.database import SessionLocal
from galvanise.integrations.github import account_token, api
from galvanise.models import (
    ConnectedSource,
    IngestionJob,
    SourceDocument,
    TechnicalGraph,
    now,
)
from galvanise.security import decrypt

MAX_TEXT = 300_000
ALLOWED = {".txt", ".md", ".pdf", ".docx"}


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
        "[REDACTED PRIVATE KEY]",
        text,
        flags=re.S,
    )


def extract(data, name):
    if len(data) > settings.max_upload_bytes:
        raise ValueError("File exceeds upload limit")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in (".txt", ".md"):
        text = data.decode("utf-8-sig")
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
            chunks.append(value)
        text = "\n".join(chunks)
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


def _extract_child(connection, data, name):
    try:
        import resource
        import sys

        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        if sys.platform.startswith("linux"):
            resource.setrlimit(
                resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024)
            )
        connection.send(("ok", extract(data, name)))
    except BaseException:
        connection.send(
            ("error", "Document cannot be extracted within supported limits")
        )
    finally:
        connection.close()


def extract_bounded(data, name):
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_extract_child, args=(sender, data, name), daemon=True
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
    token = account_token(db, payload["user_id"])
    repo = payload["full_name"]
    info = api(token, "/repos/" + repo)
    if info.get("private"):
        raise ValueError("Private repositories require a read-only GitHub App")
    tree = api(
        token, f"/repos/{repo}/git/trees/{info['default_branch']}", {"recursive": "1"}
    )
    if tree.get("truncated"):
        raise ValueError(
            "Repository tree is too large; import a focused Graphify export"
        )
    entries = [e for e in tree.get("tree", []) if e.get("type") == "blob"]
    if len(entries) > 3000:
        raise ValueError("Repository exceeds 3000 files")
    source = db.get(ConnectedSource, payload["source_id"])
    nodes = []
    total = 0
    indexed = 0
    text_extensions = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".cs",
        ".rb",
        ".php",
        ".c",
        ".h",
        ".cpp",
        ".sql",
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
    }
    for entry in entries:
        path = entry["path"]
        parts = PurePosixPath(path).parts
        if any(
            p in ("node_modules", ".git", "vendor", "dist", "build", ".venv")
            for p in parts
        ):
            continue
        if PurePosixPath(path).name.startswith(".env") or any(
            x in path.lower() for x in ("credentials", "id_rsa", ".pem", ".key")
        ):
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
            PurePosixPath(path).suffix.lower() not in text_extensions
            or entry.get("size", 0) > 100_000
            or indexed >= 300
        ):
            continue
        total += entry.get("size", 0)
        if total > 3_000_000:
            continue
        blob = api(token, f"/repos/{repo}/git/blobs/{entry['sha']}")
        raw = base64.b64decode(blob.get("content", ""))
        if len(raw) > 100_000:
            continue
        try:
            content = redact(raw.decode("utf-8"))
        except UnicodeDecodeError:
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
        "dependencies_inferred": False,
    }


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
        job.status = "running"
        db.commit()
        try:
            if job.kind == "document":
                data = base64.b64decode(decrypt(job.payload["content_ciphertext"]))
                text = extract_bounded(data, job.payload["name"])
                db.add(
                    SourceDocument(
                        project_id=job.project_id,
                        name=job.payload["name"],
                        content=text,
                        media_type=job.payload["media_type"],
                        metadata_json={"untrusted": True, "redacted": True},
                    )
                )
            elif job.kind == "github":
                ingest_repository(db, job)
            else:
                raise ValueError("Unsupported job kind")
            job.status = "completed"
            job.error = None
        except Exception as error:
            db.rollback()
            job = db.get(IngestionJob, job.id)
            job.status = "failed"
            job.error = "Ingestion failed. Check file format, extraction limits, or GitHub connection."
            if isinstance(error, (ValueError, UnicodeDecodeError, zipfile.BadZipFile)):
                job.error = "Document or repository does not satisfy ingestion limits or format requirements."
            if job.payload.get("source_id"):
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
    recover_jobs()
    while not stop.is_set():
        try:
            if not process_next_job():
                stop.wait(1)
        except Exception:
            stop.wait(2)
