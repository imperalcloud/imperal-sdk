"""Universal index phase 2, Task 6: views in the code index -- every kind gets a FileIndex, code keeps its path."""
import io
import os
import zipfile

from imperal_sdk.code_index import build_index, parse_file
from imperal_sdk.universal.index import parse_view, read_view
from imperal_sdk.universal.view import view_of


def _docx() -> bytes:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    p = lambda t, s=None: (f'<w:p><w:pPr><w:pStyle w:val="{s}"/></w:pPr>' if s else "<w:p>") + f"<w:r><w:t>{t}</w:t></w:r></w:p>"  # noqa: E731
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document {ns}><w:body>{p('Agreement', 'Heading1')}{p('Terms apply.')}"
                                        f"{p('Payment', 'Heading2')}{p('30 days.')}</w:body></w:document>")
    return buf.getvalue()


def test_every_kind_in_one_index_and_placeholders_never_read(tmp_path):
    (tmp_path / "a.py").write_text("def settle():\n    return 1\n")
    (tmp_path / "b.kt").write_text("class Wallet { fun pay() = 1 }\n")
    (tmp_path / "c.docx").write_bytes(_docx())
    (tmp_path / "d.csv").write_text("date,amount\n2026-01-02,500\n")
    (tmp_path / "e.icloud").write_bytes(b"bplist00")
    idx = build_index(str(tmp_path), ["a.py", "b.kt", "c.docx", "d.csv", "e.icloud"])
    kinds = {p: f.kind for p, f in idx.files.items()}
    assert kinds == {"a.py": "code", "b.kt": "code", "c.docx": "document", "d.csv": "data"}
    assert [s.name for s in idx.files["c.docx"].symbols] == ["Agreement", "Payment"]
    assert read_view(str(tmp_path), "e.icloud").skipped == "placeholder"


def test_code_files_keep_their_facts_byte_for_byte(tmp_path):
    src = "import os\n\ndef settle(x):\n    return os.path.join(x)\n"
    (tmp_path / "a.py").write_text(src)
    assert build_index(str(tmp_path), ["a.py"]).files["a.py"] == parse_file("a.py", src)


def test_a_file_over_its_kind_cap_is_skipped_unread(tmp_path, monkeypatch):
    from imperal_sdk.universal import index as ui
    (tmp_path / "big.pdf").write_bytes(b"%PDF-1.4" + b"0" * 2000)
    monkeypatch.setitem(ui.RAW_CAP, "document", 1000)
    assert "over" in read_view(str(tmp_path), "big.pdf").skipped


def test_parse_view_carries_sections_and_links():
    fi = parse_view("n.md", view_of("n.md", b"# Q3\n[ledger](ledger.xlsx)\n"))
    assert fi.kind == "document" and fi.symbols[0].name == "Q3" and fi.symbols[0].kind == "section"


def test_a_document_is_chunked_over_its_view(tmp_path):
    from imperal_sdk.code_index import chunk_file
    (tmp_path / "c.docx").write_bytes(_docx())
    fi = build_index(str(tmp_path), ["c.docx"]).files["c.docx"]
    chunks = chunk_file(str(tmp_path), fi)
    assert chunks and any("30 days." in c.text for c in chunks)
