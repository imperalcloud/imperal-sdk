"""The evidence record (ICNLI §7.2): whole, with its provenance, every cut and mask written on it."""
import hashlib

from imperal_sdk.evidence import BLOCKING, Cut, Evidence, Provenance, Verdict, cut_text, make_evidence, subject_of


def test_roundtrip():
    e, _ = make_evidence("Bash", "ls -la", "a.py\nb.py\n", Provenance.EXECUTED, exit_code=0, event_id="c1")
    assert Evidence.from_dict(e.to_dict()) == e


def test_cut_recorded_with_the_whole_copy():
    raw = "".join(f"row_{i} = {i}\n" for i in range(6000))
    e, whole = make_evidence("Bash", "cat big.py | cat", raw, Provenance.EXECUTED, limit=2400)
    assert (e.cut.kept, e.cut.total, e.cut.ref) == (len(e.text), len(raw), e.whole_ref)
    assert len(e.text) <= 2400 and whole == raw
    assert e.whole_ref == hashlib.sha256(raw.encode()).hexdigest()


def test_uncut_has_no_cut():
    e, _ = make_evidence("Read", "a.py", "x = 1\n", Provenance.EXECUTED, limit=2400)
    assert e.cut is None and e.text == "x = 1\n"


def test_secret_masked_rest_kept():
    raw = "origin https://gate:ghp_FAKEgate000000000000000000000000000@example.invalid/x.git (fetch)\nmain\n"
    e, whole = make_evidence("Bash", "git remote -v", raw, Provenance.EXECUTED)
    assert "ghp_FAKE" not in e.text and "ghp_FAKE" not in whole
    assert e.text.endswith("(fetch)\nmain\n")                         # the rest is evidence, never withheld whole
    assert e.masked and e.masked[0].length == len("ghp_FAKEgate000000000000000000000000000")   # the password only: the user stays


def test_subject_is_one_identity():
    assert subject_of("Bash", "ls") == subject_of("Bash", "  ls  ")
    assert subject_of("Bash", "ls a") != subject_of("Bash", "ls b")
    assert subject_of("Read", "/w/a.py") != subject_of("Bash", "/w/a.py")


def test_only_two_verdicts_block():
    assert BLOCKING == frozenset({Verdict.CONTRADICTED, Verdict.STATED_UNPROVEN})
    assert {v.value for v in Verdict} == {"shown", "contradicted", "stated_unproven", "from_source", "kernel_blind",
                                          "not_shown"}


def test_provenances():
    assert {p.value for p in Provenance} == {"executed", "measured", "frame", "user", "memory", "own_write",
                                             "notification"}


def test_a_cut_says_chars_lines_and_where_the_whole_is():
    """6.8.0 (the seven guarantees, G3): live 2026-11-16 a judge read 600-char copies ending in a bare "…" and
    approved a loop; the marker named no lines and no address."""
    raw = "".join(f"row_{i} = {i}\n" for i in range(6000))
    shown, cut = cut_text(raw, 2400, ref="abc123def4567890", address="vault_log_read(ref='vault://logs/s/c1.log')")
    assert len(shown) <= 2400 and cut.total == len(raw) and cut.kept == len(shown)
    assert cut.total_lines == 6000 and 0 < cut.kept_lines < 6000
    marker = next(ln for ln in shown.splitlines() if ln.startswith("… ["))
    assert f"of {len(raw)} chars" in marker and f"({6000 - cut.kept_lines} of 6000 lines)" in marker
    assert "the whole: vault_log_read(ref='vault://logs/s/c1.log')" in marker
    rows = [ln for ln in shown.splitlines() if ln and not ln.startswith("… [")]
    assert all(ln.startswith("row_") and " = " in ln for ln in rows) and len(rows) == cut.kept_lines   # whole lines
    assert rows[0] == "row_0 = 0" and rows[-1] == "row_5999 = 5999"
    assert Cut.from_dict(cut.to_dict()) == cut
    assert Cut.from_dict({"kept": 5, "total": 9, "ref": "r"}) == Cut(5, 9, "r")          # a record of 6.7


def test_no_address_names_the_ref_and_a_fitting_text_is_not_cut():
    shown, cut = cut_text("x" * 5000, 1000, ref="0123456789abcdef")
    assert "the whole: kept whole, ref 0123456789ab" in shown and len(shown) <= 1000 and cut.total_lines == 1
    assert cut_text("short", 1000) == ("short", None) and cut_text("anything", 0) == ("anything", None)
    assert "the whole: not kept" in cut_text("y" * 5000, 1000)[0]


def test_the_record_carries_the_address():
    raw = "".join(f"line {i}\n" for i in range(3000))
    e, _ = make_evidence("Bash", "cat big", raw, Provenance.EXECUTED, limit=1200, address="read_file(path='big')")
    assert e.cut.address == "read_file(path='big')" and "the whole: read_file(path='big')" in e.text
    assert Evidence.from_dict(e.to_dict()) == e


def test_a_window_of_a_whole_never_loaded_says_the_same_line():
    from imperal_sdk.evidence import cut_marker
    assert cut_marker(700, 1000, "vault_log_read(ref='r')") == \
        "\n… [700 of 1000 chars not shown here; the whole: vault_log_read(ref='r')] …\n"
    assert "(5 of 9 lines)" in cut_marker(700, 1000, "x", 5, 9)
