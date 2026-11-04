"""Universal index phase 2, Task 5: PDF, legacy Office, mail and image metadata as views."""
from pathlib import Path

import pytest

from imperal_sdk.universal.view import view_of

FIXTURES = Path(__file__).parent / "fixtures" / "universal"


def FIX(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_pdf_pages_and_bookmarks():
    pytest.importorskip("pypdf")
    v = view_of("r.pdf", FIX("two_pages.pdf"))
    assert [s.kind for s in v.sections].count("page") == 2 and any(s.kind == "section" for s in v.sections)
    assert "Total due 1200 EUR" in v.text and {"Summary", "Totals"} <= {s.title for s in v.sections}


def test_password_pdf_says_why():
    pytest.importorskip("pypdf")
    assert "encrypted" in view_of("p.pdf", FIX("locked.pdf")).skipped


def test_legacy_doc_has_text():
    assert "Invoice" in view_of("old.doc", FIX("invoice.doc")).text


def test_legacy_doc_without_any_converter(monkeypatch):
    """Linux has no textutil: the OLE streams are read directly."""
    pytest.importorskip("olefile")
    from imperal_sdk.universal import legacy
    monkeypatch.setattr(legacy, "_converter", lambda ext: None)
    v = view_of("old.doc", FIX("invoice.doc"))
    assert "Invoice 117" in v.text and v.meta.get("extracted") == "approximate"


def test_mail_is_a_document_with_its_attachment():
    v = view_of("m.eml", FIX("with_attachment.eml"))
    assert v.meta["from"] == "bank@example.com" and v.meta["subject"] == "Your statement"
    assert v.links == ["statement.pdf"] and "statement attached" in v.text


def test_mbox_is_one_section_per_message():
    one = FIX("with_attachment.eml")
    box = b"From bank@example.com Tue Nov  3 10:00:00 2026\n" + one + b"\nFrom x@example.com Wed Nov  4 10:00:00 2026\n" + one
    v = view_of("inbox.mbox", box)
    assert [s.kind for s in v.sections] == ["message", "message"]


def test_image_is_metadata_only():
    v = view_of("p.jpg", FIX("exif.jpg"))
    assert v.text == "" and v.meta["taken"] == "2026:11:03 10:00:00"


def test_ole_text_runs_are_linear_and_bounded():
    import time

    from imperal_sdk.universal.legacy import _runs
    blob = b"".join(f"word{i:06d} ".encode("utf-16-le") + b"\x00\x00" for i in range(60_000))
    t0 = time.monotonic()
    out = _runs(blob)
    assert time.monotonic() - t0 < 10 and len(out) > 1000


def test_pdf_extraction_stops_when_the_view_is_full(monkeypatch):
    pytest.importorskip("pypdf")
    from imperal_sdk.universal import view as uv
    monkeypatch.setattr(uv, "MAX_VIEW_CHARS", 20)
    v = view_of("r.pdf", FIX("two_pages.pdf"))
    assert [s.kind for s in v.sections].count("page") == 1          # page 2 never extracted
