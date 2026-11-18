"""Worker subprocess entry point. The working directory is a private build directory."""

from pathlib import Path

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract


if __name__ == "__main__":
    work = Path.cwd()
    root = work / "source"
    files = sorted(path for path in root.rglob("*") if path.is_file())
    result = extract(files, root=root, cache_root=work, parallel=False)
    graph = build_from_json(result, directed=True, root=root)
    to_json(graph, {}, str(work / "graph.json"), original_links=result["edges"])
