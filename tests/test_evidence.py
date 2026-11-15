"""The evidence record (ICNLI §7.2): whole, with its provenance, every cut and mask written on it."""
import hashlib

from imperal_sdk.evidence import BLOCKING, Cut, Evidence, Provenance, Verdict, make_evidence, subject_of


def test_roundtrip():
    e, _ = make_evidence("Bash", "ls -la", "a.py\nb.py\n", Provenance.EXECUTED, exit_code=0, event_id="c1")
    assert Evidence.from_dict(e.to_dict()) == e


def test_cut_recorded_with_the_whole_copy():
    raw = "".join(f"row_{i} = {i}\n" for i in range(6000))
    e, whole = make_evidence("Bash", "cat big.py | cat", raw, Provenance.EXECUTED, limit=2400)
    assert e.cut == Cut(kept=len(e.text), total=len(raw), ref=e.whole_ref)
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
