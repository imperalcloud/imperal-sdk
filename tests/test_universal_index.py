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


def test_build_index_never_reads_a_secret_whoever_passes_it(tmp_path):
    (tmp_path / ".gnupg").mkdir()
    (tmp_path / ".gnupg" / "k.py").write_text("KEY = 1\n")
    (tmp_path / "credentials.json").write_text('{"k": 1}')
    assert build_index(str(tmp_path), [".gnupg/k.py", "credentials.json"]).files == {}


def test_a_link_in_the_path_into_a_secret_store_is_never_followed(tmp_path):
    (tmp_path / ".gnupg").mkdir()
    (tmp_path / ".gnupg" / "notes.md").write_text("# private\n")
    os.symlink(tmp_path / ".gnupg", tmp_path / "docs")
    assert build_index(str(tmp_path), ["docs/notes.md"]).files == {}
    assert read_view(str(tmp_path), "docs/notes.md") is None


def test_a_root_that_is_itself_a_secret_store_is_never_read(tmp_path):
    """Final review 2026-11-04: a unit rooted at ``~/secrets`` or ``~/.aws`` names its files without the store's own
    name -- the real absolute path decides."""
    from imperal_sdk.universal.kinds import kind_of, never_read_at
    for store in ("secrets", ".aws", "Library/Keychains"):
        root = tmp_path / store
        root.mkdir(parents=True)
        (root / "notes.md").write_text("# private\n")
        (root / "keys.py").write_text("KEY = 1\n")
        assert never_read_at(str(root), "notes.md")
        assert kind_of("notes.md", root=str(root)) is None
        assert build_index(str(root), ["notes.md", "keys.py"]).files == {}
        assert read_view(str(root), "notes.md") is None
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "notes.md").write_text("# fine\n")
    assert not never_read_at(str(tmp_path / "work"), "notes.md")


def test_a_fifo_never_opens(tmp_path):
    """Reading a FIFO waits forever: the build would hang on it."""
    os.mkfifo(tmp_path / "pipe.md")
    os.mkfifo(tmp_path / "pipe.py")
    assert read_view(str(tmp_path), "pipe.md").skipped == "not a regular file"
    assert build_index(str(tmp_path), ["pipe.md", "pipe.py"]).files == {}


def test_code_over_its_cap_is_never_parsed(tmp_path):
    """Final review 2026-11-04: a 200 MB .sql dump took 8 GB in the parser -- code over its cap is never read."""
    from imperal_sdk.universal.index import RAW_CAP
    (tmp_path / "dump.sql").write_text("SELECT 1;\n" * (RAW_CAP["code"] // 10 + 1))
    (tmp_path / "small.sql").write_text("SELECT 1;\n")
    assert set(build_index(str(tmp_path), ["dump.sql", "small.sql"]).files) == {"small.sql"}


def test_windows_cloud_files_are_placeholders():
    """OneDrive and other cloud files on Windows: reading one downloads it."""
    from types import SimpleNamespace
    from imperal_sdk.universal.index import is_placeholder
    for attrs in (0x1000, 0x40000, 0x400000):
        assert is_placeholder("a.docx", SimpleNamespace(st_flags=0, st_file_attributes=attrs))
    assert not is_placeholder("a.docx", SimpleNamespace(st_flags=0, st_file_attributes=0x20))
