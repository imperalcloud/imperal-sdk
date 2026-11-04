"""Views in the code index: a file of any kind read from disk inside its cap, and its view as a ``FileIndex``
(a section is a ``Symbol``, a link a ref) so search, outline and the graph take it as they take code."""
from __future__ import annotations

import hashlib
import os

from imperal_sdk.code_index import FileIndex, Symbol
from imperal_sdk.universal.kinds import kind_of
from imperal_sdk.universal.view import View, view_of

RAW_CAP = {"code": 10 * 1024 * 1024, "config": 10 * 1024 * 1024, "document": 100 * 1024 * 1024,
           "data": 100 * 1024 * 1024, "mail": 100 * 1024 * 1024, "image": 100 * 1024 * 1024}
_SF_DATALESS = 0x40000000      # macOS: an iCloud file whose bytes are not on this Mac (reading downloads it)


def is_placeholder(rel: str, st: os.stat_result | None = None) -> bool:
    """An iCloud placeholder: never read -- opening it starts a download."""
    if rel.endswith(".icloud"):
        return True
    return bool(st is not None and getattr(st, "st_flags", 0) & _SF_DATALESS)


def read_view(root: str, rel: str) -> View | None:
    """The view of ``rel`` under ``root``: None when the index never reads it; ``skipped`` (unread) for a placeholder,
    a file over its kind's cap, a path leaving the root, or one that cannot be opened."""
    if is_placeholder(rel):
        return View("document", "", skipped="placeholder")
    kind = kind_of(rel)
    if kind is None:
        return None
    base = os.path.realpath(root)
    path = os.path.join(base, rel)
    real = os.path.realpath(path)
    if os.path.isabs(rel) or os.path.islink(path) or os.path.commonpath([base, real]) != base:
        return View(kind, "", skipped="outside the folder")
    try:
        st = os.stat(real)
    except OSError:
        return View(kind, "", skipped="cannot be opened")
    if is_placeholder(rel, st):
        return View(kind, "", skipped="placeholder")
    cap = RAW_CAP.get(kind, RAW_CAP["document"])
    if st.st_size > cap:
        return View(kind, "", skipped=f"over {cap // 1048576} MB")
    try:
        with open(real, "rb") as f:
            raw = f.read(cap + 1)
    except OSError:
        return View(kind, "", skipped="cannot be opened")
    return view_of(rel, raw)


def parse_view(rel: str, view: View) -> FileIndex:
    """A view as the code index's ``FileIndex``: sections -> symbols, links -> refs, the view's kind."""
    return FileIndex(
        path=rel, lang="other", kind=view.kind,
        symbols=[Symbol(name=s.title, kind=s.kind, path=rel, start_line=s.start_line, end_line=s.end_line,
                        signature=s.title) for s in view.sections],
        refs=list(view.links),
        content_hash=hashlib.sha256(view.text.encode("utf-8", "replace")).hexdigest())
