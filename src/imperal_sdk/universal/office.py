"""Views of Office documents: Word / Excel / PowerPoint (OOXML) and OpenDocument text, sheets, slides.

Read with ``zipfile`` and the safe XML parser only. A ZIP member that is too big, or compressed suspiciously well, is
refused (a zip bomb); an Office file that is really an OLE container is encrypted (a password) and said so.
"""
from __future__ import annotations

import io
import posixpath
import re
import zipfile

from imperal_sdk.universal.view import Section, View, close_sections, line_count, parse_xml, register

MEMBER_MAX_BYTES = 50 * 1024 * 1024     # one unpacked XML part
MEMBER_MAX_RATIO = 100                  # unpacked / packed: a deflated text part is ~5-15x
SHEET_MAX_ROWS = 100_000
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"


class _Refused(Exception):
    pass


def _open(raw: bytes) -> zipfile.ZipFile:
    if raw.startswith(_OLE):
        raise _Refused("encrypted Office document (password protected)")
    z = zipfile.ZipFile(io.BytesIO(raw))
    for info in z.infolist():
        if info.file_size > MEMBER_MAX_BYTES:
            raise _Refused(f"part {info.filename} unpacks to over {MEMBER_MAX_BYTES // 1048576} MB")
        if info.compress_size and info.file_size / info.compress_size > MEMBER_MAX_RATIO:
            raise _Refused(f"part {info.filename} is compressed over {MEMBER_MAX_RATIO}x (a zip bomb)")
    return z


def _xml(z: zipfile.ZipFile, name: str):
    try:
        return parse_xml(z.read(name))
    except KeyError:
        return None


def _rels(z: zipfile.ZipFile, part: str) -> dict[str, tuple[str, str]]:
    """``{rId: (target, mode)}`` of an OOXML part."""
    base, name = posixpath.split(part)
    root = _xml(z, posixpath.join(base, "_rels", name + ".rels"))
    if root is None:
        return {}
    return {r.get("Id"): (r.get("Target") or "", r.get("TargetMode") or "") for r in root.iter(f"{PR}Relationship")}


def _texts(el, tag: str) -> str:
    return "".join(t.text or "" for t in el.iter(tag))


def _guard(fn):
    def read(rel: str, raw: bytes) -> View:
        try:
            return fn(rel, raw)
        except _Refused as exc:
            return View("document", "", skipped=str(exc))
        except zipfile.BadZipFile:
            return View("document", "", skipped="not a valid Office file (broken ZIP)")
    return read


_HEADING = re.compile(r"^(?:heading|title)\s*(\d*)$", re.I)       # Word's built-in style ids (a file format, not meaning)


def _docx(rel: str, raw: bytes) -> View:
    z = _open(raw)
    root = _xml(z, "word/document.xml")
    if root is None:
        raise _Refused("no word/document.xml")
    rels = _rels(z, "word/document.xml")
    body = root.find(f"{W}body")
    lines: list[str] = []
    heads: list[tuple[str, str, int, int]] = []
    tables: list[Section] = []
    links: list[str] = []
    for el in (body if body is not None else []):
        if el.tag == f"{W}p":
            text = _texts(el, f"{W}t").strip()
            for h in el.iter(f"{W}hyperlink"):
                target = rels.get(h.get(f"{R}id"), ("", ""))[0]
                if target:
                    links.append(target)
            if not text:
                continue
            lines.append(text)
            style = el.find(f"{W}pPr/{W}pStyle")
            level = el.find(f"{W}pPr/{W}outlineLvl")
            m = _HEADING.match(style.get(f"{W}val") or "") if style is not None else None
            if m:
                heads.append((text, "section", int(m.group(1) or 1), len(lines)))
            elif level is not None and (level.get(f"{W}val") or "").isdigit():
                heads.append((text, "section", int(level.get(f"{W}val")) + 1, len(lines)))
        elif el.tag == f"{W}tbl":
            start = len(lines) + 1
            for row in el.iter(f"{W}tr"):
                lines.append(" | ".join(_texts(c, f"{W}t").strip() for c in row.iter(f"{W}tc")))
            if len(lines) >= start:
                tables.append(Section(f"Table {len(tables) + 1}", "table", 9, start, len(lines)))
    text = "\n".join(lines)
    sections = sorted(close_sections(heads, line_count(text)) + tables, key=lambda s: (s.start_line, s.level))
    return View("document", text, sections, list(dict.fromkeys(links)))


def _col(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n


def _xlsx(rel: str, raw: bytes) -> View:
    z = _open(raw)
    wb = _xml(z, "xl/workbook.xml")
    if wb is None:
        raise _Refused("no xl/workbook.xml")
    rels = _rels(z, "xl/workbook.xml")
    sst = _xml(z, "xl/sharedStrings.xml")
    shared = [_texts(si, f"{S}t") for si in sst.iter(f"{S}si")] if sst is not None else []
    lines: list[str] = []
    heads = []
    for sheet in wb.iter(f"{S}sheet"):
        name = sheet.get("name") or "Sheet"
        target = rels.get(sheet.get(f"{R}id"), ("", ""))[0]
        part = posixpath.normpath(posixpath.join("xl", target)) if not target.startswith("/") else target.lstrip("/")
        ws = _xml(z, part)
        lines.append(f"Sheet: {name}")
        heads.append((f"Sheet: {name}", "sheet", 1, len(lines)))
        if ws is None:
            continue
        for i, row in enumerate(ws.iter(f"{S}row")):
            if i >= SHEET_MAX_ROWS:
                break
            cells: dict[int, str] = {}
            for c in row.iter(f"{S}c"):
                kind, v = c.get("t"), c.find(f"{S}v")
                if kind == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
                    val = shared[int(v.text)]
                elif kind == "inlineStr":
                    val = _texts(c, f"{S}t")
                else:
                    val = v.text if v is not None and v.text is not None else ""
                cells[_col(c.get("r") or "") or len(cells) + 1] = val.strip()
            if cells:
                lines.append(" | ".join(cells.get(k, "") for k in range(1, max(cells) + 1)))
    text = "\n".join(lines)
    return View("data", text, close_sections(heads, line_count(text)))


def _pptx(rel: str, raw: bytes) -> View:
    z = _open(raw)
    names = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
    names.sort(key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
    lines: list[str] = []
    heads = []
    for name in names:
        root = _xml(z, name)
        num = int(re.search(r"(\d+)\.xml$", name).group(1))
        paras = [" ".join(_texts(p, f"{A}t").split()) for p in root.iter(f"{A}p")] if root is not None else []
        paras = [p for p in paras if p]
        title = f"Slide {num}" + (f": {paras[0]}" if paras else "")
        lines.append(title)
        heads.append((title, "slide", 1, len(lines)))
        lines += paras[1:]
    text = "\n".join(lines)
    return View("document", text, close_sections(heads, line_count(text)))


def _odf(rel: str, raw: bytes) -> View:
    z = _open(raw)
    root = _xml(z, "content.xml")
    if root is None:
        raise _Refused("no content.xml")
    ext = posixpath.splitext(rel.lower())[1]
    lines: list[str] = []
    heads = []
    if ext == ".odt":
        for el in root.iter():
            if el.tag == f"{TEXT}h":
                t = " ".join(_texts_all(el).split())
                if t:
                    lines.append(t)
                    heads.append((t, "section", int(el.get(f"{TEXT}outline-level") or 1), len(lines)))
            elif el.tag == f"{TEXT}p":
                t = " ".join(_texts_all(el).split())
                if t:
                    lines.append(t)
    elif ext == ".ods":
        for tbl in root.iter(f"{TABLE}table"):
            name = tbl.get(f"{TABLE}name") or "Sheet"
            lines.append(f"Sheet: {name}")
            heads.append((f"Sheet: {name}", "sheet", 1, len(lines)))
            for i, row in enumerate(tbl.iter(f"{TABLE}table-row")):
                if i >= SHEET_MAX_ROWS:
                    break
                cells = [" ".join(_texts_all(c).split()) for c in row.iter(f"{TABLE}table-cell")]
                if any(cells):
                    lines.append(" | ".join(cells).rstrip(" |"))
    else:
        for n, page in enumerate(root.iter(f"{DRAW}page"), 1):
            paras = [" ".join(_texts_all(p).split()) for p in page.iter(f"{TEXT}p")]
            paras = [p for p in paras if p]
            title = f"Slide {n}" + (f": {paras[0]}" if paras else "")
            lines.append(title)
            heads.append((title, "slide", 1, len(lines)))
            lines += paras[1:]
    text = "\n".join(lines)
    return View("data" if ext == ".ods" else "document", text, close_sections(heads, line_count(text)))


def _texts_all(el) -> str:
    return "".join(el.itertext())


register((".docx",), _guard(_docx))
register((".xlsx",), _guard(_xlsx))
register((".pptx",), _guard(_pptx))
register((".odt", ".ods", ".odp"), _guard(_odf))
