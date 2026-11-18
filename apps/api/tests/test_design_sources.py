import io
import zipfile

from galvanise.design_engine.sources import split_section
from galvanise.services.ingestion import extract_project


def test_project_archive_reads_only_source_text_and_inventories_skips():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("src/gate.py", "raise RuntimeError('text only')")
        archive.writestr("img/icon.bin", bytes([255]))
        archive.writestr("bad.txt", bytes([255]))
        archive.writestr("secrets/.env", "key")
        archive.writestr("../escaped.py", "code")
    entries = extract_project(buf.getvalue(), "project.zip")
    assert [(e["path"], e["status"]) for e in entries] == [
        ("src/gate.py", "analyzed"),
        ("img/icon.bin", "unsupported"),
        ("bad.txt", "unreadable"),
        ("secrets/.env", "unsupported"),
        ("escaped.py", "unsupported"),
    ]
    assert entries[0]["text"].startswith("raise RuntimeError")


def test_chunks_overlap_without_losing_long_lines_or_source_coordinates():
    text = "def start():\n" + "x" * 16000 + "\ndef end():\n    return True"
    parts = list(split_section(text))
    assert len(parts) > 3
    assert all(len(part) <= 4800 for part, _, _ in parts)
    assert parts[0][1] == 1 and parts[-1][2] == 4
    assert all(first == last == 2 for _, first, last in parts[1:-1])
    for (left, *_), (right, *_) in zip(parts, parts[1:]):
        assert left[-200:] in right[:1000]
