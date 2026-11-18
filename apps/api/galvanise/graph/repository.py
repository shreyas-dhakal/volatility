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
    source = db.scalar(
        select(ConnectedSource).where(
            ConnectedSource.id == job.payload["source_id"],
            ConnectedSource.project_id == job.project_id,
            ConnectedSource.kind == "github",
        )
    )
    if source is None:
        raise GraphBuildError("The repository was removed.")

    documents = db.scalars(
        select(SourceDocument)
        .where(
            SourceDocument.project_id == job.project_id,
            SourceDocument.source_id == source.id,
        )
        .order_by(SourceDocument.name)
    )
    with TemporaryDirectory() as directory:
        work = Path(directory)
        root = work / "source"
        root.mkdir()
        for document in documents:
            path = Path(document.name)
            if path.is_absolute() or ".." in path.parts or not path.name:
                raise GraphBuildError("The repository contains an invalid file path.")
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(document.content, encoding="utf-8")
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
    info = source.metadata_json
    metadata.update(
        generator="graphify",
        tree_sha=info.get("tree_sha"),
        indexed_text_files=info.get("indexed_text_files"),
        skipped_files=len(info.get("skipped", [])),
    )
    db.add(
        TechnicalGraph(
            project_id=job.project_id,
            source_id=source.id,
            name=source.name,
            nodes_json=nodes,
            edges_json=edges,
            metadata_json=metadata,
            export_json=export,
        )
    )
