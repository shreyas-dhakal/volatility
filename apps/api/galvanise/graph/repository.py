"""Build a structural Graphify export from the repository's indexed text."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select

from galvanise.graph.core import normalize
from galvanise.models import ConnectedSource, SourceDocument, TechnicalGraph


class GraphBuildError(ValueError):
    pass


def build_repository_graph(db, job):
    source_id = job.payload.get("source_id")
    docs = select(SourceDocument).where(SourceDocument.project_id == job.project_id)
    if source_id:
        source = db.scalar(
            select(ConnectedSource).where(
                ConnectedSource.id == source_id,
                ConnectedSource.project_id == job.project_id,
                ConnectedSource.kind == "github",
            )
        )
        if source is None:
            raise GraphBuildError("The repository was removed.")
        name = source.name
        info = source.metadata_json
        skipped = len(info.get("skipped", []))
        provenance = {"tree_sha": info.get("tree_sha")}
        docs = docs.where(SourceDocument.source_id == source_id)
    else:
        upload_id = job.payload["upload_id"]
        name = job.payload["name"]
        skipped = 0
        provenance = {"upload_id": upload_id}
        docs = docs.where(
            SourceDocument.metadata_json["upload_id"].as_string() == upload_id
        )
    indexed = 0
    with TemporaryDirectory() as directory:
        work = Path(directory)
        root = work / "source"
        root.mkdir()
        for document in db.scalars(docs.order_by(SourceDocument.name)):
            if (
                document.metadata_json.get("extraction_status", "analyzed")
                != "analyzed"
            ):
                skipped += 1
                continue
            path = Path(document.name)
            if path.is_absolute() or ".." in path.parts or not path.name:
                raise GraphBuildError("The repository contains an invalid file path.")
            target = root / path
            if target.exists():
                raise GraphBuildError("The archive contains duplicate file paths.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(document.content, encoding="utf-8")
            indexed += 1
        # Isolated Python prevents repository files from shadowing installed modules.
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(Path(__file__).with_name("extract_snapshot.py")),
                ],
                cwd=work,
                timeout=180,
                check=True,
                env={"PATH": ""},
            )
        except subprocess.TimeoutExpired as exc:
            raise GraphBuildError(
                "Graphify exceeded the three-minute build limit."
            ) from exc
        output = work / "graph.json"
        if output.stat().st_size > 10 * 1024 * 1024:
            raise GraphBuildError("The generated code map exceeds the 10 MiB limit.")
        export = json.loads(output.read_text(encoding="utf-8"))
    if not export["nodes"]:
        raise GraphBuildError("Graphify found no supported code in the indexed files.")
    nodes, edges, metadata = normalize(export)
    metadata.update(
        generator="graphify",
        indexed_text_files=indexed,
        skipped_files=skipped,
        **provenance,
    )
    db.add(
        TechnicalGraph(
            project_id=job.project_id,
            source_id=source_id,
            name=name,
            nodes_json=nodes,
            edges_json=edges,
            metadata_json=metadata,
            export_json=export,
        )
    )
