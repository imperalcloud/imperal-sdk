"""PDF as a view: text per page (``Page N``), the outline (bookmarks) as sections, link targets. ``pypdf`` (pure
Python, the ``universal-index`` extra); a password-protected PDF says so."""
from __future__ import annotations

import io

from imperal_sdk.universal.view import BudgetLines, View, close_sections, line_count, register

PDF_MAX_PAGES = 5_000


def _outline(reader) -> list[tuple[str, int, int]]:
    """``(title, depth, page index)`` of the bookmarks, in order."""
    out: list[tuple[str, int, int]] = []

    def walk(items, depth):
        for it in items:
            if isinstance(it, list):
                walk(it, depth + 1)
                continue
            try:
                out.append((str(it.title).strip(), depth, reader.get_destination_page_number(it)))
            except Exception:
                continue
    try:
        walk(reader.outline, 1)
    except Exception:
        return []
    return [o for o in out if o[0]]


def _pdf(rel: str, raw: bytes) -> View:
    try:
        from pypdf import PdfReader
    except ImportError:
        return View("document", "", skipped="pdf reader not installed (imperal-sdk[universal-index])")
    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return View("document", "", skipped="encrypted PDF (password protected)")
        except Exception:
            return View("document", "", skipped="encrypted PDF (password protected)")
    lines = BudgetLines()
    page_start: list[int] = []
    links: list[str] = []
    for i, page in enumerate(reader.pages):
        if i >= PDF_MAX_PAGES or lines.full:
            break                          # the view is full: no further page is decompressed
        page_start.append(len(lines) + 1)
        lines.add(f"Page {i + 1}")
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        for ln in text.splitlines():
            if ln.strip() and not lines.add(ln.rstrip()):
                break
        for annot in (page.get("/Annots") or []):
            try:
                uri = annot.get_object().get("/A", {}).get("/URI")
            except Exception:
                uri = None
            if uri:
                links.append(str(uri))
    text = "\n".join(lines)
    heads = [(title, "section", depth, page_start[p]) for title, depth, p in _outline(reader) if 0 <= p < len(page_start)]
    pages = [(f"Page {i + 1}", "page", 99, start) for i, start in enumerate(page_start)]
    order = sorted(heads + pages, key=lambda h: (h[3], h[2]))
    return View("document", text, close_sections(order, line_count(text)), list(dict.fromkeys(links)),
                meta={"pages": len(reader.pages)})


register((".pdf",), _pdf)
