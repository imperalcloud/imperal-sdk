"""Any file as a readable view: its text with line numbers, its sections, its links.

The view is what ``outline`` / ``read_symbol`` / search read for a file that is not code: a heading, a sheet, a slide,
a page or a message is a section with a line range in the view's text, so the code tools work on documents unchanged.
A reader that cannot read a file says why (``skipped``); it never raises and never guesses.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from imperal_sdk.code_index import normalise_text
from imperal_sdk.universal.kinds import kind_of

MAX_VIEW_CHARS = 2_000_000       # extracted text per file (spec 2026-11-03 §3.1)


@dataclass(frozen=True)
class Section:
    title: str
    kind: str            # section | table | sheet | slide | page | message | key
    level: int
    start_line: int
    end_line: int


@dataclass
class View:
    kind: str            # the file's kind (kinds.kind_of)
    text: str
    sections: list[Section] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    skipped: str = ""    # why the file could not be read ("" when it was)


_READERS: dict[str, Callable[[str, bytes], View]] = {}


def register(exts: tuple[str, ...], fn: Callable[[str, bytes], View]) -> None:
    for ext in exts:
        _READERS[ext.lower()] = fn


def decode(raw: bytes) -> str | None:
    """Text as the index reads it: UTF-8 / BOM / UTF-16 (``normalise_text``), else the encoding
    ``charset_normalizer`` finds when it is installed. None for binary."""
    text = normalise_text(raw)
    if text is not None:
        return text
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
    except Exception:
        return None
    if best is None:
        return None
    text = str(best)
    return None if "\x00" in text else text.replace("\r\n", "\n").replace("\r", "\n")


class UnsafeXML(ValueError):
    """An XML document that declares a DOCTYPE: entity bombs and external entities live there; no document the
    index reads needs one (OOXML, ODF and data XML have none)."""


def parse_xml(raw: bytes):
    """An ElementTree root from untrusted XML: ``defusedxml`` when installed; else an expat pass that stops at the
    first DOCTYPE or entity declaration -- before anything expands, in whatever encoding the document declares --
    and only then the stdlib parser (raises ``UnsafeXML``)."""
    try:
        import defusedxml.ElementTree as safe_et
        return safe_et.fromstring(raw)
    except ImportError:
        pass
    from xml.parsers import expat

    def refuse(*_a):
        raise UnsafeXML("XML with a DOCTYPE or an entity declaration is not read")
    check = expat.ParserCreate()
    check.StartDoctypeDeclHandler = refuse
    check.EntityDeclHandler = refuse
    check.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    check.Parse(raw, True)
    import xml.etree.ElementTree as ET
    return ET.fromstring(raw)


class BudgetLines(list):
    """A view's lines with a character budget: ``add`` says False once the view is full (``MAX_VIEW_CHARS``) --
    every reader that builds text from a compressed or repeated source stops there (security review 2026-11-04)."""

    def __init__(self, limit: int | None = None):
        super().__init__()
        self.size = 0
        self.limit = MAX_VIEW_CHARS if limit is None else limit

    def add(self, line: str) -> bool:
        if self.size >= self.limit:
            return False
        self.append(line)
        self.size += len(line) + 1
        return True

    @property
    def full(self) -> bool:
        return self.size >= self.limit


def close_sections(heads: list[tuple[str, str, int, int]], total_lines: int) -> list[Section]:
    """``(title, kind, level, start_line)`` in file order -> sections, each ending where the next head of the same or
    a higher level starts (or at the end of the text)."""
    out = []
    for i, (title, kind, level, start) in enumerate(heads):
        end = total_lines
        for _t, _k, lvl, nxt in heads[i + 1:]:
            if lvl <= level:
                end = max(start, nxt - 1)
                break
        out.append(Section(title=title, kind=kind, level=level, start_line=start, end_line=max(start, end)))
    return out


def line_count(text: str) -> int:
    return max(1, len(text.splitlines()))


def view_of(rel_path: str, raw: bytes) -> View | None:
    """The view of a file, or None when the index never reads it (``kind_of``). A reader registered for the extension
    wins over the kind (an ``.html`` file is code by kind and a document by reading)."""
    kind = kind_of(rel_path)
    if kind is None:
        return None
    ext = os.path.splitext(rel_path)[1].lower()
    reader = _READERS.get(ext)
    if reader is None:
        if kind in ("code", "config"):
            text = decode(raw)
            return View(kind, text or "", skipped="" if text is not None else "not text")
        return View(kind, "", skipped=f"no reader for {ext or 'this file'}")
    try:
        view = reader(rel_path, raw)
    except Exception as exc:          # a reader's failure is the file's reason, never the index's crash
        return View(kind, "", skipped=f"unreadable: {type(exc).__name__}")
    view.kind = kind
    if len(view.text) > MAX_VIEW_CHARS:
        view.text = view.text[:MAX_VIEW_CHARS]
        view.meta["truncated"] = True
        last = line_count(view.text)
        view.sections = [s for s in view.sections if s.start_line <= last]
    return view


# the readers register themselves (imported last: they use the types above)
from imperal_sdk.universal import image, legacy, mail, office, pdf, textual  # noqa: E402,F401
