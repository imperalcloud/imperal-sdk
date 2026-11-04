"""Universal index phase 2, Task 3: a readable view (text, sections, links) of text, markup and data files."""
from imperal_sdk.universal.view import view_of


def test_markdown_headings_are_sections():
    v = view_of("notes/plan.md", b"# Q3\nintro\n## Payments\nwire 500 EUR\n")
    assert [(s.title, s.level, s.start_line) for s in v.sections] == [("Q3", 1, 1), ("Payments", 2, 3)]
    assert v.sections[0].end_line == 4


def test_csv_header_is_the_outline_and_rows_are_text():
    v = view_of("bank.csv", b"date,amount,iban\n2026-01-02,500.00,DE89370400440532013000\n")
    assert v.kind == "data" and v.sections[0].title == "columns: date, amount, iban"
    assert "DE89370400440532013000" in v.text


def test_html_links_and_rtf_text():
    v = view_of("a.html", b"<h1>Report</h1><a href='ledger.xlsx'>ledger</a>")
    assert v.sections[0].title == "Report" and v.links == ["ledger.xlsx"]
    assert "Total due" in view_of("b.rtf", rb"{\rtf1\ansi {\b Total due} 120\par}").text


def test_json_keys_are_the_outline():
    v = view_of("cfg.json", b'{"billing": {"currency": "EUR"}, "users": []}')
    assert [s.title for s in v.sections] == ["billing", "billing.currency", "users"]


def test_unreadable_says_why():
    assert view_of("broken.json", b"\xff\xfe\x00garbage").skipped


def test_rst_toml_yaml_xml_and_plain_text():
    rst = view_of("guide.rst", b"Setup\n=====\nrun it\n\nKeys\n----\nnone\n")
    assert [(s.title, s.level) for s in rst.sections] == [("Setup", 1), ("Keys", 2)]
    assert [s.title for s in view_of("p.toml", b"[tool]\nname = 'x'\n").sections] == ["tool", "tool.name"]
    assert view_of("c.yml", b"a:\n  b: 1\n").sections[0].title == "a"
    assert view_of("d.xml", b"<invoice><total>12</total></invoice>").sections[0].title == "invoice"
    t = view_of("notes.txt", "Привет, счёт 17".encode())
    assert t.text == "Привет, счёт 17" and t.sections == []


def test_a_file_the_index_never_reads_has_no_view():
    assert view_of(".env", b"KEY=1") is None


def test_an_xml_entity_bomb_is_never_expanded():
    bomb = (b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>'
            b"<l>&b;&b;&b;</l>")
    v = view_of("x.xml", bomb)
    assert v.skipped and "aaaa" not in v.text
