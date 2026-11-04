"""Universal index phase 2, Task 4: Word, Excel, PowerPoint and OpenDocument files as views."""
import io
import zipfile

import pytest

from imperal_sdk.universal.view import view_of

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


def _p(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"


@pytest.fixture
def tmp_docx():
    body = (_p("Agreement", "Heading1") + _p("The parties agree.") + _p("3.2 Payment terms", "Heading2")
            + _p("Payment within 30 days.")
            + '<w:tbl><w:tr><w:tc>' + _p("Fee") + '</w:tc><w:tc>' + _p("500 EUR") + '</w:tc></w:tr></w:tbl>'
            + '<w:p><w:hyperlink r:id="rId5"><w:r><w:t>see invoice</w:t></w:r></w:hyperlink></w:p>')
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId5" Type="http://x/hyperlink" Target="invoice-117.pdf" TargetMode="External"/>'
            '</Relationships>')
    return _zip({"word/document.xml": f"<w:document {W}><w:body>{body}</w:body></w:document>",
                 "word/_rels/document.xml.rels": rels})


@pytest.fixture
def tmp_xlsx():
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' \
         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    wb = (f'<workbook {ns}><sheets><sheet name="Ledger" sheetId="1" r:id="rId1"/>'
          '<sheet name="Summary" sheetId="2" r:id="rId2"/></sheets></workbook>')
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="x" Target="worksheets/sheet2.xml"/></Relationships>')
    shared = f'<sst {ns}><si><t>Date</t></si><si><t>Amount</t></si></sst>'
    s1 = (f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
          '<row r="2"><c r="A2"><v>45000</v></c><c r="B2"><v>500.5</v></c></row></sheetData></worksheet>')
    s2 = f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Total</t></is></c></row></sheetData></worksheet>'
    return _zip({"xl/workbook.xml": wb, "xl/_rels/workbook.xml.rels": rels, "xl/sharedStrings.xml": shared,
                 "xl/worksheets/sheet1.xml": s1, "xl/worksheets/sheet2.xml": s2})


@pytest.fixture
def tmp_pptx():
    ns = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" ' \
         'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    slide = lambda t: f"<p:sld {ns}><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{t}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"  # noqa: E731
    return _zip({"ppt/slides/slide1.xml": slide("Roadmap"), "ppt/slides/slide2.xml": slide("Pricing"),
                 "ppt/slides/slide10.xml": slide("Thanks")})


@pytest.fixture
def tmp_odt():
    content = ('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
               '<text:h text:outline-level="1">Minutes</text:h><text:p>Budget approved.</text:p>'
               '</office:text></office:body></office:document-content>')
    return _zip({"content.xml": content, "mimetype": "application/vnd.oasis.opendocument.text"})


@pytest.fixture
def tmp_encrypted_docx():
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600          # an OLE container: Office encryption


def test_docx_sections_tables_links(tmp_docx):
    v = view_of("NDA.docx", tmp_docx)
    assert [s.title for s in v.sections if s.kind == "section"] == ["Agreement", "3.2 Payment terms"]
    assert any(s.kind == "table" for s in v.sections) and v.links == ["invoice-117.pdf"]
    pay = next(s for s in v.sections if s.title == "3.2 Payment terms")
    assert "Payment within 30 days." in "\n".join(v.text.splitlines()[pay.start_line - 1:pay.end_line])


def test_xlsx_sheets_with_header_rows(tmp_xlsx):
    v = view_of("ledger.xlsx", tmp_xlsx)
    assert [s.title for s in v.sections] == ["Sheet: Ledger", "Sheet: Summary"] and "Date | Amount" in v.text
    assert "500.5" in v.text and "Total" in v.text


def test_pptx_slides_in_order_and_odt_heading(tmp_pptx, tmp_odt):
    v = view_of("d.pptx", tmp_pptx)
    assert [s.kind for s in v.sections] == ["slide", "slide", "slide"]
    assert [s.title for s in v.sections] == ["Slide 1: Roadmap", "Slide 2: Pricing", "Slide 10: Thanks"]
    assert view_of("n.odt", tmp_odt).sections[0].title == "Minutes"


def test_broken_encrypted_and_bombs_say_why(tmp_encrypted_docx):
    assert view_of("x.docx", b"PK\x03\x04broken").skipped
    assert "encrypted" in view_of("y.docx", tmp_encrypted_docx).skipped
    bomb = _zip({"word/document.xml": "<a>" + "x" * 20_000_000 + "</a>"})
    assert "compress" in view_of("z.docx", bomb).skipped
