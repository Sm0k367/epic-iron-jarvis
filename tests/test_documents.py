"""Documents module — round-trip every supported file type, offline.

Each structured format is written with ``write_document`` and read back with
``extract_text``; the content must survive the round trip. Also covers
extension dispatch, the image note, the unsupported-binary ``ValueError``, and
the read/write Tools through a minimal ``ToolContext``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iron_jarvis.documents import (
    SUPPORTED_READ,
    SUPPORTED_WRITE,
    document_tools,
    extract_text,
    write_document,
)
from iron_jarvis.tools.base import ToolContext


# --- round-trips --------------------------------------------------------------


def test_roundtrip_docx(tmp_path):
    p = tmp_path / "doc.docx"
    write_document(p, "Hello world\nSecond paragraph")
    text = extract_text(p)
    assert "Hello world" in text
    assert "Second paragraph" in text


def test_roundtrip_xlsx_rows(tmp_path):
    p = tmp_path / "sheet.xlsx"
    rows = [["name", "age"], ["Tony", "48"], ["Pepper", "40"]]
    write_document(p, rows)
    text = extract_text(p)
    for token in ("name", "age", "Tony", "48", "Pepper"):
        assert token in text


def test_roundtrip_pptx(tmp_path):
    p = tmp_path / "deck.pptx"
    write_document(p, "Quarterly Review\nRevenue up\nCosts down")
    text = extract_text(p)
    assert "Quarterly Review" in text
    assert "Revenue up" in text
    assert "Costs down" in text


def test_roundtrip_pdf(tmp_path):
    p = tmp_path / "report.pdf"
    write_document(p, "Confidential financial summary for Stark Industries")
    text = extract_text(p)
    # A known word must appear in the extracted text.
    assert "Confidential" in text


def test_roundtrip_csv(tmp_path):
    p = tmp_path / "data.csv"
    write_document(p, [["a", "b", "c"], ["1", "2", "3"]])
    text = extract_text(p)
    for token in ("a", "b", "c", "1", "2", "3"):
        assert token in text


def test_roundtrip_md(tmp_path):
    p = tmp_path / "notes.md"
    write_document(p, "# Title\n\nSome **markdown** body.")
    text = extract_text(p)
    assert "# Title" in text
    assert "markdown" in text


def test_roundtrip_txt(tmp_path):
    p = tmp_path / "plain.txt"
    write_document(p, "just some plain text")
    assert extract_text(p) == "just some plain text"


def test_kind_overrides_suffix(tmp_path):
    # A .dat file written as a docx is still a real Word document.
    p = tmp_path / "weird.dat"
    write_document(p, "kind override works", kind="docx")
    # Rename so extract_text dispatches as a docx.
    docx_path = tmp_path / "weird.docx"
    p.rename(docx_path)
    assert "kind override works" in extract_text(docx_path)


# --- dispatch / edge cases ----------------------------------------------------


def test_extract_dispatches_by_extension(tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_text("plain", encoding="utf-8")
    json_file = tmp_path / "b.json"
    json_file.write_text('{"k": 1}', encoding="utf-8")
    assert extract_text(txt) == "plain"
    assert '"k": 1' in extract_text(json_file)


def test_unknown_but_text_is_read(tmp_path):
    p = tmp_path / "mystery.conf"
    p.write_text("key = value", encoding="utf-8")
    assert "key = value" in extract_text(p)


def test_image_returns_note(tmp_path):
    from PIL import Image

    p = tmp_path / "pic.png"
    Image.new("RGB", (24, 16), color=(10, 20, 30)).save(p)
    note = extract_text(p)
    assert note.startswith("[image")
    assert "24x16" in note
    assert "RGB" in note


def test_unsupported_binary_raises(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x00\x01\x02\x03binary\x00data")
    with pytest.raises(ValueError):
        extract_text(p)


def test_supported_sets_are_populated():
    assert {".pdf", ".docx", ".xlsx", ".pptx", ".csv"} <= SUPPORTED_READ
    assert {".docx", ".xlsx", ".pptx", ".pdf", ".csv", ".txt", ".md"} <= SUPPORTED_WRITE


# --- tools --------------------------------------------------------------------


def _ctx(workspace: Path) -> ToolContext:
    """Minimal ToolContext — only ``.workspace`` is used by the document tools."""
    return ToolContext(
        workspace=workspace,
        session_id="t",
        agent_run_id="t",
        config=None,
        event_bus=None,
        engine=None,
    )


def _tool(name: str):
    return next(t for t in document_tools() if t.name == name)


async def test_read_document_tool_absolute_path(tmp_path):
    target = tmp_path / "outside" / "real.txt"
    target.parent.mkdir(parents=True)
    target.write_text("read me from anywhere", encoding="utf-8")

    ws = tmp_path / "ws"
    ws.mkdir()
    res = await _tool("read_document").execute({"path": str(target)}, _ctx(ws))
    assert res.ok
    assert res.output == "read me from anywhere"


async def test_write_document_tool_within_workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    ctx = _ctx(ws)

    res = await _tool("write_document").execute(
        {"path": "out/memo.docx", "content": "boardroom memo"}, ctx
    )
    assert res.ok
    written = ws / "out" / "memo.docx"
    assert written.is_file()
    assert "boardroom memo" in extract_text(written)


async def test_write_document_tool_rejects_escape(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    res = await _tool("write_document").execute(
        {"path": "../escape.txt", "content": "nope"}, _ctx(ws)
    )
    assert not res.ok


async def test_extract_pdf_tool(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    pdf = ws / "doc.pdf"
    write_document(pdf, "extract pdf tool word marker")

    res = await _tool("extract_pdf").execute({"path": "doc.pdf"}, _ctx(ws))
    assert res.ok
    assert "marker" in res.output

    # Non-PDF target is rejected.
    bad = await _tool("extract_pdf").execute({"path": "doc.txt"}, _ctx(ws))
    assert not bad.ok


async def test_read_document_tool_missing_file_is_graceful(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    res = await _tool("read_document").execute({"path": "nope.pdf"}, _ctx(ws))
    assert not res.ok
    assert res.error
